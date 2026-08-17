#!/usr/bin/env python3
"""
YABBAI - Sign-In With Solana (SIWS) verification.

Proves that whoever is asking controls a wallet, by having them sign a message
this server issued. Signing a message moves nothing and costs nothing: it is an
ed25519 signature over text, not a transaction. A wallet that signs here cannot
be drained by doing so.

Two properties make it safe to rely on:

  the nonce   is issued by the server, single use, and expires. Without it a
              captured signature could be replayed forever.
  the domain  is inside the signed text, so a signature collected by some other
              site cannot be presented here.

This does not replace the hub session. Director access still requires hub SSO;
this identifies a wallet, which is a different claim from being the operator.
"""

import base64
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DOMAIN = os.environ.get("SIWS_DOMAIN", "token.yabbai.network")
NONCE_TTL = int(os.environ.get("SIWS_NONCE_TTL", "300"))

# nonce -> (issued_at, address_hint). In-process is adequate: a nonce is
# short-lived and single-use, and losing them on restart only forces a re-sign.
_nonces: Dict[str, Tuple[float, Optional[str]]] = {}


def _prune() -> None:
    cutoff = time.time() - NONCE_TTL
    for n in [n for n, (t, _) in _nonces.items() if t < cutoff]:
        _nonces.pop(n, None)


def issue_nonce(address: Optional[str] = None) -> Dict[str, Any]:
    """Create a single-use nonce and the exact text to be signed."""
    _prune()
    nonce = secrets.token_urlsafe(24)
    _nonces[nonce] = (time.time(), address)
    issued = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    statement = (
        f"{DOMAIN} wants you to sign in with your Solana account"
        f"{': ' + address if address else ''}.\n\n"
        "This proves you control this wallet. It authorises no transaction, "
        "moves no funds, and costs nothing.\n\n"
        f"Domain: {DOMAIN}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued}\n"
        f"Expires In: {NONCE_TTL}s"
    )
    return {"nonce": nonce, "message": statement, "domain": DOMAIN,
            "expires_in": NONCE_TTL}


def verify(address: str, message: str, signature_b64: str) -> Tuple[bool, str]:
    """Verify an ed25519 signature over the issued message.

    Checks, in order: the message carries our domain, its nonce was issued by us
    and has not expired or been used, the address is a valid public key, and the
    signature verifies. Any failure returns False with a reason; the nonce is
    consumed on success so the same signature cannot be presented twice.
    """
    try:
        import base58
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError
    except ImportError as e:
        return False, f"verification unavailable: {e}"

    if f"Domain: {DOMAIN}" not in message:
        return False, "message is not for this domain"

    nonce = None
    for line in message.splitlines():
        if line.startswith("Nonce: "):
            nonce = line[7:].strip()
            break
    if not nonce:
        return False, "message carries no nonce"

    _prune()
    entry = _nonces.get(nonce)
    if not entry:
        return False, "nonce unknown, already used, or expired"

    issued_at, expected_address = entry
    if time.time() - issued_at > NONCE_TTL:
        _nonces.pop(nonce, None)
        return False, "nonce expired"
    if expected_address and expected_address != address:
        return False, "nonce was issued for a different address"

    try:
        pubkey = base58.b58decode(address)
    except Exception:
        return False, "address is not valid base58"
    if len(pubkey) != 32:
        return False, "address is not a 32-byte public key"

    try:
        sig = base64.b64decode(signature_b64)
    except Exception:
        return False, "signature is not valid base64"
    if len(sig) != 64:
        return False, "signature is not 64 bytes"

    try:
        VerifyKey(pubkey).verify(message.encode("utf-8"), sig)
    except BadSignatureError:
        return False, "signature does not match this address"
    except Exception as e:
        return False, f"verification error: {e}"

    # Single use.
    _nonces.pop(nonce, None)
    return True, "verified"
