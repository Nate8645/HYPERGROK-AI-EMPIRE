"""Hyperliquid info client. Transport is fake; these tests do not open a socket."""

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from hypergrok.marketdata.hyperliquid import (
    SOURCE,
    USER_AGENT,
    HttpxTransport,
    HyperliquidInfoClient,
    InfoEnvelope,
    MarketDataError,
    mid_for,
    parse_all_mids,
    parse_l2_book,
    parse_meta_names,
    snapshot_from_l2,
)

FIXED = datetime(2026, 11, 9, 15, 0, tzinfo=timezone.utc)
URL = "https://api.hyperliquid.xyz/info"


class FakeTransport:
    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        self.calls: list[tuple] = []

    def post_json(self, url: str, body: dict, timeout: float) -> tuple[int, str]:
        self.calls.append((url, body, timeout))
        return self.status, self.body


def test_all_mids_are_labelled_and_missing_coins_are_not_invented() -> None:
    transport = FakeTransport(200, json.dumps({"BTC": "65000.5", "ETH": "2400"}))
    client = HyperliquidInfoClient(base_url=URL, transport=transport, clock=lambda: FIXED)
    envelope = client.all_mids()
    assert envelope.source == SOURCE
    assert envelope.endpoint == URL
    assert envelope.request_type == "allMids"
    assert envelope.fetched_at == FIXED
    assert envelope.exchange_time is None
    mids = parse_all_mids(envelope.payload)
    assert mids["BTC"] == Decimal("65000.5")
    assert mid_for(mids, "DOGE") is None
    assert transport.calls == [(URL, {"type": "allMids"}, 10.0)]


def test_l2_book_snapshot_keeps_source_fetch_time_and_exchange_time() -> None:
    exchange = FIXED - timedelta(hours=1)
    payload = {
        "coin": "BTC",
        "time": int(exchange.timestamp() * 1000),
        "levels": [
            [{"px": "64990", "sz": "5", "n": 2}],
            [{"px": "65010", "sz": "1", "n": 1}],
        ],
    }
    transport = FakeTransport(200, json.dumps(payload))
    client = HyperliquidInfoClient(base_url=URL, transport=transport, clock=lambda: FIXED, timeout_seconds=3)
    envelope = client.l2_book("btc")
    assert transport.calls[0][1] == {"type": "l2Book", "coin": "BTC"}
    book = parse_l2_book(envelope.payload)
    assert book.bids[0].px == Decimal("64990")
    assert book.asks[0].sz == Decimal("1")
    snapshot = snapshot_from_l2(envelope)
    assert snapshot.source == SOURCE
    assert snapshot.symbol == "BTC"
    assert snapshot.fetched_at == FIXED
    assert snapshot.mid == Decimal("65000")
    assert snapshot.exchange_time is not None
    assert snapshot.observed_at() == snapshot.exchange_time
    assert snapshot.observed_at() < snapshot.fetched_at


def test_meta_names_and_failures_do_not_invent_a_book() -> None:
    transport = FakeTransport(200, json.dumps({"universe": [{"name": "BTC", "szDecimals": 5}, {"name": "ETH"}]}))
    client = HyperliquidInfoClient(base_url=URL, transport=transport, clock=lambda: FIXED)
    envelope = client.meta()
    assert parse_meta_names(envelope.payload) == ["BTC", "ETH"]

    empty = InfoEnvelope(
        source=SOURCE,
        endpoint=URL,
        request_type="l2Book",
        fetched_at=FIXED,
        exchange_time=None,
        payload={"coin": "BTC", "levels": [[], [{"px": "1", "sz": "1"}]]},
    )
    with pytest.raises(MarketDataError):
        snapshot_from_l2(empty)

    broken = HyperliquidInfoClient(
        base_url=URL,
        transport=FakeTransport(500, "{}"),
        clock=lambda: FIXED,
    )
    with pytest.raises(MarketDataError):
        broken.all_mids()

    garbage = HyperliquidInfoClient(
        base_url=URL,
        transport=FakeTransport(200, "not-json"),
        clock=lambda: FIXED,
    )
    with pytest.raises(MarketDataError):
        garbage.meta()


def test_httpx_transport_can_be_mocked_without_a_network() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == URL
        assert json.loads(request.content) == {"type": "allMids"}
        return httpx.Response(200, json={"BTC": "1.25"})

    transport = HttpxTransport(
        client_factory=lambda timeout: httpx.Client(transport=httpx.MockTransport(handler), timeout=timeout)
    )
    client = HyperliquidInfoClient(base_url=URL, transport=transport, clock=lambda: FIXED)
    envelope = client.all_mids()
    assert mid_for(parse_all_mids(envelope.payload), "BTC") == Decimal("1.25")
    assert mid_for(parse_all_mids(envelope.payload), "SOL") is None

    default = HttpxTransport._default_client(1)
    try:
        assert default.headers["User-Agent"] == USER_AGENT
    finally:
        default.close()
