"""Capital-utilization math. Callers pass a balance and a book. This module does not read the network."""

from __future__ import annotations

from decimal import Decimal

from hypergrok.money import floor_to_increment

FRACTIONS = (Decimal("0.10"), Decimal("0.25"), Decimal("0.50"), Decimal("0.75"), Decimal("1"))


def funded_quote_currency(accounts: list[dict]) -> str | None:
    available: dict[str, Decimal] = {}
    for row in accounts:
        currency = str(row.get("currency") or "").upper()
        if not currency:
            continue
        available[currency] = available.get(currency, Decimal("0")) + Decimal(str(row.get("available") or "0"))
    usdc = available.get("USDC", Decimal("0"))
    usd = available.get("USD", Decimal("0"))
    if usdc > 0 and usd <= 0:
        return "USDC"
    if usd > 0 and usdc <= 0:
        return "USD"
    if usdc > 0 and usd > 0:
        return "USDC"
    return None


def utilization_variants(
    *,
    tradable: Decimal,
    quote_currency: str,
    taker_fee_rate: Decimal,
    maker_fee_rate: Decimal,
    quote_increment: Decimal,
    quote_min_size: Decimal,
    stop_fraction: Decimal,
    equity: Decimal,
    max_risk_fraction: Decimal,
    bids: list[dict] | None,
    asks: list[dict] | None,
    side: str,
    post_only: bool = False,
    backtest: str = "Keine Daten",
    fee_floor_rate: Decimal = Decimal("0.001"),
    slippage_floor_rate: Decimal = Decimal("0.001"),
) -> dict:
    fee_rate = maker_fee_rate if post_only else taker_fee_rate
    if fee_rate <= 0:
        fee_rate = fee_floor_rate
    risk_fee_rate = max(fee_rate * 2, fee_floor_rate)
    levels = asks if side == "buy" else bids
    variants = []
    for fraction in FRACTIONS:
        budget = tradable * fraction
        notional = floor_to_increment(budget / (Decimal(1) + fee_rate), quote_increment)
        fee = notional * fee_rate
        remaining = tradable - notional - fee
        min_ok = notional >= quote_min_size and notional > 0
        slip = _slippage(levels or [], notional, side)
        risk_slip = slippage_floor_rate if slip is None else max(slip * 2, slippage_floor_rate)
        price_loss = notional * stop_fraction
        fee_loss = notional * risk_fee_rate
        slip_loss = notional * risk_slip
        planned = price_loss + fee_loss + slip_loss
        limit = equity * max_risk_fraction
        risk_allowed = bool(min_ok and remaining >= 0 and slip is not None and planned <= limit)
        variants.append(
            {
                "fraction": format(fraction, "f"),
                "notional": format(notional, "f"),
                "quote_currency": quote_currency,
                "fee": format(fee, "f"),
                "fee_rate": format(fee_rate, "f"),
                "slippage_rate": None if slip is None else format(slip, "f"),
                "slippage": "Keine Daten" if slip is None else format(slip, "f"),
                "remaining_balance": format(remaining, "f"),
                "min_size_ok": min_ok,
                "stop_loss": format(price_loss, "f"),
                "worst_case_loss": format(notional + fee + (notional * fee_rate), "f"),
                "planned_loss": format(planned, "f"),
                "risk_limit": format(limit, "f"),
                "risk_allowed": risk_allowed,
                "backtest": backtest,
            }
        )
    return {
        "quote_currency": quote_currency,
        "tradable": format(tradable, "f"),
        "backtest": backtest,
        "variants": variants,
    }


def backtest_for_product(summary: dict | None, product_id: str) -> str:
    products = (summary or {}).get("products") or {}
    body = products.get(product_id)
    if not body:
        return "Keine Daten"
    strategies = body.get("strategies") or {}
    if not strategies:
        return "Keine Daten"
    parts = []
    for name, strategy in strategies.items():
        test = (strategy.get("splits") or {}).get("test") or {}
        expectancy = test.get("expectancy")
        warning = strategy.get("overfit_warning")
        if expectancy is None:
            continue
        parts.append(f"{name} test expectancy {expectancy} ({warning or 'no warning'})")
    return "; ".join(parts) if parts else "Keine Daten"


def _slippage(levels: list[dict], notional: Decimal, side: str) -> Decimal | None:
    if notional <= 0 or not levels:
        return None
    best = Decimal(str(levels[0]["price"]))
    if best <= 0:
        return None
    remaining = notional
    base = Decimal("0")
    spent = Decimal("0")
    for level in levels:
        price = Decimal(str(level["price"]))
        size = Decimal(str(level["size"]))
        if price <= 0 or size <= 0:
            continue
        room = price * size
        take = min(room, remaining)
        base += take / price
        spent += take
        remaining -= take
        if remaining <= 0:
            break
    if remaining > 0 or base <= 0 or spent <= 0:
        return None
    vwap = spent / base
    if side == "buy":
        return (vwap - best) / best
    return (best - vwap) / best
