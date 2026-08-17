"""
Temporal worker for the faucet payout workflow.

    temporal server start-dev              # separate terminal, or Temporal Cloud
    python backend/workflows/worker.py

Runs nothing on its own — it registers the workflow and activities and waits to
be given work. Safe to kill and restart: any in-flight workflow resumes from its
last completed step, which is the entire point of running one.

Connection comes from TEMPORAL_ADDRESS (default localhost:7233) and
TEMPORAL_NAMESPACE (default "default"). For Temporal Cloud, set both and supply
client certificates — see the SDK docs; deliberately not stubbed here, because
half-written TLS config is worse than none.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# backend/ on the path so `db` and `workflows.*` resolve when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from temporalio.client import Client
from temporalio.worker import Worker

from workflows.faucet_payout import (  # noqa: E402
    TASK_QUEUE,
    FaucetPayoutWorkflow,
    fetch_pending,
    mark_paid,
    submit_payout,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("faucet-worker")


async def main() -> None:
    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    log.info("connecting to %s (namespace %s)", address, namespace)
    try:
        client = await Client.connect(address, namespace=namespace)
    except Exception as e:
        log.error("could not reach Temporal at %s: %s", address, e)
        log.error("start one with:  temporal server start-dev")
        raise SystemExit(1)

    log.info("worker up on task queue '%s'", TASK_QUEUE)
    async with Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[FaucetPayoutWorkflow],
        activities=[fetch_pending, submit_payout, mark_paid],
    ):
        await asyncio.Future()  # run until interrupted


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("worker stopped")
