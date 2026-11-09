"""BUY and SELL cases against a mocked Coinbase client. No network and no live order."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from tests.support import authed

from hypergrok.venues.coinbase.broker import CoinbaseBroker
from hypergrok.venues.coinbase.utilization import backtest_for_product, funded_quote_currency, utilization_variants
from tests.test_coinbase import SECRET, Boom, FakeCoinbase, _app, _order

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "coinbase_read_2026-11-09.json").read_text(encoding="utf-8"))
NOW = datetime.now(timezone.utc)


def _usdc_product() -> dict:
    product = dict(FIXTURE["products"]["BTC-USDC"])
    product["base_max_size"] = "3400"
    product["quote_max_size"] = "150000000"
    return product


def _funded(fake: FakeCoinbase, *, btc: str = "0") -> None:
    fake.product = _usdc_product()
    fake.accounts = {
        "accounts": [
            {"available_balance": {"value": FIXTURE["balances"][0]["available"], "currency": "USDC"}, "hold": {"value": "0", "currency": "USDC"}},
            {"available_balance": {"value": btc, "currency": "BTC"}, "hold": {"value": "0", "currency": "BTC"}},
        ]
    }
    fake.summary = {"fee_tier": FIXTURE["fee_tier"]}
    book = FIXTURE["btc_usdc_book"]
    fake.book = {"pricebook": book}


def test_fixture_selects_usdc_and_is_not_a_live_default() -> None:
    assert funded_quote_currency(FIXTURE["balances"]) == "USDC"
    assert FIXTURE["usd_account_returned"] is False
    assert FIXTURE["fee_tier"]["taker_fee_rate"] == "0.001"
    assert FIXTURE["products"]["ETH-USDC"]["quote_min_size"] == "1"
    assert FIXTURE["products"]["SOL-USDC"]["status"] == "online"


def test_buy_preview_sell_holdings_and_balance_blocks() -> None:
    fake = FakeCoinbase()
    _funded(fake, btc="0.01")
    app = _app(fake, account_currency="USDC", starting_capital=Decimal("10.896768"), min_order_notional=Decimal("1"), min_order_notional_currency="USDC")
    with authed(app) as client:
        bought = client.post(
            "/api/coinbase/orders",
            json=_order(client_order_id="buy-preview", quote_size="2", entry_price="100", stop_price="99.5"),
        ).json()
        assert bought["status"] == "recorded"
        assert bought["transmitted"] is False
        assert bought["preview"]["rejected"] is False
        assert "preview_market_order" in fake.calls
        assert "market_order" not in fake.calls

        sold = client.post(
            "/api/coinbase/orders",
            json=_order(client_order_id="sell-preview", side="sell", order_type="market", quote_size=None, base_size="0.01", entry_price="100", stop_price="100.2"),
        ).json()
        assert sold["status"] == "recorded"
        assert sold["transmitted"] is False
        assert "market_order" not in fake.calls

        short = client.post(
            "/api/coinbase/orders",
            json=_order(client_order_id="sell-too-big", side="sell", quote_size=None, base_size="0.012", entry_price="100", stop_price="100.2"),
        ).json()
        assert short["reason"] == "sell_exceeds_holdings"
        assert short["transmitted"] is False

        fake.accounts["accounts"][0]["available_balance"]["value"] = "1"
        poor = client.post(
            "/api/coinbase/orders",
            json=_order(client_order_id="buy-poor", quote_size="2", entry_price="100", stop_price="99.5"),
        ).json()
        assert poor["reason"] == "insufficient_balance"

    flat_fake = FakeCoinbase()
    _funded(flat_fake, btc="0")
    flat_app = _app(flat_fake, account_currency="USDC", starting_capital=Decimal("10.896768"), min_order_notional=Decimal("1"), min_order_notional_currency="USDC")
    with authed(flat_app) as client:
        flat = client.post(
            "/api/coinbase/orders",
            json=_order(client_order_id="sell-flat", side="sell", quote_size=None, base_size="0.01", entry_price="100", stop_price="100.2"),
        ).json()
        assert flat["reason"] == "no_position"
        assert "market_order" not in flat_fake.calls


def test_min_size_fees_slippage_and_risk_cap() -> None:
    product = _usdc_product()
    from hypergrok.venues.coinbase.market import prepare_order_sizes

    try:
        prepare_order_sizes(product, {"side": "buy", "order_type": "market", "quote_size": "0.50"})
    except Exception as exc:
        assert exc.code == "min_size"
    else:
        raise AssertionError("min size was not enforced")

    book = FIXTURE["btc_usdc_book"]
    report = utilization_variants(
        tradable=Decimal(FIXTURE["balances"][0]["available"]),
        quote_currency="USDC",
        taker_fee_rate=Decimal(FIXTURE["fee_tier"]["taker_fee_rate"]),
        maker_fee_rate=Decimal(FIXTURE["fee_tier"]["maker_fee_rate"]),
        quote_increment=Decimal("0.01"),
        quote_min_size=Decimal("1"),
        stop_fraction=Decimal("0.01"),
        equity=Decimal(FIXTURE["balances"][0]["available"]),
        max_risk_fraction=Decimal("0.01"),
        bids=book["bids"],
        asks=book["asks"],
        side="buy",
        backtest=backtest_for_product({"products": {}}, "BTC-USDC"),
    )
    assert report["backtest"] == "Keine Daten"
    by_fraction = {row["fraction"]: row for row in report["variants"]}
    assert by_fraction["0.10"]["min_size_ok"] is True
    assert by_fraction["0.10"]["fee_rate"] == "0.001"
    assert by_fraction["0.10"]["slippage"] != "Keine Daten"
    assert Decimal(by_fraction["0.10"]["fee"]) == Decimal(by_fraction["0.10"]["notional"]) * Decimal("0.001")
    assert by_fraction["1"]["risk_allowed"] is False
    assert by_fraction["0.10"]["risk_allowed"] is True

    fake = FakeCoinbase()
    _funded(fake, btc="0")
    app = _app(fake)
    body = app.state.coinbase.capital_utilization(product_id="BTC-USDC", side="buy", stop_fraction=Decimal("0.01"))
    assert body["available"] is True
    assert body["quote_currency"] == "USDC"
    assert body["backtest"] == "Keine Daten"
    assert SECRET not in json.dumps(body)


def test_duplicate_unknown_permissions_risk_kill_and_unauthorized() -> None:
    fake = FakeCoinbase()
    _funded(fake, btc="0.5")
    app = _app(
        fake,
        account_currency="USDC",
        starting_capital=Decimal("10.896768"),
        min_order_notional=Decimal("1"),
        min_order_notional_currency="USDC",
        live_trading_enabled=True,
        coinbase_live_enabled=True,
        coinbase_product_allowlist="BTC-USDC",
        coinbase_max_capital=Decimal("10.896768"),
    )
    with authed(app) as client:
        dup_order = _order(client_order_id="dup-1", quote_size="2", entry_price="100", stop_price="99.5")
        token = client.post("/api/approvals", json={"client_order_id": "dup-1", "order": dup_order}).json()["token"]
        first = client.post(
            "/api/coinbase/orders",
            json=_order(client_order_id="dup-1", quote_size="2", entry_price="100", stop_price="99.5", request_live=True, approval_token=token),
        ).json()
        assert first["transmitted"] is True
        assert fake.calls.count("market_order") == 1
        assert "get_order" in fake.calls
        second = client.post(
            "/api/coinbase/orders",
            json=_order(client_order_id="dup-1", quote_size="2", entry_price="100", stop_price="99.5", request_live=True, approval_token=token),
        ).json()
        assert second["reason"] == "risk_rejected"
        assert "duplicate_client_order_id" in second["decision"]["reasons"]
        assert fake.calls.count("market_order") == 1

        blocked = client.post(
            "/api/coinbase/orders",
            json=_order(client_order_id="no-token", quote_size="2", entry_price="100", stop_price="99.5", request_live=True),
        ).json()
        assert blocked["reason"] == "missing_human_approval"
        assert blocked["transmitted"] is False

        wide = client.post(
            "/api/coinbase/orders",
            json=_order(client_order_id="wide-usdc", quote_size="8", entry_price="100", stop_price="90", request_live=True, approval_token="ignored"),
        ).json()
        assert wide["reason"] == "risk_rejected"
        assert "planned_risk" in wide["decision"]["reasons"]

        client.post("/api/risk/kill-switch", json={"engaged": True, "reason": "halt"})
        halted = client.post(
            "/api/coinbase/orders",
            json=_order(client_order_id="halt-usdc", quote_size="2", entry_price="100", stop_price="99.5", request_live=True),
        ).json()
        assert "kill_switch" in halted["decision"]["reasons"]
        assert fake.calls.count("market_order") == 1

        fake.fail = Boom(403, "Missing required scopes")
        denied = client.get("/api/coinbase/balances")
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "missing_api_permissions"
        fake.fail = None

    fresh = FakeCoinbase()
    _funded(fresh, btc="0")
    fresh.created = Boom(504, "gateway timeout")
    fresh.orders = {"orders": []}
    fresh_app = _app(
        fresh,
        account_currency="USDC",
        starting_capital=Decimal("10.896768"),
        min_order_notional=Decimal("1"),
        min_order_notional_currency="USDC",
    )
    from hypergrok.agents.risk_manager import RiskManager
    from hypergrok.domain import OrderIntent

    moment = datetime.now(timezone.utc)
    RiskManager(fresh_app.state.risk_service).run(
        OrderIntent(
            client_order_id="unknown-usdc",
            venue="coinbase",
            symbol="BTC-USDC",
            side="buy",
            notional=Decimal("2"),
            notional_currency="USDC",
            leverage=Decimal("1"),
            entry_price=Decimal("100"),
            stop_price=Decimal("99.5"),
            market_data_time=moment,
        ),
        now=moment,
        case_id="case-unknown-usdc",
    )
    before = fresh.calls.count("market_order")
    broker = CoinbaseBroker(fresh, clock=lambda: moment, store=fresh_app.state.store)
    first_unknown = broker.submit(
        {"client_order_id": "unknown-usdc", "product_id": "BTC-USDC", "side": "buy", "order_type": "market", "quote_size": "2", "entry_price": "100", "stop_price": "99.5", "base_size": None}
    )
    assert first_unknown["status"] == "unknown"
    assert "list_orders" in fresh.calls
    restarted = CoinbaseBroker(fresh, clock=lambda: moment, store=fresh_app.state.store)
    restarted.submit(
        {"client_order_id": "unknown-usdc", "product_id": "BTC-USDC", "side": "buy", "order_type": "market", "quote_size": "2", "entry_price": "100", "stop_price": "99.5", "base_size": None}
    )
    assert fresh.calls.count("market_order") == before + 1


def test_limit_post_only_and_team_preview_does_not_submit() -> None:
    fake = FakeCoinbase()
    _funded(fake, btc="0.5")
    app = _app(fake, account_currency="USD", starting_capital=Decimal("1000"), coinbase_product_allowlist="BTC-USD")
    fake.product = FakeCoinbase().product
    with authed(app) as client:
        fake.accounts["accounts"].append(
            {"available_balance": {"value": "1000", "currency": "USD"}, "hold": {"value": "0", "currency": "USD"}}
        )
        limited = client.post(
            "/api/coinbase/orders",
            json=_order(
                client_order_id="limit-1",
                product_id="BTC-USD",
                order_type="limit",
                quote_size=None,
                base_size="0.2",
                limit_price="100",
                entry_price="100",
                stop_price="99.5",
                post_only=True,
            ),
        ).json()
        assert limited["transmitted"] is False
        assert "preview_limit_order_gtc" in fake.calls
        assert "market_order" not in fake.calls

        team = client.post(
            "/api/desk/team",
            json={
                "symbol": "BTC-USD",
                "venue": "coinbase",
                "side": "buy",
                "thesis": "Bid-heavy book and a supplied uptrend.",
                "size_mode": "risk_limited",
                "client_order_id": "team-1",
                "request_live": True,
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
    assert [row["agent"] for row in team["agents"]] == [
        "desk_lead",
        "market_analyst",
        "research_analyst",
        "strategist",
        "risk_manager",
        "execution_trader",
        "trade_reviewer",
    ]
    assert all(row["mode"] == "rule_based" for row in team["agents"])
    assert team["submitted"] is False
    assert team["preview"]["rejected"] is False
    assert team["execution"]["transmitted"] is False
    assert "market_order" not in fake.calls
    assert "limit_order_gtc" not in fake.calls


def test_public_ticker_failure_is_keine_daten() -> None:
    app = _app()

    class Transport:
        def get(self, url, timeout):
            assert "BTC-USDC" in url
            return 500, ""

    body = app.state.coinbase.public_tickers(["BTC-USDC"], transport=Transport())
    assert body["tickers"][0]["detail"] == "Keine Daten"
