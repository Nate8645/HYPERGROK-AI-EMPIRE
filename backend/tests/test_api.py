import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from hypergrok.agents.catalog import AGENTS
from hypergrok.config import Settings
from hypergrok.main import create_app
from tests.support import auth_overrides, authed, fitting_idea, make_settings, sample_order


def test_default_paper_account_is_20_chf_and_needs_an_explicit_usd_rate() -> None:
    app = create_app(Settings(_env_file=None, database_url="sqlite://", **auth_overrides()))
    with authed(app) as client:
        account = client.get("/api/risk/account").json()
        assert account["currency"] == "CHF"
        assert account["equity"] == "20"
        assert client.get("/health").json()["live_trading_enabled"] is False

        unverified = client.post(
            "/api/risk/evaluate",
            json=sample_order("chf-no-fx", notional="15", notional_currency="CHF"),
        ).json()
        assert unverified["status"] == "REJECT"
        assert "min_notional_unverified" in unverified["reasons"]

        priced = client.post(
            "/api/risk/evaluate",
            json=sample_order(
                "chf-with-fx",
                notional="15",
                notional_currency="CHF",
                usd_per_notional_currency="1.13",
            ),
        ).json()
        assert priced["status"] == "PASS"
        assert Decimal(priced["free_collateral_after"]) >= Decimal("4")


def test_health_reports_phase1_and_no_transmission(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["phase"] == 1
    assert body["implementation"] == "rule_based"
    assert body["live_trading_enabled"] is False
    assert body["transmits_orders"] is False
    assert body["database"] == "ok"
    assert body["kill_switch_engaged"] is False


def test_agent_status_lists_seven_rule_based_agents(client) -> None:
    response = client.get("/api/agents/status")
    assert response.status_code == 200
    agents = response.json()["agents"]
    assert [agent["key"] for agent in agents] == [spec.key for spec in AGENTS]
    assert {agent["mode"] for agent in agents} == {"rule_based"}
    assert {agent["status"] for agent in agents} == {"idle"}


def test_risk_config_exposes_the_running_limits(client, settings) -> None:
    body = client.get("/api/risk/config").json()
    assert body["max_leverage"] == "1"
    assert body["max_planned_risk_fraction"] == "0.01"
    assert body["max_daily_loss_fraction"] == "0.03"
    assert body["max_open_positions"] == 1
    assert body["max_new_entries_per_day"] == 2
    assert body["hyperliquid_reserve_fraction"] == "0.2" or body["hyperliquid_reserve_fraction"] == "0.20"
    assert Decimal(body["hyperliquid_reserve_fraction"]) == Decimal("0.20")
    assert body["min_order_notional"] == "10"
    assert body["min_order_notional_currency"] == "USD"
    assert body["live_trading_enabled"] is False
    assert body["transmits_orders"] is False
    assert body["account_currency"] == settings.account_currency
    assert Decimal(body["starting_capital"]) == settings.starting_capital


def test_websocket_receives_kill_switch_events(client) -> None:
    with client.websocket_connect("/ws/events") as socket:
        hello = socket.receive_json()
        assert hello["type"] == "ws.connected"
        assert hello["transmits_orders"] is False
        response = client.post(
            "/api/risk/kill-switch",
            json={"engaged": True, "reason": "maintenance", "updated_by": "human"},
        )
        assert response.status_code == 200
        assert response.json()["engaged"] is True
        event = socket.receive_json()
        assert event["type"] == "kill_switch"
        assert event["status"] == "engaged"
        assert event["payload"]["engaged"] is True


def test_kill_switch_blocks_and_then_releases_orders(client) -> None:
    client.post("/api/risk/kill-switch", json={"engaged": True, "reason": "halt"})
    blocked = client.post("/api/risk/evaluate", json=sample_order("switch-1")).json()
    assert blocked["status"] == "REJECT"
    assert "kill_switch" in blocked["reasons"]

    client.post("/api/risk/kill-switch", json={"engaged": False, "reason": "resume"})
    released = client.post("/api/risk/evaluate", json=sample_order("switch-2")).json()
    assert released["status"] == "PASS"


def test_kill_switch_persists_across_a_new_process(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'desk.db'}"
    first = create_app(make_settings(database_url=url))
    with authed(first) as client:
        assert client.post("/api/risk/kill-switch", json={"engaged": True, "reason": "halt"}).status_code == 200
    second = create_app(make_settings(database_url=url))
    with authed(second) as client:
        assert client.get("/api/risk/kill-switch").json()["engaged"] is True
        decision = client.post("/api/risk/evaluate", json=sample_order("persist-1")).json()
        assert decision["status"] == "REJECT"
        assert "kill_switch" in decision["reasons"]


def test_duplicate_client_order_id_is_rejected_on_the_api(client) -> None:
    first = client.post("/api/risk/evaluate", json=sample_order("same-id")).json()
    assert first["status"] == "PASS"
    second = client.post("/api/risk/evaluate", json=sample_order("same-id")).json()
    assert second["status"] == "REJECT"
    assert second["reasons"] == ["duplicate_client_order_id"]
    stored = client.get("/api/risk/decisions").json()["decisions"]
    assert len(stored) >= 2


def test_daily_loss_and_stale_data_on_the_api(client) -> None:
    updated = client.put(
        "/api/risk/account",
        json={"equity": "1000", "start_of_day_equity": "1000", "realized_pnl_today": "-30"},
    )
    assert updated.status_code == 200
    blocked = client.post("/api/risk/evaluate", json=sample_order("loss-1")).json()
    assert blocked["status"] == "REJECT"
    assert "daily_loss_limit" in blocked["reasons"]

    client.put("/api/risk/account", json={"realized_pnl_today": "-29.99"})
    allowed = client.post("/api/risk/evaluate", json=sample_order("loss-2")).json()
    assert allowed["status"] == "PASS"

    old = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    stale = client.post("/api/risk/evaluate", json=sample_order("stale-1", market_data_time=old)).json()
    assert stale["status"] == "REJECT"
    assert "stale_market_data" in stale["reasons"]


def test_journal_after_a_desk_run_and_redacts_approval_tokens(client) -> None:
    idea = fitting_idea(client_order_id="journal-1", approval_token="super-secret-approval-token")
    response = client.post("/api/desk/run", json=json.loads(idea.model_dump_json()))
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "dry_run_recorded"
    listed = client.get("/api/journal").json()["entries"]
    assert len(listed) == 1
    assert listed[0]["symbol"] == "BTC"
    assert listed[0]["outcome"] == "dry_run_recorded"
    assert "transmitted=False" in listed[0]["summary"]
    fetched = client.get(f"/api/journal/{listed[0]['id']}").json()
    assert fetched["payload"]["idea"]["approval_token"] == "[redacted]"
    assert "super-secret-approval-token" not in json.dumps(fetched)
    missing = client.get("/api/journal/9999")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"

    status = client.get("/api/agents/status").json()["agents"]
    assert all(agent["status"] != "idle" for agent in status)
