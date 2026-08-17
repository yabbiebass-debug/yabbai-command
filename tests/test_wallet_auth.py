"""Tests for Sign-In With Solana verification.

The point of these is that a signature proves control of a wallet and nothing
more, and that a captured signature cannot be reused or carried over from
another site.

    python tests/test_wallet_auth.py
"""
import base64
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
)

import base58  # noqa: E402
from nacl.signing import SigningKey  # noqa: E402

import wallet_auth  # noqa: E402

failures = []


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}  {name}")
    if not condition:
        failures.append(f"{name} {detail}")


# A throwaway keypair standing in for a wallet.
key = SigningKey.generate()
address = base58.b58encode(bytes(key.verify_key)).decode()


def sign(msg: str) -> str:
    return base64.b64encode(key.sign(msg.encode()).signature).decode()


# Happy path.
issued = wallet_auth.issue_nonce(address)
ok, reason = wallet_auth.verify(address, issued["message"], sign(issued["message"]))
check("valid signature verifies", ok, reason)

# Single use: the same signature must not work twice.
ok, reason = wallet_auth.verify(address, issued["message"], sign(issued["message"]))
check("replay of consumed nonce rejected", not ok, reason)

# Wrong signer.
other = SigningKey.generate()
other_addr = base58.b58encode(bytes(other.verify_key)).decode()
issued2 = wallet_auth.issue_nonce(address)
wrong_sig = base64.b64encode(other.sign(issued2["message"].encode()).signature).decode()
ok, reason = wallet_auth.verify(address, issued2["message"], wrong_sig)
check("signature from another key rejected", not ok, reason)

# Address that did not sign.
issued3 = wallet_auth.issue_nonce()
ok, reason = wallet_auth.verify(other_addr, issued3["message"], sign(issued3["message"]))
check("mismatched address rejected", not ok, reason)

# Tampered message: valid signature, altered text.
issued4 = wallet_auth.issue_nonce(address)
sig4 = sign(issued4["message"])
ok, reason = wallet_auth.verify(address, issued4["message"] + " extra", sig4)
check("tampered message rejected", not ok, reason)

# A message this server never issued.
forged = (
    "token.yabbai.network wants you to sign in.\n\n"
    "Domain: token.yabbai.network\nNonce: made-up-nonce\n"
)
ok, reason = wallet_auth.verify(address, forged, sign(forged))
check("unissued nonce rejected", not ok, reason)

# A signature collected by a different site.
issued5 = wallet_auth.issue_nonce(address)
other_domain = issued5["message"].replace(
    "Domain: token.yabbai.network", "Domain: evil.example"
)
ok, reason = wallet_auth.verify(address, other_domain, sign(other_domain))
check("wrong domain rejected", not ok, reason)

# Nonce bound to a specific address cannot be used by another.
issued6 = wallet_auth.issue_nonce(address)
ok, reason = wallet_auth.verify(other_addr, issued6["message"],
                                base64.b64encode(other.sign(issued6["message"].encode()).signature).decode())
check("nonce bound to its address", not ok, reason)

# Malformed inputs.
issued7 = wallet_auth.issue_nonce(address)
ok, reason = wallet_auth.verify("not-base58!!", issued7["message"], sign(issued7["message"]))
check("invalid address rejected", not ok, reason)

issued8 = wallet_auth.issue_nonce(address)
ok, reason = wallet_auth.verify(address, issued8["message"], "not-base64!!")
check("invalid signature encoding rejected", not ok, reason)

# The message must say plainly that nothing is authorised.
msg = wallet_auth.issue_nonce(address)["message"]
check("message states it authorises no transaction",
      "authorises no transaction" in msg and "moves no funds" in msg, msg[:80])

print()
if failures:
    print(f"{len(failures)} FAILURE(S)")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all wallet auth tests passed")
