#!/usr/bin/env python3
"""
YABBAI — DexScreener market data.

Adds what chain reads cannot give: traded volume, buy/sell counts, price change
over a window, and the pair address so a holder can open the live chart.

Free, no API key, roughly 300 requests per minute on pair data. The legacy
/latest/dex/tokens endpoint is used deliberately — measured at 331 ms against
2556 ms for token-pairs/v1 on the same mint.

Same rule as everywhere else: a value that cannot be read comes back None and the
UI shows DATA GAP. That matters especially here. A token still on its bonding
curve has no conventional liquidity pool, so DexScreener returns no liquidity and
an empty priceChange. Rendering those as $0 and 0% would claim the token has zero
liquidity, when the truth is that the measure does not apply yet.
"""

import logging
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

BASE = "https://api.dexscreener.com/latest/dex/tokens"
TIMEOUT = 10.0


def _num(value: Any) -> Optional[float]:
    """Coerce to float, treating missing and unparsable as unavailable."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _best_pair(pairs: list) -> Optional[Dict[str, Any]]:
    """The pair with the most 24h volume, falling back to the first."""
    if not pairs:
        return None
    scored = [(_num((p.get("volume") or {}).get("h24")) or 0.0, p) for p in pairs]
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[0][1]


async def market(mint: str, client: Optional[httpx.AsyncClient] = None) -> Optional[Dict[str, Any]]:
    """Market data for a mint, or None when DexScreener has not indexed it."""
    try:
        if client is None:
            async with httpx.AsyncClient(timeout=TIMEOUT) as c:
                resp = await c.get(f"{BASE}/{mint}")
        else:
            resp = await client.get(f"{BASE}/{mint}", timeout=TIMEOUT)
    except Exception as e:
        logger.warning(f"dexscreener({mint}) unreachable: {e}")
        return None

    if resp.status_code != 200:
        logger.warning(f"dexscreener({mint}) HTTP {resp.status_code}")
        return None

    try:
        pairs = (resp.json() or {}).get("pairs") or []
    except Exception as e:
        logger.warning(f"dexscreener({mint}) bad JSON: {e}")
        return None

    pair = _best_pair(pairs)
    if not pair:
        # Not indexed yet. A brand new mint can take a while to appear.
        return None

    volume = pair.get("volume") or {}
    txns = pair.get("txns") or {}
    change = pair.get("priceChange") or {}
    h24 = txns.get("h24") or {}

    buys = h24.get("buys")
    sells = h24.get("sells")
    trades = (buys + sells) if isinstance(buys, int) and isinstance(sells, int) else None

    return {
        "dex": pair.get("dexId"),
        "pair_address": pair.get("pairAddress"),
        "pair_url": pair.get("url"),
        "quote_symbol": (pair.get("quoteToken") or {}).get("symbol"),
        "price_usd": _num(pair.get("priceUsd")),
        "fdv_usd": _num(pair.get("fdv")),
        "market_cap_usd": _num(pair.get("marketCap")),
        # None rather than 0.0 when absent: a bonding curve has no pool to measure.
        "liquidity_usd": _num((pair.get("liquidity") or {}).get("usd")),
        "volume_24h_usd": _num(volume.get("h24")),
        "volume_1h_usd": _num(volume.get("h1")),
        "price_change_24h_pct": _num(change.get("h24")),
        "price_change_1h_pct": _num(change.get("h1")),
        "buys_24h": buys,
        "sells_24h": sells,
        "trades_24h": trades,
        "pair_created_at": pair.get("pairCreatedAt"),
        "source": "dexscreener",
    }


def gaps(data: Optional[Dict[str, Any]]) -> list:
    """Which market fields are unavailable, for the caller's data_gaps list."""
    if data is None:
        return ["market_data"]
    missing = []
    for key, label in (
        ("liquidity_usd", "liquidity"),
        ("volume_24h_usd", "volume_24h"),
        ("price_change_24h_pct", "price_change_24h"),
        ("trades_24h", "trades_24h"),
    ):
        if data.get(key) is None:
            missing.append(label)
    return missing
