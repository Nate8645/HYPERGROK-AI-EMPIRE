"""Input is in `hypergrok.domain`. These are the agent outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from hypergrok.agents.catalog import MODE
from hypergrok.domain import OrderIntent, RiskDecision
from hypergrok.money import Dec


class DeskCase(BaseModel):
    agent: Literal["desk_lead"] = "desk_lead"
    mode: Literal["rule_based"] = MODE
    status: Literal["accepted", "rejected"]
    case_id: str
    reasons: list[str]
    summary: str
    symbol: str
    venue: str
    side: str | None = None


class MarketAnalysis(BaseModel):
    agent: Literal["market_analyst"] = "market_analyst"
    mode: Literal["rule_based"] = MODE
    status: Literal["completed", "insufficient_data", "stale"]
    summary: str
    symbol: str | None = None
    source: str | None = None
    fetched_at: datetime | None = None
    observed_at: datetime | None = None
    mid: Dec | None = None
    spread_bps: Dec | None = None
    imbalance: Dec | None = None
    bias: Literal["long", "short", "neutral", "none"]
    tradable: bool
    reasons: list[str]


class ResearchNote(BaseModel):
    agent: Literal["research_analyst"] = "research_analyst"
    mode: Literal["rule_based"] = MODE
    status: Literal["completed", "insufficient_evidence"]
    summary: str
    stance: Literal["support_long", "support_short", "neutral", "insufficient_evidence"]
    reasons: list[str]
    inputs_used: list[str]


class StrategyProposal(BaseModel):
    agent: Literal["strategist"] = "strategist"
    mode: Literal["rule_based"] = MODE
    status: Literal["proposed", "no_trade"]
    summary: str
    reasons: list[str]
    order: OrderIntent | None = None
    sizing: dict[str, str] = Field(default_factory=dict)


class ExecutionReport(BaseModel):
    agent: Literal["execution_trader"] = "execution_trader"
    mode: Literal["rule_based"] = MODE
    status: Literal["recorded", "rejected", "skipped", "submitted", "unknown"]
    transmitted: bool
    summary: str
    reasons: list[str]
    client_order_id: str | None = None
    gate_reason: str | None = None
    approval_consumed: bool = False
    execution_mode: str | None = None
    fills: list[dict] = Field(default_factory=list)

    @model_validator(mode="after")
    def _transmission_scope(self) -> Self:
        if self.transmitted and self.execution_mode != "live":
            raise ValueError("only a live execution can be marked transmitted")
        return self


class DeskRunResult(BaseModel):
    case_id: str
    outcome: str
    summary: str
    journal_id: int | None = None
    desk: DeskCase
    market: MarketAnalysis | None = None
    research: ResearchNote | None = None
    strategy: StrategyProposal | None = None
    risk: RiskDecision | None = None
    execution: ExecutionReport | None = None
