"""Average-cost P&L from Coinbase fills. Fees are part of cost basis and of sale proceeds.

A missing mark price leaves unrealized P&L unset. It is not replaced with zero.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal


def _dec(value: object, default: str = "0") -> Decimal:
    if value is None or value == "":
        return Decimal(default)
    return Decimal(str(value))


def _side(value: object) -> str:
    text = str(value or "").upper()
    if text in {"BUY", "B"}:
        return "BUY"
    if text in {"SELL", "S"}:
        return "SELL"
    return text


def compute_portfolio(fills: list[dict], marks: dict[str, dict] | None = None) -> dict:
    """`marks` maps product_id to {price, source, fetched_at}. Quote-currency P&L, no invented FX."""

    marks = marks or {}
    books: dict[str, dict] = {}
    ordered = sorted(fills, key=lambda item: str(item.get("trade_time") or item.get("sequence_timestamp") or ""))
    for fill in ordered:
        product_id = str(fill.get("product_id") or "")
        if not product_id:
            continue
        book = books.setdefault(
            product_id,
            {
                "product_id": product_id,
                "quantity": Decimal("0"),
                "cost": Decimal("0"),
                "realized": Decimal("0"),
                "fees": Decimal("0"),
                "clipped_sell": False,
            },
        )
        qty = _dec(fill.get("size") or fill.get("base_size"))
        price = _dec(fill.get("price"))
        fee = _dec(fill.get("commission") or fill.get("fee"))
        side = _side(fill.get("side"))
        if qty <= 0 or price <= 0 or side not in {"BUY", "SELL"}:
            continue
        book["fees"] += fee
        if side == "BUY":
            book["cost"] += qty * price + fee
            book["quantity"] += qty
            continue
        sell_qty = qty
        if sell_qty > book["quantity"]:
            sell_qty = book["quantity"]
            book["clipped_sell"] = True
        if sell_qty <= 0 or book["quantity"] <= 0:
            continue
        average = book["cost"] / book["quantity"]
        basis = average * sell_qty
        proceeds = sell_qty * price - fee
        book["realized"] += proceeds - basis
        book["cost"] -= basis
        book["quantity"] -= sell_qty
        if book["quantity"] == 0:
            book["cost"] = Decimal("0")

    positions = []
    realized_total = Decimal("0")
    unrealized_total = Decimal("0")
    unrealized_known = True
    fees_total = Decimal("0")
    for product_id, book in sorted(books.items()):
        mark = marks.get(product_id)
        mark_price = _dec(mark.get("price")) if mark and mark.get("price") not in (None, "") else None
        unrealized = None
        if book["quantity"] == 0:
            unrealized = Decimal("0")
        elif mark_price is not None and mark_price > 0:
            unrealized = book["quantity"] * mark_price - book["cost"]
        else:
            unrealized_known = False
        average = book["cost"] / book["quantity"] if book["quantity"] > 0 else Decimal("0")
        realized_total += book["realized"]
        fees_total += book["fees"]
        if unrealized is not None:
            unrealized_total += unrealized
        positions.append(
            {
                "product_id": product_id,
                "quantity": format(book["quantity"], "f"),
                "cost_basis": format(book["cost"], "f"),
                "average_cost": format(average, "f"),
                "realized_pnl": format(book["realized"], "f"),
                "unrealized_pnl": None if unrealized is None else format(unrealized, "f"),
                "fees": format(book["fees"], "f"),
                "mark_price": None if mark_price is None else format(mark_price, "f"),
                "mark_source": None if not mark else mark.get("source"),
                "mark_time": _time(mark.get("fetched_at")) if mark else None,
                "clipped_sell": book["clipped_sell"],
                "pnl_currency": "quote",
            }
        )
    return {
        "positions": positions,
        "realized_pnl": format(realized_total, "f"),
        "unrealized_pnl": None if not unrealized_known else format(unrealized_total, "f"),
        "total_pnl": None if not unrealized_known else format(realized_total + unrealized_total, "f"),
        "fees": format(fees_total, "f"),
        "method": "average_cost",
        "fees_included": True,
        "fx_applied": False,
    }


def _time(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if value:
        return str(value)
    return None
