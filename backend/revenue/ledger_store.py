#!/usr/bin/env python3
"""
YABBAI — durable storage for the truth ledger.

TruthLedger keeps entries in a Python list. That is fine for a long-lived process
and useless for this deployment: Render's free tier sleeps after roughly fifteen
minutes idle, so every cold start began with an empty ledger. Income recorded by a
payment webhook survived only until the next nap, and real_income() silently reset
to zero. A revenue system that forgets its revenue is not a revenue system.

This persists every metric to MongoDB as it is recorded, and reloads them on
startup, so totals survive restarts. The in-memory list stays as the fast path —
this is durability underneath it, not a replacement.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

COLLECTION = "revenue_metrics"


def metric_to_doc(metric: Any) -> Dict[str, Any]:
    """Flatten a Metric for storage. Uses its own to_dict when available."""
    if hasattr(metric, "to_dict"):
        doc = dict(metric.to_dict())
    else:
        doc = {
            "name": getattr(metric, "name", None),
            "value": getattr(metric, "value", None),
            "source": getattr(metric, "source", None),
            "notes": getattr(metric, "notes", None),
        }
    src = getattr(metric, "source_type", None)
    doc["source_type"] = getattr(src, "value", src)
    doc["signed_by"] = getattr(metric, "signed_by", None)
    return doc


async def ensure_indexes(db) -> None:
    """Unique index on source so a replayed webhook cannot double-count."""
    try:
        await db[COLLECTION].create_index("source", unique=True, sparse=True)
        await db[COLLECTION].create_index("recorded_at")
    except Exception as e:
        logger.warning(f"revenue_metrics index setup failed: {e}")


async def persist(db, metric: Any) -> bool:
    """Store one metric. Returns False when it was already stored.

    The unique index on `source` is the idempotency guard: payment processors
    retry webhooks, and booking the same sale twice would inflate real income.
    """
    doc = metric_to_doc(metric)
    if not doc.get("source"):
        logger.warning("refusing to persist a metric with no source")
        return False
    try:
        await db[COLLECTION].insert_one(doc)
        return True
    except Exception as e:
        if "duplicate key" in str(e).lower():
            logger.info(f"metric {doc['source']} already recorded; ignoring replay")
            return False
        logger.error(f"failed to persist metric {doc.get('source')}: {e}")
        return False


async def load_all(db, limit: int = 5000) -> List[Dict[str, Any]]:
    """Every stored metric, oldest first."""
    try:
        return await db[COLLECTION].find({}, {"_id": 0}).sort("recorded_at", 1).to_list(limit)
    except Exception as e:
        logger.error(f"failed to load revenue metrics: {e}")
        return []


async def totals(db) -> Dict[str, Any]:
    """Income and expense computed in the database rather than from memory.

    Only PAYMENT_PROCESSOR entries count as real money. That mirrors the rule in
    metric.py: a projection or an estimate is not income, however it was produced.
    """
    try:
        pipeline = [
            {"$match": {"source_type": "payment_processor"}},
            {"$group": {"_id": "$name", "total": {"$sum": "$value"}, "count": {"$sum": 1}}},
        ]
        rows = await db[COLLECTION].aggregate(pipeline).to_list(20)
        by_name = {r["_id"]: r for r in rows}
        income = by_name.get("income", {}).get("total", 0.0) or 0.0
        expense = by_name.get("expense", {}).get("total", 0.0) or 0.0
        return {
            "real_income": round(income, 2),
            "real_expense": round(expense, 2),
            "net_profit": round(income - expense, 2),
            "income_events": by_name.get("income", {}).get("count", 0),
            "expense_events": by_name.get("expense", {}).get("count", 0),
            "source": "mongodb:revenue_metrics",
        }
    except Exception as e:
        logger.error(f"failed to total revenue metrics: {e}")
        return {
            "real_income": None,
            "real_expense": None,
            "net_profit": None,
            "error": str(e),
        }
