"""API and pipeline connected through one app. No network and no live orders."""

from datetime import datetime, timezone
from decimal import Decimal

from hypergrok.domain import MarketSnapshot, ResearchInput
from hypergrok.pipeline import run_preview_pipeline
from tests.support import explicit_fx, fitting_idea, seed_spot_product


def test_health_agents_desk_and_pipeline_share_one_database(client) -> None:
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["live_trading_enabled"] is False
    assert health.json()["transmits_orders"] is False

    agents = client.get("/api/agents/status").json()["agents"]
    assert len(agents) == 7
    assert {agent["mode"] for agent in agents} == {"rule_based"}

    status = client.get("/api/coinbase/status").json()
    assert status["configured"] is False
    assert status["live_armed"] is False
    assert status["max_capital"] == "0"
    assert "private" not in status

    now = datetime.now(timezone.utc)
    seed_spot_product(client.app.state.store, "BTC-USD", now)
    seed_spot_product(client.app.state.store, "ETH-USD", now)
    idea_body = {
        "symbol": "BTC-USD",
        "venue": "coinbase",
        "side": "buy",
        "thesis": "Connected desk run uses the labelled book only.",
        "size_mode": "risk_limited",
        "client_order_id": "integration-1",
        "request_live": True,
        "usd_per_notional_currency": "1",
        "fx_source": "explicit_config",
        "fx_as_of": now.isoformat(),
        "fee_bps_round_trip": "20",
        "slippage_bps_round_trip": "10",
        "market_snapshot": {
            "source": "coinbase_advanced_trade",
            "symbol": "BTC-USD",
            "fetched_at": now.isoformat(),
            "raw_type": "product_book",
            "mid": "65000",
            "bid": "64990",
            "ask": "65010",
            "bid_size": "5",
            "ask_size": "1",
        },
        "research": {"trend": "up", "funding_bps": "1"},
    }
    ran = client.post("/api/desk/run", json=idea_body)
    assert ran.status_code == 200
    body = ran.json()
    assert body["risk"]["status"] == "PASS"
    assert body["execution"]["transmitted"] is False
    assert body["execution"]["gate_reason"] == "live_trading_disabled"

    candles = []
    for i in range(40):
        price = 100 + i
        candles.append(
            {
                "high": str(price + 1),
                "low": str(price - 1),
                "close": str(price),
                "volume": "1",
                "time": now.isoformat(),
                "fetched_at": now.isoformat(),
            }
        )
    preview = run_preview_pipeline(
        client.app.state.orchestrator,
        fitting_idea(
            now,
            symbol="ETH-USD",
            venue="coinbase",
            client_order_id="integration-preview",
            research=ResearchInput(trend="up", funding_bps=Decimal("1")),
            **explicit_fx(now),
            fee_bps_round_trip=Decimal("20"),
            slippage_bps_round_trip=Decimal("10"),
            market_snapshot=MarketSnapshot(
                source="coinbase_advanced_trade",
                symbol="ETH-USD",
                fetched_at=now,
                raw_type="product_book",
                mid=Decimal("3000"),
                bid=Decimal("2999"),
                ask=Decimal("3001"),
                bid_size=Decimal("3"),
                ask_size=Decimal("2"),
            ),
        ),
        candles=candles,
        now=now,
    )
    assert preview["halted"] is False
    assert preview["run"].execution.transmitted is False
    journal = client.get("/api/journal").json()["entries"]
    assert any(row["outcome"] == "review_metrics" for row in journal)
    assert any(row["case_id"] == body["case_id"] for row in journal)
