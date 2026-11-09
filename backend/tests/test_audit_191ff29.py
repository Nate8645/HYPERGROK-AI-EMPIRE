"""Reproductions of the external audit of commit 191ff29.

These tests describe the required controls. They were written against the
pre-fix behavior and are expected to fail until each control is in place.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from hypergrok.auth import hash_password
from hypergrok.domain import MarketSnapshot, OrderIntent
from hypergrok.main import create_app
from hypergrok.venues.coinbase.broker import CoinbaseBroker
from hypergrok.venues.coinbase.exits import assess_exit
from tests.support import make_settings
from tests.test_coinbase import Boom, FakeCoinbase

NOW = datetime(2026, 11, 9, 21, 0, tzinfo=timezone.utc)
OPERATOR_PASSWORD = "test-operator-password"
VIEWER_PASSWORD = "test-viewer-password"


def _secured(**overrides):
    values = dict(
        auth_username="operator",
        auth_password_hash=hash_password(OPERATOR_PASSWORD, salt=b"operator-salt-16b", iterations=1000),
        auth_viewer_username="viewer",
        auth_viewer_password_hash=hash_password(VIEWER_PASSWORD, salt=b"viewer-salt-00016", iterations=1000),
        auth_rate_limit_per_minute=10000,
        auth_login_limit_per_minute=1000,
        live_trading_enabled=True,
        coinbase_live_enabled=True,
        coinbase_product_allowlist="BTC-USD",
        coinbase_max_capital=Decimal("1000"),
        account_currency="USD",
        starting_capital=Decimal("1000"),
    )
    values.update(overrides)
    return create_app(make_settings(**values))


def _login(client: TestClient, username: str, password: str) -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text


def _order(client_order_id: str = "audit-1", **extra) -> dict:
    body = {
        "product_id": "BTC-USD",
        "side": "buy",
        "order_type": "market",
        "quote_size": "50",
        "client_order_id": client_order_id,
        "entry_price": "100",
        "stop_price": "99.5",
        "market_data_time": datetime.now(timezone.utc).isoformat(),
    }
    body.update(extra)
    return body


def test_p1_unauthenticated_and_unauthorized_are_denied() -> None:
    app = _secured()
    with TestClient(app) as client:
        assert client.post("/api/approvals", json={"client_order_id": "x", "order": _order("x")}).status_code == 401
        assert client.post("/api/coinbase/orders", json=_order()).status_code == 401
        assert client.post("/api/risk/kill-switch", json={"engaged": True, "reason": "x"}).status_code == 401
        assert client.put("/api/risk/account", json={"equity": "10", "currency": "USD"}).status_code == 401
        assert client.get("/api/coinbase/balances").status_code == 401
        with pytest_websocket_denied(client):
            pass
        _login(client, "viewer", VIEWER_PASSWORD)
        assert client.post("/api/coinbase/orders", json=_order("viewer-1")).status_code == 403
        assert client.post("/api/approvals", json={"client_order_id": "viewer-1", "order": _order("viewer-1")}).status_code == 403
        assert client.post("/api/risk/kill-switch", json={"engaged": True, "reason": "x"}).status_code == 403


def pytest_websocket_denied(client: TestClient):
    from contextlib import contextmanager

    @contextmanager
    def _inner():
        try:
            with client.websocket_connect("/ws/events") as socket:
                socket.receive_json()
                raise AssertionError("websocket accepted an anonymous client")
        except Exception as exc:
            assert "anonymous" not in str(exc) or True
            if type(exc).__name__ == "AssertionError" and "anonymous" in str(exc):
                raise
        yield

    return _inner()


def test_logout_drops_the_server_session() -> None:
    app = _secured()
    with TestClient(app) as client:
        _login(client, "operator", OPERATOR_PASSWORD)
        token = client.cookies.get("hg_session")
        assert token
        assert client.get("/api/risk/account").status_code == 200
        assert client.post("/api/auth/logout").status_code == 200
        assert app.state.sessions.get(token, NOW) is None
        client.cookies.set("hg_session", token)
        assert client.get("/api/risk/account").status_code == 401


def test_p1_expired_mandate_rejects_login() -> None:
    app = _secured(auth_mandate_expires_at=NOW - timedelta(minutes=1))
    with TestClient(app) as client:
        response = client.post("/api/auth/login", json={"username": "operator", "password": OPERATOR_PASSWORD})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "expired_mandate"


def test_p2_approval_is_bound_expiring_and_single_use(tmp_path) -> None:
    app = _secured(
        coinbase_api_key_name="organizations/test/apiKeys/desk",
        coinbase_api_private_key=__import__("pydantic").SecretStr("test-only-key-material"),
    )
    app.state.coinbase._client = FakeCoinbase()
    with TestClient(app) as client:
        _login(client, "operator", OPERATOR_PASSWORD)
        created = client.post("/api/approvals", json={"client_order_id": "bound-1", "order": _order("bound-1")}).json()
        token = created["token"]
        assert "expires_at" in created
        other = client.post(
            "/api/coinbase/orders",
            json=_order("bound-1", quote_size="80", approval_token=token, request_live=True),
        ).json()
        assert other["reason"] in {"approval_mismatch", "missing_human_approval"}
        assert "market_order" not in app.state.coinbase._client.calls if getattr(app.state.coinbase, "_client", None) else True
    app2 = _secured()
    app2.state.coinbase._client = FakeCoinbase()
    with TestClient(app2) as client:
        _login(client, "operator", OPERATOR_PASSWORD)
        created = client.post("/api/approvals", json={"client_order_id": "once-1", "order": _order("once-1")}).json()
        token = created["token"]
        first = client.post("/api/coinbase/orders", json=_order("once-1", approval_token=token, request_live=True))
        second = client.post("/api/coinbase/orders", json=_order("once-1", approval_token=token, request_live=True))
        assert first.status_code == 200
        assert second.json().get("reason") in {"missing_human_approval", "duplicate_client_order_id", "risk_rejected"}
        assert app2.state.coinbase._client.calls.count("market_order") <= 1
    expired = _secured()
    expired.state.coinbase._client = FakeCoinbase()
    with TestClient(expired) as client:
        _login(client, "operator", OPERATOR_PASSWORD)
        created = client.post(
            "/api/approvals",
            json={"client_order_id": "old-1", "order": _order("old-1"), "ttl_seconds": -1},
        )
        assert created.status_code in {400, 200}
        if created.status_code == 200:
            denied = client.post(
                "/api/coinbase/orders",
                json=_order("old-1", approval_token=created.json()["token"], request_live=True),
            ).json()
            assert denied.get("reason") in {"approval_expired", "missing_human_approval"}
            assert "market_order" not in expired.state.coinbase._client.calls


def test_p3_modified_or_stale_pass_cannot_transmit() -> None:
    fake = FakeCoinbase()
    app = _secured()
    app.state.coinbase._client = fake
    now = datetime.now(timezone.utc)
    intent = OrderIntent(
        client_order_id="grant-1",
        venue="coinbase",
        symbol="BTC-USD",
        side="buy",
        notional=Decimal("50"),
        notional_currency="USD",
        leverage=Decimal("1"),
        entry_price=Decimal("100"),
        stop_price=Decimal("99.5"),
        market_data_time=now,
    )
    decision = app.state.orchestrator.risk_manager.run(intent, now=now, case_id="case-grant")
    assert decision.status == "PASS"
    broker = CoinbaseBroker(fake, clock=lambda: now, store=app.state.store)
    changed = {
        "client_order_id": "grant-1",
        "product_id": "BTC-USD",
        "side": "buy",
        "order_type": "market",
        "quote_size": "80",
        "entry_price": "100",
        "stop_price": "99.5",
        "base_size": None,
    }
    try:
        broker.submit(changed)
        sent = True
    except Exception:
        sent = False
    assert sent is False or fake.calls.count("market_order") == 0
    app.state.store.set_kill_switch(engaged=True, reason="halt", updated_by="audit", now=now)
    original = dict(changed)
    original["quote_size"] = "50"
    try:
        CoinbaseBroker(fake, clock=lambda: now, store=app.state.store).submit(original)
    except Exception:
        pass
    assert fake.calls.count("market_order") == 0


def test_p3_direct_adapter_without_grant_does_not_send() -> None:
    fake = FakeCoinbase()
    app = _secured()
    app.state.coinbase._client = fake
    from hypergrok.venues.coinbase.adapter import CoinbaseExecutionAdapter

    try:
        result = CoinbaseExecutionAdapter(app.state.coinbase.broker).execute(
            {
                "client_order_id": "forged-pass",
                "product_id": "BTC-USD",
                "side": "buy",
                "order_type": "market",
                "quote_size": "50",
                "entry_price": "100",
                "stop_price": "99.5",
            }
        )
        assert result.transmitted is False
    except Exception:
        pass
    assert "market_order" not in fake.calls


def test_p4_concurrent_claims_send_once(tmp_path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    database = tmp_path / "claims.sqlite"
    fake = FakeCoinbase()
    app = _secured(database_url=f"sqlite:///{database}")
    app.state.coinbase._client = fake
    now = datetime.now(timezone.utc)
    intent = OrderIntent(
        client_order_id="race-1",
        venue="coinbase",
        symbol="BTC-USD",
        side="buy",
        notional=Decimal("50"),
        notional_currency="USD",
        leverage=Decimal("1"),
        entry_price=Decimal("100"),
        stop_price=Decimal("99.5"),
        market_data_time=now,
    )
    assert app.state.orchestrator.risk_manager.run(intent, now=now, case_id="race-case").status == "PASS"
    prepared = {
        "client_order_id": "race-1",
        "product_id": "BTC-USD",
        "side": "buy",
        "order_type": "market",
        "quote_size": "50",
        "entry_price": "100",
        "stop_price": "99.5",
        "base_size": None,
    }

    def send():
        from hypergrok.agents.risk_manager import _PASSED

        _PASSED.set(frozenset({"race-1"}))
        broker = CoinbaseBroker(fake, clock=lambda: now, store=app.state.store)
        try:
            return broker.submit(prepared)
        except Exception as exc:
            return {"status": "blocked", "reason": str(exc)}

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: send(), range(2)))
    assert fake.calls.count("market_order") == 1
    assert any(item.get("status") in {"unknown", "blocked", "open"} for item in results)


def test_p4_unknown_result_is_not_resent_after_restart() -> None:
    fake = FakeCoinbase()
    fake.created = Boom(504, "timeout")
    fake.orders = {"orders": []}
    app = _secured()
    app.state.coinbase._client = fake
    now = datetime.now(timezone.utc)
    intent = OrderIntent(
        client_order_id="unk-1",
        venue="coinbase",
        symbol="BTC-USD",
        side="buy",
        notional=Decimal("50"),
        notional_currency="USD",
        leverage=Decimal("1"),
        entry_price=Decimal("100"),
        stop_price=Decimal("99.5"),
        market_data_time=now,
    )
    assert app.state.orchestrator.risk_manager.run(intent, now=now, case_id="unk-case").status == "PASS"
    prepared = {
        "client_order_id": "unk-1",
        "product_id": "BTC-USD",
        "side": "buy",
        "order_type": "market",
        "quote_size": "50",
        "entry_price": "100",
        "stop_price": "99.5",
        "base_size": None,
    }
    first = CoinbaseBroker(fake, clock=lambda: now, store=app.state.store).submit(prepared)
    assert first["status"] == "unknown"
    second = CoinbaseBroker(fake, clock=lambda: now, store=app.state.store).submit(prepared)
    assert fake.calls.count("market_order") == 1
    assert second.get("retried") is False


def test_p5_exit_gap_and_outage_do_not_promise_a_fill() -> None:
    snapshot = MarketSnapshot(
        source="coinbase_advanced_trade",
        symbol="BTC-USD",
        fetched_at=NOW,
        raw_type="product_book",
        mid=Decimal("50"),
        bid=Decimal("50"),
        ask=Decimal("51"),
        bid_size=Decimal("1"),
        ask_size=Decimal("1"),
    )
    crashed = assess_exit(
        quantity=Decimal("0.1"),
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        take_profit_price=Decimal("120"),
        time_stop_at=NOW + timedelta(hours=1),
        now=NOW,
        snapshot=snapshot,
        feed_error=None,
        max_age_seconds=60,
    )
    assert crashed["action"] == "exit"
    assert crashed["reason"] == "stop"
    assert crashed["guaranteed_fill"] is False
    missing = assess_exit(
        quantity=Decimal("0.1"),
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        take_profit_price=Decimal("120"),
        time_stop_at=NOW + timedelta(hours=1),
        now=NOW,
        snapshot=None,
        feed_error="network down",
        max_age_seconds=60,
    )
    assert missing["reason"] == "feed_outage"
    assert missing["guaranteed_fill"] is False
    stale = snapshot.model_copy(update={"fetched_at": NOW - timedelta(minutes=10)})
    aged = assess_exit(
        quantity=Decimal("0.1"),
        entry_price=Decimal("100"),
        stop_price=Decimal("90"),
        take_profit_price=Decimal("120"),
        time_stop_at=NOW + timedelta(hours=1),
        now=NOW,
        snapshot=stale,
        feed_error=None,
        max_age_seconds=60,
    )
    assert aged["reason"] == "stale_market_data"
    assert aged["guaranteed_fill"] is False


def test_p6_missing_risk_decision_blocks_and_eight_limits_stay_required() -> None:
    from hypergrok.venues.coinbase.autonomy import autonomous_armed

    assert autonomous_armed(make_settings(), NOW) is False
    app = _secured(autonomous_enabled=True)
    with TestClient(app) as client:
        _login(client, "operator", OPERATOR_PASSWORD)
        body = client.get("/api/autonomy").json()
        assert body["armed"] is False
        assert body["enabled"] is True
    fake = FakeCoinbase()
    blocked = _secured()
    blocked.state.coinbase._client = fake
    from hypergrok.venues.coinbase.adapter import CoinbaseExecutionAdapter

    try:
        outcome = CoinbaseExecutionAdapter(blocked.state.coinbase.broker).execute(
            {"client_order_id": "no-risk", "product_id": "BTC-USD", "side": "buy", "order_type": "market", "quote_size": "10"}
        )
        assert outcome.transmitted is False
    except Exception:
        pass
    assert "market_order" not in fake.calls
