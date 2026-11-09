"""Spot exits are monitored. A stop, take-profit, or time stop is not a guaranteed fill.

A gap, a stale book, a network failure, or a partial fill can leave the
position open. This module never reports a fill as guaranteed. The Coinbase
SDK can preview a stop-limit order. This path does not call create-order.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from hypergrok.clock import ensure_utc
from hypergrok.domain import MarketSnapshot, OrderIntent


def assess_exit(
    *,
    quantity: Decimal,
    entry_price: Decimal,
    stop_price: Decimal,
    take_profit_price: Decimal,
    time_stop_at: datetime,
    now: datetime,
    snapshot: MarketSnapshot | None,
    feed_error: str | None,
    max_age_seconds: float,
) -> dict:
    if feed_error or snapshot is None or snapshot.bid is None:
        return {"action": "hold", "reason": "feed_outage", "order": None, "guaranteed_fill": False, "fill_state": "unknown"}
    age = (ensure_utc(now) - snapshot.observed_at()).total_seconds()
    if age > max_age_seconds or age < -2:
        return {"action": "hold", "reason": "stale_market_data", "order": None, "guaranteed_fill": False, "fill_state": "unknown"}
    price = snapshot.bid
    if price <= stop_price:
        reason = "stop"
    elif price >= take_profit_price:
        reason = "take_profit"
    elif ensure_utc(now) >= ensure_utc(time_stop_at):
        reason = "time_stop"
    else:
        return {"action": "hold", "reason": "no_exit", "order": None, "guaranteed_fill": False, "fill_state": "unknown"}
    return {
        "action": "exit",
        "reason": reason,
        "order": {
            "client_order_id": uuid.uuid4().hex,
            "product_id": snapshot.symbol,
            "side": "sell",
            "order_type": "stop_limit" if reason == "stop" else "market",
            "base_size": format(quantity, "f"),
            "entry_price": format(entry_price, "f"),
            "stop_price": format(stop_price, "f"),
            "limit_price": format(price, "f"),
            "market_data_time": snapshot.observed_at(),
        },
        "guaranteed_fill": False,
        "fill_state": "unknown",
    }


def monitor_open_position(
    *,
    quantity: Decimal,
    entry_price: Decimal,
    stop_price: Decimal,
    take_profit_price: Decimal,
    time_stop_at: datetime,
    now: datetime,
    snapshot: MarketSnapshot | None,
    feed_error: str | None,
    max_age_seconds: float,
    currency: str,
    risk_manager,
    store,
    preview,
) -> dict:
    """Preview an exit and store an approval request. This function does not submit."""
    assessed = assess_exit(
        quantity=quantity,
        entry_price=entry_price,
        stop_price=stop_price,
        take_profit_price=take_profit_price,
        time_stop_at=time_stop_at,
        now=now,
        snapshot=snapshot,
        feed_error=feed_error,
        max_age_seconds=max_age_seconds,
    )
    assessed["submitted"] = False
    assessed["preview"] = None
    assessed["approval"] = None
    assessed["risk_status"] = None
    if assessed["action"] != "exit" or assessed["order"] is None:
        return assessed
    intent = exit_intent(assessed["order"], currency=currency)
    decision = risk_manager.run(intent, now=now, case_id=uuid.uuid4().hex)
    assessed["risk_status"] = decision.status
    assessed["risk_reasons"] = list(decision.reasons)
    if decision.status != "PASS":
        return assessed
    if store is not None:
        assessed["approval"] = store.create_approval(
            client_order_id=intent.client_order_id,
            note=f"exit {assessed['reason']}; submit still requires the execution gate",
            now=now,
        )
        assessed["approval"] = {"client_order_id": assessed["approval"]["client_order_id"], "created_at": assessed["approval"]["created_at"]}
    if preview is not None:
        assessed["preview"] = preview(assessed["order"])
    return assessed


def exit_intent(order: dict, *, currency: str) -> OrderIntent:
    base = Decimal(str(order["base_size"]))
    price = Decimal(str(order.get("limit_price") or order["entry_price"]))
    return OrderIntent(
        client_order_id=str(order["client_order_id"]),
        venue="coinbase",
        symbol=str(order["product_id"]),
        side="sell",
        order_kind="reduce",
        notional=base * price,
        notional_currency=currency,
        leverage=Decimal("1"),
        entry_price=Decimal(str(order["entry_price"])),
        stop_price=Decimal(str(order["stop_price"])),
        market_data_time=order["market_data_time"],
    )
