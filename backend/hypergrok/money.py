"""Decimal helpers. Money is never carried as a binary float."""

from __future__ import annotations

from decimal import Decimal, ROUND_DOWN
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer


def parse_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError("send numeric values as decimal strings, not floats")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value)
        except Exception as exc:
            raise ValueError("invalid decimal") from exc
    raise ValueError("invalid decimal")


def format_decimal(value: Decimal) -> str:
    return format(value, "f")


Dec = Annotated[
    Decimal,
    BeforeValidator(parse_decimal),
    PlainSerializer(format_decimal, return_type=str, when_used="json"),
]


def floor_money(amount: Decimal, quantum: str = "0.01") -> Decimal:
    if amount <= 0:
        return Decimal("0")
    return amount.quantize(Decimal(quantum), rounding=ROUND_DOWN)


def floor_to_increment(amount: Decimal, increment: Decimal) -> Decimal:
    """Round down to an exchange increment. Never rounds up."""

    if increment <= 0:
        raise ValueError("increment must be positive")
    if amount <= 0:
        return Decimal("0")
    steps = (amount / increment).to_integral_value(rounding=ROUND_DOWN)
    return steps * increment
