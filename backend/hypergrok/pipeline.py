"""Plain Python desk pipeline.

LangGraph and CrewAI were not used. Both exist to call language models, and no
budgeted model is configured. The order of work is fixed, so a function call
is the state machine.
"""

from __future__ import annotations

from datetime import datetime

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


def _plain(value):
    from decimal import Decimal
    from hypergrok.serialize import to_jsonable

    if isinstance(value, Decimal):
        return format(value, "f")
    return to_jsonable(value) if value is not None else None
