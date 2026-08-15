"""
YABBAI Command Centre - Achievements System
Tracks learning and results from background loops, agents, and system milestones.
"""
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid


class Achievement(BaseModel):
    """Achievement record from background loops and system events."""
    id: Optional[str] = None
    timestamp: str
    category: str  # 'revenue', 'agent', 'mission', 'system', 'learning'
    milestone: str  # What was achieved
    learning: str  # What the system learned
    result: Dict[str, Any]  # Quantifiable outcome
    agent_id: Optional[str] = None
    phase: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AchievementTracker:
    """Records and retrieves achievements from background operations."""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.achievements
    
    async def record(
        self,
        category: str,
        milestone: str,
        learning: str,
        result: Dict[str, Any],
        agent_id: Optional[str] = None,
        phase: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Record a new achievement from a background loop.
        
        Args:
            category: Type of achievement (revenue, agent, mission, system, learning)
            milestone: What was achieved (e.g., "First successful revenue cycle")
            learning: What the system learned (e.g., "Product channel ROI: 3.2x")
            result: Quantifiable outcome (e.g., {"revenue_usd": 42.50, "cycles": 10})
            agent_id: ID of agent that achieved this (if applicable)
            phase: Agent phase (if applicable)
            metadata: Additional context
        
        Returns:
            Achievement ID
        """
        achievement_id = str(uuid.uuid4())
        doc = {
            "id": achievement_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "category": category,
            "milestone": milestone,
            "learning": learning,
            "result": result,
            "agent_id": agent_id,
            "phase": phase,
            "metadata": metadata or {}
        }
        
        await self.collection.insert_one(doc)
        return achievement_id
    
    async def get_recent(self, limit: int = 50, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent achievements, optionally filtered by category."""
        query = {"category": category} if category else {}
        cursor = self.collection.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit)
        achievements = await cursor.to_list(limit)
        return achievements
    
    async def get_by_agent(self, agent_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get achievements for a specific agent."""
        cursor = self.collection.find(
            {"agent_id": agent_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(limit)
    
    async def get_summary(self) -> Dict[str, Any]:
        """Get achievement summary statistics."""
        pipeline = [
            {
                "$group": {
                    "_id": "$category",
                    "count": {"$sum": 1},
                    "recent": {"$first": "$$ROOT"}
                }
            }
        ]
        
        cursor = self.collection.aggregate(pipeline)
        results = await cursor.to_list(100)
        
        return {
            "total_achievements": sum(r["count"] for r in results),
            "by_category": {
                r["_id"]: {
                    "count": r["count"],
                    "most_recent": r["recent"]["milestone"] if r.get("recent") else None
                }
                for r in results
            }
        }


# Convenience functions for common achievement types

async def record_agent_milestone(
    tracker: AchievementTracker,
    agent_id: str,
    phase: str,
    milestone: str,
    learning: str,
    result: Dict[str, Any]
):
    """Record an agent reaching a milestone."""
    return await tracker.record(
        category="agent",
        milestone=milestone,
        learning=learning,
        result=result,
        agent_id=agent_id,
        phase=phase
    )


async def record_revenue_achievement(
    tracker: AchievementTracker,
    milestone: str,
    learning: str,
    revenue_usd: float,
    metadata: Optional[Dict[str, Any]] = None
):
    """Record a revenue-related achievement."""
    return await tracker.record(
        category="revenue",
        milestone=milestone,
        learning=learning,
        result={"revenue_usd": revenue_usd},
        metadata=metadata
    )


async def record_learning_insight(
    tracker: AchievementTracker,
    insight: str,
    data: Dict[str, Any],
    source: str
):
    """Record a learning insight from system observation."""
    return await tracker.record(
        category="learning",
        milestone=f"Insight discovered: {source}",
        learning=insight,
        result=data,
        metadata={"source": source}
    )
