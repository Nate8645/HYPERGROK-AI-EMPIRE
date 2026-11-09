"""Risk Manager. Rule-based. The limits live in the risk engine, not here."""

from __future__ import annotations

from datetime import datetime

from hypergrok.agents.catalog import MODE
from hypergrok.domain import OrderIntent, RiskDecision
from hypergrok.risk.service import RiskService


class RiskManager:
    name = "risk_manager"
    mode = MODE

    def __init__(self, service: RiskService) -> None:
        self.service = service

    def run(self, order: OrderIntent, *, now: datetime, case_id: str) -> RiskDecision:
        return self.service.evaluate(order, now, case_id=case_id)
