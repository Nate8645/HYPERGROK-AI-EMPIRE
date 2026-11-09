"""Read-only desk routes plus the paper kill switch, journal, and idea runner.

Nothing on this router signs a transaction or contacts an exchange.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict, Field

from hypergrok.agents.catalog import AGENT_KEYS, AGENTS
from hypergrok.api.coinbase import router as coinbase_router
from hypergrok.agents.schemas import DeskRunResult
from hypergrok.clock import isoformat, utcnow
from hypergrok.domain import (
    AccountState,
    AccountUpdate,
    DeskIdea,
    KillSwitchState,
    KillSwitchUpdate,
    OrderIntent,
    RiskDecision,
)

logger = logging.getLogger(__name__)
router = APIRouter()
router.include_router(coinbase_router)


class ApprovalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_order_id: str = Field(min_length=1, max_length=128)
    note: str = Field(default="", max_length=500)


@router.get("/health")
def health(request: Request) -> dict:
    store = request.app.state.store
    settings = request.app.state.settings
    database_ok = store.ping()
    kill = store.get_kill_switch()
    return {
        "status": "ok" if database_ok else "degraded",
        "service": settings.app_name,
        "phase": 1,
        "implementation": "rule_based",
        "live_trading_enabled": settings.live_trading_enabled,
        "kill_switch_engaged": kill.engaged,
        "transmits_orders": request.app.state.coinbase.live_armed(),
        "database": "ok" if database_ok else "error",
    }


@router.websocket("/ws/events")
async def ws_events(websocket: WebSocket) -> None:
    bus = websocket.app.state.bus
    await websocket.accept()
    bus.bind_loop(asyncio.get_running_loop())
    queue = bus.subscribe()
    await websocket.send_json(
        {
            "type": "ws.connected",
            "at": isoformat(utcnow()),
            "transmits_orders": websocket.app.state.coinbase.live_armed(),
        }
    )
    try:
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        bus.unsubscribe(queue)


@router.get("/api/agents/status")
def agent_status(request: Request) -> dict:
    latest = request.app.state.store.latest_events_by_agent(list(AGENT_KEYS))
    agents = []
    for spec in AGENTS:
        event = latest[spec.key]
        agents.append(
            {
                "key": spec.key,
                "name": spec.name,
                "summary": spec.summary,
                "mode": "rule_based",
                "status": event["status"] if event else "idle",
                "last_case_id": None if event is None else event["case_id"],
                "last_summary": None if event is None else event["summary"],
                "updated_at": None if event is None else event["at"],
            }
        )
    return {"agents": agents, "implementation": "rule_based"}


@router.get("/api/risk/config")
def risk_config(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "account_currency": settings.account_currency,
        "starting_capital": format(settings.starting_capital, "f"),
        "max_leverage": format(settings.max_leverage, "f"),
        "max_planned_risk_fraction": format(settings.max_planned_risk_fraction, "f"),
        "max_daily_loss_fraction": format(settings.max_daily_loss_fraction, "f"),
        "max_open_positions": settings.max_open_positions,
        "max_new_entries_per_day": settings.max_new_entries_per_day,
        "hyperliquid_reserve_fraction": format(settings.hyperliquid_reserve_fraction, "f"),
        "min_order_notional": format(settings.min_order_notional, "f"),
        "min_order_notional_currency": settings.min_order_notional_currency,
        "default_fee_bps_round_trip": format(settings.default_fee_bps_round_trip, "f"),
        "default_slippage_bps_round_trip": format(settings.default_slippage_bps_round_trip, "f"),
        "default_stop_fraction": format(settings.default_stop_fraction, "f"),
        "max_market_data_age_seconds": settings.max_market_data_age_seconds,
        "live_trading_enabled": settings.live_trading_enabled,
        "transmits_orders": request.app.state.coinbase.live_armed(),
        "phase": 1,
        "min_order_notional_note": (
            "Default minimum is 10 USD, the Hyperliquid minimum order value "
            "supplied for this desk. A CHF notional is checked only with an explicit USD rate."
        ),
    }


@router.get("/api/risk/account", response_model=AccountState)
def get_account(request: Request) -> AccountState:
    return request.app.state.store.load_account(utcnow())


@router.put("/api/risk/account", response_model=AccountState)
def put_account(body: AccountUpdate, request: Request) -> AccountState:
    return request.app.state.store.update_account(body, utcnow())


@router.get("/api/risk/kill-switch", response_model=KillSwitchState)
def get_kill_switch(request: Request) -> KillSwitchState:
    return request.app.state.store.get_kill_switch()


@router.post("/api/risk/kill-switch", response_model=KillSwitchState)
def post_kill_switch(body: KillSwitchUpdate, request: Request) -> KillSwitchState:
    now = utcnow()
    state = request.app.state.store.set_kill_switch(
        engaged=body.engaged,
        reason=body.reason,
        updated_by=body.updated_by,
        now=now,
    )
    cancel = {"attempted": False, "cancelled": [], "reason": "not_engaged"}
    if state.engaged:
        cancel = request.app.state.coinbase.cancel_open_if_armed()
    payload = state.model_dump()
    payload["coinbase_cancel"] = cancel
    event = request.app.state.store.add_event(
        agent="system",
        event_type="kill_switch",
        status="engaged" if state.engaged else "disengaged",
        case_id=None,
        summary=f"kill switch {'engaged' if state.engaged else 'disengaged'}: {state.reason}",
        payload=payload,
        now=now,
    )
    request.app.state.bus.publish(event)
    logger.info(
        "kill switch updated",
        extra={"context": {"engaged": state.engaged, "updated_by": state.updated_by}},
    )
    return state


@router.post("/api/risk/evaluate", response_model=RiskDecision)
def evaluate_risk(body: OrderIntent, request: Request) -> RiskDecision:
    return request.app.state.risk_service.evaluate(body, utcnow())


@router.get("/api/risk/decisions")
def list_decisions(request: Request, limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return {"decisions": request.app.state.store.list_risk_decisions(limit)}


@router.get("/api/journal")
def list_journal(request: Request, limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return {"entries": request.app.state.store.list_journal(limit)}


@router.get("/api/journal/{journal_id}")
def get_journal(journal_id: int, request: Request) -> dict:
    return request.app.state.store.get_journal(journal_id)


@router.post("/api/desk/run", response_model=DeskRunResult)
def run_desk(body: DeskIdea, request: Request) -> DeskRunResult:
    return request.app.state.orchestrator.run(body, utcnow())


@router.post("/api/approvals")
def create_approval(body: ApprovalCreate, request: Request) -> dict:
    created = request.app.state.store.create_approval(
        client_order_id=body.client_order_id.strip(),
        note=body.note,
        now=utcnow(),
    )
    logger.info(
        "human approval recorded",
        extra={"context": {"client_order_id": body.client_order_id.strip(), "approval_present": True}},
    )
    return created


@router.get("/api/execution/attempts")
def list_attempts(request: Request, limit: int = Query(default=50, ge=1, le=200)) -> dict:
    return {"attempts": request.app.state.store.list_attempts(limit)}
