from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hypergrok.backtest import evaluate_splits, overfitting_warning, run_backtest, score_trades
from hypergrok.indicators import atr, book_metrics, ema, macd, multi_timeframe_trend, rsi, support_resistance, vwap
from hypergrok.research_rules import check_data_quality, conflicting_signals, detect_regime


def test_ema_rsi_and_vwap_match_hand_calculations() -> None:
    values = [Decimal(str(item)) for item in (1, 2, 3, 4)]
    line = ema(values, 3)
    assert line[2] == Decimal("2")
    assert line[3] == Decimal("3")

    rsi_values = [Decimal(str(item)) for item in (1, 2, 3, 2, 3)]
    score = rsi(rsi_values, 3)
    assert score[3] == Decimal("100") - (Decimal("100") / Decimal("3"))
    assert abs(score[4] - (Decimal("100") - (Decimal("100") / Decimal("4.5")))) < Decimal("0.0000001")

    candles = [
        {"high": "12", "low": "8", "close": "10", "volume": "2"},
        {"high": "14", "low": "10", "close": "12", "volume": "1"},
    ]
    # typical 10 and 12; pv = 20 + 12 = 32; volume 3; vwap = 32/3
    assert vwap(candles) == Decimal("32") / Decimal("3")


def test_macd_is_the_difference_of_emas_and_atr_uses_true_range() -> None:
    values = [Decimal(i) for i in range(1, 40)]
    pack = macd(values, fast=3, slow=6, signal=3)
    fast = ema(values, 3)
    slow = ema(values, 6)
    assert pack["macd"][-1] == fast[-1] - slow[-1]
    candles = [
        {"high": "10", "low": "8", "close": "9"},
        {"high": "12", "low": "9", "close": "11"},
    ]
    # true ranges: 2, max(3, 3, 0) = 3. period 2 average = 2.5
    assert atr(candles, 2)[-1] == Decimal("2.5")


def test_support_book_and_timeframe() -> None:
    candles = []
    for price in (5, 4, 3, 4, 5, 6, 5, 4, 5):
        candles.append({"high": str(price + 1), "low": str(price - 1), "close": str(price)})
    levels = support_resistance(candles, 2)
    assert levels["support"]
    metrics = book_metrics(Decimal("100"), Decimal("101"), Decimal("2"), Decimal("1"), [{"size": "4"}, {"size": "1"}])
    assert metrics["spread_bps"] > 0
    assert metrics["depth"] == Decimal("5")
    up = [Decimal(i) for i in range(1, 40)]
    down = list(reversed(up))
    assert multi_timeframe_trend(up, down) == "conflict"


def test_backtest_costs_splits_and_overfit_warning() -> None:
    rising = [{"high": str(i + 1), "low": str(i - 1), "close": str(i), "volume": "1"} for i in range(30, 120)]
    result = run_backtest(rising, "momentum", fee_bps=Decimal("10"), slippage_bps=Decimal("0"), use_vol_filter=False)
    assert result["trades"] >= 1
    scored = score_trades([{"return": Decimal("0.1")} for _ in range(10)])
    assert scored["sharpe"] is None
    assert scored["sharpe_sample_sufficient"] is False
    scored_large = score_trades([{"return": Decimal("0.01") if i % 2 == 0 else Decimal("-0.005")} for i in range(30)])
    assert scored_large["sharpe"] is not None
    warning = overfitting_warning(
        {"trades": 30, "expectancy": Decimal("0.05")},
        {"trades": 10, "expectancy": Decimal("0.001")},
    )
    assert warning == "in_sample_gap"
    folds = evaluate_splits(rising, "ema_cross", fee_bps=Decimal("10"), slippage_bps=Decimal("0"), use_vol_filter=False)
    assert set(folds["splits"]) == {"train", "validation", "test"}


def test_regime_quality_and_conflicts() -> None:
    now = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)
    candles = []
    for i in range(40):
        price = 100 + i
        candles.append(
            {
                "high": str(price + 1),
                "low": str(price - 1),
                "close": str(price),
                "volume": "2",
                "time": (now - timedelta(minutes=40 - i)).isoformat(),
                "fetched_at": now.isoformat(),
            }
        )
    assert detect_regime(candles) in {"trend", "high_volatility", "range"}
    quality = check_data_quality(candles, now=now, max_age_seconds=120, source="coinbase_public_candles")
    assert quality["ok"] is True
    assert quality["source"] == "coinbase_public_candles"
    stale = check_data_quality(
        [{**candles[-1], "fetched_at": (now - timedelta(hours=2)).isoformat()}],
        now=now,
        max_age_seconds=60,
        source="coinbase_public_candles",
    )
    assert "stale_market_data" in stale["problems"]
    assert "market_long_research_short" in conflicting_signals(
        market_bias="long", research_stance="support_short", strategy_signal="flat"
    )
