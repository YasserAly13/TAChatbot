"""READ-ONLY access to an external database the project does not own (ADR-0008).

Second lazy ``AsyncEngine``, separate from the project database in ``engine.py``:

- URL from ``EXTERNAL_DATABASE_URL`` (Key Vault → env). **No placeholder**: when the
  variable is unset, ``get_external_engine()`` raises a clear ``RuntimeError`` —
  a project that has no external source simply never imports this module.
- **No Alembic, no models, no writes.** The real control is the database role the
  owner provides (SELECT-only grants). Defence in depth: a ``before_cursor_execute``
  listener refuses any statement that is not a ``SELECT``/``WITH`` before it
  reaches the driver, so a bug or an over-eager AI tool cannot mutate data even if
  the role were mis-provisioned. Recommend ``ApplicationIntent=ReadOnly`` in the
  URL when the source has read-scale replicas.
- Same laziness, pooling, span and never-log-the-URL rules as the project engine.

Usage in a ``/v1`` router or an AI tool::

    from app.db import get_external_session
    ExternalSession = Annotated[AsyncSession, Depends(get_external_session)]
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext import asyncio as sa_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.config import get_settings
from app.logging_config import get_logger

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None

# Statement kinds the external engine may execute. Everything else is refused.
READ_ONLY_KEYWORDS = frozenset({"SELECT", "WITH"})


class ExternalDatabaseNotConfigured(RuntimeError):
    """``EXTERNAL_DATABASE_URL`` is unset — the external engine cannot be built."""


class ReadOnlyViolation(PermissionError):
    """A non-SELECT statement was sent to the read-only external engine."""


def _reject_writes(
    _conn: Any,
    _cursor: Any,
    statement: str,
    _parameters: Any,
    _context: Any,
    _executemany: bool,
) -> None:
    """SQLAlchemy ``before_cursor_execute`` hook: allow SELECT/WITH only."""
    first = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
    if first not in READ_ONLY_KEYWORDS:
        raise ReadOnlyViolation(
            f"external database is read-only; refused statement starting with {first!r}"
        )


def get_external_engine() -> AsyncEngine:
    """Return the read-only external engine, creating it on first use (no connect)."""
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.has_external_database:
            raise ExternalDatabaseNotConfigured(
                "EXTERNAL_DATABASE_URL is not set — the external read-only database is not "
                "configured for this deployment"
            )
        engine = sa_asyncio.create_async_engine(settings.external_database_url, pool_pre_ping=True)
        event.listen(engine.sync_engine, "before_cursor_execute", _reject_writes)
        _engine = engine
        get_logger("app.db.external").info(
            "external db engine created (lazy, read-only — no connection opened)",
            db_host=engine.url.host,
            db_driver=engine.url.drivername,
        )
    return _engine


def get_external_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the lazy external engine (built on first use)."""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_external_engine(), expire_on_commit=False)
    return _sessionmaker


async def get_external_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one read-only ``AsyncSession`` per request, closed after."""
    async with get_external_sessionmaker()() as session:
        yield session


async def dispose_external_engine() -> None:
    """Close every pooled connection and drop the singleton. Idempotent."""
    global _engine, _sessionmaker
    engine, _engine, _sessionmaker = _engine, None, None
    if engine is None:
        return
    await engine.dispose()
    get_logger("app.db.external").info("external db engine disposed")


def _reset_for_tests() -> None:
    """TEST-ONLY: forget the singletons so the next call rebuilds them."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
