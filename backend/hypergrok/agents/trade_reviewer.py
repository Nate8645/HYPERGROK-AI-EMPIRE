"""Trade Reviewer. Rule-based. Writes a journal entry from the case record."""

from __future__ import annotations

from datetime import datetime

from hypergrok.agents.catalog import MODE
from hypergrok.agents.schemas import (
    DeskCase,
    ExecutionReport,
    MarketAnalysis,
    ResearchNote,
    StrategyProposal,
)
from hypergrok.domain import DeskIdea, RiskDecision
from hypergrok.store import DeskStore


class TradeReviewer:
    name = "trade_reviewer"
    mode = MODE

    def __init__(self, store: DeskStore) -> None:
        self.store = store

    def run(
        self,
        *,
        idea: DeskIdea,
        case: DeskCase,
        market: MarketAnalysis | None,
        research: ResearchNote | None,
        strategy: StrategyProposal | None,
        risk: RiskDecision | None,
        execution: ExecutionReport | None,
        now: datetime,
    ) -> tuple[int, str, str]:
        outcome = _outcome(case, strategy, risk, execution)
        risk_text = "not_run" if risk is None else f"{risk.status} ({', '.join(risk.reasons) or 'none'})"
        execution_text = "not_run" if execution is None else f"{execution.status} transmitted={execution.transmitted}"
        summary = (
            f"Case {case.case_id} {case.symbol} {case.venue}. "
            f"Outcome {outcome}. Desk lead {case.status}. "
            f"Market {market.status if market else 'not_run'}. "
            f"Research {research.stance if research else 'not_run'}. "
            f"Strategy {strategy.status if strategy else 'not_run'}. "
            f"Risk {risk_text}. Execution {execution_text}. "
            "Rule-based review. No exchange fill is implied."
        )
        payload = {
            "implementation": MODE,
            "idea": idea,
            "desk": case,
            "market": market,
            "research": research,
            "strategy": strategy,
            "risk": risk,
            "execution": execution,
            "outcome": outcome,
        }
        journal_id = self.store.add_journal(
            case_id=case.case_id,
            symbol=case.symbol,
            venue=case.venue,
            outcome=outcome,
            summary=summary,
            payload=payload,
            now=now,
        )
        return journal_id, summary, outcome


def _outcome(
    case: DeskCase,
    strategy: StrategyProposal | None,
    risk: RiskDecision | None,
    execution: ExecutionReport | None,
) -> str:
    if case.status != "accepted":
        return "desk_rejected"
    if strategy is None or strategy.status != "proposed":
        return "no_trade"
    if risk is None or risk.status != "PASS":
        return "risk_rejected"
    if execution is not None and execution.status == "recorded":
        return "dry_run_recorded"
    if execution is not None and execution.status == "rejected":
        return "execution_rejected"
    return "unreviewed"
