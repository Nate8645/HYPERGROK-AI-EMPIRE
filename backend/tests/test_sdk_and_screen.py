"""SDK 1.8.4 surface and the public-candle screen. No network and no orders."""

import inspect
import json
from decimal import Decimal
from pathlib import Path

from coinbase.rest import RESTClient

from hypergrok.research_screen import screen_product

ROOT = Path(__file__).resolve().parents[2]


def test_broker_calls_match_sdk_1_8_4_signatures() -> None:
    expected = {
        "market_order": {"client_order_id", "product_id", "side", "quote_size", "base_size"},
        "limit_order_gtc": {"client_order_id", "product_id", "side", "base_size", "limit_price", "post_only"},
        "preview_market_order": {"product_id", "side", "quote_size", "base_size"},
        "preview_limit_order_gtc": {"product_id", "side", "base_size", "limit_price", "post_only"},
        "preview_stop_limit_order_gtc": {"product_id", "side", "base_size", "limit_price", "stop_price", "stop_direction"},
        "get_order": {"order_id"},
        "cancel_orders": {"order_ids"},
        "get_api_key_permissions": set(),
    }
    for name, used in expected.items():
        parameters = set(inspect.signature(getattr(RESTClient, name)).parameters) - {"self", "kwargs"}
        assert used <= parameters
        assert "leverage" not in used


def test_public_daily_screen_is_no_trade() -> None:
    candles = json.loads((ROOT / "docs/research/coinbase-candles-2026-11-09.json").read_text(encoding="utf-8"))
    book = json.loads((ROOT / "backend/tests/fixtures/coinbase_read_2026-11-09.json").read_text(encoding="utf-8"))
    report = screen_product(
        candles["products"]["BTC-USD"]["daily"],
        book=book["btc_usdc_book"],
        capital=Decimal("10.896768"),
        fee_rate=Decimal("0.001"),
        slippage_rate=Decimal("0.001"),
    )
    assert report["outcome"] == "NO TRADE"
    assert report["indicators"]["rsi"]
    assert report["indicators"]["macd"]
    assert report["indicators"]["ema_fast"]
    assert report["indicators"]["atr"]
    assert report["indicators"]["vwap"] == "Keine Daten"
    assert report["liquidity"]["spread_bps"]
    assert any(row["fraction"] == "fixed_100" and row["fits_1_percent"] is False for row in report["strategies"])
    assert all(row["robust"] is False for row in report["strategies"])
