---
description: API versioning is MANDATORY (URI /v1). Loaded when editing any route, controller, or BFF handler.
paths:
  - 'apps/web/src/app/api/**'
  - 'apps/api/app/**'
---

# API versioning (MANDATORY)

> **Graded autonomy:** these are conventions to apply _within_ an approved plan or roadmap item — not a licence to act outside one. Hard stops (infra apply, migration apply, push, secrets, deletes) always need explicit confirmation — see [`CLAUDE.md`](../../CLAUDE.md) → _Graded autonomy_.

**Every business HTTP endpoint MUST be URI-versioned: `/v{n}`, starting at `v1`.**
Decided in [`docs/adr/0001-api-versioning.md`](../../docs/adr/0001-api-versioning.md).
Creating a business endpoint without a version is a **blocking** review failure.

## The scheme

- **URI path versioning only** — `GET /v1/projects`, `POST /v1/agents`. Not header,
  not media-type (see ADR-0001 for why).
- One version segment, lowercase `v` + integer: `/v1`, later `/v2`. No `/v1.0`.
- The version is the **first** path segment of the service-local path.

## The only exemption: operational endpoints

`/ping`, `/info`, `/health` stay **unversioned** (container/Azure health probes hit
fixed paths). Do **not** add new endpoints to this exemption list — if you think you
need to, that's an ADR change, not a code change.

## Per service

### `apps/api` (FastAPI) — the `/v1` router

- Business routers attach to `v1_router` (`app/routers/v1.py`, `prefix="/v1"`), which
  `main.py` includes. New feature → `app/routers/<feature>.py` with an `APIRouter()`,
  then `v1_router.include_router(<feature>.router)` → served under `/v1/<feature>`.
- The operational router (`app/routes.py`) stays mounted at the root — leave it.

### `apps/web` (Next.js BFF) — the `/api/v1/` folder

- Next has no global versioning primitive; routing is folder-based, so the convention
  **is** the enforcement: business BFF handlers live at
  `src/app/api/v1/<feature>/route.ts` → `/api/v1/<feature>`.
- The BFF **mirrors the upstream version**: a handler under `/api/v1/…` calls
  `${API_BASE_URL}/v1/…` (still via `fetchUpstream`, still forwarding `x-trace-id`).
- The existing demo/operational routes (`/api/ping-backend`, `/api/info-backend`, `/health`)
  are not business endpoints and stay where they are.

## Enforcement layers (defense in depth)

1. **Structural** — the FastAPI `/v1` router and the BFF's `api/v1/` folder make versioning
   the path of least resistance.
2. **Scaffold** — `feature-scaffold` emits versioned routes.
3. **Review** — `code-reviewer` blocks any unversioned new business endpoint.
4. _(Not yet enabled)_ a CI gate that fails the build on an unversioned business route
   — add via ADR when wanted.
