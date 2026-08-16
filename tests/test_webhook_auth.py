"""Tests for webhook signature verification.

These endpoints book REAL income into the truth ledger, and real_income() is what
the withdraw phase reads when deciding whether to propose a payout. An unsigned
webhook is therefore a way to make the system believe it has money it does not.

    python tests/test_webhook_auth.py
"""
import os
import sys
import time

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
)

from revenue.webhook_auth import verify, expected_signature, configured_sources  # noqa: E402

SECRET = "test-secret-value"
BODY = b'{"sale_id":"s1","gross_usd":100}'

failures = []


def check(name, condition, detail=""):
    print(f"{'PASS' if condition else 'FAIL'}  {name}")
    if not condition:
        failures.append(f"{name} {detail}")


os.environ["WEBHOOK_SECRET"] = SECRET
ts = str(int(time.time()))
sig = expected_signature(SECRET, BODY, ts)

ok, reason = verify("product", BODY, sig, ts)
check("valid signature accepted", ok, reason)

ok, reason = verify("product", BODY, "deadbeef", ts)
check("wrong signature rejected", not ok, reason)

ok, reason = verify("product", BODY, None, ts)
check("missing signature rejected", not ok, reason)

# The critical case: same signature, altered amount.
ok, reason = verify("product", b'{"sale_id":"s1","gross_usd":999999}', sig, ts)
check("tampered body rejected", not ok, reason)

ok, reason = verify("product", BODY, sig, str(int(time.time()) - 9999))
check("stale timestamp rejected (replay)", not ok, reason)

# Signature scheme prefixes, as Stripe and GitHub send them.
ok, reason = verify("product", BODY, f"sha256={sig}", ts)
check("sha256= prefix accepted", ok, reason)

# Per-source secret should override the shared one.
os.environ["WEBHOOK_SECRET_INVOICE"] = "invoice-only-secret"
inv_sig = expected_signature("invoice-only-secret", BODY, ts)
ok, reason = verify("invoice", BODY, inv_sig, ts)
check("per-source secret used", ok, reason)

ok, reason = verify("invoice", BODY, sig, ts)
check("shared secret rejected where source secret set", not ok, reason)
del os.environ["WEBHOOK_SECRET_INVOICE"]

# Fails closed with nothing configured.
del os.environ["WEBHOOK_SECRET"]
ok, reason = verify("product", BODY, sig, ts)
check("no secret configured fails closed", not ok, reason)

sources = configured_sources()
check("configured_sources leaks no secret values",
      all(isinstance(v, bool) for v in sources.values()), sources)

print()
if failures:
    print(f"{len(failures)} FAILURE(S)")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all webhook auth tests passed")
