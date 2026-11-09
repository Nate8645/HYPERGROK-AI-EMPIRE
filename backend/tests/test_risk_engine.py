"""Each hard limit, isolated. Numbers are literals so a helper bug cannot hide a miss."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hypergrok.config import Settings
from hypergrok.domain import AccountState, OrderIntent
from hypergrok.risk.engine import RiskEngine

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def engine(**overrides: object) -> RiskEngine:
    values: dict = {
        "account_currency": "USD",
        "starting_capital": Decimal("100"),
        "default_fee_bps_round_trip": Decimal("10"),
        "default_slippage_bps_round_trip": Decimal("10"),
        "max_market_data_age_seconds": 5,
    }
    values.update(overrides)
    return RiskEngine(Settings(_env_file=None, **values))


def account(**overrides: object) -> AccountState:
    values: dict = {
        "currency": "USD",
        "equity": Decimal("100"),
        "start_of_day_equity": Decimal("100"),
        "realized_pnl_today": Decimal("0"),
        "open_position_count": 0,
        "entries_today": 0,
        "trading_day": "2026-11-09",
    }
    values.update(overrides)
    return AccountState(**values)


def order(**overrides: object) -> OrderIntent:
    values: dict = {
        "client_order_id": "ord-1",
        "venue": "hyperliquid",
        "symbol": "BTC",
        "side": "buy",
        "order_kind": "entry",
        "notional": Decimal("50"),
        "notional_currency": "USD",
        "leverage": Decimal("1"),
        "entry_price": Decimal("100"),
        "stop_price": Decimal("99.5"),
        "market_data_time": NOW,
        "fee_bps_round_trip": Decimal("10"),
        "slippage_bps_round_trip": Decimal("10"),
    }
    values.update(overrides)
    return OrderIntent(**values)


def decide(intent: OrderIntent | None = None, book: AccountState | None = None, **kwargs: object):
    return engine().evaluate(
        intent or order(),
        book or account(),
        now=NOW,
        kill_switch_engaged=bool(kwargs.get("kill", False)),
        seen_client_order_ids=set(kwargs.get("seen", set())),
    )


def test_baseline_order_passes_and_includes_fees() -> None:
    decision = decide()
    assert decision.status == "PASS"
    assert decision.reasons == []
    assert decision.fee_loss == Decimal("0.05")
    assert decision.slippage_loss == Decimal("0.05")
    assert decision.price_loss == Decimal("0.25")
    assert decision.planned_loss == decision.price_loss + decision.fee_loss + decision.slippage_loss
    assert decision.planned_loss <= decision.planned_loss_limit


def test_all_in_passes_when_reserve_and_planned_risk_both_fit() -> None:
    # 79.84 is inside the 20% reserve after 20 bps of round-trip cost.
    # Stop is 50 bps, so planned loss stays under 1% of equity.
    decision = decide(order(notional=Decimal("79.84"), stop_price=Decimal("99.5")))
    assert decision.status == "PASS"
    assert decision.free_collateral_after >= Decimal("20")
    assert decision.planned_loss <= Decimal("1")
    assert decision.fee_loss > 0
    assert decision.slippage_loss > 0


def test_all_in_minus_fees_is_rejected_for_the_reserve() -> None:
    # 99.80 plus 20 bps of cost still fits in equity and under the 1% risk cap,
    # but it leaves almost nothing against the 20% Hyperliquid reserve.
    decision = decide(order(notional=Decimal("99.80"), stop_price=Decimal("99.5")))
    assert decision.status == "REJECT"
    assert decision.reasons == ["margin_reserve"]
    assert decision.free_collateral_after < Decimal("20")
    assert decision.planned_loss < decision.planned_loss_limit


def test_reserve_sized_order_is_rejected_when_planned_risk_is_too_wide() -> None:
    decision = decide(order(notional=Decimal("70"), stop_price=Decimal("95")))
    assert decision.status == "REJECT"
    assert decision.reasons == ["planned_risk"]
    assert decision.free_collateral_after >= Decimal("20")
    assert decision.planned_loss > decision.planned_loss_limit


def test_fees_and_slippage_can_push_a_trade_over_the_one_percent_cap() -> None:
    # Price loss alone is 0.95, under the 1.00 limit. Round-trip costs add 0.10.
    decision = decide(order(notional=Decimal("50"), stop_price=Decimal("98.1")))
    assert decision.price_loss == Decimal("0.95")
    assert decision.fee_loss == Decimal("0.05")
    assert decision.slippage_loss == Decimal("0.05")
    assert decision.planned_loss == Decimal("1.05")
    assert decision.status == "REJECT"
    assert "planned_risk" in decision.reasons
    assert "fees_and_slippage_included" not in decision.reasons


def test_zero_cost_request_is_floored_at_the_configured_assumption() -> None:
    decision = decide(
        order(
            notional=Decimal("50"),
            stop_price=Decimal("99.5"),
            fee_bps_round_trip=Decimal("0"),
            slippage_bps_round_trip=Decimal("0"),
        )
    )
    assert decision.status == "PASS"
    assert decision.assumed_fee_bps == Decimal("10")
    assert decision.assumed_slippage_bps == Decimal("10")
    assert decision.fee_loss == Decimal("0.05")
    assert decision.slippage_loss == Decimal("0.05")


def test_daily_loss_stop_blocks_at_exactly_three_percent() -> None:
    blocked = decide(book=account(realized_pnl_today=Decimal("-3")))
    assert blocked.status == "REJECT"
    assert "daily_loss_limit" in blocked.reasons

    open_book = decide(
        order(client_order_id="ord-2"),
        book=account(realized_pnl_today=Decimal("-2.99")),
    )
    assert open_book.status == "PASS"


def test_daily_loss_does_not_block_a_reduce() -> None:
    decision = decide(
        order(order_kind="reduce", stop_price=None),
        book=account(realized_pnl_today=Decimal("-50"), open_position_count=1),
    )
    assert decision.status == "PASS"
    assert "daily_loss_limit" not in decision.reasons


def test_kill_switch_blocks_new_orders() -> None:
    decision = decide(kill=True)
    assert decision.status == "REJECT"
    assert "kill_switch" in decision.reasons

    reduce = decide(order(order_kind="reduce", stop_price=None), kill=True)
    assert reduce.status == "REJECT"
    assert "kill_switch" in reduce.reasons


def test_duplicate_client_order_id() -> None:
    decision = decide(seen={"ord-1"})
    assert decision.status == "REJECT"
    assert decision.reasons == ["duplicate_client_order_id"]


def test_stale_and_missing_market_data() -> None:
    stale = decide(order(market_data_time=NOW - timedelta(seconds=5.001)))
    assert stale.status == "REJECT"
    assert "stale_market_data" in stale.reasons

    fresh = decide(order(market_data_time=NOW - timedelta(seconds=5)))
    assert fresh.status == "PASS"

    missing = decide(order(market_data_time=None))
    assert missing.status == "REJECT"
    assert "missing_market_data" in missing.reasons

    ahead = decide(order(market_data_time=NOW + timedelta(seconds=10)))
    assert ahead.status == "REJECT"
    assert "stale_market_data" in ahead.reasons


def test_minimum_notional_and_explicit_fx_rate() -> None:
    tiny = decide(order(notional=Decimal("9.99")))
    assert tiny.status == "REJECT"
    assert "min_notional" in tiny.reasons

    chf_engine = engine(account_currency="CHF", min_order_notional=Decimal("10"), min_order_notional_currency="USD")
    book = account(currency="CHF")
    unverified = chf_engine.evaluate(
        order(notional=Decimal("20"), notional_currency="CHF", usd_per_notional_currency=None),
        book,
        now=NOW,
        kill_switch_engaged=False,
        seen_client_order_ids=set(),
    )
    assert unverified.status == "REJECT"
    assert "min_notional_unverified" in unverified.reasons

    below = chf_engine.evaluate(
        order(
            client_order_id="chf-low",
            notional=Decimal("8"),
            notional_currency="CHF",
            usd_per_notional_currency=Decimal("1.1"),
        ),
        book,
        now=NOW,
        kill_switch_engaged=False,
        seen_client_order_ids=set(),
    )
    assert below.status == "REJECT"
    assert "min_notional" in below.reasons

    clears = chf_engine.evaluate(
        order(
            client_order_id="chf-ok",
            notional=Decimal("20"),
            notional_currency="CHF",
            usd_per_notional_currency=Decimal("1.1"),
        ),
        book,
        now=NOW,
        kill_switch_engaged=False,
        seen_client_order_ids=set(),
    )
    assert clears.status == "PASS"


def test_leverage_must_equal_one() -> None:
    decision = decide(order(leverage=Decimal("2")))
    assert decision.status == "REJECT"
    assert "leverage" in decision.reasons


def test_position_and_entry_caps() -> None:
    second_position = decide(book=account(open_position_count=1))
    assert second_position.status == "REJECT"
    assert "max_open_positions" in second_position.reasons

    third_entry = decide(book=account(entries_today=2))
    assert third_entry.status == "REJECT"
    assert "max_daily_entries" in third_entry.reasons

    still_allowed = decide(order(client_order_id="second"), book=account(entries_today=1))
    assert still_allowed.status == "PASS"


def test_cash_above_equity_is_rejected() -> None:
    decision = decide(order(notional=Decimal("100"), stop_price=Decimal("99.9")))
    assert decision.status == "REJECT"
    assert "insufficient_balance" in decision.reasons


def test_invalid_stop_and_disabled_venue() -> None:
    bad_stop = decide(order(stop_price=Decimal("101")))
    assert bad_stop.status == "REJECT"
    assert "invalid_stop" in bad_stop.reasons

    other_venue = decide(order(venue="solana"))
    assert other_venue.status == "REJECT"
    assert "venue_not_enabled" in other_venue.reasons
