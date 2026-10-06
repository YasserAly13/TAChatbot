"""Lazy, process-wide ``AsyncEngine`` for the project database (ADR-0008).

LAZY BY CONTRACT: ``create_async_engine`` only builds the engine + pool object; it
does NOT open a connection. The first connection happens on the first query, so
the service boots with the placeholder ``DATABASE_URL`` and no reachable
database. Never ``await conn.execute(...)`` from startup code.

ONE ENGINE PER PROCESS: ``get_engine()`` is a singleton; a second engine would
mean a second connection pool. ``dispose_engine()`` is awaited from the FastAPI
``lifespan`` shutdown (closes every pooled connection) and is idempotent.

ENGINE: Azure SQL Database through the ``mssql+aioodbc`` dialect — aioodbc runs
pyodbc calls in a thread pool on top of Microsoft ODBC Driver 18 (installed in
the runtime image). The URL's query string is forwarded to the ODBC connection
string (``driver``, ``Encrypt``, ``TrustServerCertificate``, ``Authentication``).

DB SPANS: ``opentelemetry-instrumentation-sqlalchemy`` is registered in
``app/observability.py`` WITHOUT an engine, which wraps
``sqlalchemy.ext.asyncio.create_async_engine`` for every engine created
afterwards. That is why this module resolves ``create_async_engine`` through the
module attribute AT CALL TIME instead of importing the name: ``app.db`` is
imported by ``app.main`` before ``init_observability`` runs, and a name bound at
import would be the un-instrumented original.
"""

from __future__ import annotations

from sqlalchemy.ext import asyncio as sa_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import get_settings
from app.logging_config import get_logger

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use (no connect)."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = sa_asyncio.create_async_engine(
            settings.database_url,
            # Validate pooled connections before handing them out — Azure SQL
            # (and its gateway) drops idle connections; a stale one would
            # otherwise surface as a request-time error.
            pool_pre_ping=True,
        )
        # Never log the URL (it carries credentials) — the host is enough.
        get_logger("app.db").info(
            "db engine created (lazy — no connection opened)",
            db_host=_engine.url.host,
            db_driver=_engine.url.drivername,
        )
    return _engine


async def dispose_engine() -> None:
    """Close every pooled connection and drop the singleton. Idempotent."""
    global _engine
    engine, _engine = _engine, None
    if engine is None:
        return
    await engine.dispose()
    get_logger("app.db").info("db engine disposed")


def _reset_for_tests() -> None:
    """TEST-ONLY: forget the singleton so the next ``get_engine()`` rebuilds it."""
    global _engine
    _engine = None
