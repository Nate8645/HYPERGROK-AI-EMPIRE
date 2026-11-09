"""SQLite engine setup. In-memory databases share one connection for tests."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from hypergrok.models import Base


def prepare_sqlite_path(url: str) -> str:
    if not url.startswith("sqlite:///") or url in {"sqlite://", "sqlite:///:memory:"}:
        return url
    if ":memory:" in url:
        return url
    raw = url[len("sqlite:///") :]
    if not raw or raw == ":memory:":
        return url
    path = Path(raw)
    if str(path.parent) not in {"", "."}:
        path.parent.mkdir(parents=True, exist_ok=True)
    return url


def make_engine(url: str) -> Engine:
    prepared = prepare_sqlite_path(url)
    kwargs: dict = {}
    if prepared.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if prepared in {"sqlite://", "sqlite:///:memory:"}:
            kwargs["poolclass"] = StaticPool
    return create_engine(prepared, **kwargs)


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
