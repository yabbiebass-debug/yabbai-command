"""Live mainnet tests for solana_live.py.

Uses USDC because its real values are independently checkable, so a broken
implementation cannot quietly pass. Requires network access.

Set SOLANA_RPC_URL to a Helius (or equivalent) endpoint to also exercise
holder_count and largest_accounts — the public endpoint rate-limits or refuses both,
in which case those are reported as skipped rather than failed.

    python tests/test_solana_live.py
"""
import asyncio
import logging
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
)
logging.basicConfig(level=logging.ERROR)

from solana_live import SolanaLive, jupiter_price  # noqa: E402

USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
WSOL = "So11111111111111111111111111111111111111112"
RPC = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

failures = []
skips = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name} {detail}")


def skip(name, why):
    print(f"SKIP  {name} ({why})")
    skips.append(name)


def _mask(url: str) -> str:
    """RPC URLs usually carry an API key in the path or query. Never print it."""
    try:
        scheme, rest = url.split("://", 1)
        host = rest.split("/", 1)[0].split("?", 1)[0]
        return f"{scheme}://{host}/***"
    except ValueError:
        return "***"


async def main():
    print(f"RPC: {_mask(RPC)}\n")
    chain = SolanaLive(RPC)

    supply = await chain.token_supply(USDC)
    if supply is None:
        check("token_supply returns data", False, "got None")
    else:
        check("USDC decimals == 6", supply["decimals"] == 6, supply)
        check("USDC supply > 1e9", supply["supply"] > 1_000_000_000, supply)
        check("supply_raw is a digit string", str(supply["supply_raw"]).isdigit(), supply)

    auth = await chain.mint_authorities(USDC)
    if auth is None:
        check("mint_authorities returns data", False, "got None")
    else:
        check(
            "revoked flags agree with authority values",
            auth["mint_revoked"] == (auth["mint_authority"] is None)
            and auth["freeze_revoked"] == (auth["freeze_authority"] is None),
            auth,
        )

    price = await jupiter_price(USDC)
    if price is None:
        check("jupiter_price returns a price", False, "got None")
    else:
        check("USDC price within 0.90-1.10", 0.90 < price < 1.10, price)

    sol = await chain.sol_balance(WSOL)
    check("sol_balance returns a non-negative float",
          isinstance(sol, float) and sol >= 0, sol)

    # Market cap, composed the same way /api/token-stats composes it.
    if supply and price is not None:
        mcap = supply["supply"] * price
        check("USDC market cap between $1B and $100B", 1e9 < mcap < 1e11, f"{mcap:,.0f}")

    # These need an RPC that permits the heavier methods.
    largest = await chain.largest_accounts(USDC)
    if largest is None:
        skip("largest_accounts", "RPC rate-limited or refused")
    else:
        check("largest_accounts returns entries", len(largest) > 0, len(largest))
        check(
            "largest_accounts sorted descending",
            all(
                largest[i]["amount"] >= largest[i + 1]["amount"]
                for i in range(len(largest) - 1)
                if largest[i]["amount"] is not None
                and largest[i + 1]["amount"] is not None
            ),
            largest[:3],
        )

    holders = await chain.holder_count(USDC)
    if holders is None:
        skip("holder_count", "RPC refuses getProgramAccounts")
    else:
        check("holder_count positive", holders["holders"] > 0, holders)
        check(
            "holders <= token_accounts",
            holders["holders"] <= holders["token_accounts"],
            holders,
        )

    # A nonexistent mint must return None, never a fabricated zero.
    bogus = await chain.token_supply("11111111111111111111111111111111")
    check("unknown mint -> None, not 0", bogus is None, bogus)

    print()
    if skips:
        print(f"{len(skips)} skipped (needs a Helius-class RPC): {', '.join(skips)}")
    if failures:
        print(f"\n{len(failures)} FAILURE(S)")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("all live mainnet tests passed")


asyncio.run(main())
