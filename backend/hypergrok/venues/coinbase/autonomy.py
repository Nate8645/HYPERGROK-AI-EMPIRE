"""Autonomous mode stays locked unless every arming field is present and valid.

Nothing in this module turns the mode on. The default settings leave it disabled.
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from hypergrok.clock import ensure_utc
from hypergrok.config import Settings

KILL_SWITCH_CONDITIONS = ("manual_halt", "daily_loss", "stale_data", "feed_outage")
_PAIR = re.compile(r"^[A-Z0-9]{1,20}-[A-Z0-9]{1,20}$")


def autonomous_pairs(settings: Settings) -> list[str]:
    return [part.strip().upper() for part in settings.autonomous_allowed_pairs.split(",") if part.strip()]


def autonomous_blockers(settings: Settings, now: datetime) -> list[str]:
    blockers: list[str] = []
    if not settings.autonomous_enabled:
        blockers.append("autonomous_disabled")
    if settings.autonomous_max_loss_per_trade is None or settings.autonomous_max_loss_per_trade <= 0:
        blockers.append("missing_max_loss_per_trade")
    if settings.autonomous_max_loss_per_day is None or settings.autonomous_max_loss_per_day <= 0:
        blockers.append("missing_max_loss_per_day")
    if settings.autonomous_max_loss_total is None or settings.autonomous_max_loss_total <= 0:
        blockers.append("missing_max_loss_total")
    deployed = settings.autonomous_max_deployed_capital
    if deployed is None or deployed <= 0:
        blockers.append("missing_max_deployed_capital")
    pairs = autonomous_pairs(settings)
    if not pairs:
        blockers.append("missing_allowed_pairs")
    elif any(_PAIR.fullmatch(pair) is None for pair in pairs):
        blockers.append("invalid_allowed_pairs")
    if settings.autonomous_expires_at is None:
        blockers.append("missing_expiry")
    elif ensure_utc(settings.autonomous_expires_at) <= ensure_utc(now):
        blockers.append("expired")
    slip = settings.autonomous_max_slippage_bps
    if slip is None or slip < 0 or slip > Decimal("10000"):
        blockers.append("missing_or_invalid_max_slippage_bps")
    text = settings.autonomous_kill_switch_conditions.strip().lower()
    if not text or any(condition not in text for condition in KILL_SWITCH_CONDITIONS):
        blockers.append("missing_or_invalid_kill_switch_conditions")
    return blockers


def autonomous_armed(settings: Settings, now: datetime) -> bool:
    return not autonomous_blockers(settings, now)
