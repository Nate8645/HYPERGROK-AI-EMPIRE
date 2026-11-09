"""Plain Python desk pipeline.

LangGraph and CrewAI were not used. Both exist to call language models, and no
budgeted model is configured. The order of work is fixed, so a function call
is the state machine.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from hypergrok.agents.orchestrator import Orchestrator
from hypergrok.clock import utcnow
from hypergrok.domain import DeskIdea
from hypergrok.indicators import book_metrics, latest_indicators, multi_timeframe_trend
from hypergrok.research_rules import check_data_quality, conflicting_signals, detect_regime
from hypergrok.backtest import score_trades
from hypergrok.store import DeskStore


def run_preview_pipeline(
    orchestrator: Orchestrator,
    idea: DeskIdea,
    *,
    candles: list[dict] | None = None,
    higher_candles: list[dict] | None = None,
    now: datetime | None = None,
    source: str = "coinbase_public_candles",
    api_error: str | None = None,
) -> dict:
    moment = now or utcnow()
    store: DeskStore = orchestrator.store
    quality = check_data_quality(candles or [], now=moment, max_age_seconds=orchestrator.market.settings.max_market_data_age_seconds, source=source)
    regime = detect_regime(candles) if candles else "unknown"
    indicators = latest_indicators(candles) if candles else {}
    higher_trend = "unknown"
    if higher_candles and candles:
        higher_trend = multi_timeframe_trend(
            [__import__("decimal").Decimal(str(row["close"])) for row in higher_candles],
            [__import__("decimal").Decimal(str(row["close"])) for row in candles],
        )
    book = None
    if idea.market_snapshot and idea.market_snapshot.bid and idea.market_snapshot.ask:
        book = book_metrics(
            idea.market_snapshot.bid,
            idea.market_snapshot.ask,
            idea.market_snapshot.bid_size or 0,
            idea.market_snapshot.ask_size or 0,
        )
    halt_reasons = []
    if api_error:
        halt_reasons.append(f"api_error:{api_error}")
    if not quality["ok"]:
        halt_reasons.extend(quality["problems"])
    store.put_blackboard(
        "market",
        {"regime": regime, "indicators": _plain(indicators), "book": _plain(book), "quality": quality, "higher_trend": higher_trend},
        source,
        moment,
    )
    if halt_reasons:
        store.add_decision_log(case_id=None, stage="desk_lead", decision="halt", reasons=halt_reasons, now=moment)
        store.put_blackboard("trading_halt", {"engaged": True, "reasons": halt_reasons}, source, moment)
        return {"halted": True, "reasons": halt_reasons, "run": None}
    enriched = idea.model_copy(
        update={
            "request_live": False,
            "regime": regime,
        }
    ) if False else idea.model_copy(update={"request_live": False})
    research = enriched.research
    if research is not None:
        research = research.model_copy(
            update={
                "regime": regime,
                "source": source,
                "observed_at": moment,
                "conflicts": conflicting_signals(
                    market_bias=str(indicators.get("trend") or "unknown"),
                    research_stance="support_long" if research.trend == "up" else "support_short" if research.trend == "down" else "neutral",
                    strategy_signal="long" if indicators.get("trend") == "up" else "flat",
                ),
            }
        )
        enriched = enriched.model_copy(update={"research": research})
    result = orchestrator.run(enriched, now=moment)
    case_id = result.case_id
    store.add_agent_message(
        case_id=case_id,
        from_agent="market_analyst",
        to_agent="strategist",
        schema_name="market_analysis",
        body={"summary": result.market.summary if result.market else "", "indicators": _plain(indicators), "book": _plain(book)},
        now=moment,
    )
    store.add_agent_message(
        case_id=case_id,
        from_agent="research_analyst",
        to_agent="strategist",
        schema_name="research_note",
        body={"summary": result.research.summary if result.research else "", "regime": regime, "source": source},
        now=moment,
    )
    store.add_decision_log(
        case_id=case_id,
        stage="risk_manager",
        decision=result.risk.status if result.risk else "not_run",
        reasons=result.risk.reasons if result.risk else [],
        now=moment,
    )
    trades = []
    if result.execution and result.execution.status == "recorded":
        trades = [{"return": __import__("decimal").Decimal("0")}]
    review = score_trades(trades)
    store.add_journal(
        case_id=case_id,
        symbol=idea.symbol,
        venue=idea.venue,
        outcome="review_metrics",
        summary="reviewer metrics from this preview; Sharpe omitted when the sample is small",
        payload={"metrics": _plain(review), "mode": "rule_based"},
        now=moment,
    )
    return {"halted": False, "reasons": [], "run": result, "regime": regime, "indicators": _plain(indicators), "review": _plain(review)}


def run_team_case(orchestrator: Orchestrator, idea: DeskIdea, *, now: datetime | None = None) -> dict:
    """One recorded case through all seven agents, plus a read-only Coinbase preview when a client exists.

    Submit still depends on the execution gate. Live flags stay under the caller's settings.
    """
    moment = now or utcnow()
    result = orchestrator.run(idea, now=moment)
    preview = None
    preview_error = None
    order = result.strategy.order if result.strategy else None
    coinbase = getattr(orchestrator, "coinbase", None)
    if order is not None and result.risk is not None and result.risk.status == "PASS" and coinbase is not None and coinbase.configured():
        payload = {
            "product_id": order.symbol,
            "side": order.side,
            "order_type": idea.order_type or "market",
            "post_only": idea.post_only,
            "client_order_id": order.client_order_id,
            "entry_price": format(order.entry_price, "f"),
            "stop_price": None if order.stop_price is None else format(order.stop_price, "f"),
        }
        if order.side == "sell":
            payload["base_size"] = format(idea.base_size, "f") if idea.base_size is not None else None
            payload["limit_price"] = format(idea.limit_price, "f") if idea.limit_price is not None else None
        else:
            payload["quote_size"] = format(order.notional, "f")
            if idea.limit_price is not None:
                payload["limit_price"] = format(idea.limit_price, "f")
        try:
            preview = coinbase.preview_order(payload)
        except Exception as exc:
            preview_error = getattr(exc, "code", None) or "preview_failed"
    agents = [
        {"agent": "desk_lead", "status": result.desk.status, "mode": result.desk.mode},
        {"agent": "market_analyst", "status": None if result.market is None else result.market.status, "mode": "rule_based"},
        {"agent": "research_analyst", "status": None if result.research is None else result.research.status, "mode": "rule_based"},
        {"agent": "strategist", "status": None if result.strategy is None else result.strategy.status, "mode": "rule_based"},
        {"agent": "risk_manager", "status": None if result.risk is None else result.risk.status, "mode": "rule_based"},
        {"agent": "execution_trader", "status": None if result.execution is None else result.execution.status, "mode": "rule_based"},
        {"agent": "trade_reviewer", "status": "completed" if result.journal_id is not None else "skipped", "mode": "rule_based"},
    ]
    return {
        "case_id": result.case_id,
        "implementation": "rule_based",
        "agents": agents,
        "proposal": None if result.strategy is None else result.strategy.model_dump(mode="json"),
        "risk": None if result.risk is None else result.risk.model_dump(mode="json"),
        "execution": None if result.execution is None else result.execution.model_dump(mode="json"),
        "preview": preview,
        "preview_error": preview_error,
        "submitted": bool(result.execution and result.execution.transmitted),
        "journal_id": result.journal_id,
    }


def run_final_preview_case(orchestrator: Orchestrator, idea: DeskIdea, *, now: datetime | None = None) -> dict:
    """Market and research, then the strategist, then the desk lead, then risk, execution, and review.

    request_live is forced off. A live preview is not claimed.
    """
    import uuid

    from hypergrok.agents.schemas import DeskCase

    moment = now or utcnow()
    idea = idea.model_copy(update={"request_live": False, "approval_token": None})
    ran = ["market_analyst", "research_analyst", "strategist", "desk_lead", "risk_manager", "execution_trader", "trade_reviewer"]
    market = orchestrator.market.run(idea.market_snapshot, symbol=idea.symbol, now=moment)
    research = orchestrator.research.run(idea.research)
    case_id = uuid.uuid4().hex
    provisional = DeskCase(
        status="accepted",
        case_id=case_id,
        reasons=["sizing_only"],
        summary="provisional case for sizing",
        symbol=idea.symbol,
        venue=idea.venue,
        side=idea.side,
    )
    account = orchestrator.store.load_account(moment)
    strategy = orchestrator.strategist.run(idea, provisional, market, research, account)
    desk = orchestrator.desk.run(idea, case_id=case_id)
    risk = None
    execution = None
    if desk.status == "accepted" and strategy.order is not None:
        risk = orchestrator.risk_manager.run(strategy.order, now=moment, case_id=case_id)
        execution = orchestrator.trader.run(order=strategy.order, decision=risk, idea=idea, case_id=case_id, now=moment)
    journal_id, summary, outcome = orchestrator.reviewer.run(
        idea=idea,
        case=desk,
        market=market,
        research=research,
        strategy=strategy,
        risk=risk,
        execution=execution,
        now=moment,
    )
    preview = None
    preview_error = None
    order = strategy.order if desk.status == "accepted" else None
    coinbase = getattr(orchestrator, "coinbase", None)
    if order is not None and risk is not None and risk.status == "PASS" and coinbase is not None and coinbase.configured():
        try:
            preview = coinbase.preview_order(
                {
                    "product_id": order.symbol,
                    "side": order.side,
                    "order_type": "market",
                    "quote_size": format(order.notional, "f"),
                    "client_order_id": order.client_order_id,
                    "entry_price": format(order.entry_price, "f"),
                    "stop_price": None if order.stop_price is None else format(order.stop_price, "f"),
                }
            )
        except Exception as exc:
            preview_error = getattr(exc, "code", None) or "preview_failed"
    fee = None
    if order is not None and order.fee_bps_round_trip is not None:
        fee = order.notional * order.fee_bps_round_trip / Decimal("10000")
    return {
        "mode": "fixture-based",
        "agent_order": ran,
        "implementation": "rule_based",
        "outcome": outcome,
        "summary": summary,
        "journal_id": journal_id,
        "balance": format(account.equity, "f"),
        "balance_currency": account.currency,
        "proposal": strategy.model_dump(mode="json"),
        "planned_order_size": None if order is None else format(order.notional, "f"),
        "fee": None if fee is None else format(fee, "f"),
        "fee_bps_round_trip": None if order is None or order.fee_bps_round_trip is None else format(order.fee_bps_round_trip, "f"),
        "max_loss": None if risk is None or risk.planned_loss is None else format(risk.planned_loss, "f"),
        "risk_status": None if risk is None else risk.status,
        "preview": preview if preview is not None else "Keine Daten",
        "preview_error": preview_error,
        "live_preview": "Keine Daten",
        "submitted": False,
        "execution_transmitted": bool(execution and execution.transmitted),
    }


def _plain(value):
    from decimal import Decimal
    from hypergrok.serialize import to_jsonable

    if isinstance(value, Decimal):
        return format(value, "f")
    return to_jsonable(value) if value is not None else None
