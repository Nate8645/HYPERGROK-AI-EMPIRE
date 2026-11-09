"""Session auth. Passwords are checked against a PBKDF2 hash from the environment.

The hash never goes to the browser. A missing hash locks protected routes.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta

from hypergrok.clock import ensure_utc, utcnow
from hypergrok.config import Settings

OPERATOR_PATHS = (
    ("POST", "/api/risk/kill-switch"),
    ("POST", "/api/risk/evaluate"),
    ("POST", "/api/desk/"),
    ("POST", "/api/approvals"),
    ("POST", "/api/coinbase/orders"),
    ("POST", "/api/autonomy/"),
)
VIEWER_PREFIXES = (
    "/api/risk",
    "/api/journal",
    "/api/desk",
    "/api/approvals",
    "/api/execution",
    "/api/agents",
    "/api/autonomy",
    "/api/coinbase/balances",
    "/api/coinbase/portfolios",
    "/api/coinbase/portfolio",
    "/api/coinbase/orders",
    "/api/coinbase/fills",
    "/api/coinbase/fees",
    "/api/coinbase/utilization",
    "/api/coinbase/fx",
    "/api/coinbase/markets",
    "/api/audit",
)
PUBLIC_EXACT = {"/health", "/api/auth/login", "/api/auth/session", "/api/coinbase/status", "/api/coinbase/public-tickers"}


@dataclass
class Session:
    token: str
    username: str
    role: str
    expires_at: datetime


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._hits: dict[str, deque] = defaultdict(deque)
        self._logins: dict[str, deque] = defaultdict(deque)

    def put(self, session: Session) -> None:
        self._sessions[session.token] = session

    def get(self, token: str, now: datetime) -> Session | None:
        session = self._sessions.get(token)
        if session is None:
            return None
        if ensure_utc(session.expires_at) <= ensure_utc(now):
            self._sessions.pop(token, None)
            return None
        return session

    def drop(self, token: str) -> None:
        self._sessions.pop(token, None)

    def allow(self, bucket: dict[str, deque], key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        hits = bucket[key]
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = 200_000) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = stored.split("$", 3)
    except ValueError:
        return False
    if scheme != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(digest.hex(), digest_hex)


def authenticate(settings: Settings, username: str, password: str, now: datetime) -> Session | None:
    if settings.auth_mandate_expires_at is not None and ensure_utc(settings.auth_mandate_expires_at) <= ensure_utc(now):
        return None
    role = None
    stored = ""
    if username == settings.auth_username and settings.auth_password_hash:
        role = "operator"
        stored = settings.auth_password_hash
    elif username == settings.auth_viewer_username and settings.auth_viewer_password_hash:
        role = "viewer"
        stored = settings.auth_viewer_password_hash
    if role is None or not verify_password(password, stored):
        return None
    return Session(
        token=secrets.token_urlsafe(32),
        username=username,
        role=role,
        expires_at=ensure_utc(now) + timedelta(seconds=settings.auth_session_seconds),
    )


def required_role(method: str, path: str) -> str | None:
    if path in PUBLIC_EXACT or path.startswith("/api/auth/"):
        return None
    for verb, prefix in OPERATOR_PATHS:
        if method == verb and path.startswith(prefix):
            return "operator"
    if path.startswith("/ws/") or any(path.startswith(prefix) for prefix in VIEWER_PREFIXES):
        return "viewer"
    return None


def role_allows(actual: str, required: str) -> bool:
    if required == "viewer":
        return actual in {"viewer", "operator"}
    return actual == "operator"


def gate_request(request):
    from fastapi.responses import JSONResponse

    settings: Settings = request.app.state.settings
    sessions: SessionStore = request.app.state.sessions
    key = client_key(request)
    path = request.url.path
    method = request.method
    if path == "/api/auth/login" and method == "POST":
        if not sessions.allow(sessions._logins, key, settings.auth_login_limit_per_minute, 60):
            return _denied(429, "rate_limited", "too many login attempts")
        return None
    if not sessions.allow(sessions._hits, key, settings.auth_rate_limit_per_minute, 60):
        return _denied(429, "rate_limited", "too many requests")
    required = required_role(method, path)
    if required is None:
        return None
    if not settings.auth_password_hash:
        return _denied(401, "auth_not_configured", "set a password hash before using protected routes")
    token = request.cookies.get("hg_session") or _bearer(request)
    session = sessions.get(token or "", utcnow())
    if session is None:
        _audit(request, "anonymous", "none", "denied", "unauthenticated")
        return _denied(401, "unauthenticated", "login is required")
    if not role_allows(session.role, required):
        _audit(request, session.username, session.role, "denied", "wrong_role")
        return _denied(403, "unauthorized", "this role cannot call that route")
    request.state.session = session
    if method in {"POST", "PUT", "DELETE"}:
        _audit(request, session.username, session.role, "allowed", method.lower())
    return None


def _bearer(request) -> str:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


def _denied(status: int, code: str, message: str):
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _audit(request, actor: str, role: str, outcome: str, detail: str) -> None:
    store = getattr(request.app.state, "store", None)
    if store is None:
        return
    store.append_audit(
        actor=actor,
        role=role,
        action=request.method,
        path=request.url.path,
        outcome=outcome,
        detail=detail,
        now=utcnow(),
    )


def client_key(request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:80]
    host = request.client.host if request.client else "local"
    return host
