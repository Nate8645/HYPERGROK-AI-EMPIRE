"""Interpret GET /api/v3/brokerage/key_permissions. This module does not call the network."""

from __future__ import annotations

from hypergrok.venues.coinbase.market import as_dict


def assess_key_permissions(payload: object) -> dict:
    data = as_dict(payload)
    can_view = data.get("can_view") is True
    can_trade = data.get("can_trade") is True
    can_transfer = data.get("can_transfer") is True
    if can_transfer:
        reason = "transfer_permission"
    elif not can_view:
        reason = "view_permission_missing"
    elif not can_trade:
        reason = "trade_permission_missing"
    else:
        reason = "ok"
    return {
        "can_view": can_view,
        "can_trade": can_trade,
        "can_transfer": can_transfer,
        "arming_allowed": reason == "ok",
        "reason": reason,
    }
