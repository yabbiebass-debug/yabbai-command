"""The bug: converting SOL into the token read as a 36% loss.

Reproduces the exact scenario from the dashboard - treasury goes 2.747 SOL to
1.744 SOL because the operator bought 2.46M tokens with the difference - and
checks the fix reports roughly flat instead of a collapse.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
)
from performance import treasury_performance  # noqa: E402

NOW = datetime.now(timezone.utc)


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


def snap(days_ago, sol, token_value_sol=None):
    d = {"ts": (NOW - timedelta(days=days_ago)).isoformat(), "balance_sol": sol}
    if token_value_sol is not None:
        d["token_value_sol"] = token_value_sol
    return d


failures = []


def check(name, cond, detail=""):
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    if not cond:
        failures.append(f"{name} {detail}")


async def main():
    # The real scenario: 2.747 SOL, then 1.744 SOL plus ~1.0 SOL worth of token.
    db = DB([snap(1, 2.747, 0.0), snap(0, 1.744, 1.003)], [])
    r = await treasury_performance(db, 30)
    print(f"  reported: {r.get('period_return_pct')}%  basis={r.get('basis')}")
    check("swapping SOL for tokens is not a loss",
          r["available"] and abs(r["period_return_pct"]) < 1.0, r)

    # A genuine loss must still register: value falls with no offsetting token.
    db = DB([snap(1, 2.747, 0.0), snap(0, 1.744, 0.0)], [])
    r = await treasury_performance(db, 30)
    print(f"  reported: {r.get('period_return_pct')}%")
    check("a real decline still reports a loss",
          r["available"] and r["period_return_pct"] < -30, r)

    # Genuine gain: token holding appreciates.
    db = DB([snap(1, 1.0, 1.0), snap(0, 1.0, 1.5)], [])
    r = await treasury_performance(db, 30)
    print(f"  reported: {r.get('period_return_pct')}%")
    check("token appreciation reports a gain",
          r["available"] and 20 < r["period_return_pct"] < 30, r)

    # A deposit is still not a gain.
    db = DB([snap(1, 1.0, 0.0), snap(0, 3.0, 0.0)],
            [{"ts": (NOW - timedelta(hours=12)).isoformat(),
              "type": "deposit", "amount_sol": 2.0, "status": "confirmed"}])
    r = await treasury_performance(db, 30)
    print(f"  reported: {r.get('period_return_pct')}%")
    check("deposit still not counted as gain",
          r["available"] and abs(r["period_return_pct"]) < 0.01, r)

    # Old snapshots without token data must not manufacture a loss.
    db = DB([snap(1, 2.0), snap(0, 2.0)], [])
    r = await treasury_performance(db, 30)
    check("snapshots lacking token data are flagged",
          r.get("snapshots_without_token_data") == 2, r.get("snapshots_without_token_data"))

    print()
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("all treasury valuation tests passed")


asyncio.run(main())
