from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from hypergrok.main import create_app
from hypergrok.trial import run_simulated_trial
from tests.support import login, make_settings

NOW = datetime(2026, 11, 9, 21, 35, tzinfo=timezone.utc)


def _books() -> dict:
    return {
        "BTC-USDC": {
            "best_bid": "74882.08",
            "best_ask": "74882.09",
            "spread_bps": "0.001335",
            "bid_depth_20": "0.82722011",
            "ask_depth_20": "2.02413541",
        }
    }


def test_simulated_trial_steps_down_and_blocks_the_kill_switch() -> None:
    report = run_simulated_trial(
        books=_books(),
        research_trends={"BTC-USDC": "down"},
        as_of=NOW,
        balance_source="fixture: labeled test balance, not a live order",
        screen_outcome="NO TRADE",
    )
    assert report["label"] == "SIMULATED"
    assert report["real_trade"] is False
    assert report["transmitted"] is False
    assert report["order_preview"] == "NOT RUN"
    assert report["decision"] == "NO TRADE"
    assert report["flags"] == {
        "LIVE_TRADING_ENABLED": False,
        "COINBASE_LIVE_ENABLED": False,
        "AUTONOMOUS_ENABLED": False,
    }
    full = next(row for row in report["size_ladder"] if row["fraction"] == "1")
    assert full["fits_one_percent"] is False
    largest = Decimal(report["largest_size_within_one_percent"])
    assert largest < Decimal("10")
    assert largest < Decimal(full["notional"])
    assert report["mock_buy"]["transmitted"] is False
    assert report["mock_sell"]["transmitted"] is False
    assert report["mock_buy"]["label"] == "SIMULATED"
    assert report["kill_switch"]["blocked"] is True
    agents = report["cases"][0]["agents"]
    assert [row["agent"] for row in agents] == [
        "desk_lead",
        "market_analyst",
        "research_analyst",
        "strategist",
        "risk_manager",
        "execution_trader",
        "trade_reviewer",
    ]
    assert all(row["status"] for row in agents)
    assert report["cases"][0]["transmitted"] is False


def test_simulated_trial_route_requires_auth_and_stays_labelled() -> None:
    app = create_app(make_settings())
    with TestClient(app) as client:
        denied = client.get("/api/desk/simulated-trial")
        assert denied.status_code == 401
        login(client)
        body = client.get("/api/desk/simulated-trial").json()
    assert body["label"] == "SIMULATED"
    assert body.get("real_trade") is False
    assert body["order_preview"] == "NOT RUN"
