"""
Temporal worker for the faucet payout workflow.

    temporal server start-dev              # separate terminal, or Temporal Cloud
    python backend/workflows/worker.py

Runs nothing on its own — it registers the workflow and activities and waits to
be given work. Safe to kill and restart: any in-flight workflow resumes from its
last completed step, which is the entire point of running one.

CONNECTING

Local dev server — nothing to configure:

    TEMPORAL_ADDRESS=localhost:7233        (default)
    TEMPORAL_NAMESPACE=default             (default)

Temporal Cloud, API key (simplest):

    TEMPORAL_ADDRESS=<region>.<cloud>.api.temporal.io:7233
    TEMPORAL_NAMESPACE=<your-namespace>.<your-account-id>
    TEMPORAL_API_KEY=<key>

Temporal Cloud, mTLS certificates:

    TEMPORAL_ADDRESS=<namespace>.<account>.tmprl.cloud:7233
    TEMPORAL_NAMESPACE=<your-namespace>.<your-account-id>
    TEMPORAL_TLS_CERT=/path/to/client.pem
    TEMPORAL_TLS_KEY=/path/to/client.key

All of it comes from the environment. No credential is ever written into this
file or committed — backend/.env is gitignored, and a key pasted into source is
in the git history permanently even after the commit that removes it.
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
from temporalio.service import TLSConfig
from temporalio.worker import Worker

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from workflows.faucet_payout import (  # noqa: E402
    TASK_QUEUE,
    FaucetPayoutWorkflow,
    fetch_pending,
    mark_paid,
    submit_payout,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger("faucet-worker")


def connect_args() -> dict:
    """
    Build connection settings from the environment.

    Three modes, chosen by what is present rather than by a mode flag — a flag
    that disagrees with the credentials produces a confusing failure, whereas
    this can only be wrong in ways that are obvious from the log line.
    """
    api_key = os.environ.get("TEMPORAL_API_KEY", "").strip()
    cert = os.environ.get("TEMPORAL_TLS_CERT", "").strip()
    key = os.environ.get("TEMPORAL_TLS_KEY", "").strip()

    if api_key:
        # Cloud with an API key. TLS is required and non-negotiable: sending a
        # bearer credential over a plaintext connection hands it to anyone on
        # the path.
        return {"api_key": api_key, "tls": True, "mode": "cloud (api key)"}

    if cert and key:
        for label, path in (("TEMPORAL_TLS_CERT", cert), ("TEMPORAL_TLS_KEY", key)):
            if not Path(path).is_file():
                raise SystemExit(f"{label} points at a file that does not exist: {path}")
        return {
            "tls": TLSConfig(
                client_cert=Path(cert).read_bytes(),
                client_private_key=Path(key).read_bytes(),
            ),
            "mode": "cloud (mTLS)",
        }

    if cert or key:
        raise SystemExit(
            "mTLS needs both TEMPORAL_TLS_CERT and TEMPORAL_TLS_KEY; only one is set."
        )

    return {"mode": "local (no TLS)"}


async def main() -> None:
    address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")

    args = connect_args()
    mode = args.pop("mode")

    if mode.startswith("local") and not address.startswith(("localhost", "127.0.0.1")):
        log.warning("connecting to %s with no TLS and no credentials — "
                    "TEMPORAL_API_KEY or the cert pair is probably missing", address)

    log.info("connecting to %s  namespace=%s  auth=%s", address, namespace, mode)
    try:
        client = await Client.connect(address, namespace=namespace, **args)
    except Exception as e:
        log.error("could not reach Temporal at %s: %s", address, e)
        if mode.startswith("local"):
            log.error("start one with:  temporal server start-dev")
        else:
            log.error("check TEMPORAL_ADDRESS and TEMPORAL_NAMESPACE — the namespace "
                      "must include your account id, e.g. my-ns.a1b2c")
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
