---
description: SQLAlchemy 2 async + Alembic conventions on Azure SQL. Loaded when editing the api's DB layer, models, or migrations.
paths:
  - 'apps/api/app/db/**'
  - 'apps/api/app/models/**'
  - 'apps/api/alembic/**'
  - 'apps/api/alembic.ini'
---

# SQLAlchemy + Alembic conventions (apps/api)

> **Graded autonomy:** these are conventions to apply _within_ an approved plan or roadmap item — not a licence to act outside one. Hard stops (infra apply, migration apply, push, secrets, deletes) always need explicit confirmation — see [`CLAUDE.md`](../../CLAUDE.md) → _Graded autonomy_.

**SQLAlchemy 2.0.54 (asyncio) + aioodbc 0.5 / pyodbc 5.3 on Microsoft ODBC Driver 18 + Alembic
1.20** against **Azure SQL Database**. **There is no local database, ever**; the project's
database is created by the use-case Bicep deployment first (ADR-0012); **migrations are not run** by this project
(the model set is a placeholder). Decided in
[ADR-0008](../../docs/adr/0008-azure-sql-data-layer.md) (supersedes ADR-0004's driver choices).
See [`apps/api/CLAUDE.md`](../../apps/api/CLAUDE.md) → _Database_.

## The layer (`app/db/`)

- `base.py` — `class Base(DeclarativeBase)` with an explicit **naming convention** on its
  `MetaData` (`ix_`/`uq_`/`ck_`/`fk_`/`pk_`). Every model subclasses it. Never create a second
  `MetaData`.
- `engine.py` — `get_engine()` is a **lazy singleton** built with
  `sa_asyncio.create_async_engine(settings.database_url, pool_pre_ping=True)`. It must **never
  connect at import or startup** — no `await conn.execute` in `lifespan`, no `engine.begin()` in
  module scope. `dispose_engine()` is awaited on shutdown and is idempotent. **Resolve
  `create_async_engine` through the module attribute at call time** (`from sqlalchemy.ext import
asyncio as sa_asyncio`), never `from sqlalchemy.ext.asyncio import create_async_engine` — the
  OTel instrumentor wraps the module attribute after `app.db` is imported.
- `session.py` — `async_sessionmaker(expire_on_commit=False)` + the FastAPI dependency
  `get_session()` yielding one `AsyncSession` per request. **Routes get a DB handle only via
  `Depends(get_session)`.** No module-level sessions, no sessions shared across tasks.
- `external.py` — a **second, read-only** lazy engine for an external database
  (`EXTERNAL_DATABASE_URL`, no placeholder: unset ⇒ `ExternalDatabaseNotConfigured`).
  `get_external_session()` is the dependency; a `before_cursor_execute` listener refuses anything
  that is not `SELECT`/`WITH` (`ReadOnlyViolation`) — defence in depth behind the SELECT-only
  login the owner provides. No Alembic, no models, no writes, ever. AI tools that query external
  data go through it with allow-listed, parameterised queries.

## The URL (`mssql+aioodbc://`)

- Scheme `mssql+aioodbc://user:password@host:1433/database?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no`.
  Query-string keywords are forwarded to the ODBC connection string; `driver` is mandatory,
  `Encrypt=yes` + `TrustServerCertificate=no` are mandatory outside a throw-away dev experiment.
- **Deployed auth is managed identity:** `Authentication=ActiveDirectoryMsi` with the
  user-assigned identity's **client id as the username** — the form `infra/main.bicep` writes to Key Vault
  (`DATABASE-URL`). Pipelines use `Authentication=ActiveDirectoryServicePrincipal`
  (username = SP client id, password = secret). SQL auth exists only when infra enabled it.
- Passwords/secrets with reserved characters are URL-encoded. The URL is **never logged** (log
  `engine.url.host` at most) and **never in `alembic.ini`**.

## Models (`app/models/`)

- **2.0-style only:** `class Widget(Base)`, `__tablename__`, `Mapped[...]` annotations with
  `mapped_column(...)`. No `Column(...)` class attributes, no `declarative_base()`.
- One module per aggregate; **import it in `app/models/__init__.py`** — Alembic autogenerate
  only sees models that are imported when `env.py` runs.
- Explicit `__tablename__` (snake_case, plural). UUID primary keys (`UNIQUEIDENTIFIER` on SQL
  Server via SQLAlchemy's `Uuid`), timestamps with `server_default=func.now()` (renders
  `GETDATE()`/`SYSDATETIME()` per type — prefer `DateTime(timezone=True)`). `CheckConstraint`s
  MUST carry an explicit `name=` (the `ck` template uses `%(constraint_name)s`; SQLAlchemy raises
  at DDL compile otherwise). Other indexes/constraints get names through the convention — don't
  hand-name them unless the convention can't express it.
- SQL Server specifics to remember: identifiers are case-insensitive under the default
  collation; `String` without length becomes `VARCHAR(max)` — give lengths; boolean is `BIT`.

## Alembic (`alembic.ini`, `alembic/`)

- **The URL is never in `alembic.ini`.** `env.py` reads `get_settings().database_url`
  (env `DATABASE_URL`). Committing a URL there is a review-blocking violation.
- `env.py` is the **async template** (`create_async_engine` + `run_sync`); keep
  `target_metadata = Base.metadata` and `compare_type=True`.
- **Offline first:** review SQL with `uv run alembic upgrade head --sql` (no DB needed; renders
  T-SQL with `BEGIN TRANSACTION`/`GO`). `revision --autogenerate` and `check` need the **dev
  Azure SQL** database reachable (firewall allowlist) — there is no local database to point at.
- Every revision ships **`upgrade()` AND a real `downgrade()`**. SQL Server has **no
  `CONCURRENTLY`** and no `NOT VALID`; the concurrency-safe patterns are:
  - index on a populated table → `op.execute("CREATE INDEX … ON … WITH (ONLINE = ON)")`
    (online builds need a tier that supports them — Business Critical / Premium; on General
    Purpose expect a brief lock and schedule it);
  - foreign key on a populated table → `op.execute("ALTER TABLE … WITH NOCHECK ADD CONSTRAINT …")`
    then a separate `ALTER TABLE … WITH CHECK CHECK CONSTRAINT …` step;
  - `NOT NULL` on an existing column → add nullable → backfill in batches → `ALTER COLUMN … NOT NULL`;
  - altering a column's type on a large table → new column → backfill → swap.
    Destructive DDL (drop table/column, type narrowing) needs explicit human confirmation — rule 6.
- **Agents never run `alembic upgrade`** against any database (root `CLAUDE.md` → _What you
  cannot do_). Author with the `write-migration` skill / `migration-author` agent; apply through
  `.github/workflows/migrate.yml` (Environment-gated) or a named human.

## Observability

- DB dependency spans come from **`opentelemetry-instrumentation-sqlalchemy==0.61b0`**, registered
  in `app/observability.py` (`_instrument_sqlalchemy`) **without an engine** so it wraps
  `create_async_engine` and covers both lazy engines. Do **not** pass `engine=` per engine (the
  instrumentor's singleton guard would silently skip the second one) and do not add a
  driver-level package.
- Never log `DATABASE_URL` / `EXTERNAL_DATABASE_URL`; log the host at most.

## Security (see `50-security.md`)

- Parameterised queries only: ORM constructs (`select(...)`, `insert(...)`) or `text()` **with
  bound parameters** (`text("... WHERE id = :id").bindparams(id=...)`). Never f-string/`%`
  interpolate user input into SQL — on both engines.
- The external engine is read-only by construction; never "temporarily" remove the listener.

## Forbidden

- A sync `create_engine` / `Session` anywhere in the service (blocks the event loop).
- Module-level `AsyncSession` objects, or passing a session between requests/tasks.
- `TrustServerCertificate=yes` or `Encrypt=no` in any committed example or deployed URL.
- Binding `create_async_engine` by name at import (breaks span coverage — see above).
- A local database container, connecting at import/startup, a URL in `alembic.ini`, committing
  `.env`, or running `alembic upgrade` from an agent.

## Testing (see `40-testing.md`)

- Unit tests never need a DB: override `get_session` / `get_external_session` via
  `app.dependency_overrides`, and assert **`pyodbc.connect` is never called** for baseline paths
  (`tests/test_db_*.py` show the pattern; aioodbc calls `pyodbc.connect` in its thread pool).
- A real-DB integration tier is **opt-in**: gate it on a reachable `DATABASE_URL` and skip
  otherwise.
