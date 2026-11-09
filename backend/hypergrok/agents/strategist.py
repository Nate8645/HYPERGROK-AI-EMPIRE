"""Strategist. Rule-based. Builds an order; the risk engine still has to PASS it.

`size_mode=all_in` proposes 100% of equity minus round-trip costs. That can
break the Hyperliquid reserve or the 1% planned-risk cap. `risk_limited`
proposes the smallest of the balance, reserve, and planned-risk bounds.
An explicit notional on the idea is sent through unchanged.
"""

from __future__ import annotations

from decimal import Decimal

from hypergrok.agents.catalog import MODE
from hypergrok.agents.schemas import DeskCase, MarketAnalysis, ResearchNote, StrategyProposal
from hypergrok.config import Settings
from hypergrok.domain import AccountState, DeskIdea, OrderIntent
from hypergrok.money import floor_money, format_decimal
from hypergrok.risk.engine import RiskEngine

ONE = Decimal("1")


class Strategist:
    name = "strategist"
    mode = MODE

    def __init__(self, settings: Settings, engine: RiskEngine) -> None:
        self.settings = settings
        self.engine = engine

    def run(
        self,
        idea: DeskIdea,
        case: DeskCase,
        market: MarketAnalysis,
        research: ResearchNote,
        account: AccountState,
    ) -> StrategyProposal:
        side, blockers = self._side(idea, market, research)
        if side is None or market.mid is None or market.observed_at is None:
            reasons = blockers or ["no trade"]
            return self._no_trade(reasons)

        stop_fraction = idea.stop_fraction or self.settings.default_stop_fraction
        if stop_fraction <= 0 or stop_fraction >= 1:
            return self._no_trade(["stop fraction must be between 0 and 1"])

        entry = market.mid
        if side == "buy":
            stop = entry * (ONE - stop_fraction)
        else:
            stop = entry * (ONE + stop_fraction)

        try:
            bounds = self.engine.sizing_bounds(
                equity=account.equity,
                stop_fraction=stop_fraction,
                fee_bps=self.settings.default_fee_bps_round_trip,
                slippage_bps=self.settings.default_slippage_bps_round_trip,
            )
        except ValueError as exc:
            return self._no_trade([str(exc)])

        if idea.notional is not None:
            notional = idea.notional
            sizing_mode = "override"
        elif idea.size_mode == "all_in":
            notional = floor_money(bounds.by_balance)
            sizing_mode = "all_in"
        else:
            notional = floor_money(min(bounds.by_balance, bounds.by_reserve, bounds.by_risk))
            sizing_mode = "risk_limited"

        if notional <= 0:
            return self._no_trade(["sized notional is zero"])

        order = OrderIntent(
            client_order_id=idea.client_order_id or f"hg-{case.case_id}",
            venue="hyperliquid",
            symbol=case.symbol,
            side=side,
            order_kind="entry",
            notional=notional,
            notional_currency=account.currency,
            leverage=ONE,
            entry_price=entry,
            stop_price=stop,
            market_data_time=market.observed_at,
            fee_bps_round_trip=bounds.fee_bps,
            slippage_bps_round_trip=bounds.slippage_bps,
            usd_per_notional_currency=idea.usd_per_notional_currency,
        )
        sizing = {
            "mode": sizing_mode,
            "by_balance": format_decimal(bounds.by_balance),
            "by_reserve": format_decimal(bounds.by_reserve),
            "by_risk": format_decimal(bounds.by_risk),
            "notional": format_decimal(notional),
            "stop_fraction": format_decimal(stop_fraction),
        }
        return StrategyProposal(
            status="proposed",
            summary=f"proposed {side} {notional} {account.currency} via {sizing_mode}",
            reasons=[f"sized_{sizing_mode}"],
            order=order,
            sizing=sizing,
        )

    @staticmethod
    def _side(
        idea: DeskIdea,
        market: MarketAnalysis,
        research: ResearchNote,
    ) -> tuple[str | None, list[str]]:
        if not market.tradable:
            return None, list(market.reasons) or ["market not tradable"]
        if research.stance == "insufficient_evidence":
            return None, ["research evidence insufficient"]
        if market.bias == "neutral":
            return None, ["market bias is neutral"]
        bias_side = {"long": "buy", "short": "sell"}.get(market.bias)
        side = idea.side or bias_side
        if side is None:
            return None, ["no side"]
        if bias_side and side != bias_side:
            return None, ["requested side contradicts the market bias"]
        if research.stance == "support_long" and side != "buy":
            return None, ["research supports long"]
        if research.stance == "support_short" and side != "sell":
            return None, ["research supports short"]
        return side, []

    @staticmethod
    def _no_trade(reasons: list[str]) -> StrategyProposal:
        return StrategyProposal(
            status="no_trade",
            summary="no trade: " + "; ".join(reasons),
            reasons=reasons,
            order=None,
            sizing={},
        )
