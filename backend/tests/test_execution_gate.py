from datetime import datetime, timezone

from fastapi.testclient import TestClient

from hypergrok.execution.adapter import ExecutionAdapter
from hypergrok.execution.dry_run import DryRunAdapter
from hypergrok.main import create_app
from tests.support import fitting_idea, make_settings


def test_live_trading_is_disabled_by_default(app) -> None:
    assert app.state.settings.live_trading_enabled is False
    decision = app.state.gate.authorize(mode="live", client_order_id="ord-1", approval_token="present")
    assert decision.allowed is False
    assert decision.reason == "live_trading_disabled"


def test_dry_run_records_the_payload_and_does_not_transmit() -> None:
    adapter = DryRunAdapter()
    assert adapter.transmits is False
    assert ExecutionAdapter.transmits is False
    result = adapter.execute({"symbol": "BTC", "side": "buy", "notional": "10", "client_order_id": "dry-1"})
    assert result.transmitted is False
    assert result.status == "recorded"
    assert result.payload["transmitted"] is False
    assert result.payload["would_send"]["symbol"] == "BTC"
    assert "signature" not in result.payload


def test_enabled_live_request_without_approval_is_rejected() -> None:
    app = create_app(make_settings(live_trading_enabled=True))
    with TestClient(app):
        missing = app.state.gate.authorize(mode="live", client_order_id="ord-9", approval_token=None)
        assert missing.allowed is False
        assert missing.reason == "missing_human_approval"

        wrong = app.state.gate.authorize(mode="live", client_order_id="ord-9", approval_token="not-a-real-token")
        assert wrong.reason == "missing_human_approval"

        created = app.state.store.create_approval(
            client_order_id="ord-9",
            note="human",
            now=datetime.now(timezone.utc),
        )
        mismatched = app.state.gate.authorize(
            mode="live",
            client_order_id="someone-else",
            approval_token=created["token"],
        )
        assert mismatched.reason == "missing_human_approval"

        approved = app.state.gate.authorize(
            mode="live",
            client_order_id="ord-9",
            approval_token=created["token"],
        )
        assert approved.allowed is False
        assert approved.reason == "live_transmission_not_implemented"
        assert approved.approval_consumed is False


def test_desk_run_rejects_live_orders_until_phase_1_can_transmit(client) -> None:
    idea = fitting_idea(request_live=True, client_order_id="live-disabled-1")
    response = client.post("/api/desk/run", json=idea.model_dump(mode="json"))
    assert response.status_code == 200
    body = response.json()
    assert body["risk"]["status"] == "PASS"
    assert body["execution"]["status"] == "rejected"
    assert body["execution"]["gate_reason"] == "live_trading_disabled"
    assert body["execution"]["transmitted"] is False
    assert body["outcome"] == "execution_rejected"
    account = client.get("/api/risk/account").json()
    assert account["open_position_count"] == 0


def test_approved_live_order_is_still_not_transmitted() -> None:
    app = create_app(make_settings(live_trading_enabled=True))
    with TestClient(app) as client:
        bare = fitting_idea(request_live=True)
        first = client.post("/api/desk/run", json=bare.model_dump(mode="json"))
        assert first.json()["execution"]["gate_reason"] == "missing_human_approval"

        created = client.post("/api/approvals", json={"client_order_id": "approved-1", "note": "human ok"})
        assert created.status_code == 200
        token = created.json()["token"]
        idea = fitting_idea(request_live=True, client_order_id="approved-1", approval_token=token)
        second = client.post("/api/desk/run", json=idea.model_dump(mode="json"))
        body = second.json()
        assert body["risk"]["status"] == "PASS"
        assert body["execution"]["status"] == "rejected"
        assert body["execution"]["gate_reason"] == "live_transmission_not_implemented"
        assert body["execution"]["transmitted"] is False
        assert body["execution"]["approval_consumed"] is False
        attempts = client.get("/api/execution/attempts").json()["attempts"]
        assert attempts
        assert all(item["transmitted"] is False for item in attempts)
        dumped = second.text
        assert token not in dumped
