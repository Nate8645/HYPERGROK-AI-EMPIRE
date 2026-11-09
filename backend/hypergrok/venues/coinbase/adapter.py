"""ExecutionAdapter for Coinbase spot. The trader must already have passed risk and the gate."""

from __future__ import annotations

from hypergrok.execution.adapter import ExecutionAdapter, ExecutionResult
from hypergrok.venues.coinbase.broker import CoinbaseBroker

_ACCEPTED = {"open", "filled", "pending", "submitted", "queued"}


class CoinbaseExecutionAdapter(ExecutionAdapter):
    name = "coinbase"
    transmits = True

    def __init__(self, broker: CoinbaseBroker) -> None:
        self.broker = broker

    def execute(self, would_send: dict) -> ExecutionResult:
        result = self.broker.submit(would_send)
        status = str(result.get("status") or "rejected").lower()
        transmitted = status in _ACCEPTED
        return ExecutionResult(
            adapter=self.name,
            transmitted=transmitted,
            status="submitted" if transmitted else status,
            payload={
                "adapter": self.name,
                "transmitted": transmitted,
                "result": result,
                "note": "Coinbase spot only. No transfer, withdrawal, or derivative was requested.",
            },
            detail=str(result.get("reason") or status),
        )
