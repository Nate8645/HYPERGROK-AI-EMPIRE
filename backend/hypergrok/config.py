"""Environment-backed settings.

Limits below are the phase-1 defaults from the desk brief. Leverage is not
a soft default: values other than 1 are rejected at startup.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Self

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HYPERGROK_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "HYPERGROK AI EMPIRE"
    environment: str = "development"
    log_level: str = "INFO"
    log_json: bool = True
    database_url: str = "sqlite:///./data/hypergrok.db"

    account_currency: str = "CHF"
    starting_capital: Decimal = Decimal("20")
    max_leverage: Decimal = Decimal("1")
    max_planned_risk_fraction: Decimal = Decimal("0.01")
    max_daily_loss_fraction: Decimal = Decimal("0.03")
    max_open_positions: int = 1
    max_new_entries_per_day: int = 2
    hyperliquid_reserve_fraction: Decimal = Decimal("0.20")
    min_order_notional: Decimal = Decimal("10")
    min_order_notional_currency: str = "USD"
    default_fee_bps_round_trip: Decimal = Decimal("10")
    default_slippage_bps_round_trip: Decimal = Decimal("10")
    default_stop_fraction: Decimal = Decimal("0.005")
    max_market_data_age_seconds: float = 5.0
    wide_spread_bps: Decimal = Decimal("50")
    imbalance_threshold: Decimal = Decimal("0.20")

    hyperliquid_info_url: str = "https://api.hyperliquid.xyz/info"
    hyperliquid_info_timeout_seconds: float = 10.0

    live_trading_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "LIVE_TRADING_ENABLED",
            "HYPERGROK_LIVE_TRADING_ENABLED",
        ),
    )

    @model_validator(mode="after")
    def _enforce_bounds(self) -> Self:
        if self.max_leverage != Decimal("1"):
            raise ValueError("max_leverage must be exactly 1; leverage is not allowed")
        if self.starting_capital <= 0:
            raise ValueError("starting_capital must be positive")
        if not (Decimal("0") < self.max_planned_risk_fraction <= Decimal("1")):
            raise ValueError("max_planned_risk_fraction must be in (0, 1]")
        if not (Decimal("0") < self.max_daily_loss_fraction <= Decimal("1")):
            raise ValueError("max_daily_loss_fraction must be in (0, 1]")
        if self.max_open_positions < 1:
            raise ValueError("max_open_positions must be at least 1")
        if self.max_new_entries_per_day < 1:
            raise ValueError("max_new_entries_per_day must be at least 1")
        if not (Decimal("0") <= self.hyperliquid_reserve_fraction < Decimal("1")):
            raise ValueError("hyperliquid_reserve_fraction must be in [0, 1)")
        if self.min_order_notional <= 0:
            raise ValueError("min_order_notional must be positive")
        if self.default_fee_bps_round_trip < 0 or self.default_slippage_bps_round_trip < 0:
            raise ValueError("fee and slippage basis points cannot be negative")
        if not (Decimal("0") < self.default_stop_fraction < Decimal("1")):
            raise ValueError("default_stop_fraction must be between 0 and 1")
        if self.max_market_data_age_seconds <= 0:
            raise ValueError("max_market_data_age_seconds must be positive")
        if self.hyperliquid_info_timeout_seconds <= 0:
            raise ValueError("hyperliquid_info_timeout_seconds must be positive")
        self.account_currency = self.account_currency.strip().upper()
        self.min_order_notional_currency = self.min_order_notional_currency.strip().upper()
        return self
