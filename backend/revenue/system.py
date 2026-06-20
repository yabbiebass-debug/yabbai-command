"""
YABBAI Revenue System Integration

Main revenue system instance that integrates with the existing YABBAI platform.
"""

import os
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from .truth.metric import Metric, SourceType, TruthLedger, DataGap
from .gates.gates import CapitalCaps, GateController, ProposedAction
from .gates.compliance_gate import ComplianceGate
from .memory import Memory, Learning
from .channels.products.channel import ProductsChannel
from .channels.agency.channel import AgencyChannel
from .channels.trading.channel import TradingChannel, TradeCap, NoKeySigner
from .orchestrator import Orchestrator


class RevenueSystem:
    """Main revenue system integrating all components."""

    def __init__(self, db):
        """Initialize the revenue system with MongoDB database."""
        self.db = db

        # Initialize caps from environment
        caps = CapitalCaps(
            micro_spend_cap=float(os.getenv("MICRO_SPEND_CAP", "2.0")),
            spend_cap=float(os.getenv("SPEND_CAP", "25.0")),
            daily_spend_cap=float(os.getenv("DAILY_SPEND_CAP", "100.0")),
            daily_loss_cap=float(os.getenv("DAILY_LOSS_CAP", "15.0")),
        )

        trade_caps = TradeCap(
            max_real_trade_usd=float(os.getenv("MAX_REAL_TRADE_USD", "10.0")),
            token_allowlist=os.getenv("TOKEN_ALLOWLIST", "SOL,USDC").split(","),
        )

        # Core components
        self.ledger = TruthLedger()
        self.gates = GateController(caps)
        self.memory = Memory(db)
        self.compliance = ComplianceGate()

        # Channels
        self.products = ProductsChannel(self.ledger, self.gates, self.memory)
        self.agency = AgencyChannel(self.ledger, self.gates, self.memory)
        self.trading = TradingChannel(
            self.ledger,
            self.gates,
            self.memory,
            trade_caps,
            signer=NoKeySigner(),
            paper_proof_bar=int(os.getenv("PAPER_PROOF_BAR", "100")),
        )

        # Orchestrator
        self.orchestrator = Orchestrator(
            self.ledger,
            self.gates,
            self.memory,
            {"products": self.products, "agency": self.agency, "trading": self.trading},
        )

    # ── Webhooks ───────────────────────────────────────────────────────────

    def handle_product_sale(self, sale_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a product sale webhook (Stripe, Gumroad, etc.)."""
        try:
            sale_id = sale_data.get("sale_id") or sale_data.get("id")
            gross = float(sale_data.get("gross_usd", 0))
            fee = float(sale_data.get("fee_usd", 0))
            net = gross - fee

            # Create REAL income metric
            metric = Metric(
                name="income",
                value=net,
                source=f"webhook:product:{sale_id}",
                source_type=SourceType.PAYMENT_PROCESSOR,
                signed_by="products_webhook",
                notes=f"Product sale: {sale_data.get('product', 'unknown')}",
            )

            self.ledger.record(metric)

            # Record learning
            self.memory.add_learning(
                Learning(
                    kind="win",
                    channel="products",
                    agent="webhook",
                    summary=f"Sale ${net:.2f} - {sale_data.get('product', 'product')}",
                    usd_impact=net,
                    context=sale_data,
                )
            )

            return {"ok": True, "booked_usd": net, "metric": metric.to_dict()}

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def handle_invoice_paid(self, invoice_data: Dict[str, Any]) -> Dict[str, Any]:
        """Handle a paid invoice webhook (for agency services)."""
        try:
            invoice_id = invoice_data.get("invoice_id") or invoice_data.get("id")
            amount = float(invoice_data.get("amount_usd", 0))

            # Create REAL income metric
            metric = Metric(
                name="income",
                value=amount,
                source=f"webhook:invoice:{invoice_id}",
                source_type=SourceType.PAYMENT_PROCESSOR,
                signed_by="agency_webhook",
                notes=f"Invoice paid: {invoice_data.get('client', 'unknown')}",
            )

            self.ledger.record(metric)

            # Record learning
            self.memory.add_learning(
                Learning(
                    kind="win",
                    channel="agency",
                    agent="webhook",
                    summary=f"Invoice ${amount:.2f} - {invoice_data.get('service', 'service')}",
                    usd_impact=amount,
                    context=invoice_data,
                )
            )

            return {"ok": True, "booked_usd": amount, "metric": metric.to_dict()}

        except Exception as e:
            return {"ok": False, "error": str(e)}

    # ── Dashboard Data ─────────────────────────────────────────────────────

    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Get complete dashboard data."""
        return {
            "real_income": self.ledger.real_income(),
            "real_expense": self.ledger.real_expense(),
            "net_profit": self.ledger.net_profit(),
            "projected": self.ledger.projected_net(),
            "unreconciled": self.ledger.unreconciled(),
            "data_gaps": self.ledger.data_gaps(),
            "gates": self.gates.status(),
            "pending_approvals": self.gates.pending_approvals(),
            "channel_scores": {
                "products": await self.memory.channel_score("products"),
                "agency": await self.memory.channel_score("agency"),
                "trading": await self.memory.channel_score("trading"),
            },
            "recent_learnings": await self.memory.recent_learnings(20),
            "orchestrator": self.orchestrator.status(),
        }

    # ── Actions ────────────────────────────────────────────────────────────

    def propose_action(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Propose a new action (from UI or agent)."""
        try:
            action = ProposedAction(
                kind=action_data["kind"],
                channel=action_data["channel"],
                agent=action_data.get("agent", "manual"),
                usd_amount=action_data.get("usd_amount", 0.0),
                reversible=action_data.get("reversible", True),
                payload=action_data.get("payload", {}),
                reason=action_data.get("reason", ""),
                ev=action_data.get("ev"),
            )

            result = self.gates.propose(action)
            return {"ok": True, "result": result}

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def approve_action(
        self, queue_id: str, approver: str, signature: Optional[str] = None
    ) -> Dict[str, Any]:
        """Approve a queued action."""
        return self.gates.human_approve(queue_id, approver, signature)

    def reject_action(self, queue_id: str, approver: str, reason: str = "") -> Dict[str, Any]:
        """Reject a queued action."""
        return self.gates.human_reject(queue_id, approver, reason)

    # ── Compliance ─────────────────────────────────────────────────────────

    def check_compliance(self, text: str, context: str = "general") -> Dict[str, Any]:
        """Check text for compliance violations."""
        return self.compliance.check(text, context)

    # ── Controls ───────────────────────────────────────────────────────────

    def engage_kill_switch(self) -> Dict[str, Any]:
        """Engage the kill switch (halt all activity)."""
        self.gates.engage_kill_switch()
        return {"ok": True, "status": "kill_switch_engaged"}

    def disengage_kill_switch(self) -> Dict[str, Any]:
        """Disengage the kill switch (requires admin)."""
        self.gates.disengage_kill_switch()
        return {"ok": True, "status": "kill_switch_disengaged"}

    def update_caps(self, caps_data: Dict[str, float]) -> Dict[str, Any]:
        """Update capital caps (can only tighten without approval)."""
        try:
            self.gates.tighten_caps(**caps_data)
            return {"ok": True, "caps": self.gates.status()["caps"]}
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    # ── Orchestrator ───────────────────────────────────────────────────────

    def run_cycle(self) -> Dict[str, Any]:
        """Run one orchestrator cycle."""
        return self.orchestrator.cycle()
