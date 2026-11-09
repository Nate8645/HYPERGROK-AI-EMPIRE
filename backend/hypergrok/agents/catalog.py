"""The seven phase-1 agents. Every one is rule-based."""

from __future__ import annotations

from dataclasses import dataclass

MODE = "rule_based"


@dataclass(frozen=True)
class AgentSpec:
    key: str
    name: str
    summary: str


AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec(
        "desk_lead",
        "Desk Lead",
        "Opens or rejects a case. Rule-based, no language model.",
    ),
    AgentSpec(
        "market_analyst",
        "Market Analyst",
        "Reads a labelled snapshot. Does not invent prices.",
    ),
    AgentSpec(
        "research_analyst",
        "Research Analyst",
        "Uses only caller-supplied structured inputs.",
    ),
    AgentSpec(
        "strategist",
        "Strategist",
        "Proposes an order. Sizing bounds come from the risk engine, which still has to PASS the order.",
    ),
    AgentSpec(
        "risk_manager",
        "Risk Manager",
        "Submits the proposal to the independent risk engine and returns that decision unchanged.",
    ),
    AgentSpec(
        "execution_trader",
        "Execution Trader",
        "Dry-run only. A live request needs the live flag and a human approval token, and phase 1 still does not transmit.",
    ),
    AgentSpec(
        "trade_reviewer",
        "Trade Reviewer",
        "Writes the journal entry for the case.",
    ),
)

AGENT_KEYS = tuple(spec.key for spec in AGENTS)
