"""Orchestrator flow with an injected snapshot. No live market-data call."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

from hypergrok.agents.catalog import AGENT_KEYS
from hypergrok.agents.market_analyst import MarketAnalyst
from hypergrok.agents.research_analyst import ResearchAnalyst
from hypergrok.domain import MarketSnapshot
from tests.support import fitting_idea, fresh_snapshot


def test_happy_path_records_a_dry_run_and_a_journal(app) -> None:
    now = datetime.now(timezone.utc)
    result = app.state.orchestrator.run(fitting_idea(now), now=now)
    assert result.desk.mode == "rule_based"
    assert result.market.mode == "rule_based"
    assert result.research.mode == "rule_based"
    assert result.strategy.mode == "rule_based"
    assert result.execution.mode == "rule_based"
    assert result.risk is not None
    assert result.risk.engine == "risk_engine"
    assert result.risk.status == "PASS"
    assert result.risk.fee_loss > 0
    assert result.risk.slippage_loss > 0
    notional = Decimal(result.strategy.sizing["notional"])
    assert Decimal("700") < notional <= Decimal("798.40")
    assert result.execution.status == "recorded"
    assert result.execution.transmitted is False
    assert result.outcome == "dry_run_recorded"
    assert result.journal_id is not None

    account = app.state.store.load_account(now)
    assert account.open_position_count == 1
    assert account.entries_today == 1
    attempt = app.state.store.list_attempts()[0]
    assert attempt["transmitted"] is False
    assert attempt["payload"]["would_send"]["symbol"] == "BTC"
    assert attempt["payload"]["note"].startswith("Recorded only")

    latest = app.state.store.latest_events_by_agent(list(AGENT_KEYS))
    assert all(latest[key] is not None for key in AGENT_KEYS)


def test_all_in_is_rejected_by_the_reserve_before_any_record(app) -> None:
    now = datetime.now(timezone.utc)
    result = app.state.orchestrator.run(fitting_idea(now, size_mode="all_in", client_order_id="all-in-1"), now=now)
    assert result.strategy.status == "proposed"
    assert Decimal(result.strategy.sizing["notional"]) > Decimal("900")
    assert result.risk is not None
    assert result.risk.status == "REJECT"
    assert result.risk.reasons == ["margin_reserve"]
    assert result.execution.status == "skipped"
    assert result.execution.transmitted is False
    assert result.outcome == "risk_rejected"
    assert app.state.store.load_account(now).open_position_count == 0
    assert app.state.store.list_attempts() == []


def test_wide_stop_is_rejected_by_planned_risk(app) -> None:
    now = datetime.now(timezone.utc)
    idea = fitting_idea(
        now,
        notional=Decimal("700"),
        stop_fraction=Decimal("0.05"),
        client_order_id="wide-1",
    )
    result = app.state.orchestrator.run(idea, now=now)
    assert result.risk is not None
    assert result.risk.status == "REJECT"
    assert result.risk.reasons == ["planned_risk"]
    assert result.execution.transmitted is False
    assert result.outcome == "risk_rejected"


def test_missing_or_stale_snapshot_does_not_invent_a_trade(app) -> None:
    now = datetime.now(timezone.utc)
    missing = app.state.orchestrator.run(fitting_idea(now, market_snapshot=None), now=now)
    assert missing.outcome == "no_trade"
    assert missing.risk is None
    assert missing.market.tradable is False
    assert missing.execution.transmitted is False

    stale_snapshot = fresh_snapshot(now - timedelta(hours=2))
    stale = app.state.orchestrator.run(fitting_idea(now, market_snapshot=stale_snapshot), now=now)
    assert stale.outcome == "no_trade"
    assert "stale_market_data" in stale.market.reasons


def test_kill_switch_stops_the_desk(app) -> None:
    now = datetime.now(timezone.utc)
    app.state.store.set_kill_switch(engaged=True, reason="halt", updated_by="human", now=now)
    result = app.state.orchestrator.run(fitting_idea(now, client_order_id="halt-1"), now=now)
    assert result.risk.status == "REJECT"
    assert "kill_switch" in result.risk.reasons
    assert result.execution.status == "skipped"
    assert result.outcome == "risk_rejected"


def test_solana_idea_is_rejected_by_the_desk_lead(app) -> None:
    now = datetime.now(timezone.utc)
    result = app.state.orchestrator.run(fitting_idea(now, venue="solana"), now=now)
    assert result.desk.status == "rejected"
    assert "venue_not_enabled" in result.desk.reasons
    assert result.outcome == "desk_rejected"
    assert result.risk is None


def test_analysts_do_not_invent_a_signal(settings) -> None:
    now = datetime.now(timezone.utc)
    market = MarketAnalyst(settings).run(
        MarketSnapshot(
            source="hyperliquid_public_info",
            symbol="BTC",
            fetched_at=now,
            raw_type="allMids",
            mid=Decimal("65000"),
        ),
        symbol="BTC",
        now=now,
    )
    assert market.tradable is False
    assert market.bias == "none"
    research = ResearchAnalyst().run(None)
    assert research.status == "insufficient_evidence"
    assert research.stance == "insufficient_evidence"


def test_risk_manager_delegates_instead_of_reimplementing_limits() -> None:
    text = (REPO / "backend" / "hypergrok" / "agents" / "risk_manager.py").read_text(encoding="utf-8")
    assert "evaluate" in text
    assert "0.01" not in text
    assert "0.20" not in text
    assert "max_leverage" not in text
