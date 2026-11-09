"""Map Advanced Trade public payloads. Missing fields stay missing."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from hypergrok.clock import ensure_utc
from hypergrok.domain import MarketSnapshot
from hypergrok.money import floor_to_increment

SOURCE = "coinbase_advanced_trade"


class CoinbaseFailure(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        data = value.to_dict()
        if isinstance(data, dict):
            return data
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items() if not str(key).startswith("_")}
    return {}


def classify_exception(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) or getattr(exc, "status_code", None)
    text = str(exc).lower()
    if status == 401 or "invalid api key" in text or "unauthorized" in text:
        return "invalid_api_key"
    if status == 403 or "missing required scopes" in text or "permission" in text:
        return "missing_api_permissions"
    if status is not None and 400 <= int(status) < 500 and int(status) not in {408, 429}:
        return "exchange_rejected"
    return "unknown_outcome"


def _dec(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _levels(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    levels = []
    for row in raw:
        item = as_dict(row) if not isinstance(row, dict) else row
        price = item.get("price") or item.get("px")
        size = item.get("size") or item.get("sz")
        if price is None or size is None:
            continue
        levels.append({"price": str(price), "size": str(size)})
    return levels


def parse_product(payload: object) -> dict:
    data = as_dict(payload)
    product_id = str(data.get("product_id") or "")
    if not product_id:
        raise CoinbaseFailure("invalid_product", "product id is missing")
    return {
        "product_id": product_id.upper(),
        "product_type": str(data.get("product_type") or "").upper(),
        "base_currency": data.get("base_currency_id") or data.get("base_currency"),
        "quote_currency": data.get("quote_currency_id") or data.get("quote_currency"),
        "base_increment": data.get("base_increment"),
        "quote_increment": data.get("quote_increment"),
        "base_min_size": data.get("base_min_size"),
        "base_max_size": data.get("base_max_size"),
        "quote_min_size": data.get("quote_min_size"),
        "quote_max_size": data.get("quote_max_size"),
        "status": data.get("status"),
        "source": SOURCE,
    }


def require_spot(product: dict) -> None:
    if product.get("product_type") != "SPOT":
        raise CoinbaseFailure("not_spot", "only SPOT products can be traded")


def prepare_order_sizes(product: dict, order: dict) -> dict:
    require_spot(product)
    order_type = str(order.get("order_type") or "market")
    side = str(order.get("side") or "").lower()
    if order_type not in {"market", "limit"} or side not in {"buy", "sell"}:
        raise CoinbaseFailure("unsupported_order", "only market IOC and limit GTC spot orders are allowed")
    base_inc = _dec(product.get("base_increment"))
    quote_inc = _dec(product.get("quote_increment"))
    if base_inc is None or quote_inc is None or base_inc <= 0 or quote_inc <= 0:
        raise CoinbaseFailure("invalid_product", "product increments are missing")
    prepared = {
        "product_id": product["product_id"],
        "side": side,
        "order_type": order_type,
        "post_only": bool(order.get("post_only")),
        "client_order_id": order.get("client_order_id"),
    }
    if order_type == "market" and side == "buy":
        quote_size = _dec(order.get("quote_size") or order.get("notional"))
        if quote_size is None:
            raise CoinbaseFailure("invalid_size", "market buy requires a quote size")
        rounded = floor_to_increment(quote_size, quote_inc)
        _check_bound(rounded, product.get("quote_min_size"), product.get("quote_max_size"), "quote")
        prepared["quote_size"] = format(rounded, "f")
        prepared["base_size"] = None
        return prepared
    base_size = _dec(order.get("base_size"))
    if base_size is None:
        raise CoinbaseFailure("invalid_size", "this order requires a base size")
    rounded_base = floor_to_increment(base_size, base_inc)
    _check_bound(rounded_base, product.get("base_min_size"), product.get("base_max_size"), "base")
    prepared["base_size"] = format(rounded_base, "f")
    prepared["quote_size"] = None
    if order_type == "limit":
        price = _dec(order.get("limit_price"))
        if price is None or price <= 0:
            raise CoinbaseFailure("invalid_size", "limit orders require a limit price")
        rounded_price = floor_to_increment(price, quote_inc)
        if rounded_price <= 0:
            raise CoinbaseFailure("min_size", "limit price rounds below the quote increment")
        prepared["limit_price"] = format(rounded_price, "f")
    return prepared


def _check_bound(size: Decimal, minimum: object, maximum: object, label: str) -> None:
    min_size = _dec(minimum)
    max_size = _dec(maximum)
    if min_size is not None and size < min_size:
        raise CoinbaseFailure("min_size", f"{label} size {size} is below the product minimum {min_size}")
    if max_size is not None and max_size > 0 and size > max_size:
        raise CoinbaseFailure("max_size", f"{label} size {size} is above the product maximum {max_size}")


def map_preview(payload: object, *, fetched_at: datetime) -> dict:
    data = as_dict(payload)
    errors = data.get("errs") or data.get("errors") or []
    if isinstance(errors, str):
        errors = [errors] if errors else []
    reject_reason = str(data.get("reject_reason") or "")
    rejected = bool(errors) or bool(reject_reason)
    quote_size = _dec(data.get("quote_size"))
    commission = _dec(data.get("commission_total")) or Decimal("0")
    slippage = _dec(data.get("slippage"))
    fee_bps = None
    slip_bps = None
    if quote_size and quote_size > 0:
        fee_bps = commission / quote_size * Decimal("10000")
    if slippage is not None and slippage >= 0:
        slip_bps = slippage * Decimal("10000") if slippage <= 1 else None
        if slip_bps is None and quote_size and quote_size > 0:
            slip_bps = slippage / quote_size * Decimal("10000")
    return {
        "source": SOURCE,
        "fetched_at": ensure_utc(fetched_at).isoformat(),
        "rejected": rejected,
        "errors": [str(item) for item in errors] if isinstance(errors, list) else [],
        "reject_reason": reject_reason,
        "quote_size": None if quote_size is None else format(quote_size, "f"),
        "base_size": None if data.get("base_size") in (None, "") else str(data.get("base_size")),
        "commission_total": format(commission, "f"),
        "fee_bps_one_way": None if fee_bps is None else format(fee_bps, "f"),
        "fee_bps_round_trip": None if fee_bps is None else format(fee_bps * 2, "f"),
        "slippage_bps": None if slip_bps is None else format(slip_bps, "f"),
        "best_bid": data.get("best_bid"),
        "best_ask": data.get("best_ask"),
        "order_total": data.get("order_total"),
    }


def fee_bps_from_summary(payload: object, *, order_type: str, post_only: bool) -> dict:
    data = as_dict(payload)
    tier = data.get("fee_tier") or {}
    tier = as_dict(tier) if not isinstance(tier, dict) else tier
    maker = _dec(tier.get("maker_fee_rate"))
    taker = _dec(tier.get("taker_fee_rate"))
    if maker is None or taker is None:
        raise CoinbaseFailure("fees_unavailable", "transaction summary did not include maker and taker rates")
    maker_bps = maker * Decimal("10000")
    taker_bps = taker * Decimal("10000")
    one_way = maker_bps if order_type == "limit" and post_only else taker_bps
    return {
        "source": SOURCE,
        "pricing_tier": tier.get("pricing_tier"),
        "maker_fee_rate": format(maker, "f"),
        "taker_fee_rate": format(taker, "f"),
        "maker_bps": format(maker_bps, "f"),
        "taker_bps": format(taker_bps, "f"),
        "fee_bps_round_trip": format(one_way * 2, "f"),
    }


def snapshot_from_book(payload: object, *, symbol: str, fetched_at: datetime) -> MarketSnapshot:
    data = as_dict(payload)
    book = data
    books = data.get("pricebook") or data.get("pricebooks")
    if isinstance(books, list) and books:
        book = as_dict(books[0])
    elif isinstance(books, dict):
        book = books
    bids = _levels(book.get("bids"))
    asks = _levels(book.get("asks"))
    if not bids or not asks:
        raise CoinbaseFailure("invalid_book", "top of book is missing")
    bid = Decimal(bids[0]["price"])
    ask = Decimal(asks[0]["price"])
    if bid <= 0 or ask < bid:
        raise CoinbaseFailure("invalid_book", "top of book is not usable")
    exchange_time = _parse_time(book.get("time") or data.get("time"))
    return MarketSnapshot(
        source=SOURCE,
        symbol=symbol,
        fetched_at=ensure_utc(fetched_at),
        raw_type="product_book",
        mid=(bid + ask) / Decimal(2),
        bid=bid,
        ask=ask,
        bid_size=Decimal(bids[0]["size"]),
        ask_size=Decimal(asks[0]["size"]),
        exchange_time=exchange_time,
    )


def parse_best_bid_ask(payload: object, *, fetched_at: datetime) -> list[dict]:
    data = as_dict(payload)
    rows = data.get("pricebooks") or data.get("pricebook") or []
    if isinstance(rows, dict):
        rows = [rows]
    parsed = []
    for row in rows:
        item = as_dict(row) if not isinstance(row, dict) else row
        bids = _levels(item.get("bids"))
        asks = _levels(item.get("asks"))
        parsed.append(
            {
                "source": SOURCE,
                "fetched_at": ensure_utc(fetched_at).isoformat(),
                "product_id": item.get("product_id"),
                "best_bid": bids[0]["price"] if bids else None,
                "best_ask": asks[0]["price"] if asks else None,
                "bid_size": bids[0]["size"] if bids else None,
                "ask_size": asks[0]["size"] if asks else None,
                "exchange_time": item.get("time"),
            }
        )
    return parsed


def parse_candles(payload: object, *, fetched_at: datetime, product_id: str) -> dict:
    data = as_dict(payload)
    raw = data.get("candles") or []
    candles = []
    for row in raw:
        item = as_dict(row) if not isinstance(row, dict) else row
        candles.append(
            {
                "start": item.get("start"),
                "open": item.get("open"),
                "high": item.get("high"),
                "low": item.get("low"),
                "close": item.get("close"),
                "volume": item.get("volume"),
            }
        )
    return {
        "source": SOURCE,
        "fetched_at": ensure_utc(fetched_at).isoformat(),
        "product_id": product_id,
        "candles": candles,
    }


def parse_balances(payload: object) -> dict:
    data = as_dict(payload)
    rows = data.get("accounts") or []
    accounts = []
    funded = False
    for row in rows:
        item = as_dict(row) if not isinstance(row, dict) else row
        available = item.get("available_balance") or {}
        available = as_dict(available) if not isinstance(available, dict) else available
        hold = item.get("hold") or {}
        hold = as_dict(hold) if not isinstance(hold, dict) else hold
        value = _dec(available.get("value")) or Decimal("0")
        if value > 0:
            funded = True
        accounts.append(
            {
                "currency": available.get("currency") or item.get("currency"),
                "available": format(value, "f"),
                "hold": str(hold.get("value") or "0"),
            }
        )
    if not accounts:
        state = "empty"
    elif funded:
        state = "funded"
    else:
        state = "empty"
    return {"source": SOURCE, "account_state": state, "accounts": accounts}


def parse_portfolios(payload: object) -> list[dict]:
    data = as_dict(payload)
    rows = data.get("portfolios") or []
    cleaned = []
    for row in rows:
        item = as_dict(row) if not isinstance(row, dict) else row
        cleaned.append({"uuid": item.get("uuid") or item.get("id"), "name": item.get("name"), "type": item.get("type")})
    return cleaned


def public_order(payload: object) -> dict:
    item = as_dict(payload) if not isinstance(payload, dict) else payload
    allowed = (
        "order_id",
        "product_id",
        "side",
        "status",
        "client_order_id",
        "filled_size",
        "average_filled_price",
        "created_time",
        "total_fees",
        "order_type",
        "completion_percentage",
    )
    return {key: item.get(key) for key in allowed if key in item}


def public_fill(payload: object) -> dict:
    item = as_dict(payload) if not isinstance(payload, dict) else payload
    allowed = (
        "entry_id",
        "trade_id",
        "order_id",
        "product_id",
        "side",
        "size",
        "price",
        "commission",
        "trade_time",
        "sequence_timestamp",
    )
    return {key: item.get(key) for key in allowed if key in item}


def _parse_time(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return ensure_utc(value)
    text = str(value)
    if text.isdigit():
        raw = int(text)
        seconds = raw / 1000 if raw > 10_000_000_000 else raw
        return datetime.fromtimestamp(seconds, tz=timezone.utc)
    try:
        return ensure_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        return None
