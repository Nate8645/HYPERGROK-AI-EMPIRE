from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from hypergrok.config import Settings
from hypergrok.domain import DeskIdea, MarketSnapshot, ResearchInput


OPERATOR_PASSWORD = "test-operator-password"


def auth_overrides() -> dict:
    from hypergrok.auth import hash_password

    return {
        "auth_username": "operator",
        "auth_password_hash": hash_password(OPERATOR_PASSWORD, salt=b"operator-salt-16b", iterations=1000),
        "auth_rate_limit_per_minute": 100000,
        "auth_login_limit_per_minute": 10000,
    }


def make_settings(**overrides: object) -> Settings:
    values: dict = {
        "database_url": "sqlite://",
        "account_currency": "USD",
        "starting_capital": Decimal("1000"),
        "max_market_data_age_seconds": 60,
        "default_fee_bps_round_trip": Decimal("10"),
        "default_slippage_bps_round_trip": Decimal("10"),
        "live_trading_enabled": False,
        **auth_overrides(),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def login(client, username: str = "operator", password: str = OPERATOR_PASSWORD) -> None:
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    if response.status_code != 200:
        raise AssertionError(response.text)


from contextlib import contextmanager


@contextmanager
def authed(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        login(client)
        yield client


def fresh_snapshot(now: datetime | None = None) -> MarketSnapshot:
    moment = now or datetime.now(timezone.utc)
    return MarketSnapshot(
        source="hyperliquid_public_info",
        symbol="BTC",
        fetched_at=moment,
        raw_type="l2Book",
        mid=Decimal("65000"),
        bid=Decimal("64990"),
        ask=Decimal("65010"),
        bid_size=Decimal("5"),
        ask_size=Decimal("1"),
    )


def fitting_idea(now: datetime | None = None, **overrides: object) -> DeskIdea:
    moment = now or datetime.now(timezone.utc)
    values: dict = {
        "symbol": "BTC",
        "venue": "hyperliquid",
        "side": "buy",
        "thesis": "Bid-heavy book and a supplied uptrend.",
        "size_mode": "risk_limited",
        "market_snapshot": fresh_snapshot(moment),
        "research": ResearchInput(trend="up", funding_bps=Decimal("1"), notes="caller supplied"),
    }
    values.update(overrides)
    return DeskIdea(**values)


def sample_order(client_order_id: str = "ord-1", **overrides: object) -> dict:
    body = {
        "client_order_id": client_order_id,
        "venue": "hyperliquid",
        "symbol": "BTC",
        "side": "buy",
        "order_kind": "entry",
        "notional": "50",
        "notional_currency": "USD",
        "leverage": "1",
        "entry_price": "100",
        "stop_price": "99.5",
        "market_data_time": datetime.now(timezone.utc).isoformat(),
        "fee_bps_round_trip": "10",
        "slippage_bps_round_trip": "10",
    }
    body.update(overrides)
    return body
