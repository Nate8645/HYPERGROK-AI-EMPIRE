"""Risk Manager. Rule-based. The limits live in the risk engine, not here."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from datetime import datetime, timedelta

from hypergrok.agents.catalog import MODE
from hypergrok.domain import OrderIntent, RiskDecision
from hypergrok.order_binding import fingerprint
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
            ttl = getattr(self.service.engine.settings, "risk_grant_seconds", 30)
            self.service.store.insert_grant(
                decision_id=uuid.uuid4().hex,
                order_hash=fingerprint(order.model_dump()),
                client_order_id=order.client_order_id,
                case_id=case_id,
                now=now,
                expires_at=now + timedelta(seconds=int(ttl)),
            )
        return decision

    def review_full_capital(self, **kwargs) -> dict:
        """Simulation only. A REJECT or PASS here is not recorded as permission to send."""
        from hypergrok.risk.full_capital import assess_full_capital

        ceiling = self.service.engine.settings.simulation_max_capital_fraction
        fraction = min(kwargs.pop("capital_fraction", ceiling), ceiling)
        result = assess_full_capital(capital_fraction=fraction, **kwargs)
        result["pass_recorded"] = False
        return result
