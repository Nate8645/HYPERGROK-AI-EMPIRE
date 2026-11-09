"""Execution Trader. Rule-based.

Every order is checked again with the risk engine, then the execution gate.
Neither a forged PASS nor a skipped gate can reach an adapter.
"""

from __future__ import annotations

from datetime import datetime

from hypergrok.agents.catalog import MODE
from hypergrok.agents.schemas import ExecutionReport
from hypergrok.domain import DeskIdea, OrderIntent, RiskDecision
from hypergrok.errors import DeskError
from hypergrok.agents.risk_manager import RiskManager
from hypergrok.execution.adapter import ExecutionAdapter, order_payload
from hypergrok.execution.gate import ExecutionGate
from hypergrok.risk.engine import RiskEngine
from hypergrok.store import DeskStore
from hypergrok.venues.coinbase.fx import quote_from_settings


class ExecutionTrader:
    name = "execution_trader"
    mode = MODE

    def __init__(
        self,
        gate: ExecutionGate,
        adapter: ExecutionAdapter,
        store: DeskStore,
        engine: RiskEngine,
        risk_manager: RiskManager,
        coinbase: ExecutionAdapter | None = None,
    ) -> None:
        self.gate = gate
        self.adapter = adapter
        self.store = store
        self.engine = engine
        self.risk_manager = risk_manager
        self.settings = engine.settings
        self.coinbase = coinbase

    def run(
        self,
        *,
        order: OrderIntent,
        decision: RiskDecision,
        idea: DeskIdea,
        case_id: str,
        now: datetime,
    ) -> ExecutionReport:
        del decision  # A caller-supplied PASS is not authority. Risk Manager is.
        fresh = self.risk_manager.run(order, now=now, case_id=case_id)
        if fresh.status != "PASS" or fresh.engine != "risk_engine":
            return ExecutionReport(
                status="skipped",
                transmitted=False,
                summary="skipped because the risk engine did not PASS",
                reasons=["risk_not_passed", *fresh.reasons],
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
            venue=order.venue,
            product_id=order.symbol if order.venue == "coinbase" else None,
            notional=order.notional,
            notional_currency=order.notional_currency,
            fx_quote=quote_from_settings(self.settings),
            now=now,
        )
        would_send = order_payload(order, case_id)
        if order.venue == "coinbase":
            would_send["product_id"] = order.symbol
            would_send["order_type"] = idea.order_type or "market"
            would_send["post_only"] = idea.post_only
            if idea.base_size is not None:
                would_send["base_size"] = format(idea.base_size, "f")
            if idea.limit_price is not None:
                would_send["limit_price"] = format(idea.limit_price, "f")
            would_send["quote_size"] = format(order.notional, "f")
        if not gate.allowed:
            self.store.add_attempt(
                case_id=case_id,
                client_order_id=order.client_order_id,
                mode=mode,
                status="rejected",
                reason=gate.reason,
                transmitted=False,
                payload={"would_send": would_send, "transmitted": False, "reason": gate.reason},
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

        if gate.reason == "coinbase_live":
            if self.coinbase is None:
                raise DeskError("transmission_blocked", "coinbase adapter is not wired", 500)
            if idea.approval_token:
                self.store.mark_approval_used(idea.approval_token, now)
            result = self.coinbase.execute(would_send)
            self.store.add_attempt(
                case_id=case_id,
                client_order_id=order.client_order_id,
                mode="live",
                status=result.status,
                reason=result.detail,
                transmitted=result.transmitted,
                venue="coinbase",
                payload=result.payload,
                now=now,
            )
            if result.transmitted and order.order_kind == "entry":
                self.store.record_paper_entry(now)
            return ExecutionReport(
                status="submitted" if result.transmitted else result.status,
                transmitted=result.transmitted,
                summary=result.detail,
                reasons=[result.detail],
                client_order_id=order.client_order_id,
                gate_reason=gate.reason,
                approval_consumed=True,
                execution_mode="live",
                fills=(result.payload.get("result") or {}).get("fills") or [],
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
