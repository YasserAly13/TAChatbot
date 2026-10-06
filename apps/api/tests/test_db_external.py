"""The external read-only engine (ADR-0008): lazy, separate from the project
engine, absent unless ``EXTERNAL_DATABASE_URL`` is set, and refuses every
non-SELECT statement before it reaches the driver. Offline: ``pyodbc.connect``
is a fake that fails the test if anything connects.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import pyodbc
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import app.db.engine as engine_mod
import app.db.external as external_mod
from app.db import (
    ExternalDatabaseNotConfigured,
    ReadOnlyViolation,
    dispose_external_engine,
    get_external_engine,
    get_external_session,
    get_external_sessionmaker,
)

EXTERNAL_URL = (
    "mssql+aioodbc://reader:p@warehouse.invalid:1433/dw"
    "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&ApplicationIntent=ReadOnly"
)


@pytest.fixture(autouse=True)
def _reset_singletons():
    external_mod._reset_for_tests()
    engine_mod._reset_for_tests()
    yield
    external_mod._reset_for_tests()
    engine_mod._reset_for_tests()


@pytest.fixture()
def no_connect(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    attempts: list[tuple[Any, ...]] = []

    def fake_connect(*args: Any, **kwargs: Any) -> None:
        attempts.append((args, kwargs))
        raise AssertionError("pyodbc.connect must never be called by the baseline")

    monkeypatch.setattr(pyodbc, "connect", fake_connect)
    return attempts


def test_refuses_to_build_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXTERNAL_DATABASE_URL", raising=False)
    with pytest.raises(ExternalDatabaseNotConfigured):
        get_external_engine()


def test_empty_value_counts_as_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTERNAL_DATABASE_URL", "   ")
    with pytest.raises(ExternalDatabaseNotConfigured):
        get_external_engine()


def test_engine_is_lazy_separate_and_a_singleton(
    monkeypatch: pytest.MonkeyPatch, no_connect: list[tuple[Any, ...]]
) -> None:
    monkeypatch.setenv("EXTERNAL_DATABASE_URL", EXTERNAL_URL)
    engine = get_external_engine()
    assert isinstance(engine, AsyncEngine)
    assert engine is get_external_engine()
    assert engine is not engine_mod.get_engine()  # never the project engine
    assert engine.url.host == "warehouse.invalid"
    assert engine.url.query["ApplicationIntent"] == "ReadOnly"
    assert event.contains(engine.sync_engine, "before_cursor_execute", external_mod._reject_writes)
    assert no_connect == []


@pytest.mark.parametrize(
    "statement",
    ["SELECT 1", "  select * from t", "WITH cte AS (SELECT 1 AS x) SELECT x FROM cte"],
)
def test_read_statements_are_allowed(statement: str) -> None:
    external_mod._reject_writes(None, None, statement, None, None, False)  # must not raise


@pytest.mark.parametrize(
    "statement",
    [
        "INSERT INTO t VALUES (1)",
        "  update t set x = 1",
        "DELETE FROM t",
        "DROP TABLE t",
        "EXEC sp_something",
        "MERGE INTO t USING s ON 1=1 WHEN MATCHED THEN DELETE",
        "",
    ],
)
def test_write_statements_are_refused(statement: str) -> None:
    with pytest.raises(ReadOnlyViolation):
        external_mod._reject_writes(None, None, statement, None, None, False)


def test_session_dependency_yields_session_bound_to_external_engine(
    monkeypatch: pytest.MonkeyPatch, no_connect: list[tuple[Any, ...]]
) -> None:
    monkeypatch.setenv("EXTERNAL_DATABASE_URL", EXTERNAL_URL)

    async def run() -> AsyncSession:
        agen = get_external_session()
        session = await agen.__anext__()
        assert session.bind is get_external_engine()
        await agen.aclose()
        return session

    session = asyncio.run(run())
    assert isinstance(session, AsyncSession)
    assert get_external_sessionmaker() is get_external_sessionmaker()
    assert no_connect == []


def test_route_dependency_is_overridable(no_connect: list[tuple[Any, ...]]) -> None:
    app = FastAPI()

    @app.get("/v1/report")
    async def report(session: Annotated[object, Depends(get_external_session)]) -> dict[str, str]:
        return {"session": str(session)}

    async def fake_session():
        yield "fake-external"

    app.dependency_overrides[get_external_session] = fake_session
    res = TestClient(app).get("/v1/report")
    assert res.status_code == 200
    assert res.json() == {"session": "fake-external"}
    assert no_connect == []


def test_dispose_is_idempotent(
    monkeypatch: pytest.MonkeyPatch, no_connect: list[tuple[Any, ...]]
) -> None:
    monkeypatch.setenv("EXTERNAL_DATABASE_URL", EXTERNAL_URL)
    first = get_external_engine()
    asyncio.run(dispose_external_engine())
    asyncio.run(dispose_external_engine())  # no engine -> no-op
    assert get_external_engine() is not first
    assert no_connect == []
