---
description: FastAPI + uv conventions. Loaded when editing apps/api/**.
paths:
  - 'apps/api/**'
---

# FastAPI conventions (apps/api)

> **Graded autonomy:** these are conventions to apply _within_ an approved plan or roadmap item — not a licence to act outside one. Hard stops (infra apply, migration apply, push, secrets, deletes) always need explicit confirmation — see [`CLAUDE.md`](../../CLAUDE.md) → _Graded autonomy_.

Python 3.14 + FastAPI, managed by **uv**, port 8000, trace origin `0c70`. See
[`apps/api/CLAUDE.md`](../../apps/api/CLAUDE.md).

## Structure (`app/`)

- `main.py` — app factory + module-level `app` (so `uvicorn app.main:app` works). Bootstrap
  order: configure structlog → `init_observability` (fail-safe) → add `TraceMiddleware` →
  include routers (operational `routes.py` at root + `v1_router`).
- `routes.py` — **operational, unversioned** endpoints only (`/ping`, `/health`, `/info`).
- `routers/v1.py` — the **mandatory `/v1` business surface** (`v1_router`, `prefix="/v1"`).
- `errors.py` — the **error contract** (`{error, trace_id}` on every non-2xx; `ApiError` subclasses;
  handlers + `UnhandledErrorMiddleware`). Routes raise `NotFound()` / `Conflict("<code>")` /
  `ApiError("<snake_case>", status_code=…)` — never return ad-hoc error dicts, never put
  exception text in a response. Document per-route errors with `responses={404: {"model": ErrorBody}}`.
- `tracing.py`, `observability.py`, `logging_config.py`, `config.py` — cross-cutting. This
  service **is** the backend contract: the Next.js BFF (`apps/web`) is its only consumer and
  mirrors its `/v1` surface.
- `db/` (`base.py`, `engine.py`, `session.py`) and `models/` — the SQLAlchemy 2 async layer;
  `alembic/` + `alembic.ini` — migrations. Rules in `25-sqlalchemy.md`.

## Database (see `25-sqlalchemy.md` — ADR-0004)

- Lazy `AsyncEngine` singleton (`get_engine()`), never connects at import/startup; disposed in
  the `lifespan` shutdown.
- Routes get a DB handle **only** via `Depends(get_session)` (one `AsyncSession` per request);
  no module-level sessions, no sync engine.
- Alembic is wired but idle: `uv run alembic upgrade head --sql` (offline review, no DB);
  `revision --autogenerate` / `check` need the **dev Azure SQL** database reachable (there is no
  local database); **`upgrade` is the migration pipeline's or a named human's action.**
- The engine is **Azure SQL Database** via `mssql+aioodbc` (ADR-0008); an optional second,
  **read-only** engine (`app/db/external.py`) reaches an external database.

## API versioning (mandatory — see `05-api-versioning.md`)

- Business endpoints MUST be served under `/v1`. Add `app/routers/<feature>.py` with an
  `APIRouter()`, then `v1_router.include_router(<feature>.router)` → `/v1/<feature>`.
- Don't add business routes to `routes.py`; that router is the operational exemption.

## Tracing & logging (non-negotiable)

- Request-scoped trace id via **`contextvars`** — read with `get_trace_id()`. `TraceMiddleware`
  adopts/generates `x-trace-id` and echoes it.
- **Every outbound HTTP call uses `traced_client()`** (`tracing.py`) so `x-trace-id` propagates.
- DB dependency spans come from the explicit SQLAlchemy instrumentation in `observability.py`
  (`_instrument_sqlalchemy`, registered without an engine so both lazy engines are covered —
  ADR-0008); never bind `create_async_engine` by name at import (see `25-sqlalchemy.md`).
- **Log via the structlog logger (`get_logger(...)`)** — never `print()`. Lines carry
  `timestamp/level/service/origin/env/trace_id/message`.

## Dependencies (uv)

- Pin exact versions in `pyproject.toml`; run `uv sync` / `uv run`. Renaming the project name
  requires `uv lock` (the lockfile records it).
- **OTel versions are pinned by the Azure distro:** `azure-monitor-opentelemetry==1.8.8`
  hard-pins `opentelemetry-sdk==1.40` + instrumentation `==0.61b0` + `opentelemetry-api==1.40.0`.
  Don't bump instrumentation packages independently (this includes
  `opentelemetry-instrumentation-sqlalchemy`).
- **DB stack pins:** `sqlalchemy[asyncio]==2.0.54`, `aioodbc==0.5.0`, `pyodbc==5.3.0`,
  `alembic==1.20.0`. pyodbc is compiled and must keep publishing CPython 3.14 wheels (the Docker
  build is wheel-only, `--no-build`) — check PyPI before bumping the interpreter or the driver.
  The runtime image installs Microsoft ODBC Driver 18 (`Dockerfile`); pyodbc imports without it,
  so offline tests need no driver.

## Style

- `ruff` for format + lint (`uv run ruff format app alembic tests && uv run ruff check app alembic tests`).
  Line length 100. `pyproject.toml` pins `known-third-party = ["alembic"]` for isort because the
  migrations dir shares the package name — keep it.
- Type-hint everything; `from __future__ import annotations` at the top of modules.
