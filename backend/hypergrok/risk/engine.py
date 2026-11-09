"""Hard risk engine.

This module is the authority for PASS/REJECT. Agents may propose a size,
including an all-in size, and this engine rejects anything that breaks a
limit. Fees and slippage are always added on top of stop distance. Callers
cannot declare costs below the configured assumptions.

Planned loss
    price_loss = notional * abs(entry - stop) / entry
    fee_loss = notional * fee_bps / 10000
    slippage_loss = notional * slippage_bps / 10000
    planned_loss = price_loss + fee_loss + slippage_loss

Hyperliquid collateral
    cash = notional + fee_loss + slippage_loss
    free_after = equity - cash
    A new entry must leave free_after >= equity * reserve fraction.
    Leverage is not allowed to reduce the cash required. Leverage must be 1.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from hypergrok.clock import ensure_utc
from hypergrok.config import Settings
from hypergrok.domain import AccountState, CheckResult, OrderIntent, RiskDecision

BPS = Decimal("10000")
ONE = Decimal("1")
ZERO = Decimal("0")


class SizingBounds:
    def __init__(
        self,
        *,
        by_balance: Decimal,
        by_reserve: Decimal,
        by_risk: Decimal,
        fee_bps: Decimal,
        slippage_bps: Decimal,
        cost_rate: Decimal,
    ) -> None:
        self.by_balance = by_balance
        self.by_reserve = by_reserve
        self.by_risk = by_risk
        self.fee_bps = fee_bps
        self.slippage_bps = slippage_bps
        self.cost_rate = cost_rate


class RiskEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def assumed_bps(
        self,
        fee_bps: Decimal | None,
        slippage_bps: Decimal | None,
    ) -> tuple[Decimal, Decimal]:
        return (
            _at_least(fee_bps, self.settings.default_fee_bps_round_trip),
            _at_least(slippage_bps, self.settings.default_slippage_bps_round_trip),
        )

    def sizing_bounds(
        self,
        *,
        equity: Decimal,
        stop_fraction: Decimal,
        fee_bps: Decimal | None,
        slippage_bps: Decimal | None,
    ) -> SizingBounds:
        """Upper bounds the strategist may *propose*. They are not a PASS."""

        assumed_fee, assumed_slip = self.assumed_bps(fee_bps, slippage_bps)
        cost_rate = (assumed_fee + assumed_slip) / BPS
        if stop_fraction <= 0:
            raise ValueError("stop_fraction must be positive")
        if equity <= 0:
            raise ValueError("equity must be positive")
        risk_rate = stop_fraction + cost_rate
        reserve = self.settings.hyperliquid_reserve_fraction
        denominator = ONE + cost_rate
        return SizingBounds(
            by_balance=equity / denominator,
            by_reserve=equity * (ONE - reserve) / denominator,
            by_risk=(equity * self.settings.max_planned_risk_fraction) / risk_rate,
            fee_bps=assumed_fee,
            slippage_bps=assumed_slip,
            cost_rate=cost_rate,
        )

    def evaluate(
        self,
        order: OrderIntent,
        account: AccountState,
        *,
        now: datetime,
        kill_switch_engaged: bool,
        seen_client_order_ids: set[str] | frozenset[str],
    ) -> RiskDecision:
        checks: list[CheckResult] = []

        def add(rule: str, passed: bool, detail: str) -> None:
            checks.append(CheckResult(rule=rule, passed=passed, detail=detail))

        structural: list[str] = []
        stop_problems: list[str] = []
        if order.notional <= 0:
            structural.append("notional must be positive")
        if order.entry_price <= 0:
            structural.append("entry_price must be positive")
        if not order.symbol.strip():
            structural.append("symbol is required")
        if order.notional_currency != account.currency:
            structural.append(
                f"notional currency {order.notional_currency} does not match account currency {account.currency}"
            )
        if account.equity <= 0 or account.start_of_day_equity <= 0:
            structural.append("account equity must be positive")
        if account.open_position_count < 0 or account.entries_today < 0:
            structural.append("account counters cannot be negative")
        if order.order_kind == "entry":
            if order.stop_price is None or order.stop_price <= 0:
                stop_problems.append("entry orders require a positive stop_price")
            elif order.side == "buy" and order.stop_price >= order.entry_price:
                stop_problems.append("buy stop must be below the entry")
            elif order.side == "sell" and order.stop_price <= order.entry_price:
                stop_problems.append("sell stop must be above the entry")

        add("invalid_order", not structural, "; ".join(structural) if structural else "ok")
        if order.order_kind == "entry":
            add("invalid_stop", not stop_problems, "; ".join(stop_problems) if stop_problems else "ok")

        add(
            "kill_switch",
            not kill_switch_engaged,
            "engaged" if kill_switch_engaged else "disengaged",
        )
        leverage_ok = order.leverage == ONE and self.settings.max_leverage == ONE
        add(
            "leverage",
            leverage_ok,
            f"order leverage is {order.leverage}; configured max is {self.settings.max_leverage}; leverage must equal 1",
        )
        duplicate = order.client_order_id in seen_client_order_ids
        add(
            "duplicate_client_order_id",
            not duplicate,
            "client order id already used" if duplicate else "new client order id",
        )
        venue_ok = order.venue == "hyperliquid"
        add(
            "venue_not_enabled",
            venue_ok,
            "hyperliquid is enabled" if venue_ok else f"{order.venue} is not enabled in phase 1",
        )
        self._add_market_data_checks(add, order.market_data_time, now)

        if structural or stop_problems:
            return self._finish(order, account, checks)

        if order.order_kind != "entry":
            return self._finish(
                order,
                account,
                checks,
                summary_prefix="reduce order; entry limits were not applied",
            )

        breakdown = self._add_entry_checks(add, order, account)
        return self._finish(order, account, checks, breakdown=breakdown)

    def _add_market_data_checks(self, add, market_data_time: datetime | None, now: datetime) -> None:
        if market_data_time is None:
            add("missing_market_data", False, "market data timestamp is missing")
            return
        age = (ensure_utc(now) - ensure_utc(market_data_time)).total_seconds()
        add("missing_market_data", True, "timestamp present")
        limit = self.settings.max_market_data_age_seconds
        if age < -2:
            add("stale_market_data", False, f"timestamp is {-age:.3f}s ahead of the desk clock")
        elif age > limit:
            add("stale_market_data", False, f"age {age:.3f}s exceeds max {limit}s")
        else:
            add("stale_market_data", True, f"age {age:.3f}s within {limit}s")

    def _add_entry_checks(self, add, order: OrderIntent, account: AccountState) -> dict[str, Decimal | None]:
        settings = self.settings
        fee_bps, slip_bps = self.assumed_bps(order.fee_bps_round_trip, order.slippage_bps_round_trip)
        fee_loss = order.notional * fee_bps / BPS
        slip_loss = order.notional * slip_bps / BPS
        assert order.stop_price is not None
        if order.side == "buy":
            distance = order.entry_price - order.stop_price
        else:
            distance = order.stop_price - order.entry_price
        stop_fraction = distance / order.entry_price
        price_loss = order.notional * stop_fraction
        planned = price_loss + fee_loss + slip_loss
        risk_limit = account.equity * settings.max_planned_risk_fraction
        cash = order.notional + fee_loss + slip_loss
        free_after = account.equity - cash
        reserve_required = account.equity * settings.hyperliquid_reserve_fraction

        self._add_min_notional(add, order)
        loss_limit = account.start_of_day_equity * settings.max_daily_loss_fraction
        daily_ok = account.realized_pnl_today > -loss_limit
        add(
            "daily_loss_limit",
            daily_ok,
            f"realized {account.realized_pnl_today} versus floor {-loss_limit} ({settings.max_daily_loss_fraction} of start-of-day equity)",
        )
        add(
            "max_open_positions",
            account.open_position_count < settings.max_open_positions,
            f"open positions {account.open_position_count} versus max {settings.max_open_positions}",
        )
        add(
            "max_daily_entries",
            account.entries_today < settings.max_new_entries_per_day,
            f"entries today {account.entries_today} versus max {settings.max_new_entries_per_day}",
        )
        add(
            "fees_and_slippage_included",
            fee_bps > 0 and slip_bps > 0 and fee_loss > 0 and slip_loss > 0,
            f"fee_bps={fee_bps} slippage_bps={slip_bps} fee_loss={fee_loss} slippage_loss={slip_loss}",
        )
        add(
            "insufficient_balance",
            cash <= account.equity,
            f"notional plus round-trip fees and slippage {cash} versus equity {account.equity}",
        )
        if order.venue == "hyperliquid":
            reserve_ok = free_after >= reserve_required
            reserve_detail = (
                f"free collateral after the order {free_after} versus required reserve {reserve_required}"
            )
        else:
            reserve_ok = False
            reserve_detail = "reserve cannot be cleared for a venue that is not enabled"
        add("margin_reserve", reserve_ok, reserve_detail)
        add(
            "planned_risk",
            planned <= risk_limit,
            (
                f"planned loss {planned} versus limit {risk_limit} "
                f"(price {price_loss} + fees {fee_loss} + slippage {slip_loss})"
            ),
        )
        return {
            "planned_loss": planned,
            "planned_loss_limit": risk_limit,
            "price_loss": price_loss,
            "fee_loss": fee_loss,
            "slippage_loss": slip_loss,
            "assumed_fee_bps": fee_bps,
            "assumed_slippage_bps": slip_bps,
            "reserve_required": reserve_required if order.venue == "hyperliquid" else None,
            "free_collateral_after": free_after,
        }

    def _add_min_notional(self, add, order: OrderIntent) -> None:
        minimum = self.settings.min_order_notional
        minimum_currency = self.settings.min_order_notional_currency
        if order.notional_currency == minimum_currency:
            comparable = order.notional
            add("min_notional_unverified", True, f"notional already in {minimum_currency}")
            add(
                "min_notional",
                comparable >= minimum,
                f"{comparable} {minimum_currency} versus minimum {minimum} {minimum_currency}",
            )
            return
        rate = order.usd_per_notional_currency
        if minimum_currency == "USD" and rate is not None and rate > 0:
            comparable = order.notional * rate
            add(
                "min_notional_unverified",
                True,
                f"converted with the supplied rate {rate} USD per {order.notional_currency}",
            )
            add(
                "min_notional",
                comparable >= minimum,
                f"{comparable} USD versus minimum {minimum} USD",
            )
            return
        add(
            "min_notional_unverified",
            False,
            "refusing to invent an FX rate to compare the order with the venue minimum",
        )
        add("min_notional", False, "venue minimum could not be verified")

    def _finish(
        self,
        order: OrderIntent,
        account: AccountState,
        checks: list[CheckResult],
        *,
        breakdown: dict | None = None,
        summary_prefix: str | None = None,
    ) -> RiskDecision:
        reasons = [check.rule for check in checks if not check.passed]
        status = "PASS" if not reasons else "REJECT"
        extra = breakdown or {}
        if status == "PASS":
            summary = "PASS: within hard limits"
        else:
            summary = "REJECT: " + ", ".join(reasons)
        if summary_prefix and status == "PASS":
            summary = f"PASS: {summary_prefix}"
        return RiskDecision(
            status=status,
            reasons=reasons,
            checks=checks,
            summary=summary,
            client_order_id=order.client_order_id,
            notional=order.notional,
            equity=account.equity,
            planned_loss=extra.get("planned_loss"),
            planned_loss_limit=extra.get("planned_loss_limit"),
            price_loss=extra.get("price_loss"),
            fee_loss=extra.get("fee_loss"),
            slippage_loss=extra.get("slippage_loss"),
            assumed_fee_bps=extra.get("assumed_fee_bps"),
            assumed_slippage_bps=extra.get("assumed_slippage_bps"),
            reserve_required=extra.get("reserve_required"),
            free_collateral_after=extra.get("free_collateral_after"),
        )


def _at_least(given: Decimal | None, floor: Decimal) -> Decimal:
    if given is None or given < floor:
        return floor
    return given
