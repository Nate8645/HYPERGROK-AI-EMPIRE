"""Desk Lead. Rule-based. Decides whether a case is in scope for phase 1."""

from __future__ import annotations

from hypergrok.agents.catalog import MODE
from hypergrok.agents.schemas import DeskCase
from hypergrok.domain import DeskIdea


class DeskLead:
    name = "desk_lead"
    mode = MODE

    def run(self, idea: DeskIdea, *, case_id: str) -> DeskCase:
        reasons: list[str] = []
        if idea.venue != "hyperliquid":
            reasons.append("venue_not_enabled")
        if not idea.thesis.strip():
            reasons.append("thesis_required")
        if reasons:
            return DeskCase(
                status="rejected",
                case_id=case_id,
                reasons=reasons,
                summary=f"rejected {idea.symbol}: {', '.join(reasons)}",
                symbol=idea.symbol,
                venue=idea.venue,
                side=idea.side,
            )
        return DeskCase(
            status="accepted",
            case_id=case_id,
            reasons=["accepted"],
            summary=f"case opened for {idea.symbol} on hyperliquid",
            symbol=idea.symbol,
            venue=idea.venue,
            side=idea.side,
        )
