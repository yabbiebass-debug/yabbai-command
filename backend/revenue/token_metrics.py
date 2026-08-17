#!/usr/bin/env python3
"""
YABBAI — token metrics for the agent phases.

The revenue system shipped with three abstract business channels: products,
agency and trading. None of them describe what this project actually is. This is
a token with a treasury, so the numbers that matter are on-chain: supply, price,
market cap, holder count, concentration, treasury balance, traded volume, and the
LP fee share that accrues after graduation.

Every value here is measured. Where a source cannot answer, the field is None and
the caller reports DATA GAP. Nothing is projected, and nothing measured here is
income: token price moving is not revenue, and treasury balance is a position,
not a profit. Only a realised, reconciled inflow counts as income, which is what
the truth ledger is for.
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Fifty agents cycling every ten seconds means up to 300 provider calls a minute
# for data that changes far more slowly than that. Left uncached it rate-limited
# Jupiter, and price arrived as None — a real value turned into a DATA GAP purely
# by self-inflicted load. One shared measurement serves every agent inside the
# window; they are all reading the same chain at the same moment anyway.
MEASUREMENT_TTL = float(os.environ.get("TOKEN_MEASUREMENT_TTL", "30"))

_cache: Dict[str, Any] = {"at": 0.0, "value": None, "key": None}
_lock = asyncio.Lock()


async def collect_cached(*args, **kwargs) -> Dict[str, Any]:
    """collect(), shared across concurrent callers for MEASUREMENT_TTL seconds.

    The lock matters as much as the TTL: without it fifty agents all miss the
    cache simultaneously and fifty identical fan-outs go out anyway. The first
    caller measures, the rest wait and reuse the result.
    """
    key = f"{args[1] if len(args) > 1 else ''}|{args[2] if len(args) > 2 else ''}"
    now = time.time()

    if _cache["value"] is not None and _cache["key"] == key \
            and (now - _cache["at"]) < MEASUREMENT_TTL:
        return {**_cache["value"], "cached": True}

    async with _lock:
        # Re-check: another caller may have filled it while we waited.
        now = time.time()
        if _cache["value"] is not None and _cache["key"] == key \
                and (now - _cache["at"]) < MEASUREMENT_TTL:
            return {**_cache["value"], "cached": True}

        value = await collect(*args, **kwargs)
        _cache.update({"at": time.time(), "value": value, "key": key})
        return {**value, "cached": False}


async def collect(
    chain,
    mint: str,
    treasury: str,
    jupiter_price_fn,
    jupiter_key: str = "",
    dex_market_fn=None,
) -> Dict[str, Any]:
    """One full measurement of the token's on-chain and market state."""
    import asyncio

    tasks = [
        chain.token_supply(mint),
        chain.mint_authorities(mint),
        chain.holder_count(mint),
        chain.largest_accounts(mint),
        jupiter_price_fn(mint, jupiter_key),
        chain.treasury_state(treasury, mint),
    ]
    if dex_market_fn is not None:
        tasks.append(dex_market_fn(mint))

    results = await asyncio.gather(*tasks, return_exceptions=True)
    values = [None if isinstance(r, Exception) else r for r in results]
    supply, authorities, holders, largest, price, treasury_state = values[:6]
    market = values[6] if len(values) > 6 else None

    supply_amount = (supply or {}).get("supply")
    market_cap = supply_amount * price if supply_amount and price is not None else None

    concentration = None
    if largest and supply_amount:
        top = sum(a["amount"] for a in largest if a.get("amount"))
        if supply_amount > 0:
            concentration = round(top / supply_amount * 100, 4)

    treasury_state = treasury_state or {}

    gaps = []
    if supply_amount is None:
        gaps.append("supply")
    if price is None:
        gaps.append("price")
    if (holders or {}).get("holders") is None:
        gaps.append("holder_count")
    if concentration is None:
        gaps.append("concentration")
    if treasury_state.get("sol") is None:
        gaps.append("treasury_sol")

    return {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "mint": mint,
        "supply": supply_amount,
        "decimals": (supply or {}).get("decimals"),
        "price_usd": price,
        "market_cap_usd": market_cap,
        "holders": (holders or {}).get("holders"),
        "top_concentration_pct": concentration,
        "mint_authority_revoked": (authorities or {}).get("mint_revoked"),
        "freeze_authority_revoked": (authorities or {}).get("freeze_revoked"),
        "treasury_address": treasury,
        "treasury_sol": treasury_state.get("sol"),
        "treasury_token_balance": treasury_state.get("token_balance"),
        "volume_24h_usd": (market or {}).get("volume_24h_usd"),
        "trades_24h": (market or {}).get("trades_24h"),
        "liquidity_usd": (market or {}).get("liquidity_usd"),
        "venue": (market or {}).get("dex"),
        "data_gaps": gaps,
    }


def compare(previous: Optional[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Any]:
    """Change between two measurements.

    Deltas are only computed where both sides are real numbers. A field that was
    unavailable last cycle produces no delta rather than a fabricated zero.
    """
    if not previous:
        return {"first_measurement": True, "changes": {}}

    changes: Dict[str, Any] = {}
    for field in (
        "price_usd", "market_cap_usd", "holders", "top_concentration_pct",
        "treasury_sol", "treasury_token_balance", "volume_24h_usd", "trades_24h",
    ):
        before, after = previous.get(field), current.get(field)
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            delta = after - before
            if delta != 0:
                changes[field] = {
                    "from": before,
                    "to": after,
                    "delta": round(delta, 10),
                    "pct": round(delta / before * 100, 4) if before else None,
                }
    return {"first_measurement": False, "changes": changes}


def assess(current: Dict[str, Any], settings: Dict[str, Any]) -> Dict[str, Any]:
    """Compare measurements against operator-configured thresholds.

    Observations only. Nothing here executes; a treasury movement needs a human
    signature, and the withdrawal allowlist applies regardless.
    """
    obs = []
    price = current.get("price_usd")
    treasury_sol = current.get("treasury_sol")
    concentration = current.get("top_concentration_pct")
    volume = current.get("volume_24h_usd")

    drop_pct = settings.get("alert_price_drop_pct")
    if isinstance(drop_pct, (int, float)) and settings.get("_reference_price") and price:
        ref = settings["_reference_price"]
        change = (price - ref) / ref * 100 if ref else None
        if change is not None and change <= -abs(drop_pct):
            obs.append({
                "level": "alert",
                "field": "price_usd",
                "message": f"price down {abs(change):.2f}% from reference, "
                           f"threshold {drop_pct}%",
            })

    low_sol = settings.get("alert_balance_low_sol")
    if isinstance(low_sol, (int, float)) and isinstance(treasury_sol, (int, float)):
        if treasury_sol < low_sol:
            obs.append({
                "level": "alert",
                "field": "treasury_sol",
                "message": f"treasury {treasury_sol:.4f} SOL below threshold {low_sol}",
            })

    if isinstance(concentration, (int, float)) and concentration > 90:
        obs.append({
            "level": "info",
            "field": "top_concentration_pct",
            "message": "concentration above 90%, expected while on the bonding "
                       "curve since the curve holds supply",
        })

    if isinstance(volume, (int, float)) and volume == 0:
        obs.append({
            "level": "info",
            "field": "volume_24h_usd",
            "message": "no traded volume in the last 24h",
        })

    return {
        "observations": obs,
        "alert_count": sum(1 for o in obs if o["level"] == "alert"),
        "note": "Observations only. No phase executes a trade or moves funds.",
    }
