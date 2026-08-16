"""
YABBAI Agent Pool Manager

Manages 10-15 concurrent agents per phase, ensuring at least 1 agent
per phase is always running with automatic respawn on failures.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
import logging

from .cycle_agent import CycleAgent, Phase, AgentStatus

logger = logging.getLogger(__name__)


class AgentPool:
    """Manages a pool of autonomous agents across all phases."""

    def __init__(
        self,
        db,
        revenue_system,
        min_agents_per_phase: int = 1,
        max_agents_per_phase: int = 15,
        target_agents_per_phase: int = 10,
    ):
        self.db = db
        self.revenue_system = revenue_system
        self.min_agents_per_phase = min_agents_per_phase
        self.max_agents_per_phase = max_agents_per_phase
        self.target_agents_per_phase = target_agents_per_phase

        self.agents: Dict[str, CycleAgent] = {}
        self.phase_agents: Dict[Phase, Set[str]] = {
            Phase.PUMP: set(),
            Phase.ESKY: set(),
            Phase.MISSION: set(),
            Phase.SCALE: set(),
            Phase.WITHDRAW: set(),
        }

        self.running = False
        self.health_check_interval = 30  # seconds
        self.withdraw_interval = 3600  # 1 hour
        self.last_withdraw = datetime.now(timezone.utc)

    async def start(self):
        """Start the agent pool."""
        self.running = True
        logger.info("🚀 Starting Agent Pool...")

        # Spawn initial agents
        await self.spawn_initial_agents()

        # Start background tasks
        asyncio.create_task(self.health_monitor())
        asyncio.create_task(self.withdraw_coordinator())
        asyncio.create_task(self.agent_supervisor())

        logger.info(f"✅ Agent Pool started with {len(self.agents)} agents")

    async def stop(self):
        """Stop the agent pool gracefully."""
        self.running = False
        logger.info("⏸️  Stopping Agent Pool...")

        # Terminate all agents
        for agent_id in list(self.agents.keys()):
            await self.terminate_agent(agent_id)

        logger.info("✅ Agent Pool stopped")

    async def spawn_initial_agents(self):
        """Spawn initial agent distribution across phases."""
        for phase in Phase:
            for i in range(self.target_agents_per_phase):
                await self.spawn_agent(phase)

    async def spawn_agent(self, phase: Phase) -> Optional[str]:
        """Spawn a new agent for a specific phase."""
        # Check max limit
        if len(self.phase_agents[phase]) >= self.max_agents_per_phase:
            logger.warning(f"Max agents reached for {phase.value}")
            return None

        agent_id = f"agent_{phase.value}_{uuid.uuid4().hex[:8]}"
        agent = CycleAgent(agent_id, phase, self.db, self.revenue_system)

        self.agents[agent_id] = agent
        self.phase_agents[phase].add(agent_id)

        # Start agent cycle
        agent.task = asyncio.create_task(self.run_agent_loop(agent))

        logger.info(f"🤖 Spawned {agent_id} for {phase.value} phase")

        # Persist spawn event
        await self.db.agent_events.insert_one({
            "event": "agent_spawned",
            "agent_id": agent_id,
            "phase": phase.value,
            "timestamp": datetime.now(timezone.utc),
        })

        return agent_id

    async def run_agent_loop(self, agent: CycleAgent):
        """Run continuous agent cycle loop."""
        while self.running and agent.status != AgentStatus.TERMINATED:
            try:
                # Run one complete cycle
                result = await agent.run_cycle()

                logger.info(
                    f"✅ {agent.agent_id}: Cycle {agent.cycles_completed} complete. "
                    f"Revenue: ${agent.revenue_generated:.2f}"
                )

                # Brief pause between cycles
                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"❌ {agent.agent_id}: Crash in cycle: {e}")
                agent.status = AgentStatus.CRASHED
                agent.errors.append({
                    "error": str(e),
                    "at": datetime.now(timezone.utc).isoformat()
                })

                # Respawn if needed
                self.phase_agents[agent.home_phase].discard(agent.agent_id)
                self.agents.pop(agent.agent_id, None)

                if len(self.phase_agents[agent.home_phase]) < self.min_agents_per_phase:
                    logger.warning(f"⚠️  Phase {agent.home_phase.value} below minimum, respawning...")
                    await self.spawn_agent(agent.home_phase)

                break

    async def terminate_agent(self, agent_id: str):
        """Terminate a specific agent."""
        if agent_id not in self.agents:
            return

        agent = self.agents[agent_id]
        agent.status = AgentStatus.TERMINATED

        if agent.task and not agent.task.done():
            agent.task.cancel()

        # Remove from tracking
        self.phase_agents[agent.home_phase].discard(agent_id)
        del self.agents[agent_id]

        logger.info(f"🔴 Terminated {agent_id}")

        await self.db.agent_events.insert_one({
            "event": "agent_terminated",
            "agent_id": agent_id,
            "cycles_completed": agent.cycles_completed,
            "revenue_generated": agent.revenue_generated,
            "timestamp": datetime.now(timezone.utc),
        })

    async def health_monitor(self):
        """Monitor agent health and respawn if needed."""
        while self.running:
            try:
                for phase in Phase:
                    active_count = len([
                        aid for aid in self.phase_agents[phase]
                        if self.agents.get(aid) and self.agents[aid].status in [AgentStatus.RUNNING, AgentStatus.CYCLING]
                    ])

                    # Ensure minimum agents
                    if active_count < self.min_agents_per_phase:
                        needed = self.min_agents_per_phase - active_count
                        logger.warning(f"⚠️  {phase.value}: Only {active_count} active. Spawning {needed}...")
                        for _ in range(needed):
                            await self.spawn_agent(phase)

                    # Scale up to target if below
                    elif active_count < self.target_agents_per_phase:
                        needed = self.target_agents_per_phase - active_count
                        for _ in range(min(needed, 2)):  # Spawn 2 at a time
                            await self.spawn_agent(phase)

            except Exception as e:
                logger.error(f"Health monitor error: {e}")

            await asyncio.sleep(self.health_check_interval)

    async def withdraw_coordinator(self):
        """Coordinate withdrawal agents hourly."""
        while self.running:
            try:
                now = datetime.now(timezone.utc)
                elapsed = (now - self.last_withdraw).total_seconds()

                if elapsed >= self.withdraw_interval:
                    logger.info("💰 Triggering hourly withdrawal cycle...")

                    # Ensure at least 1 withdraw agent is active
                    withdraw_agents = self.phase_agents[Phase.WITHDRAW]
                    if len(withdraw_agents) == 0:
                        await self.spawn_agent(Phase.WITHDRAW)

                    self.last_withdraw = now

            except Exception as e:
                logger.error(f"Withdraw coordinator error: {e}")

            await asyncio.sleep(60)  # Check every minute

    async def agent_supervisor(self):
        """Supervise all agents and log status."""
        while self.running:
            try:
                now = datetime.now(timezone.utc)
                # Collect stats
                total_agents = len(self.agents)
                total_cycles = sum(a.cycles_completed for a in self.agents.values())
                total_revenue = sum(a.revenue_generated for a in self.agents.values())

                phase_stats = {}
                for phase in Phase:
                    phase_agents = [self.agents[aid] for aid in self.phase_agents[phase] if aid in self.agents]
                    phase_stats[phase.value] = {
                        "active": len(phase_agents),
                        "cycles": sum(a.cycles_completed for a in phase_agents),
                        "revenue": sum(a.revenue_generated for a in phase_agents),
                    }

                logger.info(
                    f"📊 Agent Pool Status: {total_agents} agents, "
                    f"{total_cycles} cycles, ${total_revenue:.2f} revenue"
                )

                # Persist status
                await self.db.agent_pool_status.update_one(
                    {"_id": "current"},
                    {
                        "$set": {
                            "total_agents": total_agents,
                            "total_cycles": total_cycles,
                            "total_revenue": round(total_revenue, 2),
                            "phase_stats": phase_stats,
                            "timestamp": now,
                        }
                    },
                    upsert=True,
                )

            except Exception as e:
                logger.error(f"Agent supervisor error: {e}")

            await asyncio.sleep(60)  # Log every minute

    def get_status(self) -> Dict:
        """Get current pool status."""
        phase_breakdown = {}
        for phase in Phase:
            agents_in_phase = [self.agents[aid] for aid in self.phase_agents[phase] if aid in self.agents]
            phase_breakdown[phase.value] = {
                "active_agents": len(agents_in_phase),
                "total_cycles": sum(a.cycles_completed for a in agents_in_phase),
                "total_revenue": round(sum(a.revenue_generated for a in agents_in_phase), 2),
                "agents": [a.to_dict() for a in agents_in_phase],
            }

        return {
            "running": self.running,
            "total_agents": len(self.agents),
            "total_cycles": sum(a.cycles_completed for a in self.agents.values()),
            "total_revenue": round(sum(a.revenue_generated for a in self.agents.values()), 2),
            "phase_breakdown": phase_breakdown,
            "last_withdraw": self.last_withdraw.isoformat(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
