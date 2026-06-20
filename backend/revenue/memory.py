"""
YABBAI Revenue System — Memory Layer

Persistent storage for learnings, actions, and metrics in MongoDB.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


@dataclass
class Learning:
    """A lesson from an outcome (win/loss/observation)."""
    kind: str  # "win" | "loss" | "observation"
    channel: str
    agent: str
    summary: str
    usd_impact: float = 0.0
    context: Dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "channel": self.channel,
            "agent": self.agent,
            "summary": self.summary,
            "usd_impact": round(self.usd_impact, 2),
            "context": self.context,
            "ts": self.ts,
        }


class Memory:
    """MongoDB-backed memory for the revenue system."""

    def __init__(self, db):
        self.db = db
        self._cache: Dict[str, List[Dict[str, Any]]] = {}

    def add(self, collection: str, record: Dict[str, Any]) -> None:
        """Add a record to a collection."""
        record["ts"] = record.get("ts") or datetime.now(timezone.utc).isoformat()
        self.db[f"revenue_{collection}"].insert_one(record)
        if collection in self._cache:
            self._cache[collection].append(record)

    def find(self, collection: str, predicate: Callable[[Dict], bool]) -> List[Dict[str, Any]]:
        """Find records matching a predicate."""
        results = list(self.db[f"revenue_{collection}"].find())
        return [r for r in results if predicate(r)]

    def add_learning(self, learning: Learning) -> None:
        """Record a learning."""
        self.add("learnings", learning.to_dict())

    def recent_learnings(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent learnings."""
        results = list(
            self.db["revenue_learnings"]
            .find()
            .sort("ts", -1)
            .limit(limit)
        )
        for r in results:
            r.pop("_id", None)
        return results

    def channel_score(self, channel: str) -> Dict[str, Any]:
        """Calculate win/loss score for a channel."""
        learnings = list(self.db["revenue_learnings"].find({"channel": channel}))
        wins = [l for l in learnings if l.get("kind") == "win"]
        losses = [l for l in learnings if l.get("kind") == "loss"]
        return {
            "channel": channel,
            "wins": len(wins),
            "losses": len(losses),
            "net_usd": sum(l.get("usd_impact", 0) for l in learnings),
            "win_rate": len(wins) / max(1, len(wins) + len(losses)),
        }
