"""Alembic environment — async engine, URL from ``DATABASE_URL`` (ADR-0004).

Adapted from ``alembic init -t async`` (Alembic 1.20):

- The URL is NEVER read from ``alembic.ini``; it comes from
  ``app.config.get_settings().database_url`` (env ``DATABASE_URL``), so the
  service and the migration tool share one source of truth and no credential can
  land in a committed file.
- ``target_metadata = Base.metadata``; importing ``app.models`` registers every
  model on it (autogenerate only sees imported models).
- OFFLINE mode (``alembic upgrade head --sql``) needs no DBAPI connection and no
  reachable database — use it to review the SQL a revision would emit.
- ONLINE mode builds a throw-away ``AsyncEngine`` with ``NullPool`` and runs the
  migrations inside ``run_sync``. Running it against a real database is a
  confirmed human action, never an agent's (``.claude/rules/25-sqlalchemy.md``).
- Logging: ``fileConfig`` wires the CLI's plain-text stderr logging from
  ``alembic.ini``. The service's structlog JSON pipeline is not involved — this
  module only ever runs inside the ``alembic`` command.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

import app.models  # noqa: F401  — registers models on Base.metadata
from app.config import get_settings
from app.db.base import Base

# Alembic Config object: access to alembic.ini values.
config = context.config

# CLI logging (alembic.ini [loggers]/[handlers]/[formatters]).
if config.config_file_name is not None:
    # Keep loggers the service already configured alive (only relevant when env.py
    # runs inside a process that also imported the app, e.g. tests).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    """The one place the URL is resolved — env-driven, never hard-coded."""
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Emit the migration SQL to stdout without connecting (``--sql``)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Connect with a throw-away engine (NullPool) and run the migrations."""
    connectable = create_async_engine(_database_url(), poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
