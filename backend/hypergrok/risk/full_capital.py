"""Simulation of a fully funded spot order. It does not place an order and does not change the 1% rule.

Size keeps cash aside for the entry fee and the exit fee, then rounds down to the quote increment.
No leverage and no borrowing: size plus both fees stays within the balance, and the position count is one.
"""

from __future__ import annotations

from decimal import Decimal
from statistics import median

from hypergrok.indicators import atr
from hypergrok.money import floor_to_increment

MATERIAL_OVERSHOOT_SHARE = Decimal("0.05")


def full_capital_size(
    balance: Decimal,
    entry_fee_rate: Decimal,
    exit_fee_rate: Decimal,
    quote_increment: Decimal = Decimal("0.01"),
) -> dict:
    if balance <= 0:
        raise ValueError("balance must be positive")
    if entry_fee_rate < 0 or exit_fee_rate < 0:
        raise ValueError("fee rates cannot be negative")
    reserve_rate = entry_fee_rate + exit_fee_rate
    if reserve_rate >= 1:
        raise ValueError("fee rates consume the whole balance")
    raw = balance / (Decimal(1) + reserve_rate)
    size = floor_to_increment(raw, quote_increment)
    entry_fee = size * entry_fee_rate
    exit_fee = size * exit_fee_rate
    fee_reserve = entry_fee + exit_fee
    return {
        "size": size,
        "quote_increment": format(quote_increment, "f"),
        "entry_fee_rate": format(entry_fee_rate, "f"),
        "exit_fee_rate": format(exit_fee_rate, "f"),
        "entry_fee": entry_fee,
        "exit_fee": exit_fee,
        "fee_reserve": fee_reserve,
        "remainder": balance - size - fee_reserve,
        "borrowed": Decimal("0"),
        "leverage": Decimal("1"),
        "max_open_positions": 1,
    }


def assess_full_capital(
    *,
    balance: Decimal,
    entry_fee_rate: Decimal,
    exit_fee_rate: Decimal,
    spread_rate: Decimal,
    slippage_rate: Decimal,
    minute_candles: list[dict],
    daily_candles: list[dict],
    max_loss_fraction: Decimal = Decimal("0.01"),
    quote_increment: Decimal = Decimal("0.01"),
    capital_fraction: Decimal = Decimal("1"),
) -> dict:
    """Ask whether a stop can keep the loss inside the existing 1% rule on this sample.

    The required stop is the widest price distance that still leaves the loss,
    after both fees, the spread, and slippage on both sides, at or under
    max_loss_fraction of the balance. It is rejected when that distance is
    inside the sampled 1-minute noise or ATR, or when more than 5% of the
    sampled gaps would push the loss through the 1% budget. 5% is this desk's
    definition of a material share, not a market constant.
    """
    if not (Decimal("0") < capital_fraction <= Decimal("1")):
        raise ValueError("capital_fraction must be in (0, 1]")
    if not minute_candles or not daily_candles:
        return _unavailable("missing_history")
    sized = full_capital_size(balance * capital_fraction, entry_fee_rate, exit_fee_rate, quote_increment)
    size = sized["size"]
    fixed = sized["entry_fee"] + sized["exit_fee"] + size * spread_rate + size * slippage_rate * 2
    budget = balance * max_loss_fraction
    required = (budget - fixed) / size if size > 0 else Decimal("-1")
    noise = _median(_bar_ranges(minute_candles))
    atr_fraction = _median_atr(minute_candles)
    minute_bar = _adverse(minute_candles, gap=False)
    minute_gap = _adverse(minute_candles, gap=True)
    daily_gap = _adverse(daily_candles, gap=True)
    shares = {
        "minute_open_to_low": _breach_share(minute_bar, size, fixed, budget),
        "minute_gap_or_stale": _breach_share(minute_gap, size, fixed, budget),
        "daily_gap": _breach_share(daily_gap, size, fixed, budget),
    }
    reasons: list[str] = []
    if required <= 0 or required < noise or required < atr_fraction:
        reasons.append("stop_tighter_than_noise")
    if any(share is not None and share >= MATERIAL_OVERSHOOT_SHARE for share in shares.values()):
        reasons.append("overshoot_breaches_risk")
    worst = max([*minute_gap, *daily_gap, Decimal("0")])
    worst = min(worst, Decimal("1"))
    typical = _typical_excess(daily_gap or minute_gap, required)
    stop_for_loss = max(required, Decimal("0"))
    return {
        "status": "REJECT" if reasons else "PASS",
        "reasons": reasons,
        "limits_replaced": False,
        "max_loss_fraction": format(max_loss_fraction, "f"),
        "material_overshoot_share": format(MATERIAL_OVERSHOOT_SHARE, "f"),
        "balance": format(balance, "f"),
        "capital_fraction": format(capital_fraction, "f"),
        "size": format(size, "f"),
        "fee_reserve": format(sized["fee_reserve"], "f"),
        "entry_fee": format(sized["entry_fee"], "f"),
        "exit_fee": format(sized["exit_fee"], "f"),
        "remainder": format(sized["remainder"], "f"),
        "borrowed": "0",
        "leverage": "1",
        "max_open_positions": 1,
        "required_stop_fraction": format(required, "f"),
        "noise_fraction": format(noise, "f"),
        "atr_fraction": format(atr_fraction, "f"),
        "overshoot_frequency": {key: None if value is None else format(value, "f") for key, value in shares.items()},
        "loss_at_stop": format(_loss(size, stop_for_loss, fixed), "f"),
        "loss_at_typical_overshoot": format(_loss(size, stop_for_loss + typical, fixed), "f"),
        "typical_overshoot_fraction": format(typical, "f"),
        "loss_at_worst_historical_move": format(_loss(size, worst, fixed), "f"),
        "worst_adverse_fraction": format(worst, "f"),
        "total_loss": format(size + sized["entry_fee"], "f"),
        "pass_recorded": False,
        "engine": "risk_engine",
    }


def _unavailable(reason: str) -> dict:
    return {
        "status": "REJECT",
        "reasons": [reason],
        "limits_replaced": False,
        "required_stop_fraction": "Keine Daten",
        "overshoot_frequency": "Keine Daten",
        "loss_at_stop": "Keine Daten",
        "loss_at_typical_overshoot": "Keine Daten",
        "loss_at_worst_historical_move": "Keine Daten",
        "total_loss": "Keine Daten",
        "pass_recorded": False,
        "engine": "risk_engine",
    }


def _loss(size: Decimal, fraction: Decimal, fixed: Decimal) -> Decimal:
    return size * fraction + fixed


def _breach_share(moves: list[Decimal], size: Decimal, fixed: Decimal, budget: Decimal) -> Decimal | None:
    if not moves:
        return None
    breaches = sum(1 for adverse in moves if size * adverse + fixed > budget)
    return Decimal(breaches) / Decimal(len(moves))


def _typical_excess(moves: list[Decimal], required: Decimal) -> Decimal:
    excess = [move - required for move in moves if move > required]
    if not excess:
        return Decimal("0")
    return _median(excess)


def _bar_ranges(candles: list[dict]) -> list[Decimal]:
    ranges = []
    for row in candles:
        open_ = Decimal(str(row["open"]))
        if open_ <= 0:
            continue
        ranges.append((Decimal(str(row["high"])) - Decimal(str(row["low"]))) / open_)
    return ranges


def _median_atr(candles: list[dict]) -> Decimal:
    prepared = [
        {"high": Decimal(str(row["high"])), "low": Decimal(str(row["low"])), "close": Decimal(str(row["close"]))}
        for row in candles
    ]
    values = []
    for row, value in zip(prepared, atr(prepared, 14)):
        if value is None or row["close"] <= 0:
            continue
        values.append(value / row["close"])
    if not values:
        return Decimal("1")
    return _median(values)


def _adverse(candles: list[dict], *, gap: bool) -> list[Decimal]:
    moves: list[Decimal] = []
    previous_close: Decimal | None = None
    for row in candles:
        low = Decimal(str(row["low"]))
        open_ = Decimal(str(row["open"]))
        close = Decimal(str(row["close"]))
        if gap and previous_close is not None and previous_close > 0:
            moves.append(max(Decimal("0"), (previous_close - low) / previous_close))
        elif not gap and open_ > 0:
            moves.append(max(Decimal("0"), (open_ - low) / open_))
        previous_close = close
    return moves


def _median(values: list[Decimal]) -> Decimal:
    if not values:
        raise ValueError("empty sample")
    return Decimal(str(median(values)))
