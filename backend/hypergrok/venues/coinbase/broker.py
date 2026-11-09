"""Spot order calls. An unknown result is reconciled once and never retried."""

from __future__ import annotations

from datetime import datetime

from hypergrok.clock import utcnow
from hypergrok.agents.risk_manager import risk_passed
from hypergrok.order_binding import fingerprint
from hypergrok.venues.coinbase.market import (
    CoinbaseFailure,
    as_dict,
    classify_exception,
    map_preview,
    public_fill,
    public_order,
)


class CoinbaseBroker:
    def __init__(self, client, *, clock=utcnow, store=None, recheck=None) -> None:
        self.client = client
        self.clock = clock
        self.store = store
        self.recheck = recheck
        self._attempted: set[str] = store.dispatched_client_order_ids() if store is not None else set()

    def preview(self, prepared: dict) -> dict:
        side = prepared["side"].upper()
        if prepared["order_type"] == "market":
            raw = self.client.preview_market_order(
                product_id=prepared["product_id"],
                side=side,
                quote_size=prepared.get("quote_size"),
                base_size=prepared.get("base_size"),
            )
        elif prepared["order_type"] == "stop_limit":
            raw = self.client.preview_stop_limit_order_gtc(
                product_id=prepared["product_id"],
                side=side,
                base_size=prepared["base_size"],
                limit_price=prepared["limit_price"],
                stop_price=prepared["stop_price"],
                stop_direction=prepared.get("stop_direction") or "STOP_DIRECTION_STOP_DOWN",
            )
        else:
            raw = self.client.preview_limit_order_gtc(
                product_id=prepared["product_id"],
                side=side,
                base_size=prepared["base_size"],
                limit_price=prepared["limit_price"],
                post_only=bool(prepared.get("post_only")),
            )
        mapped = map_preview(raw, fetched_at=self.clock())
        if mapped["rejected"]:
            raise CoinbaseFailure("preview_rejected", "the preview endpoint rejected the order")
        return mapped

    def submit(self, prepared: dict) -> dict:
        client_order_id = str(prepared.get("client_order_id") or "")
        if not client_order_id:
            raise CoinbaseFailure("invalid_order", "client_order_id is required")
        order_hash = fingerprint(prepared)
        grant = self.store.find_grant(client_order_id, order_hash, self.clock()) if self.store is not None else None
        if grant is None and not risk_passed(client_order_id):
            raise CoinbaseFailure("risk_manager_required", "the risk manager has not passed this order")
        if self.store is not None and grant is None:
            raise CoinbaseFailure("risk_grant_mismatch", "the risk pass does not match this order")
        if self.store is not None and self.store.get_kill_switch().engaged:
            raise CoinbaseFailure("kill_switch", "the kill switch is engaged")
        if self.recheck is not None and not self.recheck(prepared, None if grant is None else grant["case_id"]):
            raise CoinbaseFailure("risk_recheck_failed", "the order failed the pre-send re-check")
        if client_order_id in self._attempted:
            found = self.reconcile(client_order_id)
            if found:
                found["retried"] = False
                return found
            return {"status": "unknown", "retried": False, "reason": "already_attempted", "client_order_id": client_order_id}
        if self.store is not None:
            if not self.store.claim_dispatch(client_order_id, self.clock()):
                found = self.reconcile(client_order_id)
                if found:
                    found["retried"] = False
                    return found
                return {"status": "unknown", "retried": False, "reason": "already_attempted", "client_order_id": client_order_id}
            self.store.mark_order_dispatched(client_order_id, self.clock())
        self._attempted.add(client_order_id)
        try:
            raw = self._place_once(prepared)
        except CoinbaseFailure:
            raise
        except Exception as exc:
            code = classify_exception(exc)
            if code == "unknown_outcome":
                found = self.reconcile(client_order_id)
                if found:
                    found["retried"] = False
                    return found
                return {
                    "status": "unknown",
                    "retried": False,
                    "reason": "unknown_outcome",
                    "client_order_id": client_order_id,
                }
            return {"status": "rejected", "retried": False, "reason": code, "client_order_id": client_order_id}
        normalized = _normalize_create(raw, client_order_id)
        normalized["retried"] = False
        normalized["fills"] = self.fills_for(client_order_id, normalized.get("order_id"))
        confirmation = self.confirm(client_order_id, normalized.get("order_id"))
        if confirmation:
            normalized["confirmation"] = confirmation
        return normalized

    def confirm(self, client_order_id: str, order_id: str | None) -> dict | None:
        """Read the order back. A failed read reconciles and does not place again."""
        if order_id and hasattr(self.client, "get_order"):
            try:
                raw = self.client.get_order(order_id)
            except Exception as exc:
                if classify_exception(exc) == "unknown_outcome":
                    return self.reconcile(client_order_id)
                return self.reconcile(client_order_id)
            data = as_dict(raw)
            order = public_order(data.get("order") or data)
            if order:
                order["confirmed"] = True
                order["client_order_id"] = order.get("client_order_id") or client_order_id
                order["fills"] = self.fills_for(client_order_id, order.get("order_id") or order_id)
                return order
        return self.reconcile(client_order_id)

    def _place_once(self, prepared: dict):
        side = prepared["side"].upper()
        if prepared["order_type"] == "market":
            return self.client.market_order(
                client_order_id=prepared["client_order_id"],
                product_id=prepared["product_id"],
                side=side,
                quote_size=prepared.get("quote_size"),
                base_size=prepared.get("base_size"),
            )
        if prepared["order_type"] == "limit":
            return self.client.limit_order_gtc(
                client_order_id=prepared["client_order_id"],
                product_id=prepared["product_id"],
                side=side,
                base_size=prepared["base_size"],
                limit_price=prepared["limit_price"],
                post_only=bool(prepared.get("post_only")),
            )
        raise CoinbaseFailure("unsupported_order", "only market IOC and limit GTC spot orders are allowed")

    def reconcile(self, client_order_id: str) -> dict | None:
        for order in self.open_orders() + self.historical_orders():
            if order.get("client_order_id") == client_order_id:
                order["fills"] = self.fills_for(client_order_id, order.get("order_id"))
                order["reconciled"] = True
                order["retried"] = False
                return order
        return None

    def open_orders(self) -> list[dict]:
        raw = self.client.list_orders(order_status=["OPEN"], product_type="SPOT")
        return [public_order(item) for item in _rows(raw, "orders")]

    def historical_orders(self) -> list[dict]:
        raw = self.client.list_orders(product_type="SPOT")
        return [public_order(item) for item in _rows(raw, "orders")]

    def fills_for(self, client_order_id: str, order_id: str | None) -> list[dict]:
        raw = self.client.get_fills(order_ids=[order_id] if order_id else None)
        fills = [public_fill(item) for item in _rows(raw, "fills")]
        if order_id:
            return [fill for fill in fills if fill.get("order_id") in {None, order_id}]
        return fills

    def cancel_open(self) -> dict:
        orders = self.open_orders()
        ids = [order["order_id"] for order in orders if order.get("order_id")]
        if not ids:
            return {"cancelled": [], "reason": "no_open_orders"}
        self.client.cancel_orders(ids)
        return {"cancelled": ids, "reason": "cancelled"}


def _rows(raw, key: str) -> list:
    data = as_dict(raw)
    rows = data.get(key) or []
    return rows if isinstance(rows, list) else []


def _normalize_create(raw, client_order_id: str) -> dict:
    data = as_dict(raw)
    success = data.get("success")
    response = data.get("success_response") or data.get("order") or data
    response = as_dict(response) if not isinstance(response, dict) else response
    error = data.get("error_response") or {}
    error = as_dict(error) if not isinstance(error, dict) else error
    if success is False or error:
        return {
            "status": "rejected",
            "reason": error.get("error") or error.get("message") or "exchange_rejected",
            "client_order_id": client_order_id,
            "order_id": response.get("order_id"),
        }
    status = str(response.get("status") or data.get("status") or "submitted").lower()
    return {
        "status": status if status else "submitted",
        "order_id": response.get("order_id") or data.get("order_id"),
        "client_order_id": response.get("client_order_id") or client_order_id,
        "product_id": response.get("product_id"),
        "side": response.get("side"),
    }
