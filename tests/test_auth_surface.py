"""The anonymous API surface, asserted rather than assumed.

This project exists because the previous version was publicly reachable and got
swept. A route added later without a guard would reopen exactly that hole and
nothing would fail loudly, so the allowlist below is the contract: anything
reachable without authentication has to be named here on purpose.

    python tests/test_auth_surface.py
"""
import inspect
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, BACKEND)
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "yabbai_test")

import server  # noqa: E402

# Guards, whether applied as a dependency or called inside the handler.
GUARDS = ("require_director", "verify_revenue_admin", "_verified_webhook_body")

# Reachable without a session, deliberately. Each entry is a decision.
PUBLIC = {
    ("GET", "/api/"),                       # health check
    ("GET", "/api/public/token"),           # holders page: measured token stats
    ("GET", "/api/public/price-history"),   # holders page: recorded price points

    # ── Faucet ──────────────────────────────────────────────────────────────
    # These three must be anonymous: the people claiming are strangers with a
    # wallet and no account, which is the entire point of a faucet.
    #
    # The property that makes them safe is that NONE of them can move value.
    # backend/faucet.py stores signed intent and nothing else — the server holds
    # no key, and payouts are signed later by the operator's own wallet. The
    # worst outcome reachable from this surface is a queue full of junk, which
    # can be truncated. That is a deliberately different failure class from the
    # one that got this project swept.
    #
    # Re-check that claim before widening any of them: the moment a faucet route
    # can sign, transfer, or authorise, it stops belonging on this list.

    ("GET", "/api/faucet/status"),          # counts and cap; no addresses, no operator state
    ("POST", "/api/faucet/nonce"),          # anti-replay nonce; public by design, 10/min
    ("POST", "/api/faucet/claim"),          # ed25519-verified, deduped, capped, 5/min
}

failures = []


def guarded(route):
    dep = getattr(route, "dependant", None)
    names = [d.call.__name__ for d in (dep.dependencies if dep else [])]
    if any(g in names for g in GUARDS):
        return True
    try:
        src = inspect.getsource(route.endpoint)
    except Exception:
        return False
    return any(f"{g}(" in src for g in GUARDS)


anonymous = set()
for route in server.api_router.routes:
    if not guarded(route):
        anonymous.add((sorted(route.methods)[0], route.path))

unexpected = sorted(anonymous - PUBLIC)
stale = sorted(PUBLIC - anonymous)

print(f"api routes: {len(server.api_router.routes)}")
print(f"anonymous:  {len(anonymous)}")
for m, p in sorted(anonymous):
    print(f"   {m:5} {p}")

if unexpected:
    failures.append("routes reachable without auth and not in the allowlist:")
    failures += [f"    {m} {p}" for m, p in unexpected]
if stale:
    failures.append("allowlisted routes that are now guarded or gone "
                    "(remove them from PUBLIC):")
    failures += [f"    {m} {p}" for m, p in stale]

# The public token endpoint must not leak operator state. These keys have all
# appeared in an anonymous response at some point in this project's history.
FORBIDDEN_PUBLIC_KEYS = {
    "treasury_wallet", "main_wallet", "rpc_url", "wallets", "transactions",
    "clients", "invoices", "withdrawals", "settings", "balance_sol",
}
try:
    src = inspect.getsource(server.public_token)
    leaked = sorted(k for k in FORBIDDEN_PUBLIC_KEYS if f'"{k}"' in src)
    print(f"\npublic/token leaked keys: {leaked or 'none'}")
    if leaked:
        failures.append(f"public/token references operator-only keys: {leaked}")
except AttributeError:
    failures.append("server.public_token is missing; the holders page depends on it")

print()
if failures:
    print(f"{len(failures)} PROBLEM(S)")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("auth surface matches the allowlist")
