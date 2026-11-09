"""Screen saved public candles. A weak or tiny sample is NO TRADE.

This does not send orders and does not replace the 1% or 3% limits.
"""

from __future__ import annotations

from decimal import Decimal

from hypergrok.backtest import STRATEGIES, compare_sizing, walk_forward
from hypergrok.indicators import book_metrics, latest_indicators
from hypergrok.research_rules import detect_regime

FRACTIONS = (Decimal("0.10"), Decimal("0.25"), Decimal("0.50"), Decimal("1"))


def _shown(value: Decimal | None) -> str:
    if value is None:
        return "Keine Daten"
    return format(value, "f")


def screen_product(
    candles: list[dict],
    *,
    book: dict | None = None,
    capital: Decimal = Decimal("10.896768"),
    fee_rate: Decimal = Decimal("0.001"),
    slippage_rate: Decimal = Decimal("0.001"),
    spread_rate: Decimal = Decimal("0"),
) -> dict:
    if len(candles) < 40:
        return {"outcome": "NO TRADE", "reason": "sample_too_small", "strategies": []}
    start = int(len(candles) * Decimal("0.8"))
    sample = candles[start:]
    indicators = latest_indicators(candles)
    regime = detect_regime(candles)
    liquidity = None
    if book and book.get("bids") and book.get("asks"):
        liquidity = book_metrics(
            Decimal(str(book["bids"][0]["price"])),
            Decimal(str(book["asks"][0]["price"])),
            Decimal(str(book["bids"][0]["size"])),
            Decimal(str(book["asks"][0]["size"])),
            book.get("bids"),
        )
    rows = []
    admissible = False
    overshoot = _overshoot_share(candles, Decimal("0.05"))
    for name in STRATEGIES:
        forward = walk_forward(
            candles,
            name,
            fee_bps=fee_rate * Decimal("10000"),
            slippage_bps=slippage_rate * Decimal("10000"),
            use_vol_filter=len(candles) < 2000,
        )
        forward_oos = [fold["out_of_sample"]["trades"] for fold in forward.get("folds") or []]
        compared = compare_sizing(
            sample,
            name,
            capital=capital,
            fee_rate=fee_rate,
            slippage_rate=slippage_rate,
            spread_rate=spread_rate,
            quote_min_size=Decimal("1"),
            stop_fraction=Decimal("0.05"),
            max_risk_fraction=Decimal("0.01"),
            use_vol_filter=len(candles) < 2000,
        )
        for variant in compared["variants"]:
            if variant["variant"] == "risk_1pct":
                continue
            fraction = Decimal(variant["fraction"])
            trades = int(variant["trades"])
            expectancy = Decimal(str(variant["expectancy"]))
            rejected = int(variant["risk_rejected"])
            # A 5% stop on more than 20% of capital breaks the 1% loss budget.
            # More than 60% of capital can break the 3% daily loss budget on that stop.
            fits_one_percent = fraction <= Decimal("0.20") and rejected == 0
            fits_three_percent = fraction <= Decimal("0.60") and rejected == 0
            robust = trades >= 20 and expectancy > 0 and fits_one_percent and fits_three_percent
            if robust and overshoot >= Decimal("0.05"):
                robust = False
            if robust:
                admissible = True
            rows.append(
                {
                    "strategy": name,
                    "fraction": variant["variant"],
                    "trades": trades,
                    "expectancy": format(expectancy, "f"),
                    "risk_rejected": rejected,
                    "fits_1_percent": fits_one_percent,
                    "fits_3_percent": fits_three_percent,
                    "robust": robust,
                    "walk_forward_oos_trades": forward_oos,
                    "walk_forward_warning": forward.get("warning"),
                    "intraday_stop_overshoot_share": format(overshoot, "f"),
                }
            )
    return {
        "outcome": "TRADE" if admissible else "NO TRADE",
        "reason": "no_robust_strategy" if not admissible else "admissible",
        "regime": regime,
        "indicators": {
            "rsi": _shown(indicators.get("rsi")),
            "macd": _shown(indicators.get("macd")),
            "ema_fast": _shown(indicators.get("ema_fast")),
            "atr": _shown(indicators.get("atr")),
            "vwap": _shown(indicators.get("vwap")),
            "trend": indicators.get("trend"),
        },
        "liquidity": None
        if liquidity is None
        else {
            "spread_bps": None if liquidity["spread_bps"] is None else format(liquidity["spread_bps"], "f"),
            "imbalance": None if liquidity["imbalance"] is None else format(liquidity["imbalance"], "f"),
            "liquidity": liquidity["liquidity"],
        },
        "strategies": rows,
        "limits": {"max_loss_per_trade": "0.01", "max_loss_per_day": "0.03"},
        "gap_stress_share": format(_overshoot_share(candles, Decimal("0.006")), "f"),
    }


def _overshoot_share(candles: list[dict], stop_fraction: Decimal) -> Decimal:
    """Share of bars whose low gaps through the stop versus the previous close."""
    breaches = 0
    count = 0
    previous: Decimal | None = None
    for row in candles:
        close = Decimal(str(row["close"]))
        low = Decimal(str(row["low"]))
        if previous is not None and previous > 0:
            count += 1
            if (previous - low) / previous > stop_fraction:
                breaches += 1
        previous = close
    if count == 0:
        return Decimal("0")
    return Decimal(breaches) / Decimal(count)
