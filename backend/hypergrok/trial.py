"""Mock end-to-end trial.

Every result is labelled SIMULATED. This module does not submit an order.
A Coinbase preview runs only when a CDP key is already configured; otherwise
the preview field is the literal string ``NOT RUN``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from hypergrok.clock import ensure_utc
from hypergrok.config import Settings
from hypergrok.domain import AccountUpdate, DeskIdea, MarketSnapshot, OrderIntent, ResearchInput
from hypergrok.execution.dry_run import DryRunAdapter
from hypergrok.main import create_app
from hypergrok.money import floor_money, format_decimal
from hypergrok.venues.coinbase.credentials import load_credentials

FIXTURE_AVAILABLE_USDC = Decimal("10.896768")
STOP = Decimal("0.05")
FEE_BPS = Decimal("20")
SLIPPAGE_BPS = Decimal("10")
QUOTE_INCREMENT = Decimal("0.01")
FRACTIONS = (Decimal("1"), Decimal("0.50"), Decimal("0.25"), Decimal("0.10"))
AGENT_ORDER = (
    "desk_lead",
    "market_analyst",
    "research_analyst",
    "strategist",
    "risk_manager",
    "execution_trader",
    "trade_reviewer",
)


def run_simulated_trial(
    *,
    books: dict,
    research_trends: dict[str, str],
    as_of: datetime,
    balance: Decimal = FIXTURE_AVAILABLE_USDC,
    balance_source: str,
    screen_outcome: str,
) -> dict:
    """Run the seven agents, the size step-down, a mock buy, a mock sell, and the kill switch."""

    moment = ensure_utc(as_of)
    settings = Settings(
        _env_file=None,
        database_url="sqlite://",
        account_currency="USDC",
        starting_capital=balance,
        max_market_data_age_seconds=120,
        live_trading_enabled=False,
        coinbase_live_enabled=False,
        autonomous_enabled=False,
        coinbase_api_key_name="",
        coinbase_api_key_file="",
        coinbase_max_capital=Decimal("0"),
    )
    app = create_app(settings)
    app.state.store.update_account(
        AccountUpdate(currency="USDC", equity=balance, start_of_day_equity=balance),
        moment,
    )
    cases = []
    for product, book in books.items():
        trend = research_trends.get(product, "unknown")
        idea = _idea(product, book, trend, moment)
        result = app.state.orchestrator.run(idea, moment)
        messages, decision = _record_exchange(app, result, moment)
        events = app.state.store.events_for_case(result.case_id)
        cases.append(
            {
                "product_id": product,
                "case_id": result.case_id,
                "label": "SIMULATED",
                "implementation": "rule_based",
                "outcome": result.outcome,
                "summary": result.summary,
                "transmitted": bool(result.execution and result.execution.transmitted),
                "agents": [_agent_entry(name, events, result) for name in AGENT_ORDER],
                "risk_status": None if result.risk is None else result.risk.status,
                "strategy_status": None if result.strategy is None else result.strategy.status,
                "messages": messages,
                "decision_log": decision,
            }
        )

    ladder = _size_ladder(app, books, moment, balance)
    full = next(row for row in ladder if row["fraction"] == "1")
    fitting = [row for row in ladder if row["fits_one_percent"]]
    largest = max(fitting, key=lambda row: Decimal(row["notional"]), default=None)
    below_minimum = largest is not None and Decimal(largest["notional"]) < settings.min_order_notional
    reasons = []
    if not full["fits_one_percent"]:
        reasons.append("100 percent of the balance violates the 1 percent planned-loss budget")
    if largest is None:
        reasons.append("no smaller size fits the 1 percent planned-loss budget")
    elif below_minimum:
        reasons.append(
            "the largest size inside the 1 percent budget is below the 10 USD minimum and no FX quote was supplied"
        )
    if screen_outcome != "TRADE":
        reasons.append("no intraday strategy met the robust-screen rule")
    decision = "NO TRADE"

    mocks = _mock_round_trip(books)
    app.state.store.set_kill_switch(engaged=True, reason="simulated halt", updated_by="trial", now=moment)
    halted = _evaluate_size(app, books, moment, Decimal(largest["notional"]) if largest else Decimal("1"), "kill")
    app.state.store.set_kill_switch(engaged=False, reason="simulated halt released", updated_by="trial", now=moment)

    if load_credentials(settings) is None:
        preview = "NOT RUN"
        preview_reason = "no CDP key is configured for this desk"
    else:
        preview = "NOT RUN"
        preview_reason = "a key is configured, but this trial does not call preview without an explicit desk client"

    return {
        "label": "SIMULATED",
        "real_trade": False,
        "transmitted": False,
        "implementation": "rule_based",
        "balance": {
            "source": balance_source,
            "currency": "USDC",
            "available": format_decimal(balance),
            "hold": "0",
            "btc_available": "0",
            "chf_available": "0",
            "eur_available": "0",
        },
        "books": {
            product: {
                "best_bid": book["best_bid"],
                "best_ask": book["best_ask"],
                "spread_bps": book["spread_bps"],
                "bid_depth_20": book["bid_depth_20"],
                "ask_depth_20": book["ask_depth_20"],
            }
            for product, book in books.items()
        },
        "cases": cases,
        "proposal": {
            "stop_fraction": format_decimal(STOP),
            "fee_bps_round_trip": format_decimal(FEE_BPS),
            "slippage_bps_round_trip": format_decimal(SLIPPAGE_BPS),
            "loss_scenarios": _scenarios(balance),
        },
        "size_ladder": ladder,
        "largest_size_within_one_percent": None if largest is None else largest["notional"],
        "decision": decision,
        "decision_reasons": reasons,
        "screen_outcome": screen_outcome,
        "order_preview": preview,
        "order_preview_reason": preview_reason,
        "mock_buy": mocks["buy"],
        "mock_sell": mocks["sell"],
        "kill_switch": {
            "engaged_during_test": True,
            "order_status": halted["status"],
            "blocked": halted["status"] == "REJECT" and "kill_switch" in halted["reasons"],
            "released_after_test": True,
        },
        "flags": {
            "LIVE_TRADING_ENABLED": settings.live_trading_enabled,
            "COINBASE_LIVE_ENABLED": settings.coinbase_live_enabled,
            "AUTONOMOUS_ENABLED": settings.autonomous_enabled,
        },
    }


def _idea(product: str, book: dict, trend: str, moment: datetime) -> DeskIdea:
    bid = Decimal(book["best_bid"])
    ask = Decimal(book["best_ask"])
    return DeskIdea(
        symbol=product,
        venue="coinbase",
        thesis="Simulated trial on a saved public book. This is not a live order.",
        size_mode="all_in",
        stop_fraction=STOP,
        quote_increment=QUOTE_INCREMENT,
        fee_bps_round_trip=FEE_BPS,
        slippage_bps_round_trip=SLIPPAGE_BPS,
        product_type="SPOT",
        request_live=False,
        market_snapshot=MarketSnapshot(
            source="coinbase_public_product_book",
            symbol=product,
            fetched_at=moment,
            raw_type="product_book",
            mid=(bid + ask) / Decimal(2),
            bid=bid,
            ask=ask,
            bid_size=Decimal(book["bid_depth_20"]),
            ask_size=Decimal(book["ask_depth_20"]),
            exchange_time=moment,
        ),
        research=ResearchInput(
            trend=trend if trend in {"up", "down", "flat", "unknown"} else "unknown",
            regime="saved_public_screen",
            source="docs/research/intraday-screen-2026-11-09.json",
            observed_at=moment,
            notes="Rule-based screen. Not a forecast.",
        ),
    )


def _record_exchange(app, result, moment: datetime) -> tuple[list[dict], dict]:
    previous = "desk_lead"
    messages = []
    for name in AGENT_ORDER[1:]:
        body = {"label": "SIMULATED", "summary": result.summary}
        app.state.store.add_agent_message(
            case_id=result.case_id,
            from_agent=previous,
            to_agent=name,
            schema_name="simulated_handoff",
            body=body,
            now=moment,
        )
        messages.append({"from": previous, "to": name, "body": body})
        previous = name
    decision_name = "NO TRADE" if result.risk is None or result.risk.status != "PASS" else result.risk.status
    reasons = ["simulated", result.summary]
    app.state.store.add_decision_log(
        case_id=result.case_id,
        stage="risk_manager",
        decision=decision_name,
        reasons=reasons,
        now=moment,
    )
    return messages, {"stage": "risk_manager", "decision": decision_name, "reasons": reasons}


def _agent_entry(name: str, events: list[dict], result) -> dict:
    match = next((event for event in events if event["agent"] == name), None)
    return {
        "agent": name,
        "status": None if match is None else match["status"],
        "summary": None if match is None else match["summary"],
        "implementation": "rule_based",
    }


def _size_ladder(app, books: dict, moment: datetime, balance: Decimal) -> list[dict]:
    product = next(iter(books))
    rows = []
    for fraction in FRACTIONS:
        notional = floor_money(balance * fraction)
        rows.append(_evaluate_size(app, books, moment, notional, f"fraction-{fraction}"))
        rows[-1]["fraction"] = format_decimal(fraction)
    bounds = app.state.risk_engine.sizing_bounds(
        equity=balance,
        stop_fraction=STOP,
        fee_bps=FEE_BPS,
        slippage_bps=SLIPPAGE_BPS,
        reserve_fraction=Decimal("0"),
    )
    largest = floor_money(bounds.by_risk)
    rows.append(_evaluate_size(app, books, moment, largest, "largest-under-one-percent", product))
    rows[-1]["fraction"] = "largest_under_one_percent"
    rows[-1]["product_id"] = product
    return rows


def _evaluate_size(app, books: dict, moment: datetime, notional: Decimal, tag: str, product: str | None = None) -> dict:
    product = product or next(iter(books))
    book = books[product]
    bid = Decimal(book["best_bid"])
    ask = Decimal(book["best_ask"])
    mid = (bid + ask) / Decimal(2)
    order = OrderIntent(
        client_order_id=f"sim-{tag}-{product}",
        venue="coinbase",
        symbol=product,
        side="buy",
        notional=notional,
        notional_currency="USDC",
        leverage=Decimal("1"),
        entry_price=mid,
        stop_price=mid * (Decimal("1") - STOP),
        market_data_time=moment,
        fee_bps_round_trip=FEE_BPS,
        slippage_bps_round_trip=SLIPPAGE_BPS,
    )
    decision = app.state.orchestrator.risk_manager.run(order, now=moment, case_id=f"sim-{tag}")
    planned_ok = any(check.rule == "planned_risk" and check.passed for check in decision.checks)
    cash_ok = any(check.rule == "insufficient_balance" and check.passed for check in decision.checks)
    return {
        "product_id": product,
        "notional": format_decimal(notional),
        "status": decision.status,
        "fits_one_percent": planned_ok and cash_ok and notional > 0,
        "planned_loss": None if decision.planned_loss is None else format_decimal(decision.planned_loss),
        "planned_loss_limit": None if decision.planned_loss_limit is None else format_decimal(decision.planned_loss_limit),
        "reasons": decision.reasons,
        "label": "SIMULATED",
        "transmitted": False,
    }


def _scenarios(balance: Decimal) -> list[dict]:
    notional = floor_money(balance / (Decimal("1") + (FEE_BPS + SLIPPAGE_BPS) / Decimal("10000")))
    fee = notional * FEE_BPS / Decimal("10000")
    slip = notional * SLIPPAGE_BPS / Decimal("10000")
    stop_loss = notional * STOP + fee + slip
    return [
        {"name": "fees_and_slippage_only", "loss_usdc": format_decimal(fee + slip), "label": "SIMULATED"},
        {"name": "stop_plus_fees_and_slippage", "loss_usdc": format_decimal(stop_loss), "label": "SIMULATED"},
        {"name": "notional_goes_to_zero", "loss_usdc": format_decimal(notional + fee), "label": "SIMULATED"},
    ]


def _mock_round_trip(books: dict) -> dict:
    adapter = DryRunAdapter()
    product = next(iter(books))
    book = books[product]
    results = {}
    for side in ("buy", "sell"):
        recorded = adapter.execute(
            {
                "label": "SIMULATED",
                "side": side,
                "product_id": product,
                "quote_size": "1.00",
                "note": "Mock fill recorded in process. No order was transmitted.",
                "bid": book["best_bid"],
                "ask": book["best_ask"],
            }
        )
        results[side] = {
            "label": "SIMULATED",
            "status": recorded.status,
            "transmitted": recorded.transmitted,
            "detail": recorded.detail,
        }
    return results
