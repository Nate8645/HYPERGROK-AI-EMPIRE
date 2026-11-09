"""Rule-based indicators. Inputs are public candle rows, never invented prices.

A candle is a mapping with high, low, close, and volume. Open is optional.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence


def _d(value: object) -> Decimal:
    return Decimal(str(value))


def closes(candles: Sequence[dict]) -> list[Decimal]:
    return [_d(row["close"]) for row in candles]


def ema(values: Sequence[Decimal], period: int) -> list[Decimal | None]:
    if period < 1:
        raise ValueError("period must be positive")
    out: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period], Decimal("0")) / Decimal(period)
    out[period - 1] = seed
    k = Decimal(2) / Decimal(period + 1)
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (Decimal(1) - k)
        out[i] = prev
    return out


def rsi(values: Sequence[Decimal], period: int = 14) -> list[Decimal | None]:
    if period < 1:
        raise ValueError("period must be positive")
    out: list[Decimal | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        gains.append(change if change > 0 else Decimal("0"))
        losses.append(-change if change < 0 else Decimal("0"))
    avg_gain = sum(gains, Decimal("0")) / Decimal(period)
    avg_loss = sum(losses, Decimal("0")) / Decimal(period)
    out[period] = _rsi_from_averages(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        gain = change if change > 0 else Decimal("0")
        loss = -change if change < 0 else Decimal("0")
        avg_gain = (avg_gain * Decimal(period - 1) + gain) / Decimal(period)
        avg_loss = (avg_loss * Decimal(period - 1) + loss) / Decimal(period)
        out[i] = _rsi_from_averages(avg_gain, avg_loss)
    return out


def _rsi_from_averages(avg_gain: Decimal, avg_loss: Decimal) -> Decimal:
    if avg_loss == 0:
        return Decimal("100")
    rs = avg_gain / avg_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


def macd(
    values: Sequence[Decimal],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, list[Decimal | None]]:
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    line: list[Decimal | None] = []
    for i, _ in enumerate(values):
        if fast_ema[i] is None or slow_ema[i] is None:
            line.append(None)
        else:
            line.append(fast_ema[i] - slow_ema[i])
    usable = [item for item in line if item is not None]
    signal_raw = ema(usable, signal)
    signal_line: list[Decimal | None] = [None] * len(values)
    hist: list[Decimal | None] = [None] * len(values)
    offset = len(values) - len(usable)
    for i, item in enumerate(signal_raw):
        signal_line[offset + i] = item
        if item is not None and line[offset + i] is not None:
            hist[offset + i] = line[offset + i] - item
    return {"macd": line, "signal": signal_line, "histogram": hist}


def atr(candles: Sequence[dict], period: int = 14) -> list[Decimal | None]:
    if not candles:
        return []
    true_ranges: list[Decimal] = []
    prev_close = _d(candles[0]["close"])
    for index, row in enumerate(candles):
        high = _d(row["high"])
        low = _d(row["low"])
        if index == 0:
            true_ranges.append(high - low)
        else:
            true_ranges.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
        prev_close = _d(row["close"])
    averaged = rsi_smooth(true_ranges, period)
    return averaged


def rsi_smooth(values: Sequence[Decimal], period: int) -> list[Decimal | None]:
    """Wilder smoothing used by ATR. The first value is a simple average."""

    out: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period], Decimal("0")) / Decimal(period)
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = (prev * Decimal(period - 1) + values[i]) / Decimal(period)
        out[i] = prev
    return out


def vwap(candles: Sequence[dict]) -> Decimal | None:
    total_pv = Decimal("0")
    total_v = Decimal("0")
    for row in candles:
        volume = _d(row.get("volume") or 0)
        if volume <= 0:
            continue
        typical = (_d(row["high"]) + _d(row["low"]) + _d(row["close"])) / Decimal(3)
        total_pv += typical * volume
        total_v += volume
    if total_v == 0:
        return None
    return total_pv / total_v


def bollinger(values: Sequence[Decimal], period: int = 20, width: Decimal = Decimal("2")) -> dict[str, Decimal | None]:
    if len(values) < period:
        return {"middle": None, "upper": None, "lower": None}
    window = values[-period:]
    middle = sum(window, Decimal("0")) / Decimal(period)
    var = sum((item - middle) ** 2 for item in window) / Decimal(period)
    sigma = var.sqrt()
    return {"middle": middle, "upper": middle + width * sigma, "lower": middle - width * sigma}


def donchian(candles: Sequence[dict], period: int = 20) -> dict[str, Decimal | None]:
    if len(candles) < period:
        return {"upper": None, "lower": None}
    window = candles[-period:]
    return {"upper": max(_d(row["high"]) for row in window), "lower": min(_d(row["low"]) for row in window)}


def support_resistance(candles: Sequence[dict], window: int = 3) -> dict[str, list[Decimal]]:
    supports: list[Decimal] = []
    resistances: list[Decimal] = []
    if window < 1 or len(candles) < window * 2 + 1:
        return {"support": supports, "resistance": resistances}
    for i in range(window, len(candles) - window):
        low = _d(candles[i]["low"])
        high = _d(candles[i]["high"])
        if all(low <= _d(candles[j]["low"]) for j in range(i - window, i + window + 1)):
            supports.append(low)
        if all(high >= _d(candles[j]["high"]) for j in range(i - window, i + window + 1)):
            resistances.append(high)
    return {"support": supports[-3:], "resistance": resistances[-3:]}


def trend_from_ema(values: Sequence[Decimal], fast: int = 12, slow: int = 26) -> str:
    fast_line = ema(values, fast)
    slow_line = ema(values, slow)
    if not fast_line or fast_line[-1] is None or slow_line[-1] is None:
        return "unknown"
    if fast_line[-1] > slow_line[-1]:
        return "up"
    if fast_line[-1] < slow_line[-1]:
        return "down"
    return "flat"


def multi_timeframe_trend(higher: Sequence[Decimal], lower: Sequence[Decimal]) -> str:
    high_trend = trend_from_ema(higher)
    low_trend = trend_from_ema(lower)
    if high_trend == "unknown" or low_trend == "unknown":
        return "unknown"
    if high_trend == low_trend:
        return high_trend
    return "conflict"


def book_metrics(bid: Decimal, ask: Decimal, bid_size: Decimal, ask_size: Decimal, depth_levels: Sequence[dict] | None = None) -> dict:
    mid = (bid + ask) / Decimal(2)
    spread_bps = (ask - bid) / mid * Decimal("10000") if mid else None
    total = bid_size + ask_size
    imbalance = (bid_size - ask_size) / total if total else None
    depth = Decimal("0")
    for level in depth_levels or []:
        depth += _d(level.get("size") or 0)
    if depth == 0:
        depth = bid_size + ask_size
    return {
        "spread_bps": spread_bps,
        "imbalance": imbalance,
        "depth": depth,
        "liquidity": "thin" if depth < Decimal("1") or (spread_bps is not None and spread_bps > Decimal("50")) else "tradable",
    }


def latest_indicators(candles: Sequence[dict]) -> dict:
    values = closes(candles)
    macd_pack = macd(values) if len(values) >= 26 else {"macd": [], "signal": [], "histogram": []}
    bands = bollinger(values)
    channel = donchian(candles)
    levels = support_resistance(candles)
    return {
        "ema_fast": _last(ema(values, 12)),
        "ema_slow": _last(ema(values, 26)),
        "rsi": _last(rsi(values)),
        "macd": _last(macd_pack["macd"]),
        "macd_signal": _last(macd_pack["signal"]),
        "atr": _last(atr(candles)),
        "vwap": vwap(candles),
        "bollinger": bands,
        "donchian": channel,
        "support": levels["support"],
        "resistance": levels["resistance"],
        "trend": trend_from_ema(values),
    }


def _last(values: Sequence[Decimal | None]) -> Decimal | None:
    for item in reversed(values):
        if item is not None:
            return item
    return None
