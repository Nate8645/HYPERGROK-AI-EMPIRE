"""Environment-backed settings.

Limits below are the phase-1 defaults from the desk brief. Leverage is not
a soft default: values other than 1 are rejected at startup.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
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
    coinbase_api_key_name: str = Field(
        default="",
        validation_alias=AliasChoices("COINBASE_API_KEY_NAME", "HYPERGROK_COINBASE_API_KEY_NAME"),
    )
    coinbase_api_private_key: SecretStr = Field(
        default_factory=lambda: SecretStr(""),
        validation_alias=AliasChoices("COINBASE_API_PRIVATE_KEY", "HYPERGROK_COINBASE_API_PRIVATE_KEY"),
    )
    coinbase_api_key_file: str = Field(
        default="",
        validation_alias=AliasChoices("COINBASE_API_KEY_FILE", "HYPERGROK_COINBASE_API_KEY_FILE"),
    )
    coinbase_live_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("COINBASE_LIVE_ENABLED", "HYPERGROK_COINBASE_LIVE_ENABLED"),
    )
    coinbase_product_allowlist: str = Field(
        default="",
        validation_alias=AliasChoices("COINBASE_PRODUCT_ALLOWLIST", "HYPERGROK_COINBASE_PRODUCT_ALLOWLIST"),
    )
    coinbase_max_capital: Decimal = Field(
        default=Decimal("0"),
        validation_alias=AliasChoices("COINBASE_MAX_CAPITAL", "HYPERGROK_COINBASE_MAX_CAPITAL"),
    )
    coinbase_max_capital_currency: str = Field(
        default="",
        validation_alias=AliasChoices(
            "COINBASE_MAX_CAPITAL_CURRENCY",
            "HYPERGROK_COINBASE_MAX_CAPITAL_CURRENCY",
        ),
    )
    fx_usd_per_chf: Decimal | None = Field(
        default=None,
        validation_alias=AliasChoices("HYPERGROK_FX_USD_PER_CHF"),
    )
    fx_as_of: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("HYPERGROK_FX_AS_OF"),
    )
    fx_source: str = Field(
        default="explicit_config",
        validation_alias=AliasChoices("HYPERGROK_FX_SOURCE"),
    )
    max_fx_age_seconds: float = Field(
        default=300.0,
        validation_alias=AliasChoices("HYPERGROK_MAX_FX_AGE_SECONDS"),
    )
    max_product_metadata_age_seconds: float = Field(
        default=300.0,
        validation_alias=AliasChoices("HYPERGROK_MAX_PRODUCT_METADATA_AGE_SECONDS"),
    )
    autonomous_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("HYPERGROK_AUTONOMOUS_ENABLED", "AUTONOMOUS_ENABLED"),
    )
    autonomous_max_loss_per_trade: Decimal | None = Field(
        default=None,
        validation_alias=AliasChoices("HYPERGROK_AUTONOMOUS_MAX_LOSS_PER_TRADE"),
    )
    autonomous_max_loss_per_day: Decimal | None = Field(
        default=None,
        validation_alias=AliasChoices("HYPERGROK_AUTONOMOUS_MAX_LOSS_PER_DAY"),
    )
    autonomous_max_loss_total: Decimal | None = Field(
        default=None,
        validation_alias=AliasChoices("HYPERGROK_AUTONOMOUS_MAX_LOSS_TOTAL"),
    )
    autonomous_expires_at: datetime | None = Field(
        default=None,
        validation_alias=AliasChoices("HYPERGROK_AUTONOMOUS_EXPIRES_AT"),
    )
    autonomous_max_deployed_capital: Decimal | None = Field(
        default=None,
        validation_alias=AliasChoices("HYPERGROK_AUTONOMOUS_MAX_DEPLOYED_CAPITAL"),
    )
    autonomous_allowed_pairs: str = Field(
        default="",
        validation_alias=AliasChoices("HYPERGROK_AUTONOMOUS_ALLOWED_PAIRS"),
    )
    autonomous_max_slippage_bps: Decimal | None = Field(
        default=None,
        validation_alias=AliasChoices("HYPERGROK_AUTONOMOUS_MAX_SLIPPAGE_BPS"),
    )
    autonomous_kill_switch_conditions: str = Field(
        default="",
        validation_alias=AliasChoices("HYPERGROK_AUTONOMOUS_KILL_SWITCH_CONDITIONS"),
    )
    # Ceiling for the capital simulation only. It does not replace the 1% loss rule,
    # and the execution gate does not read it.
    simulation_max_capital_fraction: Decimal = Field(
        default=Decimal("1"),
        validation_alias=AliasChoices("HYPERGROK_SIMULATION_MAX_CAPITAL_FRACTION"),
    )
    auth_username: str = ""
    auth_password_hash: str = ""
    auth_viewer_username: str = ""
    auth_viewer_password_hash: str = ""
    auth_session_seconds: int = 3600
    auth_cookie_secure: bool = False
    auth_mandate_expires_at: datetime | None = None
    auth_rate_limit_per_minute: int = 120
    auth_login_limit_per_minute: int = 8

    def coinbase_products(self) -> frozenset[str]:
        return frozenset(
            part.strip().upper()
            for part in self.coinbase_product_allowlist.split(",")
            if part.strip()
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
        if self.max_fx_age_seconds <= 0:
            raise ValueError("max_fx_age_seconds must be positive")
        if self.max_product_metadata_age_seconds <= 0:
            raise ValueError("max_product_metadata_age_seconds must be positive")
        if self.coinbase_max_capital < 0:
            raise ValueError("coinbase_max_capital cannot be negative")
        if not (Decimal("0") < self.simulation_max_capital_fraction <= Decimal("1")):
            raise ValueError("simulation_max_capital_fraction must be in (0, 1]")
        if self.coinbase_max_capital_currency:
            self.coinbase_max_capital_currency = self.coinbase_max_capital_currency.strip().upper()
        self.account_currency = self.account_currency.strip().upper()
        self.min_order_notional_currency = self.min_order_notional_currency.strip().upper()
        return self
