"""Execution boundary for phase 1.

Concrete adapters must not sign transactions, hold private keys, or contact
an exchange or RPC. `transmits` stays False. A later phase can add a separate
adapter behind the same gate; this phase does not ship one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel


class ExecutionResult(BaseModel):
    adapter: str
    transmitted: bool = False
    status: str
    payload: dict
    detail: str


class ExecutionAdapter(ABC):
    transmits: ClassVar[bool] = False

    @abstractmethod
    def execute(self, would_send: dict) -> ExecutionResult:
        """Record or, in a later phase, transmit. Phase 1 records only."""


class Phase1Adapter(ExecutionAdapter):
    """Shared guard so a subclass cannot flip `transmits` on by accident."""

    def _refuse_transmission(self) -> None:
        if self.transmits:
            raise RuntimeError("phase 1 execution adapters are not allowed to transmit")


def order_payload(order, case_id: str | None) -> dict:
    """JSON body describing what a future adapter would send. No signature field."""

    from hypergrok.serialize import to_jsonable

    body = {
        "venue": order.venue,
        "symbol": order.symbol,
        "side": order.side,
        "order_kind": order.order_kind,
        "notional": order.notional,
        "notional_currency": order.notional_currency,
        "leverage": order.leverage,
        "entry_price": order.entry_price,
        "stop_price": order.stop_price,
        "client_order_id": order.client_order_id,
        "case_id": case_id,
    }
    return to_jsonable(body)
