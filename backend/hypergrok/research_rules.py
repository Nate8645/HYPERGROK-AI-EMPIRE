"""Rule-based research checks. They do not call a language model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from hypergrok.clock import ensure_utc
from hypergrok.indicators import atr, trend_from_ema


def detect_regime(candles: list[dict]) -> str:
    if len(candles) < 30:
        return "unknown"
    closes = [Decimal(str(row["close"])) for row in candles]
    trend = trend_from_ema(closes)
    series = atr(candles, 14)
    last = series[-1]
    close = closes[-1]
    if last is None or close <= 0:
        return "unknown"
    if last / close > Decimal("0.04"):
        return "high_volatility"
    if trend in {"up", "down"}:
        return "trend"
    return "range"


def check_data_quality(candles: list[dict], *, now: datetime, max_age_seconds: float, source: str) -> dict:
    problems: list[str] = []
    if not candles:
        problems.append("no_candles")
        return {"ok": False, "problems": problems, "source": source, "checked_at": ensure_utc(now).isoformat()}
    if not source:
        problems.append("missing_source")
    previous = None
    for row in candles:
        for field in ("high", "low", "close"):
            if Decimal(str(row[field])) <= 0:
                problems.append("non_positive_price")
                break
        if Decimal(str(row["high"])) < Decimal(str(row["low"])):
            problems.append("high_below_low")
        stamp = row.get("time") or row.get("start")
        if stamp is not None and previous is not None and str(stamp) < str(previous):
            problems.append("timestamps_out_of_order")
        previous = stamp
    newest = candles[-1].get("fetched_at") or candles[-1].get("time")
    if newest:
        try:
            observed = ensure_utc(datetime.fromisoformat(str(newest).replace("Z", "+00:00")))
            age = (ensure_utc(now) - observed).total_seconds()
            if age > max_age_seconds:
                problems.append("stale_market_data")
        except ValueError:
            problems.append("unreadable_timestamp")
    else:
        problems.append("missing_timestamp")
    return {
        "ok": not problems,
        "problems": sorted(set(problems)),
        "source": source,
        "checked_at": ensure_utc(now).isoformat(),
    }


def conflicting_signals(*, market_bias: str, research_stance: str, strategy_signal: str) -> list[str]:
    conflicts = []
    if market_bias == "long" and research_stance == "support_short":
        conflicts.append("market_long_research_short")
    if market_bias == "short" and research_stance == "support_long":
        conflicts.append("market_short_research_long")
    if strategy_signal == "long" and market_bias == "short":
        conflicts.append("strategy_long_market_short")
    if strategy_signal == "flat" and market_bias == "long" and research_stance == "support_short":
        conflicts.append("flat_strategy_against_split_desk")
    return conflicts
