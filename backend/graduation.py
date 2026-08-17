#!/usr/bin/env python3
"""
YABBAI - graduation progress.

A bonding-curve token graduates when enough has been bought to complete the
curve, at which point it migrates to a real liquidity pool and the creator's LP
fee share begins. Until then, every other metric is secondary: the token is not
tradeable in the normal sense and the fee stream does not exist.

Nothing here can make graduation happen. What it can do is state the distance
precisely, from measured data, so the target is a number rather than a feeling.
The launch parameters are configuration because they were chosen at launch and
are not readable from chain.

Deliberately absent: any projection of when graduation will occur. That depends
on buyers arriving, which nothing here measures or influences, and a date would
be a guess dressed as a forecast.
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Chosen in Jupiter Studio at launch; not derivable from chain.
INITIAL_MCAP_SOL = float(os.environ.get("LAUNCH_INITIAL_MCAP_SOL", "200"))
GRADUATION_MCAP_SOL = float(os.environ.get("LAUNCH_GRADUATION_MCAP_SOL", "1200"))
# Platform minimum raise, quoted by Jupiter Studio during setup.
REQUIRED_RAISE_SOL = float(os.environ.get("LAUNCH_REQUIRED_RAISE_SOL", "198.6"))


def assess(
    market_cap_usd: Optional[float],
    sol_price_usd: Optional[float],
    volume_24h_usd: Optional[float] = None,
) -> Dict[str, Any]:
    """Distance to graduation, measured. Returns available:false when it cannot
    be computed rather than guessing at any part of it."""
    if market_cap_usd is None or not sol_price_usd:
        return {
            "available": False,
            "reason": "market cap or SOL price unavailable",
            "initial_mcap_sol": INITIAL_MCAP_SOL,
            "graduation_mcap_sol": GRADUATION_MCAP_SOL,
        }

    mcap_sol = market_cap_usd / sol_price_usd
    span = GRADUATION_MCAP_SOL - INITIAL_MCAP_SOL

    if span <= 0:
        return {"available": False, "reason": "graduation cap must exceed initial cap"}

    # Progress along the curve, clamped: below the opening cap is 0, not negative.
    progress = max(0.0, min(1.0, (mcap_sol - INITIAL_MCAP_SOL) / span))
    remaining_sol = max(0.0, GRADUATION_MCAP_SOL - mcap_sol)

    return {
        "available": True,
        "market_cap_sol": round(mcap_sol, 4),
        "market_cap_usd": round(market_cap_usd, 2),
        "initial_mcap_sol": INITIAL_MCAP_SOL,
        "graduation_mcap_sol": GRADUATION_MCAP_SOL,
        "progress_pct": round(progress * 100, 4),
        "remaining_mcap_sol": round(remaining_sol, 4),
        "remaining_mcap_usd": round(remaining_sol * sol_price_usd, 2),
        "required_raise_sol": REQUIRED_RAISE_SOL,
        "required_raise_usd": round(REQUIRED_RAISE_SOL * sol_price_usd, 2),
        "volume_24h_usd": volume_24h_usd,
        "graduated": mcap_sol >= GRADUATION_MCAP_SOL,
        "sol_price_usd": sol_price_usd,
        "method": (
            "progress along the configured bonding curve, from measured market "
            "cap. No completion date is projected: that depends on buyers "
            "arriving, which nothing here measures."
        ),
    }


def summary_line(g: Dict[str, Any]) -> str:
    """One honest sentence for display."""
    if not g.get("available"):
        return "Graduation progress unavailable - market cap could not be measured."
    if g.get("graduated"):
        return "Graduated. The token has migrated to a liquidity pool."
    return (
        f"{g['progress_pct']:.2f}% of the way along the bonding curve. "
        f"{g['remaining_mcap_sol']:.0f} SOL of market cap remains "
        f"(about ${g['remaining_mcap_usd']:,.0f}) before it graduates."
    )
