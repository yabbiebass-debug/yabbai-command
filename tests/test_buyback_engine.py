"""Tests for autonomous buyback decisioning.

The engine spends real treasury SOL, so the cases that matter are the ones where
it must refuse: no price, an empty treasury, a fee reserve that would be
breached, a quote that prices badly, and a cooldown still running.

    python tests/test_buyback_engine.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
)

from revenue.buyback_engine import (  # noqa: E402
    should_propose, review, size_buy, MIN_SOL_RESERVE, MAX_PRICE_IMPACT_PCT,
)

NOW = datetime.now(timezone.utc)
failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name} {detail}")


ON = {"buyback_enabled": True, "risk_appetite": 40, "reinvest_rate": 60,
      "buyback_drop_pct": 15.0}
METRICS = {"treasury_sol": 1.744, "price_usd": 1.0e-05, "mint": "M"}

# Disabled by default: automation that spends money must be opted into.
r = should_propose(METRICS, {"risk_appetite": 40}, None, None)
check("disabled unless explicitly enabled", not r["propose"], r)

# Refuses without a price rather than buying blind.
r = should_propose({**METRICS, "price_usd": None}, ON, None, 1.2e-05)
check("refuses when price unavailable", not r["propose"], r)

# Fee reserve protected.
r = should_propose({**METRICS, "treasury_sol": MIN_SOL_RESERVE - 0.001}, ON, None, 1.2e-05)
check("refuses below the fee reserve", not r["propose"], r)

# Trigger requires a real fall, not any movement.
r = should_propose(METRICS, ON, None, 1.02e-05)   # only -2%
check("no proposal above the drop threshold", not r["propose"], r)

r = should_propose(METRICS, ON, None, 2.0e-05)    # -50%
check("proposes on a genuine fall", r["propose"], r)

# Cooldown prevents a queue of near-duplicates.
r = should_propose(METRICS, ON, NOW - timedelta(minutes=5), 2.0e-05)
check("cooldown respected", not r["propose"], r)

# Zeroed sliders mean nothing is spent.
r = should_propose(METRICS, {**ON, "risk_appetite": 0}, None, 2.0e-05)
check("zero risk appetite proposes nothing", not r["propose"], r)

# Sizing scales with the operator's own settings and never exceeds spendable.
small = size_buy(1.0, 20, 50)
large = size_buy(1.0, 90, 90)
check("higher risk sizes larger", large > small, (small, large))
check("size stays within spendable", large <= 1.0, large)

# A quote that prices badly is refused even after a valid trigger.
good = should_propose(METRICS, ON, None, 2.0e-05)
r = review(good, {"price_impact_pct": MAX_PRICE_IMPACT_PCT + 1, "out_amount_raw": "1"})
check("refuses excessive price impact", not r["propose"], r)

r = review(good, {"price_impact_pct": 1.5, "out_amount_raw": "1000"})
check("accepts an acceptable quote", r.get("propose"), r)
check("accepted proposal still requires a signature",
      r.get("requires_signature") is True, r)
check("proposal discloses that a buyback shrinks SOL",
      "shrinks the treasury" in (r.get("disclosure") or ""), r.get("disclosure"))

r = review(good, None)
check("refuses when no route is quoted", not r["propose"], r)

print()
if failures:
    print(f"{len(failures)} FAILURE(S)")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all buyback engine tests passed")
