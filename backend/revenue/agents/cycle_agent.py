"""
YABBAI Multi-Agent Autonomous System

Manages 10-15 agents per operational phase, cycling through:
Pump → Esky → Mission → Scale → Withdraw

Each agent runs independently, coordinated by the main orchestrator.
"""

import asyncio
import os
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
        # home_phase is the pool's bookkeeping key and never changes; current_phase
        # walks all five phases during run_cycle and is display-only.
        self.home_phase = phase
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

        # PUMP measures once; the later phases operate on that same measurement
        # rather than each re-reading chain. One RPC fan-out per cycle instead of
        # four, and every phase reasons about the same instant.
        measurement: Optional[Dict[str, Any]] = None

        for phase in phases:
            self.current_phase = phase
            self.status = AgentStatus.CYCLING
            self.last_activity = datetime.now(timezone.utc)

            try:
                logger.info(f"🤖 Agent {self.agent_id}: Running {phase.value.upper()} phase")
                result = await self.execute_phase(phase, measurement)
                if phase == Phase.PUMP:
                    measurement = result
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

        # Record achievement for milestone cycles
        if self.cycles_completed % 10 == 0:  # Every 10 cycles
            await self._record_cycle_achievement(cycle_result)

        return cycle_result
    
    async def _record_cycle_achievement(self, cycle_result: Dict[str, Any]):
        """Record achievement when reaching cycle milestones."""
        try:
            from achievements import AchievementTracker
            tracker = AchievementTracker(self.db)
            
            # Determine what was learned
            successful_phases = [p for p, r in cycle_result["phase_results"].items() if not r.get("error")]
            learning = f"Agent completed {self.cycles_completed} cycles. Success rate: {len(successful_phases)}/5 phases. Total revenue: ${self.revenue_generated:.2f}"
            
            await tracker.record(
                category="agent",
                milestone=f"Agent {self.agent_id[:8]} reached {self.cycles_completed} cycles",
                learning=learning,
                result={
                    "cycles_completed": self.cycles_completed,
                    "revenue_generated": self.revenue_generated,
                    "successful_phases": len(successful_phases),
                    "total_phases": 5
                },
                agent_id=self.agent_id,
                phase=self.current_phase.value
            )
        except Exception as e:
            logger.error(f"Failed to record achievement: {e}")

    async def execute_phase(
        self, phase: Phase, measurement: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute specific phase logic, passing PUMP's measurement downstream."""
        if phase == Phase.PUMP:
            return await self.phase_pump()
        elif phase == Phase.ESKY:
            return await self.phase_esky(measurement)
        elif phase == Phase.MISSION:
            return await self.phase_mission(measurement)
        elif phase == Phase.SCALE:
            return await self.phase_scale(measurement)
        elif phase == Phase.WITHDRAW:
            return await self.phase_withdraw(measurement)
        else:
            return {"error": "Unknown phase"}

    async def _token_context(self):
        """Chain client, mint and treasury for this deployment, or None."""
        import os
        from solana_live import SolanaLive, jupiter_price, DEFAULT_FALLBACKS
        from dexscreener import market as dex_market

        mint = (os.environ.get("TOKEN_MINT") or "").strip()
        if not mint:
            doc = await self.db.token_mint_config.find_one({})
            mint = (doc or {}).get("mint")
        if not mint:
            return None

        treasury = (os.environ.get("TREASURY_WALLET") or "").strip()
        if not treasury:
            settings = await self.db.settings.find_one({}) or {}
            treasury = settings.get("treasury_wallet")
        if not treasury:
            return None

        rpc = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        fallbacks = [
            u.strip() for u in
            os.environ.get("SOLANA_RPC_FALLBACKS", ",".join(DEFAULT_FALLBACKS)).split(",")
            if u.strip()
        ]
        return {
            "chain": SolanaLive(rpc, fallbacks=fallbacks),
            "mint": mint,
            "treasury": treasury,
            "price_fn": jupiter_price,
            "jupiter_key": os.environ.get("JUPITER_API_KEY", ""),
            "dex_fn": dex_market,
        }

    async def phase_pump(self) -> Dict[str, Any]:
        """PUMP: measure the token's current on-chain and market state.

        This used to return three hardcoded literals ($97 course, $2500 service,
        $50 momentum trade) marked as placeholders. It now takes a real
        measurement of the token this project actually launched.
        """
        ctx = await self._token_context()
        if not ctx:
            return {
                "phase": "pump",
                "measured": False,
                "reason": "no token mint or treasury configured",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        # Shared across agents inside a short window. Fifty agents measuring
        # independently every ten seconds rate-limited Jupiter, which turned a
        # real price into a DATA GAP through self-inflicted load alone.
        from revenue.token_metrics import collect_cached

        metrics = await collect_cached(
            ctx["chain"], ctx["mint"], ctx["treasury"],
            ctx["price_fn"], ctx["jupiter_key"], ctx["dex_fn"],
        )

        return {
            "phase": "pump",
            "measured": True,
            "metrics": metrics,
            "cached": metrics.get("cached", False),
            "data_gaps": metrics.get("data_gaps", []),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def phase_esky(self, measurement: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """ESKY: put the measurement on ice — store it so history accumulates.

        Previously set `leads_generated = 10  # Simulated for now`. It now
        preserves what PUMP measured, which is what gives SCALE something real to
        compare against later. Rows are capped so the collection cannot grow
        without bound.
        """
        if not measurement or not measurement.get("measured"):
            return {
                "phase": "esky",
                "stored": False,
                "reason": "nothing measured this cycle",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        metrics = measurement.get("metrics") or {}

        # Only the agent that actually measured writes a row. Without this, fifty
        # agents sharing one cached measurement would each store an identical
        # copy, and SCALE would then compare a row against its own duplicate and
        # report no change forever.
        if measurement.get("cached"):
            return {
                "phase": "esky",
                "stored": False,
                "reason": "measurement served from shared cache; already stored",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        doc = dict(metrics)
        doc.pop("cached", None)
        doc["agent_id"] = self.agent_id
        doc["ts"] = datetime.now(timezone.utc)

        try:
            await self.db.token_measurements.insert_one(doc)
            count = await self.db.token_measurements.count_documents({})
            if count > 2000:
                old = await self.db.token_measurements.find({}).sort("ts", 1) \
                    .limit(count - 2000).to_list(count - 2000)
                if old:
                    await self.db.token_measurements.delete_many(
                        {"_id": {"$in": [d["_id"] for d in old]}}
                    )
            stored = True
        except Exception as e:
            logger.error(f"{self.agent_id}: could not store measurement: {e}")
            stored = False

        return {
            "phase": "esky",
            "stored": stored,
            "price_usd": metrics.get("price_usd"),
            "treasury_sol": metrics.get("treasury_sol"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def phase_mission(self, measurement: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """MISSION: assess the measurement against operator thresholds.

        Reads alert_price_drop_pct and alert_balance_low_sol from settings — the
        knobs that already existed but were never consulted by anything — and
        reports observations. Observations only: nothing here executes a trade or
        moves funds, and a treasury movement still needs a human signature and an
        allowlisted destination.
        """
        if not measurement or not measurement.get("measured"):
            return {
                "phase": "mission",
                "assessed": False,
                "reason": "nothing measured this cycle",
                "revenue_generated": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        from revenue.token_metrics import assess

        settings = await self.db.settings.find_one({}) or {}

        # Reference price is the oldest stored measurement in the window, so a
        # drop is measured against something real rather than a guess.
        try:
            oldest = await self.db.token_measurements.find(
                {"price_usd": {"$ne": None}}
            ).sort("ts", 1).limit(1).to_list(1)
            if oldest:
                settings = {**settings, "_reference_price": oldest[0].get("price_usd")}
        except Exception:
            pass

        result = assess(measurement.get("metrics") or {}, settings)

        # Only the agent that actually measured considers a buyback. Otherwise
        # fifty agents sharing one cached measurement would each queue the same
        # proposal, and the operator would face fifty identical buttons.
        buyback = {"propose": False, "reason": "measurement served from cache"}
        if not measurement.get("cached"):
            try:
                buyback = await self._consider_buyback(measurement.get("metrics") or {})
            except Exception as e:
                logger.error(f"{self.agent_id}: buyback consideration failed: {e}")
                buyback = {"propose": False, "reason": f"error: {e}"}

        return {
            "phase": "mission",
            "assessed": True,
            "observations": result["observations"],
            "alert_count": result["alert_count"],
            "buyback": {
                "proposed": bool(buyback.get("propose")),
                "reason": buyback.get("reason"),
                "amount_sol": buyback.get("amount_sol"),
                "price_impact_pct": buyback.get("price_impact_pct"),
            },
            # Saved Mission Builder configs remain unwired; this phase assesses
            # token state, it does not run those.
            "saved_missions_executed": 0,
            "revenue_generated": 0.0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _consider_buyback(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """Decide whether to queue a buyback, and queue it if so.

        The agent does everything except sign: watches, decides, sizes against
        the operator's own risk and reinvest settings, prices it through Jupiter,
        and queues it. The operator approves with one click and their wallet
        signs. Nothing here can move funds.
        """
        from revenue.buyback_engine import should_propose, review
        from buyback import quote as bb_quote

        settings = await self.db.settings.find_one({}) or {}

        last = await self.db.buyback_proposals.find({}).sort("proposed_at", -1) \
            .limit(1).to_list(1)
        last_at = None
        if last:
            raw = last[0].get("proposed_at")
            if isinstance(raw, datetime):
                last_at = raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)

        # Reference price is the oldest stored observation, so a fall is measured
        # against something real rather than an assumption.
        reference = None
        try:
            oldest = await self.db.token_measurements.find(
                {"price_usd": {"$ne": None}}
            ).sort("ts", 1).limit(1).to_list(1)
            if oldest:
                reference = oldest[0].get("price_usd")
        except Exception:
            pass

        decision = should_propose(metrics, settings, last_at, reference)
        if not decision.get("propose"):
            return decision

        mint = metrics.get("mint")
        q = await bb_quote(
            mint, decision["amount_sol"],
            int(settings.get("slippage_bps") or 50),
            os.environ.get("JUPITER_API_KEY", ""),
        )
        reviewed = review(decision, q)
        if not reviewed.get("propose"):
            return reviewed

        await self.db.buyback_proposals.insert_one({
            "id": str(uuid.uuid4()),
            "mint": mint,
            "amount_sol": reviewed["amount_sol"],
            "price_impact_pct": reviewed.get("price_impact_pct"),
            "quoted_out_raw": reviewed.get("quoted_out_raw"),
            "reasons": reviewed.get("reasons", []),
            "disclosure": reviewed.get("disclosure"),
            "proposed_by": f"agent:{self.agent_id}",
            "proposed_at": datetime.now(timezone.utc),
            "status": "pending",
            "executed": False,
            "requires_signature": True,
        })
        logger.info(
            f"{self.agent_id}: queued buyback proposal {reviewed['amount_sol']} SOL "
            f"at {reviewed.get('price_impact_pct')}% impact"
        )
        return reviewed

    async def phase_scale(self, measurement: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """SCALE: measure change against the previous stored measurement.

        This is where growth becomes visible: holders, price, treasury balance,
        traded volume. Deltas are computed only where both sides are real numbers,
        so a field that was unavailable last cycle produces no delta rather than a
        fabricated zero.
        """
        if not measurement or not measurement.get("measured"):
            return {
                "phase": "scale",
                "compared": False,
                "reason": "nothing measured this cycle",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        from revenue.token_metrics import compare

        previous = None
        try:
            # Skip the row ESKY just wrote; compare against the one before it.
            rows = await self.db.token_measurements.find({}).sort("ts", -1).limit(2).to_list(2)
            if len(rows) > 1:
                previous = rows[1]
        except Exception as e:
            logger.warning(f"{self.agent_id}: could not load previous measurement: {e}")

        result = compare(previous, measurement.get("metrics") or {})

        return {
            "phase": "scale",
            "compared": not result.get("first_measurement", False),
            "changes": result.get("changes", {}),
            "change_count": len(result.get("changes", {})),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def phase_withdraw(self, measurement: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """WITHDRAW: propose a payout only against reconciled income.

        real_income() counts PAYMENT_PROCESSOR entries only, so a token price
        rise or a treasury balance cannot trigger this. A position is not a
        profit. Anything proposed still requires a human signature and an
        allowlisted destination.
        """
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
