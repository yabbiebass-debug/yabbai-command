"""
YABBAI Revenue System - Live Tracking

Real-time data updates, background orchestrator, and live metrics tracking.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Set
import logging

logger = logging.getLogger(__name__)


class LiveTracker:
    """Tracks and persists all revenue operations in real-time."""

    def __init__(self, db, revenue_system):
        self.db = db
        self.revenue_system = revenue_system
        self.running = False
        self.subscribers: Set[Any] = set()
        self.last_update = datetime.now(timezone.utc)
        self.cycle_interval = 60  # seconds
        self.metrics_history: List[Dict[str, Any]] = []

    async def start_background_orchestrator(self):
        """Start the background orchestrator cycle."""
        self.running = True
        logger.info("🚀 Starting live revenue orchestrator...")

        while self.running:
            try:
                # Run one orchestrator cycle
                cycle_result = self.revenue_system.run_cycle()

                # Persist cycle results
                await self.persist_cycle(cycle_result)

                # Notify subscribers
                await self.broadcast_update({
                    "type": "cycle_complete",
                    "data": cycle_result,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

                logger.info(
                    f"✅ Cycle {cycle_result['cycle']}: "
                    f"{cycle_result['metrics_observed']} metrics, "
                    f"{cycle_result['actions_proposed']} actions"
                )

            except Exception as e:
                logger.error(f"❌ Orchestrator cycle error: {e}")

            # Wait for next cycle
            await asyncio.sleep(self.cycle_interval)

    async def stop_background_orchestrator(self):
        """Stop the background orchestrator."""
        self.running = False
        logger.info("⏸️  Stopping live revenue orchestrator...")

    async def persist_cycle(self, cycle_result: Dict[str, Any]):
        """Persist cycle results to MongoDB."""
        try:
            # Store cycle snapshot
            await self.db.revenue_cycles.insert_one({
                "cycle": cycle_result["cycle"],
                "timestamp": datetime.now(timezone.utc),
                "metrics_observed": cycle_result["metrics_observed"],
                "actions_proposed": cycle_result["actions_proposed"],
                "actions_routed": cycle_result["actions_routed"],
                "ledger_summary": cycle_result["ledger_summary"],
                "gate_status": cycle_result["gate_status"],
            })

            # Update latest snapshot
            await self.db.revenue_latest.update_one(
                {"_id": "latest"},
                {
                    "$set": {
                        "cycle": cycle_result["cycle"],
                        "timestamp": datetime.now(timezone.utc),
                        "data": cycle_result,
                    }
                },
                upsert=True,
            )

        except Exception as e:
            logger.error(f"Failed to persist cycle: {e}")

    async def track_metric(self, metric: Dict[str, Any]):
        """Track a new metric in real-time."""
        try:
            # Add to history
            metric_record = {
                **metric,
                "tracked_at": datetime.now(timezone.utc),
            }

            await self.db.revenue_metrics_live.insert_one(metric_record)
            self.metrics_history.append(metric_record)

            # Keep only last 1000 in memory
            if len(self.metrics_history) > 1000:
                self.metrics_history = self.metrics_history[-1000:]

            # Broadcast to subscribers
            await self.broadcast_update({
                "type": "new_metric",
                "data": metric,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        except Exception as e:
            logger.error(f"Failed to track metric: {e}")

    async def track_action(self, action: Dict[str, Any], result: Dict[str, Any]):
        """Track an action and its result in real-time."""
        try:
            action_record = {
                "action": action,
                "result": result,
                "timestamp": datetime.now(timezone.utc),
            }

            await self.db.revenue_actions_live.insert_one(action_record)

            # Broadcast to subscribers
            await self.broadcast_update({
                "type": "action_processed",
                "data": action_record,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

        except Exception as e:
            logger.error(f"Failed to track action: {e}")

    async def track_income(self, source: str, amount: float, data: Dict[str, Any]):
        """Track real income in real-time."""
        try:
            income_record = {
                "source": source,
                "amount": amount,
                "data": data,
                "timestamp": datetime.now(timezone.utc),
            }

            await self.db.revenue_income_live.insert_one(income_record)

            # Broadcast to subscribers
            await self.broadcast_update({
                "type": "income_received",
                "data": income_record,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

            logger.info(f"💰 Income tracked: ${amount:.2f} from {source}")

        except Exception as e:
            logger.error(f"Failed to track income: {e}")

    async def get_live_status(self) -> Dict[str, Any]:
        """Get current live status."""
        try:
            latest = await self.db.revenue_latest.find_one({"_id": "latest"})

            return {
                "running": self.running,
                "last_cycle": latest.get("cycle") if latest else 0,
                "last_update": latest.get("timestamp").isoformat() if latest else None,
                "real_income": self.revenue_system.ledger.real_income(),
                "net_profit": self.revenue_system.ledger.net_profit(),
                "gates": self.revenue_system.gates.status(),
                "subscribers": len(self.subscribers),
                "metrics_tracked": len(self.metrics_history),
            }

        except Exception as e:
            logger.error(f"Failed to get live status: {e}")
            return {"error": str(e)}

    async def get_live_metrics(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent live metrics."""
        try:
            cursor = (
                self.db.revenue_metrics_live.find()
                .sort("tracked_at", -1)
                .limit(limit)
            )
            metrics = []
            async for doc in cursor:
                doc.pop("_id", None)
                if "tracked_at" in doc:
                    doc["tracked_at"] = doc["tracked_at"].isoformat()
                metrics.append(doc)
            return metrics

        except Exception as e:
            logger.error(f"Failed to get live metrics: {e}")
            return []

    async def get_live_income_stream(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get live income stream."""
        try:
            cursor = (
                self.db.revenue_income_live.find()
                .sort("timestamp", -1)
                .limit(limit)
            )
            income = []
            async for doc in cursor:
                doc.pop("_id", None)
                if "timestamp" in doc:
                    doc["timestamp"] = doc["timestamp"].isoformat()
                income.append(doc)
            return income

        except Exception as e:
            logger.error(f"Failed to get live income stream: {e}")
            return []

    # WebSocket support
    def subscribe(self, websocket):
        """Subscribe to live updates."""
        self.subscribers.add(websocket)
        logger.info(f"📡 New subscriber. Total: {len(self.subscribers)}")

    def unsubscribe(self, websocket):
        """Unsubscribe from live updates."""
        self.subscribers.discard(websocket)
        logger.info(f"📡 Subscriber left. Total: {len(self.subscribers)}")

    async def broadcast_update(self, message: Dict[str, Any]):
        """Broadcast update to all subscribers."""
        if not self.subscribers:
            return

        disconnected = set()
        for websocket in self.subscribers:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send to subscriber: {e}")
                disconnected.add(websocket)

        # Clean up disconnected
        for ws in disconnected:
            self.unsubscribe(ws)

    async def get_live_dashboard(self) -> Dict[str, Any]:
        """Get complete live dashboard data."""
        return {
            "status": await self.get_live_status(),
            "dashboard": await self.revenue_system.get_dashboard_data(),
            "live_metrics": await self.get_live_metrics(20),
            "live_income": await self.get_live_income_stream(20),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
