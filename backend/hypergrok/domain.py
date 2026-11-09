"""Shared desk schemas.

Money fields are decimal strings on the wire. Floats are rejected so a JSON
number cannot silently change a risk figure.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from hypergrok.clock import ensure_utc
from hypergrok.money import Dec


class CheckResult(BaseModel):
    rule: str
    passed: bool
    detail: str


class RiskDecision(BaseModel):
    engine: Literal["risk_engine"] = "risk_engine"
    status: Literal["PASS", "REJECT"]
    reasons: list[str]
    checks: list[CheckResult]
    summary: str
    client_order_id: str
    notional: Dec
    equity: Dec
    planned_loss: Dec | None = None
    planned_loss_limit: Dec | None = None
    price_loss: Dec | None = None
    fee_loss: Dec | None = None
    slippage_loss: Dec | None = None
    assumed_fee_bps: Dec | None = None
    assumed_slippage_bps: Dec | None = None
    reserve_required: Dec | None = None
    free_collateral_after: Dec | None = None


class AccountState(BaseModel):
    currency: str
    equity: Dec
    start_of_day_equity: Dec
    realized_pnl_today: Dec
    open_position_count: int
    entries_today: int
    trading_day: str


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str | None = None
    equity: Dec | None = None
    start_of_day_equity: Dec | None = None
    realized_pnl_today: Dec | None = None
    open_position_count: int | None = Field(default=None, ge=0)
    entries_today: int | None = Field(default=None, ge=0)

    @field_validator("currency")
    @classmethod
    def _currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3,8}", cleaned):
            raise ValueError("currency must be 3-8 letters")
        return cleaned


class KillSwitchState(BaseModel):
    engaged: bool
    reason: str
    updated_at: str
    updated_by: str


class KillSwitchUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engaged: bool
    reason: str = Field(default="", max_length=500)
    updated_by: str = Field(default="human", max_length=80)


class OrderIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_order_id: str = Field(min_length=1, max_length=128)
    venue: str
    symbol: str
    side: Literal["buy", "sell"]
    order_kind: Literal["entry", "reduce"] = "entry"
    notional: Dec
    notional_currency: str
    leverage: Dec
    entry_price: Dec
    stop_price: Dec | None = None
    market_data_time: datetime | None = None
    fee_bps_round_trip: Dec | None = None
    slippage_bps_round_trip: Dec | None = None
    usd_per_notional_currency: Dec | None = None
    fx_source: str | None = None
    fx_as_of: datetime | None = None

    @field_validator("client_order_id")
    @classmethod
    def _client_order_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("client_order_id is required")
        return cleaned

    @field_validator("venue")
    @classmethod
    def _venue(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,20}(?:-[A-Z0-9]{1,20})?", cleaned):
            raise ValueError("symbol must be an alphanumeric product id")
        return cleaned

    @field_validator("notional_currency")
    @classmethod
    def _notional_currency(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not re.fullmatch(r"[A-Z]{3,8}", cleaned):
            raise ValueError("notional_currency must be 3-8 letters")
        return cleaned


class MarketSnapshot(BaseModel):
    """A labelled observation. `source` and `fetched_at` are required.

    The desk never fills these in with a guessed price.
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1, max_length=120)
    symbol: str
    fetched_at: datetime
    raw_type: str = Field(min_length=1, max_length=40)
    mid: Dec | None = None
    bid: Dec | None = None
    ask: Dec | None = None
    bid_size: Dec | None = None
    ask_size: Dec | None = None
    exchange_time: datetime | None = None

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,20}(?:-[A-Z0-9]{1,20})?", cleaned):
            raise ValueError("symbol must be an alphanumeric product id")
        return cleaned

    def observed_at(self) -> datetime:
        fetched = ensure_utc(self.fetched_at)
        if self.exchange_time is None:
            return fetched
        return min(fetched, ensure_utc(self.exchange_time))


class ResearchInput(BaseModel):
    """Caller-supplied observations only. Free text is stored, not scored."""

    model_config = ConfigDict(extra="forbid")

    trend: Literal["up", "down", "flat", "unknown"] = "unknown"
    funding_bps: Dec | None = None
    observed_spread_bps: Dec | None = None
    notes: str = Field(default="", max_length=2000)


class DeskIdea(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    venue: str = "hyperliquid"
    side: Literal["buy", "sell"] | None = None
    thesis: str = Field(min_length=1, max_length=2000)
    size_mode: Literal["risk_limited", "all_in"] = "risk_limited"
    notional: Dec | None = None
    stop_fraction: Dec | None = None
    client_order_id: str | None = None
    market_snapshot: MarketSnapshot | None = None
    research: ResearchInput | None = None
    usd_per_notional_currency: Dec | None = None
    fx_source: str | None = None
    fx_as_of: datetime | None = None
    request_live: bool = False
    approval_token: str | None = None
    order_type: Literal["market", "limit"] | None = None
    post_only: bool = False
    base_size: Dec | None = None
    limit_price: Dec | None = None
    load_coinbase_book: bool = False
    product_type: str | None = None
    quote_increment: Dec | None = None
    fee_bps_round_trip: Dec | None = None
    slippage_bps_round_trip: Dec | None = None

    @field_validator("symbol")
    @classmethod
    def _symbol(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,20}(?:-[A-Z0-9]{1,20})?", cleaned):
            raise ValueError("symbol must be an alphanumeric product id")
        return cleaned

    @field_validator("venue")
    @classmethod
    def _venue(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("client_order_id")
    @classmethod
    def _client_order_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("approval_token")
    @classmethod
    def _approval_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
