"""The async engine is LAZY (never connects on import, creation or dispose), a
process-wide singleton, disposable/idempotent, and torn down by the lifespan.

Offline by contract (.claude/rules/40-testing.md): ``pyodbc.connect`` — the
DBAPI call aioodbc runs in its thread pool — is replaced with a fake that fails
the test if anything ever tries to connect.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pyodbc
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

import app.db.engine as engine_mod
import app.db.session as session_mod

TEST_URL = (
    "mssql+aioodbc://u:p@db.invalid:1433/app"
    "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
)


@pytest.fixture(autouse=True)
def _reset_db_singletons():
    engine_mod._reset_for_tests()
    session_mod._reset_for_tests()
    yield
    engine_mod._reset_for_tests()
    session_mod._reset_for_tests()


@pytest.fixture()
def no_connect(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    """Fail loudly if the driver is ever asked to open a connection."""
    attempts: list[tuple[Any, ...]] = []

    def fake_connect(*args: Any, **kwargs: Any) -> None:
        attempts.append((args, kwargs))
        raise AssertionError("pyodbc.connect must never be called by the baseline")

    monkeypatch.setattr(pyodbc, "connect", fake_connect)
    return attempts


def test_engine_is_created_lazily_without_connecting(
    monkeypatch: pytest.MonkeyPatch, no_connect: list[tuple[Any, ...]]
) -> None:
    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    engine = engine_mod.get_engine()
    assert isinstance(engine, AsyncEngine)
    assert engine.url.drivername == "mssql+aioodbc"
    assert engine.url.host == "db.invalid"
    assert engine.url.database == "app"
    # ODBC keywords ride in the query string and reach the driver unchanged.
    assert engine.url.query["Encrypt"] == "yes"
    assert engine.url.query["TrustServerCertificate"] == "no"
    assert "18" in engine.url.query["driver"]
    assert no_connect == []


def test_engine_is_a_singleton(
    monkeypatch: pytest.MonkeyPatch, no_connect: list[tuple[Any, ...]]
) -> None:
    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    assert engine_mod.get_engine() is engine_mod.get_engine()
    assert no_connect == []


def test_engine_uses_placeholder_url_when_env_missing(
    monkeypatch: pytest.MonkeyPatch, no_connect: list[tuple[Any, ...]]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    engine = engine_mod.get_engine()
    assert engine.url.drivername == "mssql+aioodbc"
    assert engine.url.host == "your-server.database.windows.net"
    assert engine.url.port == 1433
    # The placeholder still enforces validated TLS.
    assert engine.url.query["Encrypt"] == "yes"
    assert engine.url.query["TrustServerCertificate"] == "no"
    # Credentials never leak through the rendered URL.
    assert "PASSWORD" not in engine.url.render_as_string(hide_password=True)
    assert no_connect == []


def test_dispose_is_idempotent_and_resets_the_singleton(
    monkeypatch: pytest.MonkeyPatch, no_connect: list[tuple[Any, ...]]
) -> None:
    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    first = engine_mod.get_engine()

    asyncio.run(engine_mod.dispose_engine())
    asyncio.run(engine_mod.dispose_engine())  # second call: no engine -> no-op, no error

    second = engine_mod.get_engine()
    assert second is not first
    assert no_connect == []


def test_dispose_without_engine_is_a_noop() -> None:
    asyncio.run(engine_mod.dispose_engine())  # nothing created yet -> must not raise


def test_engine_resolves_create_async_engine_at_call_time(
    monkeypatch: pytest.MonkeyPatch, no_connect: list[tuple[Any, ...]]
) -> None:
    """ADR-0008: the SQLAlchemy instrumentor wraps ``create_async_engine`` on the
    module AFTER app.db was imported; the factory must pick the wrapped one up."""
    from sqlalchemy.ext import asyncio as sa_asyncio

    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    original = sa_asyncio.create_async_engine
    seen: list[str] = []

    def wrapped(url: str, **kwargs: Any) -> AsyncEngine:
        seen.append(str(url))
        return original(url, **kwargs)

    monkeypatch.setattr(sa_asyncio, "create_async_engine", wrapped)
    engine_mod.get_engine()
    assert len(seen) == 1
    assert no_connect == []


def test_lifespan_disposes_engine_on_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.main as main_mod

    calls: list[bool] = []

    async def fake_dispose() -> None:
        calls.append(True)

    monkeypatch.setattr(main_mod, "dispose_engine", fake_dispose)
    with TestClient(main_mod.app):  # runs the lifespan startup + shutdown
        pass
    assert calls == [True]
