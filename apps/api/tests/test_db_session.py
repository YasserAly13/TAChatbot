"""``get_session`` yields one ``AsyncSession`` bound to the lazy engine, closes it
afterwards, never connects unless a query runs, and is overridable via
``app.dependency_overrides`` so route tests need no database.
"""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import pyodbc
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.engine as engine_mod
import app.db.session as session_mod
from app.db import get_session, get_sessionmaker

TEST_URL = (
    "mssql+aioodbc://u:p@db.invalid:1433/app"
    "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
)


@pytest.fixture(autouse=True)
def _reset_db_singletons(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    engine_mod._reset_for_tests()
    session_mod._reset_for_tests()
    yield
    engine_mod._reset_for_tests()
    session_mod._reset_for_tests()


@pytest.fixture()
def no_connect(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, ...]]:
    attempts: list[tuple[Any, ...]] = []

    def fake_connect(*args: Any, **kwargs: Any) -> None:
        attempts.append((args, kwargs))
        raise AssertionError("pyodbc.connect must never be called by the baseline")

    monkeypatch.setattr(pyodbc, "connect", fake_connect)
    return attempts


def test_get_session_yields_session_bound_to_engine_and_closes_it(
    monkeypatch: pytest.MonkeyPatch, no_connect: list[tuple[Any, ...]]
) -> None:
    closed: list[AsyncSession] = []
    original_close = AsyncSession.close

    async def spy_close(self: AsyncSession) -> None:
        closed.append(self)
        await original_close(self)

    monkeypatch.setattr(AsyncSession, "close", spy_close)

    async def run() -> AsyncSession:
        agen = get_session()
        session = await agen.__anext__()
        assert isinstance(session, AsyncSession)
        assert session.bind is engine_mod.get_engine()
        await agen.aclose()  # dependency teardown -> `async with` exit -> close()
        return session

    session = asyncio.run(run())
    assert closed == [session]
    assert no_connect == []


def test_sessionmaker_is_cached_and_bound_to_the_singleton_engine(
    no_connect: list[tuple[Any, ...]],
) -> None:
    factory = get_sessionmaker()
    assert factory is get_sessionmaker()
    assert factory.kw["bind"] is engine_mod.get_engine()
    assert factory.kw["expire_on_commit"] is False
    assert no_connect == []


def test_route_with_session_dependency_does_not_connect_without_a_query(
    no_connect: list[tuple[Any, ...]],
) -> None:
    app = FastAPI()

    @app.get("/v1/things")
    async def things(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> dict[str, bool]:
        return {"has_session": isinstance(session, AsyncSession)}

    res = TestClient(app).get("/v1/things")
    assert res.status_code == 200
    assert res.json() == {"has_session": True}
    assert no_connect == []


def test_dependency_can_be_overridden_for_tests(no_connect: list[tuple[Any, ...]]) -> None:
    app = FastAPI()

    @app.get("/v1/things")
    async def things(session: Annotated[object, Depends(get_session)]) -> dict[str, str]:
        return {"session": str(session)}

    async def fake_session():
        yield "fake-session"

    app.dependency_overrides[get_session] = fake_session
    res = TestClient(app).get("/v1/things")
    assert res.status_code == 200
    assert res.json() == {"session": "fake-session"}
    assert no_connect == []
