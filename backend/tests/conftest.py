"""Shared fixtures. Market snapshots are injected; tests do not call the network."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from hypergrok.config import Settings  # noqa: E402
from hypergrok.main import create_app  # noqa: E402
from tests.support import fresh_snapshot, fitting_idea, make_settings, sample_order  # noqa: E402

__all__ = ["fresh_snapshot", "fitting_idea", "make_settings", "sample_order"]


@pytest.fixture(autouse=True)
def _clear_desk_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("HYPERGROK_") or key == "LIVE_TRADING_ENABLED":
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
