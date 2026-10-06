---
description: Global architecture rules for the AI Accelerator. Always loaded.
paths:
  - '**/*'
---

# Architecture rules (global)

> **Graded autonomy:** these are conventions to apply _within_ an approved plan or roadmap item — not a licence to act outside one. Hard stops (infra apply, migration apply, push, secrets, deletes) always need explicit confirmation — see [`CLAUDE.md`](../../CLAUDE.md) → _Graded autonomy_.

AI Accelerator is a **polyglot monorepo of independent packages** (no pnpm
workspace, no Turborepo): `apps/web` (Next.js BFF + UI) and `apps/api` (FastAPI — the
**sole backend**, [ADR-0003](../../docs/adr/0003-remove-nestjs-api-layer.md)). See
[`CLAUDE.md`](../../CLAUDE.md) and each app's `CLAUDE.md` for the full map.

## Boundaries

- The browser talks **only** to `apps/web` (the BFF). `apps/web` route handlers call
  `apps/api` **server-side** via `API_BASE_URL`. Never call the backend directly from the
  browser; never put a service URL in a `NEXT_PUBLIC_*` var.
- Each app is its own package with its own lockfile and Dockerfile. Run app commands with
  `pnpm -C apps/web …` (**not** `pnpm --filter` — there is no workspace) or
  `uv run --directory apps/api …` for the api service.
- Cross-service calls go over HTTP and **must propagate `x-trace-id`** (see
  `60-observability.md`). There is no shared code package between services today; if you
  need one, write an ADR first (`/write-adr`).
- Every **business** HTTP endpoint is **URI-versioned (`/v1`)** — mandatory in both
  services. Only `/ping`, `/info`, `/health` are exempt. See `05-api-versioning.md`.

## The trace_id invariant (every request, every service)

`trace_id` = `origin(4 hex) + env(1 hex) + random(27 hex)` = 32 hex. Origins: `web=0eb0`,
`api=0c70`. **`0a71` is retired** (the former **NestJS** `api` service removed in ADR-0003 — a different service from today's FastAPI `apps/api`, ADR-0005) — reserved, never
reassign it. Header `x-trace-id`. Adopt a valid inbound id else generate with this service's
origin; store request-scoped; forward on every outbound call; echo on the response. Full detail
in [`README.md`](../../README.md).

## The architecture document (ADR-0006)

- [`docs/architecture/ARCHITECTURE.md`](../../docs/architecture/ARCHITECTURE.md) is the living
  architecture. **Part A** (template baseline) is template-owned — never edit it inside a
  project. **Part B** (project architecture) is the team's — **read it, together with
  `docs/design/`, before planning or scaffolding anything**; if it is missing what you need,
  ask rather than invent.
- Agents and skills **propose** changes to Part B (a diff in chat, or a `Proposed` ADR) and let
  the team apply them; they never rewrite it silently. When code and Part B disagree, say so —
  the code wins, then the team fixes the document.

## Database

- `apps/api` owns the database: **SQLAlchemy 2 async + Alembic** against an **external Azure
  database — never a local one** (no DB container, ever). The engine is **lazy** (no connection
  until the first query), the model set is a placeholder, and **migrations are not run** by
  this project. The engine is **Azure SQL Database** via `mssql+aioodbc` (ODBC Driver 18;
  managed-identity auth when deployed); an optional second engine reads an **external** database
  **read-only** (`app/db/external.py`). Rules in `25-sqlalchemy.md` and
  [ADR-0008](../../docs/adr/0008-azure-sql-data-layer.md) (supersedes ADR-0004's driver choices).
- A project's database is **created by the use-case Bicep deployment first** (ADR-0012); autogenerate and
  `alembic check` run against the **dev** database; applying is the migration pipeline or a
  named human.

## What needs an ADR (`docs/adr/`)

Adopting/removing a tool or a service, introducing a shared package, changing the
trace/observability contract, **changing the API-versioning scheme** (`05-api-versioning.md` /
ADR-0001), adding auth, or any cross-service contract change. Bug fixes and refactors do not.

Decisions on record: ADR-0001 (URI `/v1` versioning) · ADR-0002 (superseded by 0004) ·
ADR-0003 (remove the NestJS api layer) · ADR-0004 (SQLAlchemy 2 async + Alembic layer design;
driver choices superseded by 0008) · ADR-0005 (services named by role) · ADR-0006 (living
architecture document) · ADR-0007 (superseded by 0012) · ADR-0008 (Azure SQL via `mssql+aioodbc`;
DB spans via SQLAlchemy instrumentation) · ADR-0009 (LangChain + LangGraph on Foundry; AI Search) ·
ADR-0010/0011 (UI foundation; component tests) · ADR-0012 (Bicep on a shared, cloud-team-owned
platform; use-case-scoped infrastructure; roles as requests — rule `80-bicep.md`).
