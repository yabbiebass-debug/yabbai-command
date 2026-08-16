#!/usr/bin/env python3
"""
YABBAI — webhook signature verification.

The revenue webhooks book REAL income into the truth ledger. They were
unauthenticated, so anyone who guessed the URL could POST a payload and inflate
real_income() at will. Since real_income() is what the withdraw phase reads to
decide whether to propose a payout, that is not a cosmetic problem.

plan.md already listed this as a hardening item and explained why Director auth is
the wrong tool: a payment processor cannot hold a hub session. The right control
is a shared secret and an HMAC over the raw body, which is what Stripe, Gumroad
and PayPal all provide.

Fails closed. With no secret configured, every webhook is rejected — an
unverifiable payment is not booked.
"""

import hashlib
import hmac
import logging
import os
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Tolerance for clock skew and delivery delay. Beyond this a replayed capture is
# refused even when the signature is valid.
MAX_AGE_SECONDS = int(os.environ.get("WEBHOOK_MAX_AGE_SECONDS", "300"))


def _secret_for(source: str) -> Optional[str]:
    """Per-source secret, falling back to a shared one."""
    specific = os.environ.get(f"WEBHOOK_SECRET_{source.upper()}")
    return specific or os.environ.get("WEBHOOK_SECRET") or None


def expected_signature(secret: str, raw_body: bytes, timestamp: str = "") -> str:
    """HMAC-SHA256 over `timestamp.body`, hex encoded."""
    payload = f"{timestamp}.".encode() + raw_body if timestamp else raw_body
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def verify(
    source: str,
    raw_body: bytes,
    signature: Optional[str],
    timestamp: Optional[str] = None,
) -> Tuple[bool, str]:
    """Check a webhook signature. Returns (ok, reason)."""
    secret = _secret_for(source)
    if not secret:
        # Fail closed. Booking unverifiable income is worse than dropping it.
        return False, (
            f"no secret configured for '{source}'. Set WEBHOOK_SECRET_{source.upper()} "
            "or WEBHOOK_SECRET to accept webhooks."
        )

    if not signature:
        return False, "missing signature header"

    if timestamp:
        try:
            age = abs(time.time() - float(timestamp))
        except (TypeError, ValueError):
            return False, "malformed timestamp"
        if age > MAX_AGE_SECONDS:
            return False, f"timestamp {age:.0f}s old, limit {MAX_AGE_SECONDS}s"

    expected = expected_signature(secret, raw_body, timestamp or "")

    # Some senders prefix the scheme, e.g. "sha256=abc123".
    provided = signature.split("=", 1)[1] if "=" in signature else signature

    # Constant time: a plain == leaks the correct prefix through timing.
    if not hmac.compare_digest(expected, provided.strip()):
        return False, "signature mismatch"

    return True, "verified"


def configured_sources() -> dict:
    """Which webhook sources have a secret set. Values are never returned."""
    shared = bool(os.environ.get("WEBHOOK_SECRET"))
    out = {"shared_secret_set": shared}
    for source in ("product", "invoice", "sweep"):
        out[source] = bool(os.environ.get(f"WEBHOOK_SECRET_{source.upper()}")) or shared
    return out
