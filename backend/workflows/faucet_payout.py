"""
Faucet payout as a durable workflow.

WHY THIS ONE FIRST

Paying a faucet batch is four steps across two systems that must not half-happen:

    read pending claims -> send tokens on chain -> confirm -> mark paid

Every failure mode in the middle is bad in a specific way. Crash after sending
but before marking paid, and the next run pays the same wallets twice. Crash
after marking paid but before the transaction confirms, and holders are recorded
as paid having received nothing. Retry the whole thing naively and you double
spend. None of that is fixed by a try/except, because the process that would run
the except clause is the thing that died.

Temporal solves exactly this shape: workflow state is persisted at every step, so
a worker that dies mid-payout resumes where it stopped rather than restarting or
losing the thread.

WHAT MOVES MONEY, AND WHAT DOES NOT

Nothing here signs anything. `submit_payout` is deliberately a stub that raises,
because automating the send requires a private key on the server, and this
project's whole security posture is that no key lives there. The workflow drives
the *bookkeeping* around a payout the operator performs, and its value is that
the bookkeeping cannot end up half-applied.

If the send is ever automated, it belongs behind a program-owned key with spend
caps, not a keypair in an environment variable. Read backend/faucet.py first.

RUNNING IT

    pip install temporalio
    temporal server start-dev            # or point at Temporal Cloud
    python backend/workflows/worker.py

Tested without any server via temporalio's bundled test environment:

    python tests/test_faucet_workflow.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import List, Optional

from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

TASK_QUEUE = "yabbai-faucet"


@dataclass
class PayoutInput:
    """Everything the workflow needs, captured at start.

    The batch is resolved by an activity rather than passed in, so a replay
    after a crash reads the queue as it was recorded — not as it looks now.
    """
    limit: int = 500
    dry_run: bool = True


@dataclass
class Claim:
    address: str
    tokens: float


@dataclass
class PayoutResult:
    claims: int = 0
    tokens: float = 0.0
    signature: Optional[str] = None
    marked_paid: int = 0
    status: str = "pending"
    addresses: List[str] = field(default_factory=list)


# ── activities ───────────────────────────────────────────────────────────────
# Activities do the I/O. They are the only things allowed to touch Mongo or the
# network; workflow code must stay deterministic so it can be replayed.


@activity.defn
async def fetch_pending(limit: int) -> List[Claim]:
    """Read unpaid claims. Safe to retry — it reads and changes nothing."""
    from db import get_db  # imported inside so the module loads without Mongo

    db = get_db()
    rows = await db.faucet_claims.find(
        {"status": "pending"}, {"_id": 0, "address": 1, "tokens": 1}
    ).sort("claimed_at", 1).to_list(length=limit)
    return [Claim(address=r["address"], tokens=float(r.get("tokens", 0))) for r in rows]


@activity.defn
async def submit_payout(claims: List[Claim]) -> str:
    """
    Send the tokens. NOT IMPLEMENTED, on purpose.

    Automating this needs a signing key on the server, which would be the first
    private key this application has ever held. The faucet was built as a queue
    specifically so that the public surface could not move value; putting a key
    here to save the operator a manual step gives that back.

    Left raising rather than silently returning a fake signature, so a workflow
    run cannot record a payout that never happened.
    """
    raise ApplicationError(
        "submit_payout is intentionally unimplemented. Send the batch from the "
        "operator wallet via /faucet, then run this workflow with dry_run=False "
        "and the resulting signature.",
        non_retryable=True,
    )


@activity.defn
async def mark_paid(addresses: List[str], signature: str) -> int:
    """
    Record that a payout landed.

    Idempotent by construction: the update matches only rows still `pending`, so
    running it twice marks nothing the second time and returns 0. That property
    is what makes the retry safe, not the retry policy.
    """
    from db import get_db
    from datetime import datetime, timezone

    db = get_db()
    result = await db.faucet_claims.update_many(
        {"address": {"$in": addresses}, "status": "pending"},
        {"$set": {
            "status": "paid",
            "paid_at": datetime.now(timezone.utc),
            "payout_signature": signature,
        }},
    )
    return int(result.modified_count)


# ── workflow ─────────────────────────────────────────────────────────────────


@workflow.defn
class FaucetPayoutWorkflow:
    """
    Durable payout. Survives a worker dying at any point between steps.

    State lives in Temporal, so `self._result` is restored on replay. The
    operator's signature arrives by signal, which means the workflow can wait —
    for minutes or for days — without holding a process open or polling.
    """

    def __init__(self) -> None:
        self._result = PayoutResult()
        self._signature: Optional[str] = None
        self._cancelled = False

    @workflow.signal
    def payout_sent(self, signature: str) -> None:
        """Operator reports the on-chain signature after sending."""
        self._signature = signature.strip()

    @workflow.signal
    def cancel_payout(self) -> None:
        self._cancelled = True

    @workflow.query
    def status(self) -> PayoutResult:
        """Readable at any time, including mid-run, without disturbing it."""
        return self._result

    @workflow.run
    async def run(self, params: PayoutInput) -> PayoutResult:
        retry = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            maximum_interval=timedelta(seconds=30),
            maximum_attempts=5,
        )

        claims = await workflow.execute_activity(
            fetch_pending,
            params.limit,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry,
        )

        self._result.claims = len(claims)
        self._result.tokens = sum(c.tokens for c in claims)
        self._result.addresses = [c.address for c in claims]

        if not claims:
            self._result.status = "nothing_pending"
            return self._result

        if params.dry_run:
            # The default. Resolves the batch and stops, so a run can always be
            # started safely to see what *would* be paid.
            self._result.status = "dry_run"
            return self._result

        # Wait for the operator, who is sending from their own wallet. One hour
        # is generous on purpose: a human is in this loop and timing out on them
        # is how a batch ends up half-paid.
        self._result.status = "awaiting_signature"
        await workflow.wait_condition(
            lambda: self._signature is not None or self._cancelled,
            timeout=timedelta(hours=1),
        )

        if self._cancelled:
            self._result.status = "cancelled"
            return self._result

        self._result.signature = self._signature

        # Only after a real signature exists. mark_paid is idempotent, so a
        # crash between here and completion costs nothing on retry.
        self._result.marked_paid = await workflow.execute_activity(
            mark_paid,
            args=[self._result.addresses, self._signature],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry,
        )
        self._result.status = "paid"
        return self._result
