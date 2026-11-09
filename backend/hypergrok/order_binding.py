"""Stable identity for one order. A pass or an approval for a different payload does not match."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal


def _norm(value: object) -> str:
    if value in (None, ""):
        return ""
    return format(Decimal(str(value)), "f")


def fingerprint(data: dict) -> str:
    notional = data.get("quote_size")
    if notional in (None, ""):
        notional = data.get("notional")
    canonical = {
        "client_order_id": str(data.get("client_order_id") or "").strip(),
        "product_id": str(data.get("product_id") or data.get("symbol") or "").upper(),
        "side": str(data.get("side") or "").lower(),
        "order_type": str(data.get("order_type") or "market"),
        "notional": _norm(notional),
        "base_size": _norm(data.get("base_size")),
        "limit_price": _norm(data.get("limit_price")),
        "stop_price": _norm(data.get("stop_price")),
        "entry_price": _norm(data.get("entry_price")),
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
