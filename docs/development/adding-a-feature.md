# Adding a feature

An end-to-end walkthrough: adding a hypothetical **`projects`** resource across both services.
It exists to show _where things go_ and _which helpers are mandatory_ — the snippets are
illustrative skeletons, not copy-paste production code.

The finished surface:

```
browser ──▶ web BFF  GET /api/v1/projects
                └──▶ api        GET /v1/projects        (FastAPI, owns the resource + database)
```

The hop carries the same `x-trace-id`. The browser never talks to the `api` directly.

> The repo ships a `feature-scaffold` skill (and the `/scaffold-feature` command) that
> generates this structure in one pass. This document stands alone — read it either to write
> the code yourself, or to know what the scaffold produced and why.

---

## Before you start

Decide what the feature needs. In this walkthrough the `api` owns `projects` (it owns the
database — SQLAlchemy 2 async + Alembic, [ADR-0004](../adr/0004-sqlalchemy-async-alembic-db-layer.md))
and `web` is a pass-through BFF. Not every feature needs both layers: a BFF route with no new
backend endpoint, or a backend endpoint with no UI, are both normal. Do not add a hop — or a
table — you do not need.

Two things are true of every layer below:

- **The endpoint is versioned.** `/v1` is mandatory on all business endpoints
  ([ADR-0001](../adr/0001-api-versioning.md)); only `/ping`, `/info`, `/health` are exempt.
  An unversioned business endpoint is a blocking review failure.
- **Outbound HTTP goes through the traced wrapper**, and logging goes through the structured
  logger. Bare `fetch` / `httpx` and `console.log` / `print()` are forbidden in committed
  code.

---

## 1. `apps/api` — the model, the router, the session

### Model — 2.0-style, registered for Alembic

Models live one module per aggregate under `app/models/`, subclass `app.db.Base`, and use
`Mapped[]` annotations with `mapped_column(...)`. The declarative base carries a constraint
naming convention, so do not hand-name indexes or constraints.

```python
# apps/api/app/models/project.py
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
```

```python
# apps/api/app/models/__init__.py — import it so it registers on Base.metadata
from app.models.project import Project  # noqa: F401

__all__ = ["Project"]
```

That import is load-bearing: Alembic autogenerate only sees models that are imported when
`alembic/env.py` runs (`env.py` does `import app.models`).

### Router — `v1`, and a session via `Depends(get_session)`

Business routers live in `app/routers/<feature>.py` and attach to the mandatory `v1_router`
([`app/routers/v1.py`](../../apps/api/app/routers/v1.py), `prefix="/v1"`). Never add a
business route to `app/routes.py` — that router is the operational exemption (`/ping`,
`/health`, `/info`) and stays mounted at the root.

The **only** way a route gets a database handle is the `get_session` dependency — one
`AsyncSession` per request, closed afterwards. No module-level sessions, no sync engine.

```python
# apps/api/app/routers/projects.py
"""Business endpoints for projects (served under /v1)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.logging_config import get_logger
from app.models import Project
from app.tracing import get_trace_id, traced_client

router = APIRouter(prefix="/projects", tags=["projects"])
_log = get_logger("app.routers.projects")

DbSession = Annotated[AsyncSession, Depends(get_session)]


@router.get("")
async def list_projects(session: DbSession) -> dict[str, object]:
    """List projects — the session is request-scoped, injected, and closed for you."""
    result = await session.execute(select(Project).order_by(Project.created_at))
    projects = [{"id": str(p.id), "name": p.name} for p in result.scalars()]
    _log.info("projects listed", count=len(projects))
    return {"service": "api", "projects": projects, "trace_id": get_trace_id()}


@router.get("/{project_id}")
async def get_project(project_id: UUID, session: DbSession) -> dict[str, object]:
    project = await session.get(Project, project_id)
    if project is None:
        # HTTPException, never a bare exception out of a route.
        raise HTTPException(status_code=404, detail=f"project {project_id} not found")
    return {"service": "api", "project": {"id": str(project.id), "name": project.name},
            "trace_id": get_trace_id()}


@router.get("/external")
async def external() -> dict[str, object]:
    """Example outbound hop — traced_client is the ONLY sanctioned client."""
    async with traced_client(timeout=5.0) as client:  # forwards x-trace-id
        res = await client.get("https://example.invalid/data")
    return {"service": "api", "upstream_status": res.status_code, "trace_id": get_trace_id()}
```

Attach it to the versioned router:

```python
# apps/api/app/routers/v1.py
from app.routers import projects

v1_router = APIRouter(prefix=API_V1_PREFIX)
v1_router.include_router(projects.router)   # -> GET /v1/projects, /v1/projects/{id}
```

Notes:

- `get_trace_id()` reads the `contextvars`-backed request scope set by `TraceMiddleware`.
- `get_logger(...)` is structlog — lines carry
  `timestamp/level/service/origin/env/trace_id/message` automatically.
- Query with ORM constructs (`select`, `insert`, …) or `text()` **with bound parameters**;
  never interpolate user input into SQL
  ([`.claude/rules/50-security.md`](../../.claude/rules/50-security.md)).
- Type-hint everything and start each module with `from __future__ import annotations`.
- Give every outbound call a timeout; never an unbounded wait.
- Nothing here connects to the database at import or startup — the engine is lazy, and the
  first query opens the first connection
  ([`.claude/rules/25-sqlalchemy.md`](../../.claude/rules/25-sqlalchemy.md)).

### Migration — generate, review offline, apply by hand

The model exists in code; the table does not exist until a migration is applied. With the
**dev Azure SQL database** reachable in `DATABASE_URL` (URL from Key Vault, your IP on the
firewall allowlist — there is no local database):

```bash
uv run --directory apps/api alembic revision --autogenerate -m "add projects"
uv run --directory apps/api alembic upgrade head --sql      # review the SQL — no DB needed
```

Review the generated file in `alembic/versions/` — it must carry both `upgrade()` and a real
`downgrade()`. **Applying it (`alembic upgrade head`) is a deliberate, confirmed human step**;
the project and its agents never run it ([data.md](../architecture/data.md) → _Migrations are a
deliberate, confirmed step_). Until it is applied, the route above returns a database error on
the first query — which is the correct signal, not something to paper over with a lazy
`create_all()`.

Verify: `curl http://localhost:8000/v1/projects` returns 200 (against a migrated database) and
`curl http://localhost:8000/projects` returns **404**.

---

## 2. `apps/web` — the BFF route handler

Next has no global versioning primitive — routing is folder-based, so **the folder is the
enforcement**. Business handlers live at `src/app/api/v1/<feature>/route.ts` and call the
matching `/v1` upstream.

```
apps/web/src/app/api/v1/projects/route.ts   ->   GET /api/v1/projects
```

```ts
// apps/web/src/app/api/v1/projects/route.ts
import { log } from '@/lib/logger';
import { fetchUpstream, withBff } from '@/lib/trace';

export const dynamic = 'force-dynamic';

export async function GET(req: Request): Promise<Response> {
  return withBff(req, async ({ traceId }) => {
    const base = process.env.API_BASE_URL ?? 'http://localhost:8000';
    const url = `${base}/v1/projects`;

    log('info', 'bff inbound', { route: '/api/v1/projects' });

    try {
      log('info', 'bff upstream call', { upstream: url, target: 'api' });
      const res = await fetchUpstream(url, traceId);
      const data = await res.json();
      log('info', 'bff upstream ok', { upstream: url, status: res.status });
      return Response.json(data, { status: res.status });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'upstream error';
      log('error', 'bff upstream failed', { upstream: url, error: message });
      return Response.json(
        { error: 'upstream_unreachable', target: 'api', trace_id: traceId },
        { status: 502 },
      );
    }
  });
}
```

What each piece is doing, and why it is not optional:

- **`withBff`** adopts a valid inbound `x-trace-id` (or mints a `0eb0…` one), runs the handler
  inside the `AsyncLocalStorage` scope, **echoes the header on the response**, and records the
  request-duration metric. If your route sits under a dynamic segment, pass the bounded
  pattern — `withBff(req, handler, { routeClass: '/api/v1/projects/[id]' })` — so metric
  cardinality stays bounded.
- **`fetchUpstream`** is the only sanctioned HTTP client in `web`. It forwards `x-trace-id`,
  records the hop-duration metric and the upstream-failure counter; the W3C `traceparent`
  header and the dependency span come from the undici instrumentation below it.
- **The `502` path is required.** On upstream failure return a JSON body that **includes
  `trace_id`**, so the UI degrades gracefully and a user can quote one id in a bug report.
- **Nothing server-side leaks to the client.** `API_BASE_URL` is server-only env. **Never**
  `NEXT_PUBLIC_*` for a service URL or a secret.

If the feature has UI, keep it a React Server Component by default and add `'use client'`
only where you genuinely need state, effects, refs, or browser APIs — and remember that
client components may only call **same-origin** Next routes.

---

## 3. Environment variables

If the feature introduces a new variable:

1. Add it with a **placeholder value and an explanatory comment** to every `.env.example`
   that needs it — [`.env.example`](../../.env.example) (root, if Compose must pass it
   through), plus `apps/web/.env.example` and/or `apps/api/.env.example`.
2. If containers need it, add it to the relevant service in
   [`docker-compose.yml`](../../docker-compose.yml) (with a `${VAR:-default}` substitution).
3. Add a row to the [_Environment variables_](../../README.md#environment-variables) table in
   the root README and to [`docs/reference/environment-variables.md`](../reference/environment-variables.md).
4. Never commit a real secret. Real values come from Azure Key Vault in deployed environments.

The walkthrough above needs no new variables: `API_BASE_URL` and `DATABASE_URL` already
exist.

---

## 4. Tests

Each layer is tested in its own service's stack, offline, with upstreams mocked and **no
database**. Full conventions: [testing guide](testing.md).

| Layer      | Framework                       | Where the file goes                     |
| ---------- | ------------------------------- | --------------------------------------- |
| `apps/web` | Vitest (node env)               | `src/app/api/v1/projects/route.test.ts` |
| `apps/api` | pytest + Starlette `TestClient` | `tests/test_projects.py`                |

### Two invariants every suite asserts

1. **The trace contract** — a valid inbound `x-trace-id` is **adopted** and **echoed**; an
   absent or invalid one is **regenerated** with that service's origin (`web=0eb0`,
   `api=0c70`) and matches `^[0-9a-f]{32}$`. For a new outbound call, assert the traced
   helper **forwarded** the id.
2. **Fail-safe observability** — with no `APPLICATIONINSIGHTS_CONNECTION_STRING` the service
   still boots and `/health` reports `"observability": "disabled"`.

### `apps/web` — Vitest

```ts
// apps/web/src/app/api/v1/projects/route.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { GET } from '@/app/api/v1/projects/route';
import { TRACE_HEADER } from '@/lib/trace';

describe('GET /api/v1/projects', () => {
  beforeEach(() => {
    process.env.API_BASE_URL = 'http://api:8000';
  });
  afterEach(() => vi.restoreAllMocks());

  it('calls the versioned upstream, forwards and echoes x-trace-id', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ projects: [] }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );

    const res = await GET(new Request('http://web/api/v1/projects'));

    expect(res.status).toBe(200);
    expect(spy.mock.calls[0][0]).toBe('http://api:8000/v1/projects');
    const traceId = res.headers.get(TRACE_HEADER)!;
    expect(traceId).toMatch(/^0eb0[0-9a-f]{28}$/);
    expect(new Headers(spy.mock.calls[0][1]?.headers).get(TRACE_HEADER)).toBe(traceId);
  });

  it('returns a graceful 502 with a trace_id when the upstream is unreachable', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('ECONNREFUSED'));
    const res = await GET(new Request('http://web/api/v1/projects'));
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body).toMatchObject({ error: 'upstream_unreachable', target: 'api' });
    expect(body.trace_id).toMatch(/^0eb0[0-9a-f]{28}$/);
  });
});
```

### `apps/api` — pytest, with the session dependency overridden

A route that depends on `get_session` is tested **without a database**: override the
dependency with a fake session through `app.dependency_overrides`, and make an accidental
real connection fail loudly by monkeypatching `pyodbc.connect` — the call aioodbc runs in its
thread pool (the pattern in `tests/test_db_session.py`).

```python
# apps/api/tests/test_projects.py
from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pyodbc
import pytest
from fastapi.testclient import TestClient

from app.db import get_session
from app.main import app

ORIGIN_RE = re.compile(r"^0c70[0-9a-f]{28}$")


@pytest.fixture(autouse=True)
def no_real_database(monkeypatch: pytest.MonkeyPatch) -> None:
    def _refuse(*_: Any, **__: Any) -> None:
        raise AssertionError("pyodbc.connect must never be called from a unit test")

    monkeypatch.setattr(pyodbc, "connect", _refuse)


@pytest.fixture
def client() -> AsyncIterator[TestClient]:
    async def fake_session() -> AsyncIterator[Any]:
        session = MagicMock()
        result = MagicMock()
        result.scalars.return_value = []            # no rows
        session.execute = AsyncMock(return_value=result)
        yield session

    app.dependency_overrides[get_session] = fake_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_list_mints_origin_trace_id_and_echoes_header(client: TestClient) -> None:
    res = client.get("/v1/projects")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "api"
    assert body["projects"] == []
    assert ORIGIN_RE.match(body["trace_id"])
    assert res.headers["x-trace-id"] == body["trace_id"]


def test_list_adopts_valid_inbound_trace_id(client: TestClient) -> None:
    tid = "0eb00" + "a" * 27
    res = client.get("/v1/projects", headers={"x-trace-id": tid})
    assert res.json()["trace_id"] == tid


def test_list_is_not_served_unversioned(client: TestClient) -> None:
    assert client.get("/projects").status_code == 404
```

A real-database integration tier would be **opt-in** (gated on a reachable `DATABASE_URL`,
skipped otherwise) — none exists in the template today.

Run everything: `make test` (or `make test-cov` for the CI-equivalent coverage run).

---

## 5. Docs to update

In the **same change**, not later:

- [`README.md`](../../README.md) — if the HTTP surface, a command, a port, or an env var
  changed.
- The relevant `.env.example` files — every new variable, with a comment.
- The per-app docs (`apps/<svc>/CLAUDE.md`) — if the layout, conventions, or gotchas changed.
- `docs/reference/http-api.md` — the endpoint reference, when the surface changes.
- [`docs/architecture/data.md`](../architecture/data.md) — if the feature changes how the data
  layer is shaped (not for adding an ordinary model).
- [`docs/adr/`](../adr/README.md) — only if the feature involved a decision that qualifies
  (see [workflow → ADR process](workflow.md#adr-process)).
- The service's `CHANGELOG.md`, if one exists.

---

## Checklist

- [ ] Endpoint is under **`/v1`** in every service that serves it (and 404s unversioned).
- [ ] FastAPI: router in `app/routers/<feature>.py`, attached to `v1_router`; nothing business
      added to `routes.py`; `HTTPException`, not bare exceptions.
- [ ] Model: 2.0-style `Mapped[]` class subclassing `app.db.Base`, imported in
      `app/models/__init__.py`; DB access only via `Depends(get_session)`; no connect at
      import/startup; no sync engine or module-level session.
- [ ] Migration: `alembic revision --autogenerate` reviewed (both `upgrade()` and
      `downgrade()`), offline `--sql` output checked; **applied by a human, not by this change**.
- [ ] BFF: handler at `src/app/api/v1/<feature>/route.ts`, wrapped in `withBff`, calling the
      matching `/v1` upstream via `fetchUpstream`, returning `502` **with `trace_id`** on
      failure.
- [ ] Every outbound call uses `fetchUpstream` / `traced_client` — no bare `fetch` or `httpx`,
      and every call has a timeout.
- [ ] All logging through the pino logger / structlog `get_logger` — no `console.log`, no
      `print()`; no PII in log fields or span/metric attributes.
- [ ] No service URL or secret exposed to the client; no `NEXT_PUBLIC_*` for either.
- [ ] New env vars documented in every relevant `.env.example` (+ compose + README table).
- [ ] Tests written for each layer touched, covering **happy and error paths**, plus the trace
      contract and the fail-safe observability invariant; no test touches a database.
      `make test` passes.
- [ ] Docs updated in the same change.
- [ ] Service version bumped per [SemVer](workflow.md#versioning) (MINOR for a new endpoint).
- [ ] Code review done; security review done (this change touches the BFF boundary, external
      HTTP, and the database layer, so it qualifies).
