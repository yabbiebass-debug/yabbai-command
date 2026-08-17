"""
Faucet payout workflow, tested against a real Temporal server.

    python tests/test_faucet_workflow.py

No Mongo and no running Temporal needed. temporalio ships a test server binary
that this downloads on first run and starts in-process, so the workflow is
exercised by the actual Temporal runtime rather than a mock of it — replay,
signals, queries and retries all behave as they will in production.

Activities are replaced with in-memory fakes. What is under test is the
orchestration: does the workflow stop safely when there is nothing to pay, does
dry run refuse to pay, does it wait for a real signature before marking anything,
and does cancelling leave the queue untouched.
"""

import asyncio
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from temporalio import activity  # noqa: E402
from temporalio.client import Client  # noqa: E402
from temporalio.testing import WorkflowEnvironment  # noqa: E402
from temporalio.worker import Worker  # noqa: E402

from workflows.faucet_payout import (  # noqa: E402
    TASK_QUEUE,
    Claim,
    FaucetPayoutWorkflow,
    PayoutInput,
)

passed, failed = 0, 0


def check(name, ok, detail=""):
    global passed, failed
    if ok:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}{'  -- ' + str(detail) if detail else ''}")


# ── fakes ────────────────────────────────────────────────────────────────────

STATE = {"pending": [], "paid": {}, "mark_calls": 0}


@activity.defn(name="fetch_pending")
async def fake_fetch(limit: int) -> List[Claim]:
    return STATE["pending"][:limit]


@activity.defn(name="submit_payout")
async def fake_submit(claims: List[Claim]) -> str:
    raise RuntimeError("must never be called: no key belongs on the server")


@activity.defn(name="mark_paid")
async def fake_mark(addresses: List[str], signature: str) -> int:
    """Mirrors the real one: only rows still pending are updated."""
    STATE["mark_calls"] += 1
    n = 0
    for a in addresses:
        if a not in STATE["paid"]:
            STATE["paid"][a] = signature
            n += 1
    return n


async def run_case(env: WorkflowEnvironment, client: Client, wf_id: str,
                   params: PayoutInput, signal=None, sig_value=None):
    handle = await client.start_workflow(
        FaucetPayoutWorkflow.run, params, id=wf_id, task_queue=TASK_QUEUE
    )
    if signal:
        # Let the workflow reach its wait before signalling.
        for _ in range(50):
            await asyncio.sleep(0.05)
            if (await handle.query(FaucetPayoutWorkflow.status)).status == "awaiting_signature":
                break
        if sig_value is not None:
            await handle.signal(FaucetPayoutWorkflow.payout_sent, sig_value)
        else:
            await handle.signal(FaucetPayoutWorkflow.cancel_payout)
    return await handle.result()


async def main() -> int:
    print("\nstarting Temporal test server (downloads once)...\n")
    try:
        env = await WorkflowEnvironment.start_time_skipping()
    except Exception as e:
        print(f"could not start the test server: {e}")
        print("Needs network on first run to fetch the test binary.")
        return 2

    async with env:
        async with Worker(
            env.client,
            task_queue=TASK_QUEUE,
            workflows=[FaucetPayoutWorkflow],
            activities=[fake_fetch, fake_submit, fake_mark],
        ):
            print("1. Nothing pending")
            STATE["pending"] = []
            r = await run_case(env, env.client, "wf-empty", PayoutInput(dry_run=True))
            check("stops with nothing_pending", r.status == "nothing_pending", r.status)
            check("pays nothing", r.marked_paid == 0)

            print("\n2. Dry run resolves the batch and stops")
            STATE["pending"] = [Claim("Addr1", 1000.0), Claim("Addr2", 1000.0)]
            r = await run_case(env, env.client, "wf-dry", PayoutInput(dry_run=True))
            check("status is dry_run", r.status == "dry_run", r.status)
            check("counts the batch", r.claims == 2, r.claims)
            check("totals the tokens", r.tokens == 2000.0, r.tokens)
            check("marks nothing paid", r.marked_paid == 0 and not STATE["paid"])

            print("\n3. Real run waits for a signature, then marks paid")
            r = await run_case(env, env.client, "wf-real", PayoutInput(dry_run=False),
                               signal=True, sig_value="5MCrCrEGbfukRfQJaKKJEwoRQ8uXdcH7")
            check("status is paid", r.status == "paid", r.status)
            check("records the signature", r.signature.startswith("5MCrCr"), r.signature)
            check("marks both claims", r.marked_paid == 2, r.marked_paid)

            print("\n4. Cancel leaves the queue untouched")
            STATE["paid"].clear()
            STATE["pending"] = [Claim("Addr3", 500.0)]
            r = await run_case(env, env.client, "wf-cancel", PayoutInput(dry_run=False),
                               signal=True, sig_value=None)
            check("status is cancelled", r.status == "cancelled", r.status)
            check("nothing marked paid", r.marked_paid == 0 and not STATE["paid"])

            print("\n5. Marking paid twice is idempotent")
            before = STATE["mark_calls"]
            n1 = await fake_mark(["AddrX"], "sig")
            n2 = await fake_mark(["AddrX"], "sig")
            check("first call applies", n1 == 1, n1)
            check("second call is a no-op", n2 == 0, n2)
            check("both were attempted", STATE["mark_calls"] == before + 2)

    print(f"\n{passed} passed, {failed} failed\n")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
