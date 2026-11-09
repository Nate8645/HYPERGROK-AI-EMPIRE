"""JSON logs with a redaction pass for secret-looking fields.

Phase 1 does not handle private keys. The redactor is here so a later
change cannot casually log one.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from hypergrok.clock import isoformat, utcnow

SENSITIVE_KEYS = {
    "private_key",
    "privatekey",
    "seed",
    "seed_phrase",
    "mnemonic",
    "api_key",
    "apikey",
    "secret",
    "authorization",
    "approval_token",
    "password",
    "signature",
    "token",
}


def _key_is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return lowered in SENSITIVE_KEYS or lowered.endswith("_token") or lowered.endswith("_secret")


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if _key_is_sensitive(str(key)):
                cleaned[str(key)] = "[redacted]"
            else:
                cleaned[str(key)] = redact(item)
        return cleaned
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": isoformat(utcnow()),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload["context"] = redact(context)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str, json_logs: bool = True) -> None:
    logger = logging.getLogger("hypergrok")
    logger.handlers.clear()
    logger.setLevel(level.upper())
    handler = logging.StreamHandler()
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
