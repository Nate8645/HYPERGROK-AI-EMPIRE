"""Application factory. Uvicorn entry: hypergrok.main:create_app --factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from hypergrok import __version__
from hypergrok.api.routes import router
from hypergrok.clock import utcnow
from hypergrok.config import Settings
from hypergrok.db import init_db, make_engine, make_session_factory
from hypergrok.events import EventBus
from hypergrok.execution.dry_run import DryRunAdapter
from hypergrok.execution.gate import ExecutionGate
from hypergrok.logging_config import configure_logging
from hypergrok.agents.orchestrator import Orchestrator
from hypergrok.risk.engine import RiskEngine
from hypergrok.risk.service import RiskService
from hypergrok.store import DeskStore
from hypergrok.errors import DeskError
from hypergrok.venues.coinbase.adapter import CoinbaseExecutionAdapter
from hypergrok.venues.coinbase.service import CoinbaseService

logger = logging.getLogger(__name__)


class _LazyCoinbase:
    """Builds the broker only when a live Coinbase order is actually sent."""

    transmits = True
    name = "coinbase"

    def __init__(self, service: CoinbaseService) -> None:
        self.service = service

    def execute(self, would_send: dict):
        return CoinbaseExecutionAdapter(self.service.broker).execute(would_send)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings.log_level, json_logs=settings.log_json)
    db_engine = make_engine(settings.database_url)
    init_db(db_engine)
    store = DeskStore(make_session_factory(db_engine))
    store.seed(settings)
    bus = EventBus()
    risk_engine = RiskEngine(settings)
    risk_service = RiskService(store, risk_engine, bus)
    gate = ExecutionGate(settings, store)
    adapter = DryRunAdapter()
    coinbase = CoinbaseService(
        settings,
        risk_service=risk_service,
        gate=gate,
        dry_run=adapter,
        store=store,
        clock=utcnow,
    )
    orchestrator = Orchestrator(
        settings=settings,
        store=store,
        risk_service=risk_service,
        engine=risk_engine,
        gate=gate,
        adapter=adapter,
        bus=bus,
    )
    orchestrator.coinbase = coinbase
    orchestrator.trader.coinbase = CoinbaseExecutionAdapter(coinbase.broker) if False else _LazyCoinbase(coinbase)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        import asyncio

        bus.bind_loop(asyncio.get_running_loop())
        try:
            yield
        finally:
            db_engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Phase 1 rule-based trading desk. The risk engine can reject orders. "
            "This process does not sign transactions or send them to an exchange."
        ),
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db_engine = db_engine
    app.state.bus = bus
    app.state.store = store
    app.state.risk_engine = risk_engine
    app.state.risk_service = risk_service
    app.state.gate = gate
    app.state.adapter = adapter
    app.state.orchestrator = orchestrator
    app.state.coinbase = coinbase
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DeskError)
    async def handle_desk_error(_request: Request, exc: DeskError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    app.include_router(router)
    logger.info(
        "desk started",
        extra={
            "context": {
                "phase": 1,
                "live_trading_enabled": settings.live_trading_enabled,
                "transmits_orders": coinbase.live_armed(),
                "currency": settings.account_currency,
                "implementation": "rule_based",
            }
        },
    )
    return app
