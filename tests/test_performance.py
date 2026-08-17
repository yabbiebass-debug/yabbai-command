"""Unit tests for performance.treasury_performance.

The case that matters most is #3: depositing SOL into a treasury must NOT be reported
as a gain. That is precisely the error the old `risk * 8 + 200` display invited.
"""
import asyncio, os, sys
from datetime import datetime, timezone, timedelta

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
)
from performance import treasury_performance  # noqa: E402

NOW = datetime.now(timezone.utc)

# Fixtures sit at 28 days against a 30-day window deliberately. A snapshot placed at
# exactly the window edge is racy: NOW is captured at import, but treasury_performance
# computes `since` when it runs, milliseconds later, so an edge row falls outside and
# the case silently degrades to "insufficient_data" instead of testing what it claims.


class Cursor:
    def __init__(self, docs): self.docs = docs
    def sort(self, *a, **k): return self
    async def to_list(self, n): return self.docs[:n]


class Coll:
    def __init__(self, docs): self.docs = docs
    def find(self, *a, **k): return Cursor(self.docs)


class DB:
    def __init__(self, snaps, txs):
        self.treasury_snapshots = Coll(snaps)
        self.transactions = Coll(txs)


def snap(days_ago, bal):
    return {"ts": (NOW - timedelta(days=days_ago)).isoformat(), "balance_sol": bal}


def tx(days_ago, kind, amt):
    return {"ts": (NOW - timedelta(days=days_ago)).isoformat(), "type": kind,
            "amount_sol": amt, "status": "confirmed"}


async def main():
    failures = []

    def check(name, cond, detail=""):
        print(f"{'PASS' if cond else 'FAIL'}  {name}")
        if not cond:
            failures.append(f"{name} {detail}")

    # 1. Not enough history
    r = await treasury_performance(DB([snap(1, 10.0)], []), 30)
    check("1 single snapshot -> unavailable",
          r["available"] is False and r["reason"] == "insufficient_data", r)

    # 2. Real growth, no flows: 10 -> 11 over 30d
    r = await treasury_performance(DB([snap(28,10.0), snap(0, 11.0)], []), 30)
    check("2 growth 10->11 = +10% period",
          r["available"] and abs(r["period_return_pct"] - 10.0) < 0.01, r)
    check("2 annualised present for 30d window",
          r["annualised_pct"] is not None and 100 < r["annualised_pct"] < 140, r)

    # 3. THE CRITICAL CASE — balance doubled purely from a deposit
    r = await treasury_performance(
        DB([snap(28,10.0), snap(0, 20.0)], [tx(15, "deposit", 10.0)]), 30)
    check("3 deposit is NOT counted as gain (0%)",
          r["available"] and abs(r["period_return_pct"]) < 0.01, r)
    check("3 net_flows captured as +10",
          abs(r["net_flows_sol"] - 10.0) < 1e-9, r)

    # 4. Withdrawal must not be counted as a loss
    r = await treasury_performance(
        DB([snap(28,20.0), snap(0, 10.0)], [tx(10, "sweep", 10.0)]), 30)
    check("4 sweep is NOT counted as loss (0%)",
          r["available"] and abs(r["period_return_pct"]) < 0.01, r)

    # 5. Deposit + genuine yield: start 10, deposit 5, end 16.5 -> 1.5 real on 10 = 15%
    r = await treasury_performance(
        DB([snap(28,10.0), snap(0, 16.5)], [tx(20, "deposit", 5.0)]), 30)
    check("5 mixed flow+yield isolates the 15% yield",
          r["available"] and abs(r["period_return_pct"] - 15.0) < 0.01, r)

    # 6. Window too short to annualise honestly
    r = await treasury_performance(DB([snap(2, 10.0), snap(0, 11.0)], []), 30)
    check("6 short window -> annualised withheld",
          r["available"] and r["annualised_pct"] is None, r)

    # 7. Zero starting capital -> percentage undefined
    r = await treasury_performance(DB([snap(28,0.0), snap(0, 5.0)], []), 30)
    check("7 zero start -> no_starting_capital",
          r["available"] is False and r["reason"] == "no_starting_capital", r)

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        for f in failures:
            print(" -", f)
        sys.exit(1)
    print("all performance tests passed")


asyncio.run(main())
