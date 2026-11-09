"""Execution Trader. Rule-based. Refuses to transmit.

A PASS from the risk engine is required. Live mode still goes through the
gate, and phase 1 rejects it after the gate because no live adapter exists.
"""

from __future__ import annotations

from datetime import datetime

from hypergrok.agents.catalog import MODE
from hypergrok.agents.schemas import ExecutionReport
from hypergrok.domain import DeskIdea, OrderIntent, RiskDecision
from hypergrok.errors import DeskError
from hypergrok.execution.adapter import ExecutionAdapter, order_payload
from hypergrok.execution.gate import ExecutionGate
from hypergrok.store import DeskStore


class ExecutionTrader:
    name = "execution_trader"
    mode = MODE

    def __init__(self, gate: ExecutionGate, adapter: ExecutionAdapter, store: DeskStore) -> None:
        self.gate = gate
        self.adapter = adapter
        self.store = store

    def run(
        self,
        *,
        order: OrderIntent,
        decision: RiskDecision,
        idea: DeskIdea,
        case_id: str,
        now: datetime,
    ) -> ExecutionReport:
        if decision.status != "PASS" or decision.engine != "risk_engine":
            return ExecutionReport(
                status="skipped",
                transmitted=False,
                summary="skipped because the risk engine did not PASS",
                reasons=["risk_not_passed"],
                client_order_id=order.client_order_id,
                gate_reason=None,
                approval_consumed=False,
                execution_mode=None,
            )

        mode = "live" if idea.request_live else "dry_run"
        gate = self.gate.authorize(
            mode=mode,
            client_order_id=order.client_order_id,
            approval_token=idea.approval_token,
        )
        would_send = order_payload(order, case_id)
        if not gate.allowed:
            self.store.add_attempt(
                case_id=case_id,
                client_order_id=order.client_order_id,
                mode=mode,
                status="rejected",
                reason=gate.reason,
                transmitted=False,
                payload={
                    "would_send": would_send,
                    "transmitted": False,
                    "reason": gate.reason,
                },
                now=now,
            )
            return ExecutionReport(
                status="rejected",
                transmitted=False,
                summary=f"rejected by execution gate: {gate.reason}",
                reasons=[gate.reason],
                client_order_id=order.client_order_id,
                gate_reason=gate.reason,
                approval_consumed=False,
                execution_mode=mode,
            )

        result = self.adapter.execute(would_send)
        if result.transmitted or self.adapter.transmits:
            raise DeskError("transmission_blocked", "adapter attempted to transmit", 500)
        self.store.add_attempt(
            case_id=case_id,
            client_order_id=order.client_order_id,
            mode=mode,
            status="recorded",
            reason="dry_run_recorded",
            transmitted=False,
            payload=result.payload,
            now=now,
        )
        if order.order_kind == "entry":
            self.store.record_paper_entry(now)
        return ExecutionReport(
            status="recorded",
            transmitted=False,
            summary="dry run recorded; nothing was signed or sent",
            reasons=["dry_run_recorded"],
            client_order_id=order.client_order_id,
            gate_reason=gate.reason,
            approval_consumed=False,
            execution_mode=mode,
        )
