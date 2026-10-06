"""Database layer — SQLAlchemy 2 async on Azure SQL via ``mssql+aioodbc`` (ADR-0008).

- ``base.py``     — ``Base`` (2.0-style ``DeclarativeBase``) with an Alembic-friendly
                    constraint naming convention. Models subclass it.
- ``engine.py``   — ``get_engine()`` lazy singleton ``AsyncEngine`` for the PROJECT database
                    (never connects at import or startup) + ``dispose_engine()`` for shutdown.
- ``session.py``  — ``get_session()`` FastAPI dependency yielding one ``AsyncSession`` per
                    request; the ONLY way route code gets a handle on the project database.
- ``external.py`` — ``get_external_engine()`` / ``get_external_session()``: a second, lazy,
                    READ-ONLY engine for an external database (``EXTERNAL_DATABASE_URL``);
                    no Alembic, no models, writes refused before they reach the driver.

Rules: ``.claude/rules/25-sqlalchemy.md``. Databases are Azure SQL and are never local; the
service boots with the placeholder ``DATABASE_URL`` and no reachable database — the first
connection happens on the first query.
"""

from __future__ import annotations

from app.db.base import Base
from app.db.engine import dispose_engine, get_engine
from app.db.external import (
    ExternalDatabaseNotConfigured,
    ReadOnlyViolation,
    dispose_external_engine,
    get_external_engine,
    get_external_session,
    get_external_sessionmaker,
)
from app.db.session import get_session, get_sessionmaker

__all__ = [
    "Base",
    "ExternalDatabaseNotConfigured",
    "ReadOnlyViolation",
    "dispose_engine",
    "dispose_external_engine",
    "get_engine",
    "get_external_engine",
    "get_external_session",
    "get_external_sessionmaker",
    "get_session",
    "get_sessionmaker",
]
