"""Coinbase spot uses the cached product. It does not fall back to 10 USD."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hypergrok.domain import AccountState, OrderIntent
from hypergrok.risk.engine import RiskEngine
from hypergrok.venues.coinbase.products import verified_usdc_product
from tests.support import make_settings

NOW = datetime(2026, 11, 9, 21, 40, tzinfo=timezone.utc)


def _engine() -> RiskEngine:
    return RiskEngine(make_settings(account_currency="USDC", starting_capital=Decimal("10.896768"), max_product_metadata_age_seconds=300))


def _account() -> AccountState:
    return AccountState(
        currency="USDC",
        equity=Decimal("10.896768"),
        start_of_day_equity=Decimal("10.896768"),
        realized_pnl_today=Decimal("0"),
        open_position_count=0,
        entries_today=0,
        trading_day="2026-11-09",
    )


def _order(**overrides) -> OrderIntent:
    values = dict(
        client_order_id="min-1",
        venue="coinbase",
        symbol="BTC-USDC",
        side="buy",
        notional=Decimal("2.05"),
        notional_currency="USDC",
        leverage=Decimal("1"),
        entry_price=Decimal("74882.08"),
        stop_price=Decimal("71138"),
        market_data_time=NOW,
        fee_bps_round_trip=Decimal("10"),
        slippage_bps_round_trip=Decimal("10"),
    )
    values.update(overrides)
    return OrderIntent(**values)


def _decide(order: OrderIntent, product=None):
    return _engine().evaluate(
        order,
        _account(),
        now=NOW,
        kill_switch_engaged=False,
        seen_client_order_ids=set(),
        product=product,
    )


def test_usdc_product_minimum_replaces_the_ten_dollar_floor() -> None:
    product = verified_usdc_product("BTC-USDC", "BTC", NOW, source="verified_fixture")
    allowed = _decide(_order(notional=Decimal("1.00")), product)
    assert allowed.status == "PASS"
    assert allowed.fee_loss == Decimal("1.00") * Decimal("0.002")
    blocked = _decide(_order(client_order_id="min-low", notional=Decimal("0.99")), product)
    assert blocked.status == "REJECT"
    assert "min_notional" in blocked.reasons
    assert "10 USD" not in blocked.summary


def test_notional_is_rounded_down_to_the_quote_increment() -> None:
    product = verified_usdc_product("ETH-USDC", "ETH", NOW, source="verified_fixture")
    decision = _decide(
        _order(symbol="ETH-USDC", client_order_id="round-1", notional=Decimal("1.019"), entry_price=Decimal("2130"), stop_price=Decimal("2023.5")),
        product,
    )
    increment = next(check for check in decision.checks if check.rule == "quote_increment")
    assert "1.01" in increment.detail
    assert decision.status == "PASS"


def test_missing_or_stale_product_data_rejects_without_a_default() -> None:
    missing = _decide(_order())
    assert missing.status == "REJECT"
    assert "missing_product_data" in missing.reasons
    assert "10 USD" not in missing.summary
    stale_product = verified_usdc_product("BTC-USDC", "BTC", NOW - timedelta(hours=2), source="verified_fixture")
    stale = _decide(_order(client_order_id="stale-1"), stale_product)
    assert stale.status == "REJECT"
    assert "stale_product_data" in stale.reasons


def test_non_usdc_quote_requires_a_verified_rate() -> None:
    from hypergrok.venues.coinbase.products import SpotProduct

    product = SpotProduct(
        product_id="BTC-EUR",
        quote_currency="EUR",
        base_currency="BTC",
        quote_min_size=Decimal("1"),
        base_min_size=Decimal("0.00000001"),
        quote_increment=Decimal("0.01"),
        base_increment=Decimal("0.00000001"),
        taker_fee_rate=Decimal("0.001"),
        maker_fee_rate=Decimal("0.0009"),
        source="test_fixture",
        fetched_at=NOW,
    )
    engine = RiskEngine(make_settings(account_currency="EUR", max_product_metadata_age_seconds=300))
    account = _account().model_copy(update={"currency": "EUR"})
    bare = _order(symbol="BTC-EUR", notional_currency="EUR", notional=Decimal("1.20"), entry_price=Decimal("100"), stop_price=Decimal("99"))
    rejected = engine.evaluate(bare, account, now=NOW, kill_switch_engaged=False, seen_client_order_ids=set(), product=product)
    assert rejected.status == "REJECT"
    assert "missing_fx_rate" in rejected.reasons
    verified = bare.model_copy(
        update={
            "client_order_id": "eur-ok",
            "usd_per_notional_currency": Decimal("1.08"),
            "fx_source": "explicit_config",
            "fx_as_of": NOW,
        }
    )
    # Quote and notional are both EUR, so the verified rate allows the product minimum of 1.
    accepted = engine.evaluate(verified, account, now=NOW, kill_switch_engaged=False, seen_client_order_ids=set(), product=product)
    assert accepted.status == "PASS"


def test_maker_fee_is_reserved_on_both_sides_when_post_only() -> None:
    product = verified_usdc_product("SOL-USDC", "SOL", NOW, source="verified_fixture")
    decision = _decide(
        _order(symbol="SOL-USDC", client_order_id="maker-1", notional=Decimal("2"), entry_price=Decimal("86"), stop_price=Decimal("81.7"), post_only=True),
        product,
    )
    assert decision.fee_loss == Decimal("2") * Decimal("0.0018")


def test_hyperliquid_keeps_the_ten_dollar_minimum() -> None:
    from tests.test_risk_engine import decide, order

    tiny = decide(order(notional=Decimal("9.99")))
    assert tiny.status == "REJECT"
    assert "min_notional" in tiny.reasons
