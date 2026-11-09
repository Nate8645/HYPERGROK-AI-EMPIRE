"""Desk pipeline.

idea -> analysis -> strategy proposal -> risk engine -> execution gate -> journal.

Market data is whatever the caller labelled and attached. This orchestrator
does not call the network.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from hypergrok.agents.desk_lead import DeskLead
from hypergrok.agents.execution_trader import ExecutionTrader
from hypergrok.agents.market_analyst import MarketAnalyst
from hypergrok.agents.research_analyst import ResearchAnalyst
from hypergrok.agents.risk_manager import RiskManager
from hypergrok.agents.schemas import DeskRunResult, ExecutionReport
from hypergrok.agents.strategist import Strategist
from hypergrok.agents.trade_reviewer import TradeReviewer
from hypergrok.clock import utcnow
from hypergrok.config import Settings
from hypergrok.domain import DeskIdea
from hypergrok.events import EventBus
from hypergrok.execution.adapter import ExecutionAdapter
from hypergrok.execution.gate import ExecutionGate
from hypergrok.risk.engine import RiskEngine
from hypergrok.risk.service import RiskService
from hypergrok.store import DeskStore

DOWNSTREAM = (
    "market_analyst",
    "research_analyst",
    "strategist",
    "risk_manager",
    "execution_trader",
)


class Orchestrator:
    def __init__(
        self,
        *,
        settings: Settings,
        store: DeskStore,
        risk_service: RiskService,
        engine: RiskEngine,
        gate: ExecutionGate,
        adapter: ExecutionAdapter,
        bus: EventBus,
    ) -> None:
        self.store = store
        self.bus = bus
        self.desk = DeskLead()
        self.market = MarketAnalyst(settings)
        self.research = ResearchAnalyst()
        self.strategist = Strategist(settings, engine)
        self.risk_manager = RiskManager(risk_service)
        self.coinbase = None
        self.trader = ExecutionTrader(gate, adapter, store, engine, self.risk_manager)
        self.reviewer = TradeReviewer(store)

    def run(self, idea: DeskIdea, now: datetime | None = None) -> DeskRunResult:
        moment = now or utcnow()
        case_id = uuid.uuid4().hex
        case = self.desk.run(idea, case_id=case_id)
        self._emit("desk_lead", "agent_event", case.status, case_id, case.summary, case, moment)

        market = None
        research = None
        strategy = None
        risk = None
        execution = None

        if case.status != "accepted":
            for name in DOWNSTREAM:
                self._emit(name, "agent_event", "skipped", case_id, "desk lead rejected the idea", {}, moment)
        else:
            snapshot = idea.market_snapshot
            if snapshot is None and idea.load_coinbase_book and self.coinbase is not None:
                snapshot = self.coinbase.safe_snapshot(idea.symbol)
            market = self.market.run(snapshot, symbol=case.symbol, now=moment)
            self._emit("market_analyst", "agent_event", market.status, case_id, market.summary, market, moment)
            research_input = idea.research
            if case.venue == "coinbase" and market.spread_bps is not None:
                from hypergrok.domain import ResearchInput

                base = idea.research or ResearchInput()
                research_input = base.model_copy(update={"observed_spread_bps": market.spread_bps})
            research = self.research.run(research_input)
            self._emit("research_analyst", "agent_event", research.status, case_id, research.summary, research, moment)
            account = self.store.load_account(moment)
            strategy = self.strategist.run(idea, case, market, research, account)
            self._emit("strategist", "agent_event", strategy.status, case_id, strategy.summary, strategy, moment)
            if strategy.order is None:
                self._emit("risk_manager", "agent_event", "skipped", case_id, "no order proposed", {}, moment)
                execution = _skipped_execution(None, ["no_order"])
                self._emit(
                    "execution_trader",
                    "agent_event",
                    execution.status,
                    case_id,
                    execution.summary,
                    execution,
                    moment,
                )
            else:
                risk = self.risk_manager.run(strategy.order, now=moment, case_id=case_id)
                execution = self.trader.run(
                    order=strategy.order,
                    decision=risk,
                    idea=idea,
                    case_id=case_id,
                    now=moment,
                )
                self._emit(
                    "execution_trader",
                    "agent_event",
                    execution.status,
                    case_id,
                    execution.summary,
                    execution,
                    moment,
                )

        journal_id, summary, outcome = self.reviewer.run(
            idea=idea,
            case=case,
            market=market,
            research=research,
            strategy=strategy,
            risk=risk,
            execution=execution,
            now=moment,
        )
        self._emit(
            "trade_reviewer",
            "agent_event",
            "completed",
            case_id,
            summary,
            {"journal_id": journal_id, "outcome": outcome},
            moment,
        )
        return DeskRunResult(
            case_id=case_id,
            outcome=outcome,
            summary=summary,
            journal_id=journal_id,
            desk=case,
            market=market,
            research=research,
            strategy=strategy,
            risk=risk,
            execution=execution,
        )

    def _emit(
        self,
        agent: str,
        event_type: str,
        status: str,
        case_id: str,
        summary: str,
        payload: object,
        now: datetime,
    ) -> None:
        event = self.store.add_event(
            agent=agent,
            event_type=event_type,
            status=status,
            case_id=case_id,
            summary=summary,
            payload={"body": payload, "implementation": "rule_based"},
            now=now,
        )
        self.bus.publish(event)


def _skipped_execution(client_order_id: str | None, reasons: list[str]) -> ExecutionReport:
    return ExecutionReport(
        status="skipped",
        transmitted=False,
        summary="skipped: " + ", ".join(reasons),
        reasons=reasons,
        client_order_id=client_order_id,
        gate_reason=None,
        approval_consumed=False,
        execution_mode=None,
    )
