"""Load Coinbase CDP credentials from the environment or a JSON key file.

The private key is never logged, returned from an API, or written to the journal.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import SecretStr

from hypergrok.config import Settings


class CoinbaseCredentials:
    def __init__(self, key_name: str, private_key: str) -> None:
        self.key_name = key_name
        self._private_key = private_key

    @property
    def private_key(self) -> str:
        return self._private_key

    def __repr__(self) -> str:
        return "CoinbaseCredentials(configured=True)"

    def __str__(self) -> str:
        return "CoinbaseCredentials(configured=True)"


def _secret(value: SecretStr | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, SecretStr):
        return value.get_secret_value().strip()
    return str(value).strip()


def load_credentials(settings: Settings) -> CoinbaseCredentials | None:
    path = (settings.coinbase_api_key_file or "").strip()
    if path:
        return _from_file(path)
    name = (settings.coinbase_api_key_name or "").strip()
    private_key = _secret(settings.coinbase_api_private_key)
    if name and private_key:
        return CoinbaseCredentials(name, private_key)
    return None


def _from_file(path: str) -> CoinbaseCredentials | None:
    file_path = Path(path)
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    name = str(payload.get("name") or payload.get("id") or "").strip()
    private_key = str(payload.get("privateKey") or payload.get("private_key") or "").strip()
    if not name or not private_key:
        return None
    return CoinbaseCredentials(name, private_key)
