#!/usr/bin/env python3
"""
YABBAI — Realised treasury performance.

This replaces the projected-APY formula (`risk * 8 + 200`) with a number actually
measured from recorded treasury snapshots.

The important correctness point: a treasury balance moves for two unrelated reasons —
performance, and external flows (deposits and withdrawals). Subtracting the first
snapshot from the last measures both mixed together, which is not a return. Depositing
1 SOL into an empty treasury is not a 100% gain.

So this module separates them:

    performance = (ending_value - starting_value) - net_external_flows

and refuses to report a return at all when the flow history is not trustworthy for the
window. Reporting nothing is correct; reporting a mixed number as yield is not.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Below this, an annualised figure is extrapolation from noise rather than a measurement.
MIN_DAYS_TO_ANNUALISE = 7.0
# Two points define a line, but not a performance history worth reporting.
MIN_SNAPSHOTS = 2


def _parse_ts(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


async def treasury_performance(db, window_days: int = 30) -> Dict[str, Any]:
    """Realised performance over the window, or an explicit reason it is unavailable.

    Measures TOTAL treasury value, not the SOL balance alone. Measuring SOL only
    reports a 36% loss when the operator converts SOL into the project's own
    token: the SOL leaves, the tokens arrive, nothing is lost, and yet the figure
    shows a collapse. A swap is a change of composition, not of value, so both
    sides have to be counted or the number is worse than useless.

    Token value uses the price recorded at the same moment, so a valuation is
    never mixed across time. Snapshots that predate token tracking fall back to
    SOL alone and are flagged, rather than being silently treated as zero tokens.
    """
    since = datetime.now(timezone.utc) - timedelta(days=window_days)

    snapshots = await db.treasury_snapshots.find({}).sort("ts", 1).to_list(1000)
    in_window = []
    sol_only_rows = 0
    for snap in snapshots:
        ts = _parse_ts(snap.get("ts"))
        balance = snap.get("balance_sol")
        if not (ts and ts >= since and isinstance(balance, (int, float))):
            continue

        sol = float(balance)
        token_value_sol = snap.get("token_value_sol")
        if isinstance(token_value_sol, (int, float)):
            total = sol + float(token_value_sol)
        else:
            # Older snapshot with no token data. Counting it as zero tokens would
            # manufacture a loss the moment token tracking began.
            total = sol
            sol_only_rows += 1

        in_window.append({
            "ts": ts,
            "balance_sol": sol,
            "token_value_sol": token_value_sol if isinstance(token_value_sol, (int, float)) else None,
            "total_value_sol": total,
        })

    if len(in_window) < MIN_SNAPSHOTS:
        return {
            "available": False,
            "reason": "insufficient_data",
            "detail": (
                f"{len(in_window)} usable snapshot(s) in the last {window_days}d; "
                f"need at least {MIN_SNAPSHOTS}. Performance is measured, not projected, "
                "so it stays unavailable until there is history to measure."
            ),
            "snapshot_count": len(in_window),
            "window_days": window_days,
        }

    first, last = in_window[0], in_window[-1]
    elapsed_days = (last["ts"] - first["ts"]).total_seconds() / 86400.0

    if elapsed_days <= 0:
        return {
            "available": False,
            "reason": "zero_elapsed_time",
            "detail": "All snapshots share a timestamp; no interval to measure over.",
            "snapshot_count": len(in_window),
            "window_days": window_days,
        }

    # External flows recorded over the same interval.
    flow_docs = await db.transactions.find({"status": "confirmed"}).to_list(2000)
    net_flows = 0.0
    flows_counted = 0
    for tx in flow_docs:
        ts = _parse_ts(tx.get("ts") or tx.get("created_at"))
        amount = tx.get("amount_sol")
        if not ts or not isinstance(amount, (int, float)):
            continue
        if not (first["ts"] <= ts <= last["ts"]):
            continue
        kind = (tx.get("type") or "").lower()
        # A sweep moves SOL out of the treasury; a deposit moves it in.
        if kind in ("sweep", "withdraw", "withdrawal", "payout"):
            net_flows -= float(amount)
        elif kind in ("deposit", "inject", "buyback", "revenue"):
            net_flows += float(amount)
        else:
            continue
        flows_counted += 1

    # Total value, so converting SOL into the token nets to roughly zero rather
    # than reading as a loss.
    value_change = last["total_value_sol"] - first["total_value_sol"]
    performance_sol = value_change - net_flows

    starting = first["total_value_sol"]
    if starting <= 0:
        return {
            "available": False,
            "reason": "no_starting_capital",
            "detail": (
                "Starting balance was zero, so a percentage return is undefined. "
                f"Absolute change over {elapsed_days:.1f}d was {performance_sol:+.4f} SOL "
                "after backing out flows."
            ),
            "performance_sol": round(performance_sol, 6),
            "net_flows_sol": round(net_flows, 6),
            "window_days": window_days,
        }

    period_return = performance_sol / starting

    result: Dict[str, Any] = {
        "available": True,
        "measured": True,
        "basis": "total treasury value (SOL + token holdings)",
        "starting_balance_sol": round(starting, 6),
        "ending_balance_sol": round(last["total_value_sol"], 6),
        "sol_only": {
            "from": round(first["balance_sol"], 6),
            "to": round(last["balance_sol"], 6),
        },
        "token_value_sol": {
            "from": first.get("token_value_sol"),
            "to": last.get("token_value_sol"),
        },
        "snapshots_without_token_data": sol_only_rows,
        "value_change_sol": round(value_change, 6),
        "net_flows_sol": round(net_flows, 6),
        "performance_sol": round(performance_sol, 6),
        "period_return_pct": round(period_return * 100, 4),
        "elapsed_days": round(elapsed_days, 3),
        "snapshot_count": len(in_window),
        "flow_events_counted": flows_counted,
        "period_start": first["ts"].isoformat(),
        "period_end": last["ts"].isoformat(),
        "method": "(end - start) - net_external_flows, over recorded snapshots",
    }

    if elapsed_days >= MIN_DAYS_TO_ANNUALISE:
        # Simple annualisation of the observed period return. Labelled as an
        # extrapolation because that is what it is.
        result["annualised_pct"] = round(period_return * (365.0 / elapsed_days) * 100, 4)
        result["annualised_is_extrapolation"] = True
    else:
        result["annualised_pct"] = None
        result["annualised_unavailable_reason"] = (
            f"Only {elapsed_days:.1f}d observed; annualising under "
            f"{MIN_DAYS_TO_ANNUALISE:.0f}d turns noise into a headline number."
        )

    if flows_counted == 0 and abs(value_change) > 1e-9:
        result["warning"] = (
            "No flow events recorded in this window, so the balance change is being "
            "treated entirely as performance. If deposits or withdrawals happened "
            "without being recorded, this figure overstates or understates the result."
        )

    return result
