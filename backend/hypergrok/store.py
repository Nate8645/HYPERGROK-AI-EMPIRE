"""Persistence for the paper desk. Balances here are local SQLite state, not an exchange."""

from __future__ import annotations

import secrets
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session, sessionmaker

from hypergrok.clock import ensure_utc, isoformat, utcnow
from hypergrok.config import Settings
from hypergrok.domain import AccountState, AccountUpdate, KillSwitchState
from hypergrok.errors import DeskError
from hypergrok.logging_config import redact
from hypergrok.models import (
    AgentMessageRow,
    BlackboardRow,
    CandleCacheRow,
    DecisionLogRow,
    AgentEventRow,
    ApprovalRow,
    AuditLogRow,
    ClientOrderRow,
    DispatchClaimRow,
    ExecutionAttemptRow,
    JournalRow,
    KillSwitchRow,
    PaperAccountRow,
    RiskDecisionRow,
    RiskGrantRow,
)
from hypergrok.money import format_decimal
from hypergrok.serialize import to_jsonable


class DeskStore:
    def __init__(self, session_factory: sessionmaker) -> None:
        self._session_factory = session_factory

    def _session(self) -> Session:
        return self._session_factory()

    def ping(self) -> bool:
        session = self._session()
        try:
            session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
        finally:
            session.close()

    def seed(self, settings: Settings, now: datetime | None = None) -> None:
        moment = now or utcnow()
        today = ensure_utc(moment).date().isoformat()
        session = self._session()
        try:
            if session.get(KillSwitchRow, 1) is None:
                session.add(
                    KillSwitchRow(
                        id=1,
                        engaged=False,
                        reason="",
                        updated_at=isoformat(moment),
                        updated_by="system",
                    )
                )
            if session.get(PaperAccountRow, 1) is None:
                capital = format_decimal(settings.starting_capital)
                session.add(
                    PaperAccountRow(
                        id=1,
                        currency=settings.account_currency,
                        equity=capital,
                        start_of_day_equity=capital,
                        realized_pnl_today="0",
                        open_position_count=0,
                        entries_today=0,
                        trading_day=today,
                        updated_at=isoformat(moment),
                    )
                )
            session.commit()
        finally:
            session.close()

    def load_account(self, now: datetime) -> AccountState:
        session = self._session()
        try:
            row = self._account_row(session, now)
            session.commit()
            return self._account_state(row)
        finally:
            session.close()

    def update_account(self, patch: AccountUpdate, now: datetime) -> AccountState:
        session = self._session()
        try:
            row = self._account_row(session, now)
            if patch.currency is not None:
                row.currency = patch.currency
            if patch.equity is not None:
                if patch.equity <= 0:
                    raise DeskError("invalid_account", "equity must be positive", 422)
                row.equity = format_decimal(patch.equity)
            if patch.start_of_day_equity is not None:
                if patch.start_of_day_equity <= 0:
                    raise DeskError("invalid_account", "start_of_day_equity must be positive", 422)
                row.start_of_day_equity = format_decimal(patch.start_of_day_equity)
            if patch.realized_pnl_today is not None:
                row.realized_pnl_today = format_decimal(patch.realized_pnl_today)
            if patch.open_position_count is not None:
                row.open_position_count = patch.open_position_count
            if patch.entries_today is not None:
                row.entries_today = patch.entries_today
            row.trading_day = ensure_utc(now).date().isoformat()
            row.updated_at = isoformat(now)
            session.commit()
            return self._account_state(row)
        finally:
            session.close()

    def record_paper_entry(self, now: datetime) -> AccountState:
        session = self._session()
        try:
            row = self._account_row(session, now)
            row.open_position_count += 1
            row.entries_today += 1
            row.updated_at = isoformat(now)
            session.commit()
            return self._account_state(row)
        finally:
            session.close()

    def get_kill_switch(self) -> KillSwitchState:
        session = self._session()
        try:
            row = session.get(KillSwitchRow, 1)
            if row is None:
                return KillSwitchState(
                    engaged=True,
                    reason="kill switch row is missing; failing closed",
                    updated_at="",
                    updated_by="system",
                )
            return self._kill_state(row)
        finally:
            session.close()

    def set_kill_switch(
        self,
        *,
        engaged: bool,
        reason: str,
        updated_by: str,
        now: datetime,
    ) -> KillSwitchState:
        session = self._session()
        try:
            row = session.get(KillSwitchRow, 1)
            if row is None:
                row = KillSwitchRow(id=1, engaged=engaged, reason=reason, updated_at=isoformat(now), updated_by=updated_by)
                session.add(row)
            else:
                row.engaged = engaged
                row.reason = reason
                row.updated_by = updated_by
                row.updated_at = isoformat(now)
            session.commit()
            return self._kill_state(row)
        finally:
            session.close()

    def client_order_exists(self, session: Session, client_order_id: str) -> bool:
        return session.get(ClientOrderRow, client_order_id) is not None

    def insert_client_order(
        self,
        session: Session,
        *,
        client_order_id: str,
        status: str,
        now: datetime,
    ) -> None:
        session.add(
            ClientOrderRow(
                client_order_id=client_order_id,
                first_seen_at=isoformat(now),
                last_status=status,
            )
        )

    def insert_risk_decision(
        self,
        session: Session,
        *,
        case_id: str | None,
        client_order_id: str,
        status: str,
        reasons: list[str],
        payload: dict,
        now: datetime,
    ) -> None:
        session.add(
            RiskDecisionRow(
                created_at=isoformat(now),
                case_id=case_id,
                client_order_id=client_order_id,
                status=status,
                reasons_json=reasons,
                payload_json=payload,
            )
        )

    def list_risk_decisions(self, limit: int = 50) -> list[dict]:
        session = self._session()
        try:
            rows = session.scalars(select(RiskDecisionRow).order_by(RiskDecisionRow.id.desc()).limit(limit)).all()
            return [
                {
                    "id": row.id,
                    "created_at": row.created_at,
                    "case_id": row.case_id,
                    "client_order_id": row.client_order_id,
                    "status": row.status,
                    "reasons": row.reasons_json,
                    "decision": row.payload_json,
                }
                for row in rows
            ]
        finally:
            session.close()

    def insert_event(
        self,
        session: Session,
        *,
        agent: str,
        event_type: str,
        status: str,
        case_id: str | None,
        summary: str,
        payload: dict,
        now: datetime,
    ) -> dict:
        safe_payload = redact(to_jsonable(payload))
        created = isoformat(now)
        session.add(
            AgentEventRow(
                created_at=created,
                agent=agent,
                event_type=event_type,
                status=status,
                case_id=case_id,
                summary=summary,
                payload_json=safe_payload,
            )
        )
        return {
            "type": event_type,
            "agent": agent,
            "status": status,
            "case_id": case_id,
            "summary": summary,
            "at": created,
            "mode": "rule_based" if agent != "system" else "system",
            "payload": safe_payload,
        }

    def add_event(
        self,
        *,
        agent: str,
        event_type: str,
        status: str,
        case_id: str | None,
        summary: str,
        payload: dict,
        now: datetime,
    ) -> dict:
        session = self._session()
        try:
            event = self.insert_event(
                session,
                agent=agent,
                event_type=event_type,
                status=status,
                case_id=case_id,
                summary=summary,
                payload=payload,
                now=now,
            )
            session.commit()
            return event
        finally:
            session.close()

    def events_for_case(self, case_id: str) -> list[dict]:
        session = self._session()
        try:
            rows = session.scalars(
                select(AgentEventRow).where(AgentEventRow.case_id == case_id).order_by(AgentEventRow.id)
            ).all()
            return [
                {
                    "agent": row.agent,
                    "status": row.status,
                    "summary": row.summary,
                    "at": row.created_at,
                }
                for row in rows
            ]
        finally:
            session.close()

    def latest_events_by_agent(self, agents: list[str]) -> dict[str, dict | None]:
        session = self._session()
        try:
            found: dict[str, dict | None] = {}
            for agent in agents:
                row = session.scalars(
                    select(AgentEventRow)
                    .where(AgentEventRow.agent == agent)
                    .order_by(AgentEventRow.id.desc())
                    .limit(1)
                ).first()
                if row is None:
                    found[agent] = None
                else:
                    found[agent] = {
                        "status": row.status,
                        "case_id": row.case_id,
                        "summary": row.summary,
                        "at": row.created_at,
                        "event_type": row.event_type,
                    }
            return found
        finally:
            session.close()

    def add_journal(
        self,
        *,
        case_id: str,
        symbol: str,
        venue: str,
        outcome: str,
        summary: str,
        payload: dict,
        now: datetime,
    ) -> int:
        session = self._session()
        try:
            row = JournalRow(
                created_at=isoformat(now),
                case_id=case_id,
                symbol=symbol,
                venue=venue,
                outcome=outcome,
                summary=summary,
                payload_json=redact(to_jsonable(payload)),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return int(row.id)
        finally:
            session.close()

    def list_journal(self, limit: int = 50) -> list[dict]:
        session = self._session()
        try:
            rows = session.scalars(select(JournalRow).order_by(JournalRow.id.desc()).limit(limit)).all()
            return [self._journal_dict(row) for row in rows]
        finally:
            session.close()

    def get_journal(self, journal_id: int) -> dict:
        session = self._session()
        try:
            row = session.get(JournalRow, journal_id)
            if row is None:
                raise DeskError("not_found", "journal entry not found", 404)
            return self._journal_dict(row)
        finally:
            session.close()

    def create_approval(
        self,
        *,
        client_order_id: str,
        note: str,
        now: datetime,
        order_hash: str = "",
        expires_at: datetime | None = None,
        created_by: str = "",
    ) -> dict:
        token = secrets.token_urlsafe(32)
        session = self._session()
        try:
            session.add(
                ApprovalRow(
                    token=token,
                    client_order_id=client_order_id,
                    note=note[:500],
                    created_at=isoformat(now),
                    used_at=None,
                    order_hash=order_hash,
                    expires_at="" if expires_at is None else isoformat(expires_at),
                    created_by=created_by[:80],
                )
            )
            session.commit()
            self.append_audit(
                actor=created_by or "unknown",
                role="operator",
                action="approval_created",
                path="/api/approvals",
                outcome="allowed",
                detail=client_order_id,
                now=now,
            )
            return {
                "client_order_id": client_order_id,
                "token": token,
                "created_at": isoformat(now),
                "expires_at": "" if expires_at is None else isoformat(expires_at),
                "order_hash": order_hash,
                "note": note[:500],
            }
        finally:
            session.close()

    def ids_for_risk_recheck(self, client_order_id: str, case_id: str | None) -> set[str]:
        """Ids already used. The in-flight case is not treated as its own duplicate."""

        session = self._session()
        try:
            ids = {row.client_order_id for row in session.scalars(select(ClientOrderRow))}
            if not case_id:
                return ids
            rows = session.scalars(
                select(RiskDecisionRow).where(RiskDecisionRow.client_order_id == client_order_id)
            ).all()
            if rows and all(row.case_id == case_id for row in rows):
                ids.discard(client_order_id)
            return ids
        finally:
            session.close()

    def mark_approval_used(self, token: str, now: datetime) -> bool:
        """Consume a token once. A second caller in another process gets False."""
        session = self._session()
        try:
            result = session.execute(
                update(ApprovalRow)
                .where(ApprovalRow.token == token, ApprovalRow.used_at.is_(None))
                .values(used_at=isoformat(now))
            )
            session.commit()
            consumed = int(result.rowcount or 0) == 1
            if consumed:
                self.append_audit(
                    actor="gate",
                    role="operator",
                    action="approval_consumed",
                    path="/api/coinbase/orders",
                    outcome="allowed",
                    detail="single_use",
                    now=now,
                )
            return consumed
        finally:
            session.close()

    def get_approval(self, token: str) -> dict | None:
        session = self._session()
        try:
            row = session.get(ApprovalRow, token)
            if row is None:
                return None
            return {
                "token": row.token,
                "client_order_id": row.client_order_id,
                "used_at": row.used_at,
                "order_hash": row.order_hash,
                "expires_at": row.expires_at,
            }
        finally:
            session.close()

    def add_attempt(
        self,
        *,
        case_id: str | None,
        client_order_id: str,
        mode: str,
        status: str,
        reason: str,
        transmitted: bool,
        payload: dict,
        now: datetime,
        venue: str | None = None,
    ) -> int:
        if transmitted and venue != "coinbase":
            raise DeskError("transmission_blocked", "phase 1 cannot record a transmitted order", 500)
        session = self._session()
        try:
            row = ExecutionAttemptRow(
                created_at=isoformat(now),
                case_id=case_id,
                client_order_id=client_order_id,
                mode=mode,
                status=status,
                reason=reason,
                transmitted=bool(transmitted) if venue == "coinbase" else False,
                payload_json=redact(to_jsonable(payload)),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return int(row.id)
        finally:
            session.close()

    def put_blackboard(self, key: str, payload: dict, source: str, now: datetime) -> None:
        session = self._session()
        try:
            row = session.get(BlackboardRow, key)
            if row is None:
                session.add(BlackboardRow(key=key, updated_at=isoformat(now), source=source, payload_json=redact(to_jsonable(payload))))
            else:
                row.updated_at = isoformat(now)
                row.source = source
                row.payload_json = redact(to_jsonable(payload))
            session.commit()
        finally:
            session.close()

    def add_agent_message(self, *, case_id: str, from_agent: str, to_agent: str, schema_name: str, body: dict, now: datetime) -> int:
        session = self._session()
        try:
            row = AgentMessageRow(
                created_at=isoformat(now),
                case_id=case_id,
                from_agent=from_agent,
                to_agent=to_agent,
                schema_name=schema_name,
                body_json=redact(to_jsonable(body)),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return int(row.id)
        finally:
            session.close()

    def add_decision_log(self, *, case_id: str | None, stage: str, decision: str, reasons: list[str], now: datetime) -> int:
        session = self._session()
        try:
            row = DecisionLogRow(
                created_at=isoformat(now),
                case_id=case_id,
                stage=stage,
                decision=decision,
                reasons_json=reasons,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return int(row.id)
        finally:
            session.close()

    def cache_candles(self, *, product_id: str, granularity: str, candles: list, source: str, now: datetime) -> None:
        session = self._session()
        try:
            session.add(
                CandleCacheRow(
                    product_id=product_id,
                    granularity=granularity,
                    fetched_at=isoformat(now),
                    source=source,
                    payload_json=candles,
                )
            )
            session.commit()
        finally:
            session.close()

    def mark_order_dispatched(self, client_order_id: str, now: datetime) -> None:
        """Persist a live place attempt before the network call returns.

        A later process treats this id as already sent and reconciles it.
        """
        self.add_attempt(
            case_id=None,
            client_order_id=client_order_id,
            mode="live",
            status="dispatch_started",
            reason="outcome_unknown_until_reconciled",
            transmitted=False,
            payload={"client_order_id": client_order_id},
            now=now,
            venue="coinbase",
        )

    def dispatched_client_order_ids(self) -> set[str]:
        session = self._session()
        try:
            rows = session.scalars(
                select(ExecutionAttemptRow.client_order_id).where(ExecutionAttemptRow.status == "dispatch_started")
            ).all()
            return set(rows)
        finally:
            session.close()

    def insert_grant(
        self,
        *,
        decision_id: str,
        order_hash: str,
        client_order_id: str,
        case_id: str,
        now: datetime,
        expires_at: datetime,
    ) -> None:
        session = self._session()
        try:
            session.add(
                RiskGrantRow(
                    decision_id=decision_id,
                    order_hash=order_hash,
                    client_order_id=client_order_id,
                    case_id=case_id,
                    created_at=isoformat(now),
                    expires_at=isoformat(expires_at),
                )
            )
            session.commit()
        finally:
            session.close()

    def find_grant(self, client_order_id: str, order_hash: str, now: datetime) -> dict | None:
        session = self._session()
        try:
            rows = session.scalars(
                select(RiskGrantRow)
                .where(RiskGrantRow.client_order_id == client_order_id, RiskGrantRow.order_hash == order_hash)
                .order_by(RiskGrantRow.created_at.desc())
            ).all()
            current = ensure_utc(now).isoformat()
            for row in rows:
                if row.expires_at > current:
                    return {
                        "decision_id": row.decision_id,
                        "order_hash": row.order_hash,
                        "case_id": row.case_id,
                        "expires_at": row.expires_at,
                    }
            return None
        finally:
            session.close()

    def claim_dispatch(self, client_order_id: str, now: datetime) -> bool:
        from sqlalchemy.exc import IntegrityError

        session = self._session()
        try:
            session.add(
                DispatchClaimRow(
                    client_order_id=client_order_id,
                    claimed_at=isoformat(now),
                    state="claimed",
                )
            )
            session.commit()
            return True
        except IntegrityError:
            session.rollback()
            return False
        finally:
            session.close()

    def append_audit(
        self,
        *,
        actor: str,
        role: str,
        action: str,
        path: str,
        outcome: str,
        detail: str,
        now: datetime,
    ) -> None:
        session = self._session()
        try:
            session.add(
                AuditLogRow(
                    created_at=isoformat(now),
                    actor=actor[:80],
                    role=role[:40],
                    action=action[:80],
                    path=path[:200],
                    outcome=outcome[:40],
                    detail=detail[:300],
                )
            )
            session.commit()
        finally:
            session.close()

    def list_audit(self, limit: int = 50) -> list[dict]:
        session = self._session()
        try:
            rows = session.scalars(select(AuditLogRow).order_by(AuditLogRow.id.desc()).limit(limit)).all()
            return [
                {
                    "id": row.id,
                    "created_at": row.created_at,
                    "actor": row.actor,
                    "role": row.role,
                    "action": row.action,
                    "path": row.path,
                    "outcome": row.outcome,
                    "detail": row.detail,
                }
                for row in rows
            ]
        finally:
            session.close()

    def list_attempts(self, limit: int = 50) -> list[dict]:
        session = self._session()
        try:
            rows = session.scalars(
                select(ExecutionAttemptRow).order_by(ExecutionAttemptRow.id.desc()).limit(limit)
            ).all()
            return [
                {
                    "id": row.id,
                    "created_at": row.created_at,
                    "case_id": row.case_id,
                    "client_order_id": row.client_order_id,
                    "mode": row.mode,
                    "status": row.status,
                    "reason": row.reason,
                    "transmitted": row.transmitted,
                    "payload": row.payload_json,
                }
                for row in rows
            ]
        finally:
            session.close()

    def _account_row(self, session: Session, now: datetime) -> PaperAccountRow:
        row = session.get(PaperAccountRow, 1)
        if row is None:
            raise DeskError("account_missing", "paper account is not seeded", 500)
        today = ensure_utc(now).date().isoformat()
        if row.trading_day != today:
            row.trading_day = today
            row.start_of_day_equity = row.equity
            row.realized_pnl_today = "0"
            row.entries_today = 0
            row.updated_at = isoformat(now)
        return row

    @staticmethod
    def _account_state(row: PaperAccountRow) -> AccountState:
        return AccountState(
            currency=row.currency,
            equity=Decimal(row.equity),
            start_of_day_equity=Decimal(row.start_of_day_equity),
            realized_pnl_today=Decimal(row.realized_pnl_today),
            open_position_count=row.open_position_count,
            entries_today=row.entries_today,
            trading_day=row.trading_day,
        )

    @staticmethod
    def _kill_state(row: KillSwitchRow) -> KillSwitchState:
        return KillSwitchState(
            engaged=bool(row.engaged),
            reason=row.reason,
            updated_at=row.updated_at,
            updated_by=row.updated_by,
        )

    @staticmethod
    def _journal_dict(row: JournalRow) -> dict:
        return {
            "id": row.id,
            "created_at": row.created_at,
            "case_id": row.case_id,
            "symbol": row.symbol,
            "venue": row.venue,
            "outcome": row.outcome,
            "summary": row.summary,
            "payload": row.payload_json,
        }
