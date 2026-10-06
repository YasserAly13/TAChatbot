# ADR-0004: Database access via SQLAlchemy 2 async + Alembic; DB spans via asyncpg driver instrumentation

|        |                                                                                                                                                                                                                                                                                                                                                       |
| ------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Status | Superseded by [ADR-0008](0008-azure-sql-data-layer.md) for the driver (asyncpg → `mssql+aioodbc` on Azure SQL), the TLS/auth URL syntax, the instrumentation and the DDL guidance. The layer design (lazy async engine, session per request, Alembic with the URL from `DATABASE_URL`, offline tests, no migrations run by the service) still stands. |
| Date   | 2026-09-20                                                                                                                                                                                                                                                                                                                                            |

## Context

ADR-0003 removes the NestJS `api` service, which was the only database owner (Prisma 7 with the
`@prisma/adapter-pg` driver adapter, lazy connect, placeholder schema, no migrations run).
`apps/python` (FastAPI, Python 3.14, uv — renamed `apps/api` by ADR-0005) must take that capability over with parity: an external
Azure Postgres target, a service that boots with a placeholder `DATABASE_URL` and no reachable
database, a migration toolchain that is present but never run automatically, and database
dependency spans in Azure Monitor `AppDependencies`. The Azure Monitor distro
(`azure-monitor-opentelemetry==1.8.8`) hard-pins every `opentelemetry-instrumentation-*` package
to `0.61b0`; its default instrumentation set (verified in `_constants.py`) is `azure_sdk`,
`django`, `fastapi`, `flask`, `psycopg2`, `requests`, `urllib`, `urllib3` — **no asyncpg**, so DB
spans need explicit registration. ADR-0002 chose driver-level over ORM-level instrumentation for
the Node service because ORM instrumentation packages pin their own OTel line and can throw inside
the query path; that reasoning carries over unchanged.

## Decision

We use **SQLAlchemy 2.x with the asyncio extension** (`create_async_engine` + `AsyncSession`,
2.0-style `DeclarativeBase` / `Mapped[]` models) over the **asyncpg** driver
(`postgresql+asyncpg://…?ssl=require`), with **Alembic** (async `env.py`) as the migration tool.
The engine is a **lazy singleton** (`app/db/engine.py`) that never connects at import or startup;
routes get a per-request `AsyncSession` only through the `get_session` dependency. DB dependency
spans come from **`opentelemetry-instrumentation-asyncpg==0.61b0`**, registered in
`init_observability` next to the FastAPI/httpx/system-metrics instrumentors, fail-safe. Alembic is
run by humans: agents may only use offline / `check` / `heads` modes; `alembic upgrade` against a
real database is a confirmed human action. This ADR **supersedes ADR-0002**.

## Consequences

- Good: parity with the Prisma baseline — boots with the placeholder URL, no connection until the
  first query, `engine.dispose()` on shutdown mirrors `$disconnect`.
- Good: the driver instrumentation sits on the distro's own `0.61b0` line (verified on PyPI:
  `opentelemetry-instrumentation-asyncpg 0.61b0` requires `opentelemetry-instrumentation==0.61b0`),
  so no second OTel version line enters the service — the ADR-0002 failure mode is avoided.
- Good: asyncpg 0.31.0 publishes CPython 3.14 wheels for Linux (manylinux/musllinux) and Windows,
  so `uv sync --frozen` stays wheel-only (`--no-build`) in the Dockerfile.
- Good: Alembic offline mode (`alembic upgrade head --sql`) lets migrations be reviewed with no
  database, matching the "never run migrations from an agent" rule.
- Bad: async SQLAlchemy requires `greenlet`; it has 3.14 wheels today but is one more compiled
  dependency to watch on interpreter upgrades.
- Bad: asyncpg does not accept `sslmode` — SQLAlchemy forwards URL query parameters straight to
  `asyncpg.connect()`, which has only an `ssl` keyword, so the URL uses `?ssl=require` (a
  `?sslmode=require` URL fails at connect time). Documented in every `.env.example`.
- Bad: driver-level spans show SQL against asyncpg, not ORM-level semantics (`Model.select`), the
  same trade-off ADR-0002 accepted.
- Bad: runtime proof of a query landing in `AppDependencies` is still pending until a real Azure
  Postgres and App Insights resource exist ([HUMAN], roadmap Phase 6).

## Alternatives considered

- **psycopg 3 (`postgresql+psycopg://`) + `opentelemetry-instrumentation-psycopg`** — kept as the
  documented fallback only. asyncpg was preferred for its native asyncio protocol and its 3.14
  wheels; psycopg 3 is pure-Python by default (`psycopg[binary]` for the C loader) and its OTel
  package goes through the generic dbapi instrumentation.
- **SQLAlchemy sync engine in a threadpool** — rejected: the service is fully async (FastAPI +
  httpx); a sync engine would block the event loop or need `run_in_threadpool` on every query.
- **ORM-level tracing via `opentelemetry-instrumentation-sqlalchemy`** — rejected for the same
  reason ADR-0002 rejected `@prisma/instrumentation`: a second instrumentation surface whose event
  hooks run inside the query path; driver spans already reflect what hits the wire.
- **Keep Prisma via the Prisma Python client** — rejected: the community Python client lags the
  Prisma 7 engine/driver-adapter model and would add a Node-built engine binary to the image.
- **No migration tool (hand-written SQL)** — rejected: Alembic autogenerate + `downgrade()` +
  `check` are the standard toolchain the `migration-author` agent and `write-migration` skill
  target.

## References

- Related ADRs: ADR-0002 (superseded — same rationale, Node/Prisma context), ADR-0003 (why python
  owns the DB)
- Docs: `.claude/rules/25-sqlalchemy.md`; `.claude/rules/60-observability.md` → _Distributed
  traces_; `apps/api/CLAUDE.md` → _Database_; `README.md` → _Database_
- External: SQLAlchemy asyncpg dialect (`create_connect_args` forwards `url.query` to the driver);
  asyncpg `connect()` signature (`ssl=` keyword, `sslmode` DSN-only); Azure Monitor distro
  `_constants.py` `_FULLY_SUPPORTED_INSTRUMENTED_LIBRARIES`
