"""
Token claim faucet — a queue, not a hot wallet.

WHY IT IS BUILT THIS WAY

The obvious faucet holds a funded keypair on the server and pays out the
instant someone asks. That would be the first private key this application has
ever held, and the README's strongest claim ("the app holds no private keys and
signs nothing") would stop being true. A server key is reachable by anything
that can read the filesystem, dump the environment, or run code in-process —
and the whole point of a faucet is that strangers can poke it.

So this stores intent instead of moving value:

  1. Claimer signs a message with their wallet, proving they hold the address.
     Verified with the same ed25519 path as wallet_auth, no key on our side.
  2. The claim is queued, one per address, forever.
  3. The operator reviews pending claims and pays the batch from their own
     wallet, signed in their own extension.
  4. The payout signature is recorded against the claims.

Slower than an instant faucet, and worth it: the worst case here is a junk
queue, not a drained wallet. A queue can be truncated. A drained wallet cannot
be undone.

Sybil resistance is deliberately NOT claimed. One claim per address is trivial
to defeat with a thousand addresses, and every "solution" (captcha, IP limits,
wallet age) is defeated nearly as easily. The real control is the operator
seeing the batch before paying it, and the per-batch cap. Do not tell holders
this is sybil-proof; it is not, and neither is anyone else's.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

import wallet_auth

logger = logging.getLogger(__name__)

# Base58, 32-byte pubkey. Same shape check used elsewhere in the app.
_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")

CLAIM_MESSAGE_PREFIX = "YABBAI faucet claim"


def _enabled() -> bool:
    return os.environ.get("FAUCET_ENABLED", "").strip().lower() in ("1", "true", "yes")


def _tokens_per_claim() -> float:
    try:
        return float(os.environ.get("FAUCET_TOKENS_PER_CLAIM", "1000"))
    except ValueError:
        return 1000.0


def _max_claims() -> int:
    """Hard ceiling on total claims ever queued. Bounds the giveaway."""
    try:
        return int(os.environ.get("FAUCET_MAX_CLAIMS", "1000"))
    except ValueError:
        return 1000


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ClaimRequest(BaseModel):
    address: str = Field(..., min_length=32, max_length=44)
    message: str
    signature: str


def build_router(db, require_director, limiter) -> APIRouter:
    """
    Factory rather than a module-level router: server.py owns the database
    handle, the auth dependency and the rate limiter, and importing them back
    out of server.py would be circular.
    """
    router = APIRouter(prefix="/faucet", tags=["faucet"])

    async def _claimed_count() -> int:
        return await db.faucet_claims.count_documents({})

    # ── public ───────────────────────────────────────────────────────────────

    @router.get("/status")
    async def status() -> Dict[str, Any]:
        """Public. Safe to render on the holders page."""
        claimed = await _claimed_count()
        paid = await db.faucet_claims.count_documents({"status": "paid"})
        cap = _max_claims()
        return {
            "enabled": _enabled(),
            "tokens_per_claim": _tokens_per_claim(),
            "claims_total": claimed,
            "claims_paid": paid,
            "claims_pending": claimed - paid,
            "cap": cap,
            "remaining": max(0, cap - claimed),
            # Stated plainly rather than implied. A claimer should know a queue
            # position is not a transfer.
            "note": "A claim is a queued request. Tokens move when the operator "
                    "signs the payout batch, not at claim time.",
        }

    @router.post("/nonce")
    @limiter.limit("10/minute")
    async def nonce(request: Request, address: str = Query(...)) -> Dict[str, Any]:
        if not _ADDRESS_RE.match(address.strip()):
            raise HTTPException(status_code=400, detail="not a Solana address")
        issued = wallet_auth.issue_nonce(address.strip())
        return {
            "nonce": issued.get("nonce"),
            "message": f"{CLAIM_MESSAGE_PREFIX}\naddress: {address.strip()}\nnonce: {issued.get('nonce')}",
        }

    @router.post("/claim")
    @limiter.limit("5/minute")
    async def claim(request: Request, body: ClaimRequest) -> Dict[str, Any]:
        if not _enabled():
            raise HTTPException(status_code=503, detail="faucet is closed")

        address = body.address.strip()
        if not _ADDRESS_RE.match(address):
            raise HTTPException(status_code=400, detail="not a Solana address")

        # Bind the signed message to this address, so a signature harvested
        # from somewhere else cannot be replayed to claim for another wallet.
        if not body.message.startswith(CLAIM_MESSAGE_PREFIX):
            raise HTTPException(status_code=400, detail="unexpected message")
        if f"address: {address}" not in body.message:
            raise HTTPException(status_code=400, detail="message does not match address")

        ok, reason = wallet_auth.verify(address, body.message, body.signature)
        if not ok:
            logger.info("faucet claim rejected for %s: %s", address, reason)
            raise HTTPException(status_code=401, detail=f"signature rejected: {reason}")

        if await db.faucet_claims.find_one({"address": address}):
            raise HTTPException(status_code=409, detail="already claimed")

        # Check the cap AFTER verification so an unsigned request cannot probe
        # how full the queue is, and re-check rather than trusting the earlier
        # status read.
        if await _claimed_count() >= _max_claims():
            raise HTTPException(status_code=410, detail="faucet is empty")

        doc = {
            "address": address,
            "tokens": _tokens_per_claim(),
            "status": "pending",
            "claimed_at": _now(),
            "paid_at": None,
            "payout_signature": None,
        }
        await db.faucet_claims.insert_one(doc)
        logger.info("faucet claim queued: %s", address)

        position = await db.faucet_claims.count_documents({"status": "pending"})
        return {
            "status": "queued",
            "address": address,
            "tokens": _tokens_per_claim(),
            "queue_position": position,
        }

    # ── operator ─────────────────────────────────────────────────────────────

    @router.get("/pending")
    async def pending(limit: int = Query(100, ge=1, le=500),
                      user: dict = Depends(require_director)) -> Dict[str, Any]:
        """Director only. The batch to be paid."""
        rows = await db.faucet_claims.find(
            {"status": "pending"}, {"_id": 0}
        ).sort("claimed_at", 1).to_list(length=limit)

        for r in rows:
            for k in ("claimed_at", "paid_at"):
                if isinstance(r.get(k), datetime):
                    r[k] = r[k].isoformat()

        return {
            "count": len(rows),
            "total_tokens": sum(r.get("tokens", 0) for r in rows),
            "claims": rows,
        }

    class PaidRequest(BaseModel):
        addresses: list[str]
        signature: str = Field(..., min_length=32)

    @router.post("/paid")
    async def mark_paid(body: PaidRequest,
                        user: dict = Depends(require_director)) -> Dict[str, Any]:
        """
        Record that a payout landed. Called after the operator's wallet has
        signed and the transaction confirmed — this writes history, it does not
        move anything.
        """
        addresses = [a.strip() for a in body.addresses if _ADDRESS_RE.match(a.strip())]
        if not addresses:
            raise HTTPException(status_code=400, detail="no valid addresses")

        result = await db.faucet_claims.update_many(
            {"address": {"$in": addresses}, "status": "pending"},
            {"$set": {
                "status": "paid",
                "paid_at": _now(),
                "payout_signature": body.signature.strip(),
            }},
        )
        logger.info("faucet: marked %d claims paid, sig %s",
                    result.modified_count, body.signature.strip()[:16])
        return {"marked_paid": result.modified_count, "signature": body.signature.strip()}

    return router
