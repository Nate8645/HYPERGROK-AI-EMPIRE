"""Read-only Hyperliquid info client.

POST https://api.hyperliquid.xyz/info with type allMids, l2Book, or meta.
Responses are labelled with source `hyperliquid_public_info` and the local
fetch time. Missing coins and unexpected shapes raise or return None.
This module does not invent prices and does not send orders.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict

from hypergrok.clock import utcnow
from hypergrok.domain import MarketSnapshot
from hypergrok.money import Dec

SOURCE = "hyperliquid_public_info"
USER_AGENT = "hypergrok-phase1/0.1 (read-only)"


class MarketDataError(Exception):
    """The public info endpoint did not return usable data. Nothing is fabricated."""


class InfoTransport(Protocol):
    def post_json(self, url: str, body: dict, timeout: float) -> tuple[int, str]:
        """Return HTTP status and response text."""


class InfoEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    endpoint: str
    request_type: str
    fetched_at: datetime
    exchange_time: datetime | None
    payload: Any


class BookLevel(BaseModel):
    px: Dec
    sz: Dec


class L2Book(BaseModel):
    coin: str
    bids: list[BookLevel]
    asks: list[BookLevel]
    exchange_time: datetime | None


class HttpxTransport:
    def __init__(self, client_factory: Callable[[float], httpx.Client] | None = None) -> None:
        self._client_factory = client_factory or self._default_client

    @staticmethod
    def _default_client(timeout: float) -> httpx.Client:
        return httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT})

    def post_json(self, url: str, body: dict, timeout: float) -> tuple[int, str]:
        with self._client_factory(timeout) as client:
            response = client.post(url, json=body)
            return response.status_code, response.text


class HyperliquidInfoClient:
    def __init__(
        self,
        *,
        base_url: str,
        transport: InfoTransport | None = None,
        timeout_seconds: float = 10.0,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.base_url = base_url
        self.transport = transport or HttpxTransport()
        self.timeout_seconds = timeout_seconds
        self.clock = clock or utcnow

    def all_mids(self) -> InfoEnvelope:
        return self._call({"type": "allMids"})

    def l2_book(self, coin: str) -> InfoEnvelope:
        if not coin or not coin.strip():
            raise MarketDataError("coin is required")
        return self._call({"type": "l2Book", "coin": coin.strip().upper()})

    def meta(self) -> InfoEnvelope:
        return self._call({"type": "meta"})

    def _call(self, body: dict) -> InfoEnvelope:
        status, text = self.transport.post_json(self.base_url, body, self.timeout_seconds)
        fetched_at = self.clock()
        if status != 200:
            raise MarketDataError(f"hyperliquid info HTTP {status}")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MarketDataError("hyperliquid info returned non-JSON") from exc
        return InfoEnvelope(
            source=SOURCE,
            endpoint=self.base_url,
            request_type=str(body.get("type", "")),
            fetched_at=fetched_at,
            exchange_time=_exchange_time(payload),
            payload=payload,
        )


def parse_all_mids(payload: Any) -> dict[str, Decimal]:
    if not isinstance(payload, dict):
        raise MarketDataError("allMids payload must be an object")
    mids: dict[str, Decimal] = {}
    for key, value in payload.items():
        if key == "time":
            continue
        try:
            mids[str(key).upper()] = Decimal(str(value))
        except Exception as exc:
            raise MarketDataError(f"allMids price for {key} is not a decimal") from exc
    return mids


def mid_for(mids: dict[str, Decimal], coin: str) -> Decimal | None:
    return mids.get(coin.upper())


def parse_l2_book(payload: Any) -> L2Book:
    if not isinstance(payload, dict):
        raise MarketDataError("l2Book payload must be an object")
    coin = payload.get("coin")
    levels = payload.get("levels")
    if not isinstance(coin, str) or not coin:
        raise MarketDataError("l2Book coin is missing")
    if not isinstance(levels, list) or len(levels) < 2:
        raise MarketDataError("l2Book levels are missing")
    return L2Book(
        coin=coin.upper(),
        bids=_parse_levels(levels[0]),
        asks=_parse_levels(levels[1]),
        exchange_time=_exchange_time(payload),
    )


def parse_meta_names(payload: Any) -> list[str]:
    if not isinstance(payload, dict) or not isinstance(payload.get("universe"), list):
        raise MarketDataError("meta universe is missing")
    names: list[str] = []
    for row in payload["universe"]:
        if not isinstance(row, dict) or "name" not in row:
            raise MarketDataError("meta asset is missing a name")
        names.append(str(row["name"]).upper())
    return names


def snapshot_from_l2(envelope: InfoEnvelope) -> MarketSnapshot:
    book = parse_l2_book(envelope.payload)
    if not book.bids or not book.asks:
        raise MarketDataError(f"no top of book for {book.coin}")
    bid = book.bids[0]
    ask = book.asks[0]
    if bid.px <= 0 or ask.px <= 0 or ask.px < bid.px:
        raise MarketDataError(f"unusable top of book for {book.coin}")
    mid = (bid.px + ask.px) / Decimal(2)
    return MarketSnapshot(
        source=envelope.source,
        symbol=book.coin,
        fetched_at=envelope.fetched_at,
        raw_type="l2Book",
        mid=mid,
        bid=bid.px,
        ask=ask.px,
        bid_size=bid.sz,
        ask_size=ask.sz,
        exchange_time=envelope.exchange_time or book.exchange_time,
    )


def _parse_levels(raw: Any) -> list[BookLevel]:
    if not isinstance(raw, list):
        raise MarketDataError("book side is not a list")
    levels: list[BookLevel] = []
    for row in raw:
        if not isinstance(row, dict) or "px" not in row or "sz" not in row:
            raise MarketDataError("book level is missing px or sz")
        try:
            levels.append(BookLevel(px=Decimal(str(row["px"])), sz=Decimal(str(row["sz"]))))
        except Exception as exc:
            raise MarketDataError("book level price or size is not a decimal") from exc
    return levels


def _exchange_time(payload: Any) -> datetime | None:
    if not isinstance(payload, dict) or "time" not in payload:
        return None
    raw = payload["time"]
    try:
        millis = int(raw)
    except (TypeError, ValueError) as exc:
        raise MarketDataError("exchange time is not an integer timestamp") from exc
    return datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
