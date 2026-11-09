"""Long-only spot backtests. No orders are sent.

Sharpe is omitted unless there are at least 30 closed trades. A large
in-sample versus out-of-sample gap, or fewer than 20 trades, is an overfitting warning.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable, Sequence

from hypergrok.indicators import bollinger, donchian, ema, rsi

Signal = Callable[[Sequence[dict], int], int]


def ema_cross(candles: Sequence[dict], index: int) -> int:
    values = [_d(row["close"]) for row in candles[: index + 1]]
    fast = ema(values, 8)
    slow = ema(values, 21)
    if fast[-1] is None or slow[-1] is None:
        return 0
    return 1 if fast[-1] > slow[-1] else 0


def mean_reversion(candles: Sequence[dict], index: int) -> int:
    values = [_d(row["close"]) for row in candles[: index + 1]]
    if len(values) < 20:
        return 0
    score = rsi(values, 14)
    bands = bollinger(values, 20)
    if score[-1] is None or bands["lower"] is None:
        return 0
    if score[-1] < Decimal("30") and values[-1] <= bands["lower"]:
        return 1
    if score[-1] > Decimal("70"):
        return 0
    return 1 if score[-1] < Decimal("45") else 0


def breakout(candles: Sequence[dict], index: int) -> int:
    if index < 20:
        return 0
    channel = donchian(candles[index - 20 : index], 20)
    if channel["upper"] is None:
        return 0
    return 1 if _d(candles[index]["close"]) > channel["upper"] else 0


def momentum(candles: Sequence[dict], index: int) -> int:
    if index < 10:
        return 0
    now = _d(candles[index]["close"])
    then = _d(candles[index - 10]["close"])
    return 1 if now > then else 0


def volatility_filter(candles: Sequence[dict], index: int, max_atr_fraction: Decimal = Decimal("0.08")) -> bool:
    if index < 14:
        return False
    from hypergrok.indicators import atr

    series = atr(candles[: index + 1], 14)
    if series[-1] is None:
        return False
    close = _d(candles[index]["close"])
    if close <= 0:
        return False
    return series[-1] / close <= max_atr_fraction


STRATEGIES: dict[str, Signal] = {
    "ema_cross": ema_cross,
    "mean_reversion": mean_reversion,
    "breakout": breakout,
    "momentum": momentum,
}


def run_backtest(
    candles: Sequence[dict],
    strategy: str,
    *,
    fee_bps: Decimal = Decimal("60"),
    slippage_bps: Decimal = Decimal("5"),
    use_vol_filter: bool = True,
) -> dict:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy {strategy}")
    signal = STRATEGIES[strategy]
    equity = Decimal("1")
    peak = equity
    max_dd = Decimal("0")
    position = False
    entry = Decimal("0")
    trades: list[dict] = []
    cost = (fee_bps + slippage_bps) / Decimal("10000")
    for i in range(len(candles)):
        if use_vol_filter and not volatility_filter(candles, i):
            want = 0
        else:
            want = signal(candles, i)
        price = _d(candles[i]["close"])
        if want == 1 and not position:
            position = True
            entry = price * (Decimal("1") + cost)
        elif want == 0 and position:
            exit_price = price * (Decimal("1") - cost)
            ret = (exit_price - entry) / entry
            equity *= Decimal("1") + ret
            trades.append({"return": ret, "entry": entry, "exit": exit_price})
            position = False
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak if peak else Decimal("0"))
    if position and candles:
        exit_price = _d(candles[-1]["close"]) * (Decimal("1") - cost)
        ret = (exit_price - entry) / entry
        equity *= Decimal("1") + ret
        trades.append({"return": ret, "entry": entry, "exit": exit_price, "closed": "end_of_sample"})
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak else Decimal("0"))
    metrics = score_trades(trades, equity=equity, max_drawdown=max_dd)
    metrics["strategy"] = strategy
    metrics["bars"] = len(candles)
    return metrics


def score_trades(trades: Sequence[dict], *, equity: Decimal = Decimal("1"), max_drawdown: Decimal = Decimal("0")) -> dict:
    rets = [item["return"] if isinstance(item, dict) else item for item in trades]
    wins = [item for item in rets if item > 0]
    losses = [item for item in rets if item < 0]
    count = len(rets)
    win_rate = (Decimal(len(wins)) / Decimal(count)) if count else Decimal("0")
    gross_win = sum(wins, Decimal("0"))
    gross_loss = abs(sum(losses, Decimal("0")))
    profit_factor = (gross_win / gross_loss) if gross_loss else None
    expectancy = (sum(rets, Decimal("0")) / Decimal(count)) if count else Decimal("0")
    sharpe = None
    if count >= 30:
        mean = expectancy
        var = sum((item - mean) ** 2 for item in rets) / Decimal(count)
        sigma = var.sqrt()
        sharpe = (mean / sigma) if sigma else None
    return {
        "trades": count,
        "expectancy": expectancy,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "ending_equity": equity,
        "sharpe_sample_sufficient": count >= 30,
    }


def split_ranges(count: int) -> dict[str, tuple[int, int]]:
    train = int(count * Decimal("0.6"))
    valid = int(count * Decimal("0.2"))
    return {"train": (0, train), "validation": (train, train + valid), "test": (train + valid, count)}


def walk_forward(candles: Sequence[dict], strategy: str, folds: int = 3, **kwargs) -> dict:
    if folds < 2 or len(candles) < folds * 10:
        return {"folds": [], "warning": "too_few_bars"}
    size = len(candles) // folds
    results = []
    for i in range(folds - 1):
        train = candles[: (i + 1) * size]
        test = candles[(i + 1) * size : (i + 2) * size]
        in_sample = run_backtest(train, strategy, **kwargs)
        out_sample = run_backtest(test, strategy, **kwargs)
        results.append({"in_sample": in_sample, "out_of_sample": out_sample, "overfit": overfitting_warning(in_sample, out_sample)})
    return {"folds": results, "warning": None}


def overfitting_warning(in_sample: dict, out_of_sample: dict) -> str | None:
    if in_sample["trades"] < 20 or out_of_sample["trades"] < 5:
        return "too_few_trades"
    gap = in_sample["expectancy"] - out_of_sample["expectancy"]
    if gap > Decimal("0.01") and in_sample["expectancy"] > 0 and out_of_sample["expectancy"] < in_sample["expectancy"] / 2:
        return "in_sample_gap"
    return None


def evaluate_splits(candles: Sequence[dict], strategy: str, **kwargs) -> dict:
    ranges = split_ranges(len(candles))
    parts = {}
    for name, (start, end) in ranges.items():
        parts[name] = run_backtest(candles[start:end], strategy, **kwargs)
    warning = overfitting_warning(parts["train"], parts["test"])
    forward = walk_forward(candles, strategy, **kwargs)
    return {"splits": parts, "overfit_warning": warning, "walk_forward": forward, "strategy": strategy}


def _d(value: object) -> Decimal:
    return Decimal(str(value))
