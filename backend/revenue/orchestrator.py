"""
YABBAI Revenue System — Orchestrator

The one cycle that observes all channels, scores candidate actions by EV,
and routes each through the gates. Never scales on a single data point.
"""

from typing import Any, Dict, List
from .truth.metric import Metric, TruthLedger
from .gates.gates import GateController, ProposedAction
from .memory import Memory


class Orchestrator:
    """Drives all channels in one cycle."""

    def __init__(
        self,
        ledger: TruthLedger,
        gates: GateController,
        memory: Memory,
        channels: Dict[str, Any],
    ):
        self.ledger = ledger
        self.gates = gates
        self.memory = memory
        self.channels = channels
        self.cycle_count = 0

    def observe_all(self) -> List[Metric]:
        """Observe all channels and collect metrics."""
        all_metrics: List[Metric] = []
        for name, channel in self.channels.items():
            if hasattr(channel, "observe"):
                metrics = channel.observe()
                all_metrics.extend(metrics)
                # Record in ledger
                for m in metrics:
                    self.ledger.record(m)
        return all_metrics

    def propose_all(self) -> List[ProposedAction]:
        """Collect proposed actions from all channels."""
        all_actions: List[ProposedAction] = []
        for name, channel in self.channels.items():
            if hasattr(channel, "propose"):
                actions = channel.propose()
                all_actions.extend(actions)
        return all_actions

    def score_actions(self, actions: List[ProposedAction]) -> List[Dict[str, Any]]:
        """Score actions by EV = P(success) × upside - cost."""
        scored = []
        for action in actions:
            ev_data = action.ev or {}
            p = ev_data.get("p_success", 0.5)
            upside = ev_data.get("upside_usd", 0.0)
            cost = ev_data.get("cost_usd", action.usd_amount)
            risk_adj = ev_data.get("risk_adjustment", 0.0)
            ev = (p * upside) - cost - risk_adj
            scored.append({"action": action, "ev": ev, "ev_data": ev_data})
        # Sort by EV descending
        scored.sort(key=lambda x: x["ev"], reverse=True)
        return scored

    def cycle(self) -> Dict[str, Any]:
        """Run one orchestrator cycle."""
        self.cycle_count += 1

        # 1. Observe
        metrics = self.observe_all()

        # 2. Propose
        actions = self.propose_all()

        # 3. Score
        scored = self.score_actions(actions)

        # 4. Route top actions through gates
        routed = []
        for item in scored[:10]:  # Top 10 actions
            action = item["action"]
            result = self.gates.propose(action)
            routed.append({"action": action.to_public(), "gate_result": result})

        return {
            "cycle": self.cycle_count,
            "metrics_observed": len(metrics),
            "actions_proposed": len(actions),
            "actions_routed": len(routed),
            "routed": routed,
            "ledger_summary": self.ledger.summary(),
            "gate_status": self.gates.status(),
        }

    def status(self) -> Dict[str, Any]:
        """Get orchestrator status."""
        return {
            "cycle_count": self.cycle_count,
            "ledger": self.ledger.summary(),
            "gates": self.gates.status(),
            "channels": list(self.channels.keys()),
        }
