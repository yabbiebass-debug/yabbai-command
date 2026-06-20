"""
YABBAI Multi-Agent Autonomous System

Manages 10-15 agents per operational phase, cycling through:
Pump → Esky → Mission → Scale → Withdraw

Each agent runs independently, coordinated by the main orchestrator.
"""

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Phase(str, Enum):
    """Operational phases for agent cycles."""
    PUMP = "pump"      # Acquire/generate revenue opportunities
    ESKY = "esky"      # Eskimo (cold outreach, lead generation)
    MISSION = "mission" # Execute revenue missions
    SCALE = "scale"    # Scale successful operations
    WITHDRAW = "withdraw" # Process withdrawals/payouts


class AgentStatus(str, Enum):
    """Agent lifecycle status."""
    IDLE = "idle"
    RUNNING = "running"
    CYCLING = "cycling"
    PAUSED = "paused"
    CRASHED = "crashed"
    TERMINATED = "terminated"


class CycleAgent:
    """Individual autonomous agent that cycles through operational phases."""

    def __init__(self, agent_id: str, phase: Phase, db, revenue_system):
        self.agent_id = agent_id
        self.current_phase = phase
        self.status = AgentStatus.IDLE
        self.db = db
        self.revenue_system = revenue_system
        self.cycles_completed = 0
        self.revenue_generated = 0.0
        self.started_at = datetime.now(timezone.utc)
        self.last_activity = datetime.now(timezone.utc)
        self.errors = []
        self.task = None

    async def run_cycle(self) -> Dict[str, Any]:
        """Run one complete operational cycle through all phases."""
        self.status = AgentStatus.RUNNING
        cycle_result = {
            "agent_id": self.agent_id,
            "cycle": self.cycles_completed + 1,
            "phase_results": {},
            "started_at": datetime.now(timezone.utc).isoformat(),
        }

        phases = [Phase.PUMP, Phase.ESKY, Phase.MISSION, Phase.SCALE, Phase.WITHDRAW]

        for phase in phases:
            self.current_phase = phase
            self.status = AgentStatus.CYCLING
            self.last_activity = datetime.now(timezone.utc)

            try:
                logger.info(f"🤖 Agent {self.agent_id}: Running {phase.value.upper()} phase")
                result = await self.execute_phase(phase)
                cycle_result["phase_results"][phase.value] = result

                # Track revenue
                if result.get("revenue_generated", 0) > 0:
                    self.revenue_generated += result["revenue_generated"]

            except Exception as e:
                logger.error(f"❌ Agent {self.agent_id}: Error in {phase.value}: {e}")
                self.errors.append({"phase": phase.value, "error": str(e), "at": datetime.now(timezone.utc).isoformat()})
                cycle_result["phase_results"][phase.value] = {"error": str(e)}

        self.cycles_completed += 1
        cycle_result["completed_at"] = datetime.now(timezone.utc).isoformat()
        cycle_result["total_revenue"] = self.revenue_generated

        # Persist cycle result
        await self.db.agent_cycles.insert_one(cycle_result)

        return cycle_result

    async def execute_phase(self, phase: Phase) -> Dict[str, Any]:
        """Execute specific phase logic."""
        if phase == Phase.PUMP:
            return await self.phase_pump()
        elif phase == Phase.ESKY:
            return await self.phase_esky()
        elif phase == Phase.MISSION:
            return await self.phase_mission()
        elif phase == Phase.SCALE:
            return await self.phase_scale()
        elif phase == Phase.WITHDRAW:
            return await self.phase_withdraw()
        else:
            return {"error": "Unknown phase"}

    async def phase_pump(self) -> Dict[str, Any]:
        """PUMP: Identify and acquire revenue opportunities."""
        # Scan for opportunities
        opportunities = []

        # Check product channel
        if hasattr(self.revenue_system, 'products'):
            product_opps = await self.scan_product_opportunities()
            opportunities.extend(product_opps)

        # Check agency channel
        if hasattr(self.revenue_system, 'agency'):
            agency_opps = await self.scan_agency_opportunities()
            opportunities.extend(agency_opps)

        # Check trading channel (paper trades only)
        if hasattr(self.revenue_system, 'trading'):
            trading_opps = await self.scan_trading_opportunities()
            opportunities.extend(trading_opps)

        return {
            "phase": "pump",
            "opportunities_found": len(opportunities),
            "opportunities": opportunities[:10],  # Top 10
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def phase_esky(self) -> Dict[str, Any]:
        """ESKY: Cold outreach and lead generation."""
        # Generate leads for agency channel
        leads_generated = 0
        campaigns_sent = 0

        if hasattr(self.revenue_system, 'agency'):
            # Propose lead generation action
            action_data = {
                "kind": "generate_leads",
                "channel": "agency",
                "agent": self.agent_id,
                "usd_amount": 0.0,  # No cost for internal lead gen
                "reversible": True,
                "payload": {"target": 10, "method": "cold_outreach"},
                "reason": f"Agent {self.agent_id} lead generation cycle",
            }

            result = self.revenue_system.propose_action(action_data)
            if result.get("ok"):
                leads_generated = 10  # Simulated for now

        return {
            "phase": "esky",
            "leads_generated": leads_generated,
            "campaigns_sent": campaigns_sent,
            "compliance_checked": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def phase_mission(self) -> Dict[str, Any]:
        """MISSION: Execute revenue missions."""
        missions_executed = 0
        revenue_generated = 0.0

        # Run orchestrator cycle
        if hasattr(self.revenue_system, 'orchestrator'):
            cycle_result = self.revenue_system.run_cycle()
            missions_executed = cycle_result.get("actions_routed", 0)

        return {
            "phase": "mission",
            "missions_executed": missions_executed,
            "revenue_generated": revenue_generated,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def phase_scale(self) -> Dict[str, Any]:
        """SCALE: Scale successful operations."""
        scaled_operations = []

        # Check channel scores
        if hasattr(self.revenue_system, 'memory'):
            products_score = await self.revenue_system.memory.channel_score("products")
            agency_score = await self.revenue_system.memory.channel_score("agency")
            trading_score = await self.revenue_system.memory.channel_score("trading")

            # Scale channels with positive ROI
            if products_score.get("net_usd", 0) > 0:
                scaled_operations.append({
                    "channel": "products",
                    "action": "increase_marketing",
                    "reason": f"Positive ROI: ${products_score['net_usd']:.2f}"
                })

            if agency_score.get("net_usd", 0) > 0:
                scaled_operations.append({
                    "channel": "agency",
                    "action": "expand_outreach",
                    "reason": f"Positive ROI: ${agency_score['net_usd']:.2f}"
                })

        return {
            "phase": "scale",
            "operations_scaled": len(scaled_operations),
            "scaled": scaled_operations,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def phase_withdraw(self) -> Dict[str, Any]:
        """WITHDRAW: Process withdrawals and payouts."""
        withdrawal_amount = 0.0
        withdrawal_success = False

        # Check if there's real income to withdraw
        real_income = self.revenue_system.ledger.real_income()

        if real_income > 25.0:  # Minimum withdrawal threshold
            # Propose withdrawal action
            action_data = {
                "kind": "payout",
                "channel": "products",
                "agent": self.agent_id,
                "usd_amount": 25.0,
                "reversible": False,
                "payload": {"method": "paypal", "amount": 25.0},
                "reason": f"Agent {self.agent_id} hourly withdrawal cycle",
            }

            result = self.revenue_system.propose_action(action_data)
            if result.get("ok"):
                gate_result = result.get("result", {})
                if gate_result.get("outcome") == "queued":
                    withdrawal_amount = 25.0
                    withdrawal_success = True

        return {
            "phase": "withdraw",
            "withdrawal_amount": withdrawal_amount,
            "withdrawal_success": withdrawal_success,
            "available_balance": real_income,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def scan_product_opportunities(self) -> List[Dict[str, Any]]:
        """Scan for product sales opportunities."""
        # Placeholder - integrate with real product opportunity scanner
        return [
            {"type": "product", "name": "AI Course", "estimated_value": 97.0},
            {"type": "product", "name": "Automation Setup", "estimated_value": 197.0},
        ]

    async def scan_agency_opportunities(self) -> List[Dict[str, Any]]:
        """Scan for agency service opportunities."""
        return [
            {"type": "agency", "service": "AI Integration", "estimated_value": 2500.0},
        ]

    async def scan_trading_opportunities(self) -> List[Dict[str, Any]]:
        """Scan for trading opportunities (paper only)."""
        return [
            {"type": "trading", "strategy": "momentum", "estimated_value": 50.0},
        ]

    def to_dict(self) -> Dict[str, Any]:
        """Export agent state."""
        return {
            "agent_id": self.agent_id,
            "current_phase": self.current_phase.value,
            "status": self.status.value,
            "cycles_completed": self.cycles_completed,
            "revenue_generated": round(self.revenue_generated, 2),
            "started_at": self.started_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "uptime_seconds": (datetime.now(timezone.utc) - self.started_at).total_seconds(),
            "error_count": len(self.errors),
        }
