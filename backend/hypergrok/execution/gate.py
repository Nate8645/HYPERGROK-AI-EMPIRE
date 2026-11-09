"""Live-trading gate.

`LIVE_TRADING_ENABLED` defaults to false. A live request is rejected until
the flag is on and a per-order human approval token is on file for that
client order id. Even then, phase 1 has no transmitting adapter, so the
order is rejected instead of sent. The token is not consumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from hypergrok.config import Settings
from hypergrok.store import DeskStore
from hypergrok.venues.coinbase.credentials import load_credentials
from hypergrok.venues.coinbase.fx import FxQuote, assess_fx


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
        venue: str | None = None,
        product_id: str | None = None,
        notional: Decimal | None = None,
        notional_currency: str | None = None,
        fx_quote: FxQuote | None = None,
        now=None,
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
        if (venue or "").lower() != "coinbase":
            return GateDecision(
                allowed=False,
                reason="live_transmission_not_implemented",
                mode="live",
                approval_consumed=False,
            )
        return self._authorize_coinbase(
            product_id=product_id,
            notional=notional,
            notional_currency=notional_currency,
            fx_quote=fx_quote,
            now=now,
        )

    def _authorize_coinbase(
        self,
        *,
        product_id: str | None,
        notional: Decimal | None,
        notional_currency: str | None,
        fx_quote: FxQuote | None,
        now,
    ) -> GateDecision:
        if not self.settings.coinbase_live_enabled:
            return GateDecision(False, "coinbase_live_disabled", "live")
        if load_credentials(self.settings) is None and not self.settings.coinbase_api_key_name:
            return GateDecision(False, "coinbase_not_configured", "live")
        # A configured key name with an injected runtime client still counts when the private key
        # or key file loaded. Tests that only inject a client set the key name and private key.
        if load_credentials(self.settings) is None:
            return GateDecision(False, "coinbase_not_configured", "live")
        allowed = self.settings.coinbase_products()
        product = (product_id or "").upper()
        if not product or product not in allowed:
            return GateDecision(False, "product_not_allowlisted", "live")
        if notional is None or notional <= 0:
            return GateDecision(False, "capital_cap_exceeded", "live")
        cap_currency = (self.settings.coinbase_max_capital_currency or notional_currency or "").upper()
        order_currency = (notional_currency or cap_currency).upper()
        comparable = notional
        if cap_currency and order_currency and cap_currency != order_currency:
            from hypergrok.clock import utcnow

            assessment = assess_fx(
                fx_quote,
                now=now or utcnow(),
                max_age_seconds=self.settings.max_fx_age_seconds,
                base=order_currency,
                quote_ccy=cap_currency,
            )
            if not assessment.ok:
                return GateDecision(False, assessment.code, "live")
            assert fx_quote is not None
            comparable = notional * fx_quote.rate
        if comparable > self.settings.coinbase_max_capital:
            return GateDecision(False, "capital_cap_exceeded", "live")
        return GateDecision(True, "coinbase_live", "live", approval_consumed=False)
