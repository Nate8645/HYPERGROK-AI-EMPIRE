from decimal import Decimal

import pytest
from pydantic import ValidationError

from hypergrok.config import Settings


def test_phase1_defaults_match_the_desk_brief() -> None:
    settings = Settings(_env_file=None)
    assert settings.account_currency == "CHF"
    assert settings.starting_capital == Decimal("20")
    assert settings.max_leverage == Decimal("1")
    assert settings.max_planned_risk_fraction == Decimal("0.01")
    assert settings.max_daily_loss_fraction == Decimal("0.03")
    assert settings.max_open_positions == 1
    assert settings.max_new_entries_per_day == 2
    assert settings.hyperliquid_reserve_fraction == Decimal("0.20")
    assert settings.min_order_notional == Decimal("10")
    assert settings.min_order_notional_currency == "USD"
    assert settings.live_trading_enabled is False
    assert settings.default_fee_bps_round_trip > 0
    assert settings.default_slippage_bps_round_trip > 0


def test_live_trading_env_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")
    assert Settings(_env_file=None).live_trading_enabled is True
    monkeypatch.delenv("LIVE_TRADING_ENABLED")
    monkeypatch.setenv("HYPERGROK_LIVE_TRADING_ENABLED", "false")
    assert Settings(_env_file=None).live_trading_enabled is False


def test_leverage_above_one_is_rejected_at_startup() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, max_leverage=Decimal("2"))
