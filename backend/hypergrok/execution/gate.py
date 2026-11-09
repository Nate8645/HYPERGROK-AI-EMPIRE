"""Live-trading gate.

`LIVE_TRADING_ENABLED` defaults to false. A live request is rejected until
the flag is on and a per-order human approval token is on file for that
client order id. Even then, phase 1 has no transmitting adapter, so the
order is rejected instead of sent. The token is not consumed.
"""

from __future__ import annotations

from dataclasses import dataclass

from hypergrok.config import Settings
from hypergrok.store import DeskStore


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str
    mode: str
    approval_consumed: bool = False


class ExecutionGate:
    def __init__(self, settings: Settings, store: DeskStore) -> None:
        self.settings = settings
        self.store = store

    def authorize(
        self,
        *,
        mode: str,
        client_order_id: str,
        approval_token: str | None,
    ) -> GateDecision:
        if mode == "dry_run":
            return GateDecision(allowed=True, reason="dry_run", mode="dry_run")
        if mode != "live":
            return GateDecision(allowed=False, reason="unknown_execution_mode", mode=mode)
        if not self.settings.live_trading_enabled:
            return GateDecision(allowed=False, reason="live_trading_disabled", mode="live")
        if not approval_token:
            return GateDecision(allowed=False, reason="missing_human_approval", mode="live")
        record = self.store.get_approval(approval_token)
        if record is None or record["client_order_id"] != client_order_id or record["used_at"] is not None:
            return GateDecision(allowed=False, reason="missing_human_approval", mode="live")
        return GateDecision(
            allowed=False,
            reason="live_transmission_not_implemented",
            mode="live",
            approval_consumed=False,
        )
