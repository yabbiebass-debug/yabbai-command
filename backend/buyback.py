#!/usr/bin/env python3
"""
YABBAI - treasury buyback quoting.

Buying the token with treasury SOL is the one lever that moves market cap toward
graduation using money already under the operator's control. This prices that
buy honestly and shows what it would actually achieve.

It quotes and proposes. It does not execute. Executing needs a signature, and a
signature needs a key, and a key on the server is exactly what allowed the sweep
that prompted this rebuild. The operator signs in their own wallet or follows the
Jupiter link; nothing here can move funds on its own.

Quotes come from Jupiter's quote API, so price impact and route are real rather
than derived from a spot price. On a bonding curve a large buy moves the price
against itself, and a naive `amount / price` calculation hides that entirely.
"""

import logging
import os
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"
SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = 1_000_000_000

# Leave enough SOL behind to pay for transactions; a buyback that empties the
# treasury cannot pay the fee to execute itself.
FEE_RESERVE_SOL = float(os.environ.get("BUYBACK_FEE_RESERVE_SOL", "0.05"))


async def quote(
    output_mint: str,
    amount_sol: float,
    slippage_bps: int = 50,
    api_key: str = "",
) -> Optional[Dict[str, Any]]:
    """Real Jupiter quote for spending `amount_sol` on the token."""
    if amount_sol <= 0:
        return None

    params = {
        "inputMint": SOL_MINT,
        "outputMint": output_mint,
        "amount": str(int(amount_sol * LAMPORTS_PER_SOL)),
        "slippageBps": str(slippage_bps),
    }
    headers = {"Accept": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(QUOTE_URL, params=params, headers=headers)
    except Exception as e:
        logger.warning(f"buyback quote unreachable: {e}")
        return None

    if resp.status_code != 200:
        logger.warning(f"buyback quote HTTP {resp.status_code}: {resp.text[:160]}")
        return None

    try:
        data = resp.json()
    except Exception as e:
        logger.warning(f"buyback quote bad JSON: {e}")
        return None

    out_amount = data.get("outAmount")
    if out_amount is None:
        return None

    return {
        "in_amount_lamports": data.get("inAmount"),
        "out_amount_raw": out_amount,
        "price_impact_pct": float(data.get("priceImpactPct") or 0) * 100,
        "slippage_bps": slippage_bps,
        "route_count": len(data.get("routePlan") or []),
        "raw": data,
    }


SWAP_URL = "https://lite-api.jup.ag/swap/v1/swap"


async def build_transaction(
    quote_raw: Dict[str, Any],
    user_public_key: str,
    api_key: str = "",
) -> Optional[Dict[str, Any]]:
    """Ask Jupiter to build the swap transaction for a given quote.

    Returns an unsigned, serialised transaction. It is useless without a
    signature, and the only thing that can sign it is the wallet holding that
    public key. This service never sees a key and cannot sign, so a transaction
    returned here cannot execute unless the operator approves it in their own
    wallet, where the amounts are displayed before they accept.
    """
    payload = {
        "quoteResponse": quote_raw,
        "userPublicKey": user_public_key,
        "wrapAndUnwrapSol": True,
        # Priority fee sized automatically; a swap that never lands is worse
        # than one that costs a fraction more to confirm.
        "dynamicComputeUnitLimit": True,
        "prioritizationFeeLamports": "auto",
    }
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(SWAP_URL, json=payload, headers=headers)
    except Exception as e:
        logger.warning(f"swap build unreachable: {e}")
        return None

    if resp.status_code != 200:
        logger.warning(f"swap build HTTP {resp.status_code}: {resp.text[:200]}")
        return None

    try:
        data = resp.json()
    except Exception as e:
        logger.warning(f"swap build bad JSON: {e}")
        return None

    tx = data.get("swapTransaction")
    if not tx:
        return None

    return {
        "swap_transaction": tx,
        "last_valid_block_height": data.get("lastValidBlockHeight"),
        "priority_fee_lamports": data.get("prioritizationFeeLamports"),
        "signed": False,
        "note": (
            "Unsigned. Requires the operator's wallet to sign. This service holds "
            "no keys and cannot sign or submit it."
        ),
    }


def plan(
    treasury_sol: Optional[float],
    quote_result: Optional[Dict[str, Any]],
    decimals: int,
    amount_sol: float,
    graduation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Turn a quote into a proposal with its consequences stated."""
    if treasury_sol is None:
        return {"available": False, "reason": "treasury balance unavailable"}

    spendable = max(0.0, treasury_sol - FEE_RESERVE_SOL)
    if amount_sol > spendable:
        return {
            "available": False,
            "reason": "amount exceeds spendable treasury",
            "treasury_sol": treasury_sol,
            "fee_reserve_sol": FEE_RESERVE_SOL,
            "spendable_sol": round(spendable, 6),
        }

    if not quote_result:
        return {
            "available": False,
            "reason": "no route quoted; the pool may be too thin for this size",
            "treasury_sol": treasury_sol,
            "spendable_sol": round(spendable, 6),
        }

    tokens_out = int(quote_result["out_amount_raw"]) / (10 ** decimals)
    impact = quote_result["price_impact_pct"]

    result = {
        "available": True,
        "executes": False,
        "amount_sol": amount_sol,
        "tokens_out": tokens_out,
        "effective_price_sol": amount_sol / tokens_out if tokens_out else None,
        "price_impact_pct": round(impact, 4),
        "slippage_bps": quote_result["slippage_bps"],
        "route_count": quote_result["route_count"],
        "treasury_sol": treasury_sol,
        "fee_reserve_sol": FEE_RESERVE_SOL,
        "spendable_sol": round(spendable, 6),
        "treasury_sol_after": round(treasury_sol - amount_sol, 6),
        "note": (
            "A proposal, not an execution. This service holds no keys and cannot "
            "sign. Execute in your own wallet, where you approve the transaction."
        ),
    }

    # Price impact is the honest warning: on a thin curve a large buy pays far
    # above spot, and the difference is a real cost, not a rounding error.
    if impact >= 10:
        result["warning"] = (
            f"Price impact {impact:.2f}%. This size moves the price substantially "
            "against itself; a smaller buy gets a materially better rate."
        )
    elif impact >= 3:
        result["warning"] = (
            f"Price impact {impact:.2f}%. Consider splitting this across several "
            "smaller buys."
        )

    # What it would do to graduation progress, if that is measurable.
    if graduation and graduation.get("available"):
        remaining = graduation.get("remaining_mcap_sol")
        if isinstance(remaining, (int, float)) and remaining > 0:
            result["graduation"] = {
                "remaining_mcap_sol_before": remaining,
                "note": (
                    "Buying raises market cap, but not one-for-one with SOL spent: "
                    "the curve prices each token higher as supply is bought. "
                    "Measure the effect after the fact rather than assuming it."
                ),
            }

    return result
