"""Per-request ``AsyncSession`` — the ONLY way route code gets a DB handle.

Usage in a business router (always under ``/v1`` — ADR-0001)::

    from typing import Annotated

    from fastapi import APIRouter, Depends
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db import get_session

    router = APIRouter(prefix="/widgets", tags=["widgets"])
    DbSession = Annotated[AsyncSession, Depends(get_session)]

    @router.get("")
    async def list_widgets(session: DbSession) -> list[dict]:
        result = await session.execute(select(Widget))
        ...

Tests override it with ``app.dependency_overrides[get_session] = fake_session``
so unit tests never need a database (``.claude/rules/40-testing.md``).

No module-level sessions: a session is request-scoped state and must never be
shared across requests or tasks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.engine import get_engine

_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the lazy engine (built on first use, no connect)."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(),
            # Objects stay usable after commit without an implicit refresh
            # round-trip — the standard setting for async sessions.
            expire_on_commit=False,
        )
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield one ``AsyncSession`` per request and close it after."""
    async with get_sessionmaker()() as session:
        yield session


def _reset_for_tests() -> None:
    """TEST-ONLY: drop the cached factory so a reset engine is picked up."""
    global _sessionmaker
    _sessionmaker = None
