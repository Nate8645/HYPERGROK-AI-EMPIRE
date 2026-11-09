"""Risk Manager. Rule-based. The limits live in the risk engine, not here."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import datetime

from hypergrok.agents.catalog import MODE
from hypergrok.domain import OrderIntent, RiskDecision
from hypergrok.risk.service import RiskService

_PASSED: ContextVar[frozenset[str]] = ContextVar("hypergrok_risk_passed", default=frozenset())


def risk_passed(client_order_id: str) -> bool:
    return client_order_id in _PASSED.get()


class RiskManager:
    name = "risk_manager"
    mode = MODE

    def __init__(self, service: RiskService) -> None:
        self.service = service

    def run(self, order: OrderIntent, *, now: datetime, case_id: str) -> RiskDecision:
        decision = self.service.evaluate(order, now, case_id=case_id)
        if decision.status == "PASS" and decision.engine == "risk_engine":
            _PASSED.set(frozenset(set(_PASSED.get()) | {order.client_order_id}))
        return decision
