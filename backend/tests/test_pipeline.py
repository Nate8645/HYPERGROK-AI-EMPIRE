from datetime import datetime, timedelta, timezone
from decimal import Decimal

from hypergrok.domain import MarketSnapshot, ResearchInput
from hypergrok.pipeline import run_preview_pipeline
from tests.support import explicit_fx, fitting_idea, make_settings, seed_spot_product
from hypergrok.main import create_app


def _candles(now: datetime, fresh: bool) -> list[dict]:
    stamp = now if fresh else now - timedelta(hours=3)
    rows = []
    for i in range(40):
        price = 100 + i
        rows.append(
            {
                "high": str(price + 1),
                "low": str(price - 1),
                "close": str(price),
                "volume": "2",
                "time": (stamp - timedelta(minutes=40 - i)).isoformat(),
                "fetched_at": stamp.isoformat(),
            }
        )
    return rows


def test_pipeline_preview_does_not_transmit_and_logs_decisions(app) -> None:
    now = datetime.now(timezone.utc)
    seed_spot_product(app.state.store, "BTC-USD", now)
    idea = fitting_idea(
        now,
        symbol="BTC-USD",
        venue="coinbase",
        research=ResearchInput(trend="up", funding_bps=Decimal("1")),
        fee_bps_round_trip=Decimal("20"),
        slippage_bps_round_trip=Decimal("10"),
        **explicit_fx(now),
    )
    idea = idea.model_copy(
        update={
            "request_live": True,
            "market_snapshot": MarketSnapshot(
                source="coinbase_advanced_trade",
                symbol="BTC-USD",
                fetched_at=now,
                raw_type="product_book",
                mid=Decimal("65000"),
                bid=Decimal("64990"),
                ask=Decimal("65010"),
                bid_size=Decimal("5"),
                ask_size=Decimal("1"),
            ),
        }
    )
    result = run_preview_pipeline(app.state.orchestrator, idea, candles=_candles(now, True), now=now)
    assert result["halted"] is False
    assert result["run"].execution.transmitted is False
    assert result["run"].execution.execution_mode == "dry_run"
    journal = app.state.store.list_journal(20)
    assert any(row["outcome"] == "review_metrics" for row in journal)


def test_stale_data_and_api_errors_halt_before_execution(app) -> None:
    now = datetime.now(timezone.utc)
    idea = fitting_idea(now)
    stale = run_preview_pipeline(app.state.orchestrator, idea, candles=_candles(now, False), now=now)
    assert stale["halted"] is True
    assert "stale_market_data" in stale["reasons"]
    assert app.state.store.list_attempts() == []
    halted = run_preview_pipeline(
        app.state.orchestrator,
        idea,
        candles=_candles(now, True),
        now=now,
        api_error="coinbase_http_500",
    )
    assert halted["halted"] is True
    assert any(item.startswith("api_error:") for item in halted["reasons"])
