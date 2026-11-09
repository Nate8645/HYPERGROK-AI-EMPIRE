"""SQLite tables for events, the journal, risk decisions, and the kill switch."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class AgentEventRow(Base):
    __tablename__ = "agent_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    agent: Mapped[str] = mapped_column(String, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    case_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class JournalRow(Base):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    case_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String, nullable=False)
    venue: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class RiskDecisionRow(Base):
    __tablename__ = "risk_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    case_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    client_order_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    reasons_json: Mapped[list] = mapped_column(JSON, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class KillSwitchRow(Base):
    __tablename__ = "kill_switch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    engaged: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False, default="")
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_by: Mapped[str] = mapped_column(String, nullable=False)


class ClientOrderRow(Base):
    __tablename__ = "client_orders"

    client_order_id: Mapped[str] = mapped_column(String, primary_key=True)
    first_seen_at: Mapped[str] = mapped_column(String, nullable=False)
    last_status: Mapped[str] = mapped_column(String, nullable=False)


class PaperAccountRow(Base):
    __tablename__ = "paper_account"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    currency: Mapped[str] = mapped_column(String, nullable=False)
    equity: Mapped[str] = mapped_column(String, nullable=False)
    start_of_day_equity: Mapped[str] = mapped_column(String, nullable=False)
    realized_pnl_today: Mapped[str] = mapped_column(String, nullable=False)
    open_position_count: Mapped[int] = mapped_column(Integer, nullable=False)
    entries_today: Mapped[int] = mapped_column(Integer, nullable=False)
    trading_day: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


class ApprovalRow(Base):
    __tablename__ = "approval_tokens"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    note: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    used_at: Mapped[str | None] = mapped_column(String, nullable=True)
    order_hash: Mapped[str] = mapped_column(String, nullable=False, default="")
    expires_at: Mapped[str] = mapped_column(String, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String, nullable=False, default="")


class RiskGrantRow(Base):
    __tablename__ = "risk_grants"

    decision_id: Mapped[str] = mapped_column(String, primary_key=True)
    order_hash: Mapped[str] = mapped_column(String, nullable=False, index=True)
    client_order_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    case_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[str] = mapped_column(String, nullable=False)


class DispatchClaimRow(Base):
    __tablename__ = "dispatch_claims"

    client_order_id: Mapped[str] = mapped_column(String, primary_key=True)
    claimed_at: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False)


class BlackboardRow(Base):
    __tablename__ = "blackboard"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class AgentMessageRow(Base):
    __tablename__ = "agent_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    case_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    from_agent: Mapped[str] = mapped_column(String, nullable=False)
    to_agent: Mapped[str] = mapped_column(String, nullable=False)
    schema_name: Mapped[str] = mapped_column(String, nullable=False)
    body_json: Mapped[dict] = mapped_column(JSON, nullable=False)


class DecisionLogRow(Base):
    __tablename__ = "decision_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    case_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    stage: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    reasons_json: Mapped[list] = mapped_column(JSON, nullable=False)


class CandleCacheRow(Base):
    __tablename__ = "candle_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    granularity: Mapped[str] = mapped_column(String, nullable=False)
    fetched_at: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    payload_json: Mapped[list] = mapped_column(JSON, nullable=False)


class AuditLogRow(Base):
    """Append-only. The store exposes insert and list, not update or delete."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    outcome: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str] = mapped_column(String, nullable=False, default="")


class ExecutionAttemptRow(Base):
    __tablename__ = "execution_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    case_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    client_order_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    reason: Mapped[str] = mapped_column(String, nullable=False)
    transmitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
