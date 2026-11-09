"""Coinbase spot adapter. The client is fake; nothing here touches the network or a real key."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from hypergrok.config import Settings
from hypergrok.domain import AccountState, DeskIdea, MarketSnapshot, OrderIntent, ResearchInput, RiskDecision
from hypergrok.execution.gate import ExecutionGate
from hypergrok.main import create_app
from hypergrok.venues.coinbase.fx import PublicExchangeRateClient, parse_public_exchange_rates
from hypergrok.venues.coinbase.market import fee_bps_from_summary, map_preview, prepare_order_sizes
from hypergrok.venues.coinbase.pnl import compute_portfolio
from tests.support import make_settings

NOW = datetime(2026, 11, 9, 18, 0, tzinfo=timezone.utc)
SECRET = "test-only-key-material"


class Boom(Exception):
    def __init__(self, status_code: int, text: str) -> None:
        super().__init__(text)
        self.response = type("Response", (), {"status_code": status_code, "text": text})()


class FakeCoinbase:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.fail: Boom | None = None
        self.preview = {
            "commission_total": "0.60",
            "quote_size": "100",
            "base_size": "0.001",
            "best_bid": "65000",
            "best_ask": "65010",
            "slippage": "0.0002",
            "order_total": "100.60",
        }
        self.accounts = {
            "accounts": [
                {"available_balance": {"value": "1000", "currency": "USD"}, "hold": {"value": "0", "currency": "USD"}}
            ]
        }
        self.summary = {"fee_tier": {"pricing_tier": "Advanced 1", "maker_fee_rate": "0.004", "taker_fee_rate": "0.006"}}
        self.product = {
            "product_id": "BTC-USD",
            "product_type": "SPOT",
            "quote_currency_id": "USD",
            "base_currency_id": "BTC",
            "base_increment": "0.00000001",
            "quote_increment": "0.01",
            "base_min_size": "0.00001",
            "base_max_size": "10",
            "quote_min_size": "1",
            "quote_max_size": "1000000",
        }
        self.book = {"pricebooks": [{"product_id": "BTC-USD", "bids": [{"price": "64990", "size": "5"}], "asks": [{"price": "65010", "size": "1"}], "time": "2026-11-09T17:59:00+00:00"}]}
        self.created = {"success": True, "success_response": {"order_id": "ord-1", "client_order_id": "c1", "product_id": "BTC-USD", "side": "BUY", "status": "OPEN"}}
        self.orders = {"orders": []}
        self.fills = {"fills": []}

    def _hit(self, name: str):
        self.calls.append(name)
        if self.fail is not None and name in {"get_accounts", "market_order", "get_products"}:
            raise self.fail

    def get_products(self, **kwargs):
        self._hit("get_products")
        return {"products": [self.product]}

    def get_product(self, product_id: str, **kwargs):
        self._hit("get_product")
        return self.product

    def get_best_bid_ask(self, product_ids=None, **kwargs):
        self._hit("get_best_bid_ask")
        return self.book

    def get_product_book(self, product_id: str, **kwargs):
        self._hit("get_product_book")
        return self.book

    def get_candles(self, product_id, start, end, granularity, **kwargs):
        self._hit("get_candles")
        return {"candles": [{"start": "1", "open": "1", "high": "2", "low": "1", "close": "2", "volume": "3"}]}

    def get_accounts(self, **kwargs):
        self._hit("get_accounts")
        return self.accounts

    def get_portfolios(self, **kwargs):
        self._hit("get_portfolios")
        return {"portfolios": [{"uuid": "p1", "name": "Default", "type": "DEFAULT"}]}

    def get_transaction_summary(self, **kwargs):
        self._hit("get_transaction_summary")
        return self.summary

    def preview_market_order(self, **kwargs):
        self._hit("preview_market_order")
        assert "leverage" not in kwargs
        return self.preview

    def preview_limit_order_gtc(self, **kwargs):
        self._hit("preview_limit_order_gtc")
        assert "leverage" not in kwargs
        return self.preview

    def market_order(self, **kwargs):
        self._hit("market_order")
        assert "leverage" not in kwargs
        assert kwargs["side"] in {"BUY", "SELL"}
        if isinstance(self.created, Exception):
            raise self.created
        return self.created

    def limit_order_gtc(self, **kwargs):
        self._hit("limit_order_gtc")
        assert "leverage" not in kwargs
        return self.created

    def list_orders(self, **kwargs):
        self._hit("list_orders")
        return self.orders

    def get_fills(self, **kwargs):
        self._hit("get_fills")
        return self.fills

    def cancel_orders(self, order_ids):
        self._hit("cancel_orders")
        self.cancelled = list(order_ids)
        return {"results": [{"success": True, "order_id": item} for item in order_ids]}


def _app(fake: FakeCoinbase | None = None, **overrides):
    values = dict(
        account_currency="USD",
        starting_capital=Decimal("1000"),
        live_trading_enabled=False,
        coinbase_live_enabled=False,
        coinbase_api_key_name="organizations/test/apiKeys/desk",
        coinbase_api_private_key=SecretStr(SECRET),
        coinbase_product_allowlist="BTC-USD",
        coinbase_max_capital=Decimal("1000"),
    )
    values.update(overrides)
    app = create_app(make_settings(**values))
    if fake is not None:
        app.state.coinbase._client = fake
    return app


def _order(**extra):
    body = {
        "product_id": "BTC-USD",
        "side": "buy",
        "order_type": "market",
        "quote_size": "50",
        "client_order_id": "c1",
        "entry_price": "65000",
        "stop_price": "64900",
        "market_data_time": datetime.now(timezone.utc).isoformat(),
    }
    body.update(extra)
    return body


def test_credentials_round_trip_and_are_redacted(tmp_path, capsys) -> None:
    key_file = tmp_path / "cdp.json"
    key_file.write_text('{"name": "organizations/test/apiKeys/desk", "privateKey": "' + SECRET + '"}', encoding="utf-8")
    loaded = Settings(
        _env_file=None,
        coinbase_api_key_file=str(key_file),
    )
    from hypergrok.venues.coinbase.credentials import load_credentials
    from hypergrok.logging_config import JsonFormatter
    import logging

    creds = load_credentials(loaded)
    assert creds is not None
    assert SECRET not in repr(creds)
    record = logging.LogRecord("hypergrok", logging.INFO, __file__, 1, "loaded key", (), None)
    record.context = {"coinbase_api_private_key": creds.private_key, "product_id": "BTC-USD"}
    rendered = JsonFormatter().format(record)
    assert SECRET not in rendered
    assert "BTC-USD" in rendered
    status = _app().state.coinbase.status()
    assert status["configured"] is True
    assert SECRET not in str(status)


def test_increment_and_min_size() -> None:
    product = FakeCoinbase().product
    rounded = prepare_order_sizes(product, {"side": "buy", "order_type": "market", "quote_size": "10.239"})
    assert rounded["quote_size"] == "10.23"
    with pytest.raises(Exception) as caught:
        prepare_order_sizes(product, {"side": "buy", "order_type": "market", "quote_size": "0.50"})
    assert caught.value.code == "min_size"


def test_preview_mapping_includes_fees_and_slippage() -> None:
    mapped = map_preview(FakeCoinbase().preview, fetched_at=NOW)
    assert mapped["source"] == "coinbase_advanced_trade"
    assert mapped["rejected"] is False
    assert Decimal(mapped["fee_bps_one_way"]) == Decimal("60")
    assert Decimal(mapped["slippage_bps"]) == Decimal("2")
    rates = fee_bps_from_summary(FakeCoinbase().summary, order_type="market", post_only=False)
    assert Decimal(rates["fee_bps_round_trip"]) == Decimal("120")


def test_public_fx_rate_is_labelled_and_not_invented() -> None:
    quote = parse_public_exchange_rates(
        {"data": {"currency": "CHF", "rates": {"USD": "1.13"}}},
        base="CHF",
        quote="USD",
        fetched_at=NOW,
    )
    assert quote.source == "coinbase_public_exchange_rates"
    assert quote.rate == Decimal("1.13")
    with pytest.raises(Exception):
        parse_public_exchange_rates({"data": {"rates": {"EUR": "1"}}}, base="CHF", quote="USD", fetched_at=NOW)

    class Transport:
        def get(self, url, timeout):
            assert "currency=CHF" in url
            return 200, '{"data": {"currency": "CHF", "rates": {"USD": "1.20"}}}'

    fetched = PublicExchangeRateClient(Transport(), clock=lambda: NOW).usd_per("CHF")
    assert fetched.fetched_at == NOW
    assert fetched.rate == Decimal("1.20")


def test_missing_and_stale_fx_reject_conversion() -> None:
    from hypergrok.risk.engine import RiskEngine

    engine = RiskEngine(make_settings(account_currency="CHF", max_fx_age_seconds=300))
    account = AccountState(
        currency="CHF",
        equity=Decimal("100"),
        start_of_day_equity=Decimal("100"),
        realized_pnl_today=Decimal("0"),
        open_position_count=0,
        entries_today=0,
        trading_day="2026-11-09",
    )

    def intent(**extra):
        values = dict(
            client_order_id="fx-1",
            venue="coinbase",
            symbol="BTC-USD",
            side="buy",
            notional=Decimal("20"),
            notional_currency="CHF",
            leverage=Decimal("1"),
            entry_price=Decimal("100"),
            stop_price=Decimal("99.5"),
            market_data_time=NOW,
            usd_per_notional_currency=Decimal("1.13"),
        )
        values.update(extra)
        return OrderIntent(**values)

    missing = engine.evaluate(intent(fx_source="explicit_config", fx_as_of=None, usd_per_notional_currency=Decimal("1.13")), account, now=NOW, kill_switch_engaged=False, seen_client_order_ids=set())
    assert missing.status == "REJECT"
    assert "missing_fx_rate" in missing.reasons
    stale = engine.evaluate(
        intent(fx_source="explicit_config", fx_as_of=NOW - timedelta(hours=2)),
        account,
        now=NOW,
        kill_switch_engaged=False,
        seen_client_order_ids=set(),
    )
    assert "stale_fx_rate" in stale.reasons
    fresh = engine.evaluate(
        intent(fx_source="coinbase_public_exchange_rates", fx_as_of=NOW - timedelta(seconds=30)),
        account,
        now=NOW,
        kill_switch_engaged=False,
        seen_client_order_ids=set(),
    )
    assert fresh.status == "PASS"


def test_each_missing_live_condition_rejects_and_full_gate_calls_once() -> None:
    fake = FakeCoinbase()
    base = dict(
        live_trading_enabled=True,
        coinbase_live_enabled=True,
        coinbase_api_key_name="organizations/test/apiKeys/desk",
        coinbase_api_private_key=SecretStr(SECRET),
        coinbase_product_allowlist="BTC-USD",
        coinbase_max_capital=Decimal("1000"),
    )
    cases = [
        ({"live_trading_enabled": False}, "live_trading_disabled"),
        ({"coinbase_live_enabled": False}, "coinbase_live_disabled"),
        ({"coinbase_product_allowlist": ""}, "product_not_allowlisted"),
        ({"coinbase_max_capital": Decimal("0")}, "capital_cap_exceeded"),
        ({"coinbase_api_key_name": "", "coinbase_api_private_key": SecretStr("")}, "coinbase_not_configured"),
    ]
    for overrides, reason in cases:
        values = dict(base)
        values.update(overrides)
        app = _app(fake, **values)
        with TestClient(app) as client:
            if reason != "missing_human_approval":
                token = client.post("/api/approvals", json={"client_order_id": "c1", "note": "human"}).json()["token"]
            else:
                token = None
            body = _order(request_live=True, approval_token=token)
            response = client.post("/api/coinbase/orders", json=body).json()
            assert response["reason"] == reason or response.get("error", {}).get("code") == reason
            assert "market_order" not in fake.calls

    fake.calls.clear()
    app = _app(fake, **base)
    with TestClient(app) as client:
        denied = client.post("/api/coinbase/orders", json=_order(client_order_id="c-deny", request_live=True)).json()
        assert denied["reason"] == "missing_human_approval"
        token = client.post("/api/approvals", json={"client_order_id": "c-ok", "note": "human"}).json()["token"]
        accepted = client.post(
            "/api/coinbase/orders",
            json=_order(client_order_id="c-ok", request_live=True, approval_token=token),
        ).json()
        assert accepted["transmitted"] is True
        assert fake.calls.count("market_order") == 1
        again = client.post(
            "/api/coinbase/orders",
            json=_order(request_live=True, approval_token=token, client_order_id="c-again"),
        ).json()
        assert again["reason"] == "missing_human_approval"
        assert fake.calls.count("market_order") == 1


def test_unknown_outcome_is_not_retried() -> None:
    fake = FakeCoinbase()
    fake.created = Boom(504, "gateway timeout")
    fake.orders = {"orders": [{"order_id": "ord-9", "client_order_id": "c9", "product_id": "BTC-USD", "status": "OPEN", "side": "BUY"}]}
    app = _app(
        fake,
        live_trading_enabled=True,
        coinbase_live_enabled=True,
        coinbase_max_capital=Decimal("1000"),
    )
    broker = app.state.coinbase.broker
    prepared = {"client_order_id": "c9", "product_id": "BTC-USD", "side": "buy", "order_type": "market", "quote_size": "50", "base_size": None}
    first = broker.submit(prepared)
    assert first["reconciled"] is True
    assert fake.calls.count("market_order") == 1
    second = broker.submit(prepared)
    assert fake.calls.count("market_order") == 1
    assert second["retried"] is False


def test_permissions_invalid_key_empty_account_and_rejected_preview() -> None:
    fake = FakeCoinbase()
    fake.fail = Boom(403, "Missing required scopes")
    app = _app(fake)
    with TestClient(app) as client:
        response = client.get("/api/coinbase/balances")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "missing_api_permissions"
        assert SECRET not in response.text

    fake.fail = Boom(401, "invalid api key")
    response = TestClient(app).get("/api/coinbase/balances")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"
    assert SECRET not in response.text

    fake.fail = None
    fake.accounts = {"accounts": [{"available_balance": {"value": "0", "currency": "USD"}, "hold": {"value": "0", "currency": "USD"}}]}
    app = _app(fake, live_trading_enabled=True, coinbase_live_enabled=True, coinbase_max_capital=Decimal("1000"))
    with TestClient(app) as client:
        balances = client.get("/api/coinbase/balances").json()
        assert balances["account_state"] == "empty"
        token = client.post("/api/approvals", json={"client_order_id": "empty-1"}).json()["token"]
        rejected = client.post("/api/coinbase/orders", json=_order(client_order_id="empty-1", request_live=True, approval_token=token)).json()
        assert rejected["reason"] == "empty_account"
        assert "market_order" not in fake.calls

    fake.accounts = {"accounts": [{"available_balance": {"value": "1000", "currency": "USD"}, "hold": {"value": "0", "currency": "USD"}}]}
    fake.preview = {"errs": ["PREVIEW_INVALID_SIZE"], "quote_size": "50", "commission_total": "0.1"}
    app = _app(fake, live_trading_enabled=True, coinbase_live_enabled=True, coinbase_max_capital=Decimal("1000"))
    with TestClient(app) as client:
        token = client.post("/api/approvals", json={"client_order_id": "bad-preview"}).json()["token"]
        response = client.post(
            "/api/coinbase/orders",
            json=_order(client_order_id="bad-preview", request_live=True, approval_token=token),
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "preview_rejected"
        assert "market_order" not in fake.calls


def test_risk_limit_kill_switch_and_stale_price_block_orders() -> None:
    fake = FakeCoinbase()
    app = _app(fake, live_trading_enabled=True, coinbase_live_enabled=True, coinbase_max_capital=Decimal("1000"))
    with TestClient(app) as client:
        token = client.post("/api/approvals", json={"client_order_id": "wide"}).json()["token"]
        wide = client.post(
            "/api/coinbase/orders",
            json=_order(
                client_order_id="wide",
                quote_size="200",
                entry_price="100",
                stop_price="90",
                request_live=True,
                approval_token=token,
            ),
        ).json()
        assert wide["reason"] == "risk_rejected"
        assert "planned_risk" in wide["decision"]["reasons"]
        assert "market_order" not in fake.calls

        client.post("/api/risk/kill-switch", json={"engaged": True, "reason": "halt"})
        token = client.post("/api/approvals", json={"client_order_id": "halted"}).json()["token"]
        halted = client.post("/api/coinbase/orders", json=_order(client_order_id="halted", request_live=True, approval_token=token)).json()
        assert halted["reason"] == "risk_rejected"
        assert "kill_switch" in halted["decision"]["reasons"]

    fake.orders = {"orders": [{"order_id": "open-1", "product_id": "BTC-USD", "status": "OPEN", "side": "BUY", "client_order_id": "old"}]}
    app = _app(fake, live_trading_enabled=True, coinbase_live_enabled=True, coinbase_max_capital=Decimal("100"))
    with TestClient(app) as client:
        client.post("/api/risk/kill-switch", json={"engaged": True, "reason": "halt"})
        assert fake.cancelled == ["open-1"]

    fake.calls.clear()
    app = _app(fake, live_trading_enabled=True, coinbase_live_enabled=True, coinbase_max_capital=Decimal("1000"))
    with TestClient(app) as client:
        token = client.post("/api/approvals", json={"client_order_id": "stale"}).json()["token"]
        stale = client.post(
            "/api/coinbase/orders",
            json=_order(client_order_id="stale", request_live=True, approval_token=token, market_data_time="2020-01-01T00:00:00+00:00"),
        ).json()
        assert stale["reason"] == "risk_rejected"
        assert "stale_market_data" in stale["decision"]["reasons"]
        assert "market_order" not in fake.calls


def test_pnl_includes_fees_in_cost_basis_and_realized() -> None:
    fills = [
        {"product_id": "BTC-USD", "side": "BUY", "size": "1", "price": "100", "commission": "1", "trade_time": "2026-11-09T10:00:00Z"},
        {"product_id": "BTC-USD", "side": "SELL", "size": "0.4", "price": "110", "commission": "1", "trade_time": "2026-11-09T11:00:00Z"},
    ]
    marked = compute_portfolio(fills, {"BTC-USD": {"price": "120", "source": "coinbase_advanced_trade", "fetched_at": NOW}})
    position = marked["positions"][0]
    assert Decimal(position["average_cost"]) == Decimal("101")
    assert Decimal(position["quantity"]) == Decimal("0.6")
    assert Decimal(position["realized_pnl"]) == Decimal("2.6")
    assert Decimal(position["unrealized_pnl"]) == Decimal("11.4")
    unmarked = compute_portfolio(fills[:1], {})
    assert unmarked["unrealized_pnl"] is None
    assert unmarked["positions"][0]["unrealized_pnl"] is None


def test_portfolio_endpoint_reports_cost_basis() -> None:
    fake = FakeCoinbase()
    fake.orders = {
        "orders": [
            {"order_id": "o1", "client_order_id": "c", "product_id": "BTC-USD", "status": "FILLED", "side": "BUY"}
        ]
    }
    fake.fills = {
        "fills": [
            {
                "order_id": "o1",
                "product_id": "BTC-USD",
                "side": "BUY",
                "size": "1",
                "price": "100",
                "commission": "1",
                "trade_time": "2026-11-09T10:00:00Z",
            }
        ]
    }
    app = _app(fake)
    with TestClient(app) as client:
        body = client.get("/api/coinbase/portfolio").json()
        assert body["fees_included"] is True
        assert body["method"] == "average_cost"
        assert body["positions"][0]["cost_basis"] == "101"
        assert SECRET not in client.get("/api/coinbase/portfolio").text


def test_portfolio_endpoint_and_agents_stay_rule_based(client) -> None:
    status = client.get("/api/coinbase/status").json()
    assert status["configured"] is False
    assert status["live_enabled"] is False
    assert status["implementation"] == "rule_based"
    assert "private" not in status
    missing = client.get("/api/coinbase/balances")
    assert missing.status_code == 409
    idea = DeskIdea(
        symbol="BTC-USD",
        venue="coinbase",
        side="buy",
        thesis="Coinbase book is bid-heavy and the supplied trend is up.",
        size_mode="risk_limited",
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
        client_order_id="desk-btc",
    )
    result = client.app.state.orchestrator.run(idea, now=datetime.now(timezone.utc))
    assert result.desk.mode == "rule_based"
    assert result.market.source == "coinbase_advanced_trade"
    assert result.research.mode == "rule_based"
    assert "observed_spread_bps" in result.research.inputs_used
    assert result.strategy.order.venue == "coinbase"
    assert result.risk.status == "PASS"
    assert result.execution.transmitted is False
    assert result.execution.status == "recorded"


def test_execution_trader_cannot_bypass_risk_or_gate(app) -> None:
    events: list[str] = []
    trader = app.state.orchestrator.trader
    real_engine = trader.engine
    real_gate = trader.gate
    real_adapter = trader.adapter

    class Engine:
        def evaluate(self, *args, **kwargs):
            events.append("risk")
            return real_engine.evaluate(*args, **kwargs)

    class Gate:
        def authorize(self, **kwargs):
            events.append("gate")
            return real_gate.authorize(**kwargs)

    class Adapter:
        transmits = False

        def execute(self, payload):
            events.append("dry")
            return real_adapter.execute(payload)

    class Coinbase:
        transmits = True

        def execute(self, payload):
            events.append("coinbase")
            raise AssertionError("coinbase transmit")

    trader.engine = Engine()
    trader.gate = Gate()
    trader.adapter = Adapter()
    trader.coinbase = Coinbase()
    now = datetime.now(timezone.utc)
    forged = RiskDecision(
        status="PASS",
        reasons=[],
        checks=[],
        summary="forged",
        client_order_id="forged-1",
        notional=Decimal("80"),
        equity=Decimal("1000"),
    )
    idea = DeskIdea(
        symbol="BTC",
        venue="hyperliquid",
        side="buy",
        thesis="forged pass must still be checked",
        request_live=True,
        client_order_id="forged-1",
        approval_token="not-a-token",
    )
    order = OrderIntent(
        client_order_id="forged-1",
        venue="hyperliquid",
        symbol="BTC",
        side="buy",
        notional=Decimal("80"),
        notional_currency="USD",
        leverage=Decimal("1"),
        entry_price=Decimal("100"),
        stop_price=Decimal("50"),
        market_data_time=now,
    )
    blocked = trader.run(order=order, decision=forged, idea=idea, case_id="case-forged", now=now)
    assert blocked.transmitted is False
    assert events == ["risk"]
    assert blocked.status == "skipped"

    events.clear()
    tight = order.model_copy(update={"client_order_id": "tight-1", "notional": Decimal("50"), "stop_price": Decimal("99.5")})
    idea = idea.model_copy(update={"client_order_id": "tight-1", "request_live": True})
    rejected = trader.run(order=tight, decision=forged, idea=idea, case_id="case-tight", now=now)
    assert rejected.transmitted is False
    assert events == ["risk", "gate"]
    assert "coinbase" not in events
    assert "dry" not in events
