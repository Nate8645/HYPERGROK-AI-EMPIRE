"""Cached Coinbase spot product rules.

A missing field stays missing. This module does not fill in a 10 USD minimum
or any other default size.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from hypergrok.clock import ensure_utc


@dataclass(frozen=True)
class SpotProduct:
    product_id: str
    quote_currency: str
    base_currency: str
    quote_min_size: Decimal
    base_min_size: Decimal
    quote_increment: Decimal
    base_increment: Decimal
    taker_fee_rate: Decimal
    maker_fee_rate: Decimal
    source: str
    fetched_at: datetime


def verified_usdc_product(product_id: str, base_currency: str, fetched_at: datetime, *, source: str) -> SpotProduct:
    """The 2026-11-09 verified BTC/ETH/SOL-USDC rules. Tests pass their own timestamp."""

    return SpotProduct(
        product_id=product_id,
        quote_currency="USDC",
        base_currency=base_currency,
        quote_min_size=Decimal("1"),
        base_min_size=Decimal("0.00000001"),
        quote_increment=Decimal("0.01"),
        base_increment=Decimal("0.00000001"),
        taker_fee_rate=Decimal("0.001"),
        maker_fee_rate=Decimal("0.0009"),
        source=source,
        fetched_at=ensure_utc(fetched_at),
    )


def spot_product_from_payload(
    payload: dict,
    *,
    fetched_at: datetime,
    taker_fee_rate: Decimal,
    maker_fee_rate: Decimal,
    source: str,
) -> SpotProduct | None:
    """Build a product only when every required field is present and positive."""

    product_id = str(payload.get("product_id") or "").upper()
    quote = str(payload.get("quote_currency_id") or payload.get("quote_currency") or "").upper()
    base = str(payload.get("base_currency_id") or payload.get("base_currency") or "").upper()
    if not product_id or not quote or not base:
        return None
    if taker_fee_rate <= 0 or maker_fee_rate <= 0:
        return None
    try:
        quote_min = Decimal(str(payload["quote_min_size"]))
        base_min = Decimal(str(payload["base_min_size"]))
        quote_inc = Decimal(str(payload["quote_increment"]))
        base_inc = Decimal(str(payload["base_increment"]))
    except (KeyError, ValueError, ArithmeticError):
        return None
    if min(quote_min, base_min, quote_inc, base_inc) <= 0:
        return None
    return SpotProduct(
        product_id=product_id,
        quote_currency=quote,
        base_currency=base,
        quote_min_size=quote_min,
        base_min_size=base_min,
        quote_increment=quote_inc,
        base_increment=base_inc,
        taker_fee_rate=taker_fee_rate,
        maker_fee_rate=maker_fee_rate,
        source=source,
        fetched_at=ensure_utc(fetched_at),
    )
