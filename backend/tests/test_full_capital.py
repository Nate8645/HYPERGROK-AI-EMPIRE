"""Full-capital simulation. The 1% loss rule is not replaced, and nothing is sent."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from hypergrok.agents.risk_manager import risk_passed
from hypergrok.config import Settings
from hypergrok.domain import MarketSnapshot
from hypergrok.risk.full_capital import assess_full_capital, full_capital_size
from hypergrok.venues.coinbase.autonomy import autonomous_armed, autonomous_blockers
from hypergrok.venues.coinbase.exits import monitor_open_position
from tests.support import make_settings
from tests.test_coinbase import FakeCoinbase, _app

BALANCE = Decimal("10.896768")
ROOT = Path(__file__).resolve().parents[2]
CANDLES = json.loads((ROOT / "docs" / "research" / "coinbase-candles-2026-11-09.json").read_text(encoding="utf-8"))
READ = json.loads((ROOT / "backend" / "tests" / "fixtures" / "coinbase_read_2026-11-09.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 11, 9, 20, 50, tzinfo=timezone.utc)


def test_size_reserves_both_fees_and_rounds_down() -> None:
    sized = full_capital_size(BALANCE, Decimal("0.001"), Decimal("0.001"), Decimal("0.01"))
    assert sized["size"] == Decimal("10.87")
    assert sized["entry_fee"] == Decimal("0.01087")
    assert sized["exit_fee"] == Decimal("0.01087")
    assert sized["fee_reserve"] == Decimal("0.02174")
    assert sized["remainder"] == Decimal("0.005028")
    assert sized["size"] + sized["fee_reserve"] <= BALANCE
    larger = sized["size"] + Decimal("0.01")
    assert larger + larger * Decimal("0.002") > BALANCE
    assert sized["borrowed"] == Decimal("0")
    assert sized["leverage"] == Decimal("1")
    assert sized["max_open_positions"] == 1
    settings = Settings(_env_file=None)
    assert settings.max_planned_risk_fraction == Decimal("0.01")
    assert settings.max_leverage == Decimal("1")
    assert settings.max_open_positions == 1
    assert settings.simulation_max_capital_fraction == Decimal("1")
    assert settings.autonomous_enabled is False


def test_real_candle_sample_is_checked_without_recording_a_pass() -> None:
    product = CANDLES["products"]["BTC-USD"]
    book = READ["btc_usdc_book"]
    bid = Decimal(book["bids"][0]["price"])
    ask = Decimal(book["asks"][0]["price"])
    app = _app(account_currency="USDC", starting_capital=BALANCE, min_order_notional=Decimal("1"), min_order_notional_currency="USDC")
    result = app.state.orchestrator.risk_manager.review_full_capital(
        balance=BALANCE,
        entry_fee_rate=Decimal(READ["fee_tier"]["taker_fee_rate"]),
        exit_fee_rate=Decimal(READ["fee_tier"]["taker_fee_rate"]),
        spread_rate=(ask - bid) / ((ask + bid) / 2),
        slippage_rate=Decimal("0.001"),
        minute_candles=product["minute"],
        daily_candles=product["daily"],
        max_loss_fraction=Decimal("0.01"),
        quote_increment=Decimal("0.01"),
        capital_fraction=Decimal("1"),
    )
    assert result["size"] == "10.87"
    assert result["limits_replaced"] is False
    assert result["max_loss_fraction"] == "0.01"
    assert result["pass_recorded"] is False
    assert result["status"] in {"PASS", "REJECT"}
    assert Decimal(result["required_stop_fraction"])
    for key in ("loss_at_stop", "loss_at_typical_overshoot", "loss_at_worst_historical_move", "total_loss"):
        assert Decimal(result[key]) >= 0
    daily_share = Decimal(result["overshoot_frequency"]["daily_gap"])
    minute_share = Decimal(result["overshoot_frequency"]["minute_gap_or_stale"])
    if daily_share >= Decimal("0.05") or minute_share >= Decimal("0.05"):
        assert "overshoot_breaches_risk" in result["reasons"]
        assert result["status"] == "REJECT"
    assert risk_passed("not-an-order") is False
    assert product["minute"][0]["time"] < product["minute"][-1]["time"]
    assert len(product["daily"]) == 350


def test_noise_and_overshoot_rules_reject_on_synthetic_bars() -> None:
    quiet = [{"open": "100", "high": "100.01", "low": "99.99", "close": "100"} for _ in range(30)]
    noisy = []
    for index in range(30):
        close = 100 - index
        noisy.append({"open": str(close + 5), "high": str(close + 5), "low": str(close), "close": str(close)})
    tight = assess_full_capital(
        balance=Decimal("100"),
        entry_fee_rate=Decimal("0.02"),
        exit_fee_rate=Decimal("0.02"),
        spread_rate=Decimal("0.02"),
        slippage_rate=Decimal("0.02"),
        minute_candles=quiet,
        daily_candles=quiet,
        max_loss_fraction=Decimal("0.01"),
    )
    assert tight["status"] == "REJECT"
    assert "stop_tighter_than_noise" in tight["reasons"]
    breached = assess_full_capital(
        balance=Decimal("100"),
        entry_fee_rate=Decimal("0"),
        exit_fee_rate=Decimal("0"),
        spread_rate=Decimal("0"),
        slippage_rate=Decimal("0"),
        minute_candles=quiet,
        daily_candles=noisy,
        max_loss_fraction=Decimal("0.01"),
    )
    assert breached["status"] == "REJECT"
    assert "overshoot_breaches_risk" in breached["reasons"]


def test_missing_history_rejects() -> None:
    result = assess_full_capital(
        balance=BALANCE,
        entry_fee_rate=Decimal("0.001"),
        exit_fee_rate=Decimal("0.001"),
        spread_rate=Decimal("0"),
        slippage_rate=Decimal("0"),
        minute_candles=[],
        daily_candles=[],
    )
    assert result["status"] == "REJECT"
    assert result["required_stop_fraction"] == "Keine Daten"


def test_autonomous_mode_stays_locked_until_every_field_is_valid() -> None:
    assert "autonomous_disabled" in autonomous_blockers(make_settings(), NOW)
    assert autonomous_armed(make_settings(), NOW) is False
    complete = dict(
        autonomous_enabled=True,
        autonomous_max_loss_per_trade=Decimal("0.20"),
        autonomous_max_loss_per_day=Decimal("0.60"),
        autonomous_max_loss_total=Decimal("2"),
        autonomous_max_deployed_capital=BALANCE,
        autonomous_allowed_pairs="BTC-USDC,ETH-USDC,SOL-USDC",
        autonomous_expires_at=NOW + timedelta(days=1),
        autonomous_max_slippage_bps=Decimal("10"),
        autonomous_kill_switch_conditions="manual_halt, daily_loss, stale_data, feed_outage",
    )
    assert autonomous_armed(make_settings(**complete), NOW) is True
    for field in (
        "autonomous_max_loss_per_trade",
        "autonomous_max_loss_per_day",
        "autonomous_max_loss_total",
        "autonomous_max_deployed_capital",
        "autonomous_expires_at",
        "autonomous_max_slippage_bps",
    ):
        broken = dict(complete)
        broken[field] = None
        assert autonomous_armed(make_settings(**broken), NOW) is False
    assert autonomous_armed(make_settings(**{**complete, "autonomous_allowed_pairs": ""}), NOW) is False
    assert autonomous_armed(make_settings(**{**complete, "autonomous_allowed_pairs": "not a pair"}), NOW) is False
    assert autonomous_armed(make_settings(**{**complete, "autonomous_max_slippage_bps": Decimal("-1")}), NOW) is False
    assert autonomous_armed(make_settings(**{**complete, "autonomous_kill_switch_conditions": "manual_halt"}), NOW) is False
    assert autonomous_armed(make_settings(**{**complete, "autonomous_expires_at": NOW - timedelta(seconds=1)}), NOW) is False
    assert autonomous_armed(make_settings(**{**complete, "autonomous_enabled": False}), NOW) is False
    assert Settings(_env_file=None).autonomous_enabled is False


def test_exit_preview_respects_feed_stale_data_and_kill_switch() -> None:
    calls = []

    def preview(order):
        calls.append(order["order_type"])
        return {"rejected": False, "source": "fixture"}

    app = _app()
    manager = app.state.orchestrator.risk_manager
    fresh = MarketSnapshot(
        source="coinbase_advanced_trade",
        symbol="BTC-USD",
        fetched_at=NOW,
        raw_type="product_book",
        mid=Decimal("100"),
        bid=Decimal("98"),
        ask=Decimal("100"),
        bid_size=Decimal("1"),
        ask_size=Decimal("1"),
    )
    common = dict(
        quantity=Decimal("0.2"),
        entry_price=Decimal("100"),
        stop_price=Decimal("99"),
        take_profit_price=Decimal("120"),
        time_stop_at=NOW + timedelta(hours=1),
        now=NOW,
        max_age_seconds=60,
        currency="USD",
        risk_manager=manager,
        store=app.state.store,
        preview=preview,
    )
    outage = monitor_open_position(**common, snapshot=None, feed_error="timeout")
    assert outage["reason"] == "feed_outage"
    assert outage["submitted"] is False
    assert calls == []
    stale_snapshot = fresh.model_copy(update={"fetched_at": NOW - timedelta(minutes=5)})
    stale = monitor_open_position(**common, snapshot=stale_snapshot, feed_error=None)
    assert stale["reason"] == "stale_market_data"
    assert calls == []
    app.state.store.set_kill_switch(engaged=True, reason="halt", updated_by="test", now=NOW)
    halted = monitor_open_position(**common, snapshot=fresh, feed_error=None)
    assert halted["risk_status"] == "REJECT"
    assert "kill_switch" in halted["risk_reasons"]
    assert halted["submitted"] is False
    assert calls == []
    app.state.store.set_kill_switch(engaged=False, reason="resume", updated_by="test", now=NOW)
    exited = monitor_open_position(**common, snapshot=fresh, feed_error=None)
    assert exited["reason"] == "stop"
    assert exited["risk_status"] == "PASS"
    assert exited["submitted"] is False
    assert calls == ["stop_limit"]
    assert exited["approval"]["client_order_id"]


def test_final_seven_agent_preview_does_not_submit() -> None:
    fake = FakeCoinbase()
    app = _app(fake, account_currency="USD", starting_capital=Decimal("1000"))
    with TestClient(app) as client:
        body = client.post(
            "/api/desk/team",
            json={
                "symbol": "BTC-USD",
                "venue": "coinbase",
                "side": "buy",
                "thesis": "Bid-heavy book and a supplied uptrend.",
                "size_mode": "risk_limited",
                "client_order_id": "final-team",
                "request_live": True,
                "fee_bps_round_trip": "20",
                "slippage_bps_round_trip": "10",
                "market_snapshot": {
                    "source": "coinbase_advanced_trade",
                    "symbol": "BTC-USD",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                    "raw_type": "product_book",
                    "mid": "65000",
                    "bid": "64990",
                    "ask": "65010",
                    "bid_size": "5",
                    "ask_size": "1",
                },
                "research": {"trend": "up", "funding_bps": "1"},
            },
        ).json()
        from hypergrok.pipeline import run_final_preview_case
        from hypergrok.domain import DeskIdea, ResearchInput

        final = run_final_preview_case(
            app.state.orchestrator,
            DeskIdea(
                symbol="BTC-USD",
                venue="coinbase",
                side="buy",
                thesis="Bid-heavy book and a supplied uptrend.",
                size_mode="risk_limited",
                client_order_id="final-order",
                request_live=True,
                fee_bps_round_trip=Decimal("20"),
                slippage_bps_round_trip=Decimal("10"),
                market_snapshot=MarketSnapshot(
                    source="coinbase_advanced_trade",
                    symbol="BTC-USD",
                    fetched_at=datetime.now(timezone.utc),
                    raw_type="product_book",
                    mid=Decimal("65000"),
                    bid=Decimal("64990"),
                    ask=Decimal("65010"),
                    bid_size=Decimal("5"),
                    ask_size=Decimal("1"),
                ),
                research=ResearchInput(trend="up", funding_bps=Decimal("1")),
            ),
        )
    assert [row["agent"] for row in body["agents"]] == [
        "desk_lead",
        "market_analyst",
        "research_analyst",
        "strategist",
        "risk_manager",
        "execution_trader",
        "trade_reviewer",
    ]
    assert body["submitted"] is False
    assert "market_order" not in fake.calls
    assert final["agent_order"] == [
        "market_analyst",
        "research_analyst",
        "strategist",
        "desk_lead",
        "risk_manager",
        "execution_trader",
        "trade_reviewer",
    ]
    assert final["submitted"] is False
    assert final["execution_transmitted"] is False
    assert final["live_preview"] == "Keine Daten"
    assert final["mode"] == "fixture-based"
    assert final["planned_order_size"] is not None
    assert Decimal(final["max_loss"]) <= Decimal("1000") * Decimal("0.01")
    assert "market_order" not in fake.calls
