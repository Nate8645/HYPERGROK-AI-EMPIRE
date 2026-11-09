"""Research Analyst. Rule-based. Scores only the structured fields the caller supplied."""

from __future__ import annotations

from decimal import Decimal

from hypergrok.agents.catalog import MODE
from hypergrok.agents.schemas import ResearchNote
from hypergrok.domain import ResearchInput

CROWDING_BPS = Decimal("20")


class ResearchAnalyst:
    name = "research_analyst"
    mode = MODE

    def run(self, research: ResearchInput | None) -> ResearchNote:
        if research is None or (research.trend == "unknown" and research.funding_bps is None):
            inputs: list[str] = []
            reasons = ["no structured research inputs were supplied"]
            if research is not None and research.observed_spread_bps is not None:
                inputs.append("observed_spread_bps")
                reasons.append("observed spread is recorded and is not a directional signal")
            return ResearchNote(
                status="insufficient_evidence",
                summary="no structured research inputs; nothing was fetched or inferred",
                stance="insufficient_evidence",
                reasons=reasons,
                inputs_used=inputs,
            )

        inputs: list[str] = []
        reasons: list[str] = []
        if research.trend != "unknown":
            inputs.append("trend")
        if research.funding_bps is not None:
            inputs.append("funding_bps")
        if research.notes.strip():
            inputs.append("notes_recorded_not_interpreted")
            reasons.append("free-text notes are stored and are not turned into a signal")
        if research.observed_spread_bps is not None:
            inputs.append("observed_spread_bps")
            reasons.append("observed spread is recorded and is not a directional signal")

        funding = research.funding_bps
        crowded_long = funding is not None and funding > CROWDING_BPS
        crowded_short = funding is not None and funding < -CROWDING_BPS
        if research.trend == "up" and not crowded_long:
            stance = "support_long"
            reasons.append("supplied trend is up")
        elif research.trend == "down" and not crowded_short:
            stance = "support_short"
            reasons.append("supplied trend is down")
        elif research.trend == "flat":
            stance = "neutral"
            reasons.append("supplied trend is flat")
        elif crowded_long or crowded_short:
            stance = "neutral"
            reasons.append("supplied funding is crowded against the trend")
        else:
            stance = "insufficient_evidence"
            reasons.append("research inputs do not support a side")

        status = "completed" if stance != "insufficient_evidence" else "insufficient_evidence"
        return ResearchNote(
            status=status,
            summary=f"{status} stance={stance}",
            stance=stance,
            reasons=reasons,
            inputs_used=inputs,
        )
