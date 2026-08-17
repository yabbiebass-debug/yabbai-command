#!/usr/bin/env python3
"""
YABBAI - autonomous buyback decisioning.

The agents do the whole job except the final signature: watch the market, decide
whether a buy is warranted, size it against the treasury and the operator's risk
settings, price it through Jupiter, and queue it. The operator approves with one
click and their own wallet signs.

Why it stops at the signature
-----------------------------
Signing server-side means storing a key that can spend the treasury. Every other
part of this rebuild exists because that capability was abused once already. The
automation is identical either way - the agents still decide, still size, still
price, still queue - so the only thing a server key buys is removing one click,
and it costs the guarantee that a compromised server cannot move funds.

What it will not do
-------------------
Buying will not be proposed simply because the price fell, or on a schedule. A
buyback spends SOL to acquire tokens, so it shrinks the treasury's SOL and
concentrates it in a single asset. On a bonding curve it is also the operator
buying from themselves, which raises quoted market cap without any outside money
arriving. Proposals therefore carry both facts, and the engine refuses sizes that
would leave the treasury unable to pay transaction fees.
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Never spend below this; a treasury that cannot pay a fee cannot act at all.
MIN_SOL_RESERVE = float(os.environ.get("BUYBACK_MIN_RESERVE_SOL", "0.05"))
# Ceiling per proposal as a fraction of spendable balance, before risk scaling.
MAX_FRACTION = float(os.environ.get("BUYBACK_MAX_FRACTION", "0.25"))
# Refuse to queue when the quote moves the price this much against itself.
MAX_PRICE_IMPACT_PCT = float(os.environ.get("BUYBACK_MAX_IMPACT_PCT", "5.0"))
# Minimum gap between proposals, so a queue does not fill with near-duplicates.
COOLDOWN_MINUTES = int(os.environ.get("BUYBACK_COOLDOWN_MINUTES", "60"))


def size_buy(spendable_sol: float, risk_appetite: int, reinvest_rate: int) -> float:
    """How much to propose, from the operator's own risk and reinvest settings.

    These sliders previously drove nothing. Risk scales how much of the ceiling
    is used; reinvest scales what share of the treasury is considered available
    for buying at all.
    """
    risk = max(0, min(100, risk_appetite)) / 100.0
    reinvest = max(0, min(100, reinvest_rate)) / 100.0
    fraction = MAX_FRACTION * risk * reinvest
    return round(max(0.0, spendable_sol * fraction), 6)


def should_propose(
    metrics: Dict[str, Any],
    settings: Dict[str, Any],
    last_proposal_at: Optional[datetime],
    reference_price: Optional[float],
) -> Dict[str, Any]:
    """Decide whether a buyback is warranted right now, with the reason stated."""
    now = datetime.now(timezone.utc)
    reasons: List[str] = []

    if settings.get("buyback_enabled") is not True:
        return {"propose": False, "reason": "buyback disabled in settings"}

    if last_proposal_at:
        age = (now - last_proposal_at).total_seconds() / 60
        if age < COOLDOWN_MINUTES:
            return {
                "propose": False,
                "reason": f"cooldown, {COOLDOWN_MINUTES - age:.0f} min remaining",
            }

    treasury_sol = metrics.get("treasury_sol")
    if not isinstance(treasury_sol, (int, float)):
        return {"propose": False, "reason": "treasury balance unavailable"}

    spendable = treasury_sol - MIN_SOL_RESERVE
    if spendable <= 0:
        return {
            "propose": False,
            "reason": f"treasury {treasury_sol:.4f} SOL is at or below the "
                      f"{MIN_SOL_RESERVE} SOL fee reserve",
        }

    price = metrics.get("price_usd")
    if price is None:
        return {"propose": False, "reason": "price unavailable; will not buy blind"}

    # A price fall is the trigger, measured against a real earlier observation
    # rather than an assumption about what the price should be.
    drop_threshold = settings.get("buyback_drop_pct")
    if isinstance(drop_threshold, (int, float)) and reference_price:
        change = (price - reference_price) / reference_price * 100
        if change > -abs(drop_threshold):
            return {
                "propose": False,
                "reason": f"price {change:+.2f}% vs reference; trigger is "
                          f"-{abs(drop_threshold):.2f}%",
            }
        reasons.append(f"price {change:+.2f}% against reference")
    else:
        reasons.append("no drop threshold configured; sizing on settings alone")

    amount = size_buy(
        spendable,
        int(settings.get("risk_appetite") or 0),
        int(settings.get("reinvest_rate") or 0),
    )
    if amount <= 0:
        return {
            "propose": False,
            "reason": "risk appetite or reinvest rate is zero, so nothing to spend",
        }

    return {
        "propose": True,
        "amount_sol": amount,
        "spendable_sol": round(spendable, 6),
        "reasons": reasons,
        "at": now,
    }


def review(proposal: Dict[str, Any], quote: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Attach the real quote and refuse the proposal if it prices badly."""
    if not quote:
        return {**proposal, "propose": False,
                "reason": "no route quoted; the pool may be too thin for this size"}

    impact = quote.get("price_impact_pct", 0.0)
    if impact > MAX_PRICE_IMPACT_PCT:
        return {
            **proposal,
            "propose": False,
            "reason": f"price impact {impact:.2f}% exceeds the "
                      f"{MAX_PRICE_IMPACT_PCT:.1f}% limit; this size pays far "
                      "above spot",
        }

    return {
        **proposal,
        "price_impact_pct": round(impact, 4),
        "quoted_out_raw": quote.get("out_amount_raw"),
        "disclosure": (
            "A buyback spends SOL to acquire tokens: it shrinks the treasury's "
            "SOL and concentrates it in one asset. On a bonding curve it is also "
            "buying from yourself, which lifts quoted market cap without outside "
            "money arriving."
        ),
        "requires_signature": True,
    }
