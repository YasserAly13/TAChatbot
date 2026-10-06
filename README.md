# AI Accelerator

> A brandless starter template that the **[Diriyah Company](https://www.diriyahcompany.sa/en/) AI team** uses to accelerate
> the development of its AI projects. Built and maintained by **[Orion Digital Solutions](https://www.orion360.com/)** for the
> Diriyah Company. Every project-identity string is a placeholder — clone, rename, build.

## Overview

The AI Accelerator is exactly that — an accelerator: clone it, rename it (see
[Using this template](#using-this-template)), and start building your AI project's features
on a foundation that already works. It ships two wired-together services — a Next.js
BFF + UI and a FastAPI backend that owns the database — with **end-to-end `trace_id`
propagation** and **Azure Monitor / OpenTelemetry** observability baked into both
services, and is designed from the start for **continuous monitoring, performance
optimization, and measurable business impact** on **Microsoft Azure**.

## Using this template

Every project-identity string in the repo is a placeholder from one family, so a new
project renames everything in one pass:

| Placeholder token    | Used for                                                      |
| -------------------- | ------------------------------------------------------------- |
| `AI Accelerator`     | display name — page titles, docs headings, API/OpenAPI titles |
| `ai-accelerator`     | kebab-case slug — OTEL service names, Docker images, compose  |
| `@ai-accelerator/*`  | npm package scope (`apps/web`)                                |
| `ai-accelerator-api` | Python distribution name (`pyproject.toml`, `app/config.py`)  |

To rename, run the **`/rename-project`** command (backed by the
`.claude/skills/rename-project/` skill): it asks for your project's display name,
derives the kebab-case slug (lowercase letters/digits/hyphens only — no spaces or
special characters), replaces every token above across the repo, regenerates
`apps/api/uv.lock`, and verifies nothing was missed. Doing it by hand? Replace the
four token families above, then run `uv lock` in `apps/api` and rebuild.

## Scope & delivery status

This repository is the template's engineering monorepo. The table tracks what an
AI project typically builds on top against what the template **actually ships
today**, so the roadmap is never mistaken for what's shipped.

| Capability                       | What it is                                                                                                                                                                                                                                                                                  | Status                                                                                                                                                                                                  |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Cross-service foundation**     | two services (BFF + backend), end-to-end `trace_id`, Azure/OTel observability, `ping`/`health`/`info`                                                                                                                                                                                       | ✅ Included (baseline)                                                                                                                                                                                  |
| **Business features**            | your project's actual domain modules, built on the foundation                                                                                                                                                                                                                               | ⛔ Not included — built per project                                                                                                                                                                     |
| **Auth / RBAC**                  | authentication & authorization                                                                                                                                                                                                                                                              | ⛔ Not included — needs a threat model + ADR                                                                                                                                                            |
| **Database schema & migrations** | SQLAlchemy 2 async + Alembic (in `apps/api`) wired to an external Azure database — **never local**                                                                                                                                                                                          | ⏳ Empty model set, Alembic wired, no migrations; code still targets Postgres/asyncpg, the team's engine is **Azure SQL** (migration planned — `docs/template-roadmap.md` Phase 3)                      |
| **Azure deployment (IaC)**       | **Bicep** on a shared, cloud-team-owned platform (ADR-0012): the project deploys its container apps, Azure SQL, storage, Key Vault, App Insights + alerts and its AI Search index; Foundry, the Container Apps Environment, the registry and the AI Search service pre-exist and are shared | ⏳ Authored and `bicep build`/`lint`-clean for dev/staging/prod against placeholder manifests; **not yet deployed** (first `dev` deploy is a human step after the cloud team's manifests + role grants) |

> **Current status — foundation only.** What the template runs out of the box is the
> cross-service **foundation** a real project builds on: the `web → api`
> chain carrying one `x-trace-id` unchanged, Azure Monitor / OpenTelemetry
> observability in both services, and `ping` / `health` / `info` endpoints. **No
> business features and no auth are implemented**; the SQLAlchemy model set is an
> empty placeholder with Alembic wired but idle, and `infra/` holds the use-case Bicep
> (not yet deployed) on the cloud team's shared platform. The living architecture is
> [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md); what the template
> itself still needs is tracked in [`docs/template-roadmap.md`](docs/template-roadmap.md).

## The foundation at a glance

Two layers: a Next.js Backend-for-Frontend (BFF) in front of a FastAPI backend,
with **end-to-end `trace_id` propagation** and **Azure Monitor / OpenTelemetry**
observability baked into both services. Services are named by **role**, not runtime
([ADR-0005](docs/adr/0005-name-services-by-role.md)): `web` and `api`. (The former
**NestJS** `apps/api` layer — a different service from today's FastAPI `apps/api`; its
origin `0a71` is retired — was removed in
[ADR-0003](docs/adr/0003-remove-nestjs-api-layer.md).)

| App        | Stack                                          | Port | Trace origin |
| ---------- | ---------------------------------------------- | ---- | ------------ |
| `apps/web` | Next.js 16.2.6 (App Router)                    | 3000 | `0eb0`       |
| `apps/api` | Python 3.14 + FastAPI + SQLAlchemy 2 + Alembic | 8000 | `0c70`       |

- **Package managers:** pnpm `11.5.2` (web), uv (api). Node **24** LTS
  pinned across `.nvmrc`, the web Dockerfile, and `engines`.
- **Database:** SQLAlchemy 2 async (`mssql+aioodbc`) in `apps/api` against
  **Azure SQL Database** (created by the use-case Bicep deployment; **never local**). The model set
  is an empty placeholder and Alembic is wired but idle — **no database
  container anywhere**. An optional second engine reads an external database
  **read-only**.
- **Observability:** OpenTelemetry → Azure Monitor + Log Analytics. Structured
  JSON logs to stdout always. **Fail-safe**: runs fine with no Azure connection
  string (degraded mode).

---

## Documentation

This README is the quick orientation. The full documentation lives in
[`docs/`](docs/README.md), organized by purpose: [getting started](docs/getting-started.md) ·
[architecture](docs/architecture/README.md) · [development](docs/development/README.md)
(workflow, adding a feature, testing, coding standards) · [reference](docs/reference/README.md)
(HTTP API, env vars, commands) · [operations](docs/operations/README.md) (deployment, runbooks,
KQL) · [security](docs/security/README.md) · [ADRs](docs/adr/README.md).

---

## Prerequisites

> **Fastest path:** run `bash scripts/doctor.sh` (or `make doctor` / `just doctor`) — it checks
> every tool below against the repo's pins and prints the install command for your OS. In Claude
> Code, `/setup-dev-env` runs the same check, offers to install what is missing, and hands you
> step-by-step instructions when an install needs admin rights or a new terminal. Full manual
> steps: [`docs/getting-started.md`](docs/getting-started.md#installing-the-tools).

- **Docker** (with Compose v2) — for the containerized stack.
- **Node 24** — via [`fnm`](https://github.com/Schniz/fnm) / `nvm` (`.nvmrc`
  pins `24`), with **pnpm 11.5.2** (enable via `corepack enable`).
- **uv** ≥ 0.10 and **Python 3.14** — for `apps/api`.
- Task runner (same targets in both): [`just`](https://github.com/casey/just)
  — **recommended on Windows** (runs recipes via PowerShell) — _or_ **GNU make**
  (POSIX/CI; assumes a Unix shell). On Windows, make sure `node`/`pnpm` (via
  fnm), `uv`, and `docker` are on your `PATH` before running `just dev`.

---

## Repo structure

```
.
├─ apps/
│  ├─ web/                # Next.js 16 — UI + BFF route handlers; /health
│  └─ api/                # FastAPI — /ping, /info, /health; owns the database
│     ├─ app/db/          #   SQLAlchemy 2 async: Base, lazy engine, get_session()
│     ├─ app/models/      #   ORM models (empty placeholder + commented example)
│     ├─ alembic/         #   Alembic env (async) + versions/ (empty)
│     └─ alembic.ini
├─ infra/
│  ├─ main.bicep          # the use-case tier (ADR-0012) + main.<env>.bicepparam — see infra/README.md
│  ├─ modules/            # the infra team's building blocks (vendored) + template-owned observability/alerts
│  └─ platform/           # the cloud team's manifests of the SHARED tier per environment
├─ roadmaps/              # the plan of record: roadmaps/<api|web|infra>/ROADMAP.md (schema in roadmaps/README.md)
├─ docs/                  # documentation hub — start at docs/README.md
├─ docker-compose.yml     # builds both services, one network, no database (Azure SQL only)
├─ Makefile / justfile    # task runner (parity)
├─ package.json           # root tooling (concurrently, prettier) + dev/fmt scripts
├─ .env.example           # root env (compose) — copy to .env
├─ .nvmrc                 # 24
└─ .prettierrc / .prettierignore / .gitignore / .dockerignore
```

Each app is an **independent package** with its **own lockfile** (so
`docker build apps/<svc>` is individually buildable and reproducible) — there is
no pnpm workspace.

---

## Quick start (Docker — recommended)

```bash
cp .env.example .env          # optionally add APPLICATIONINSIGHTS_CONNECTION_STRING + DATABASE_URL
make up                       # or: just up   — or: docker compose up --build
```

Then open **http://localhost:3000** and click through the two button rows (Ping and Info). Other targets:

```bash
make build   # build all images        (docker compose build)
make up      # build + start the stack (docker compose up --build)
make down    # stop + remove containers
make logs    # tail logs from all services
make clean   # down -v + remove local build artifacts
```

`docker compose up` waits for each service's `/health` healthcheck (web starts
only once `api` is healthy), so the `web → api` chain works on the first click.

## Quick start (local, no Docker)

```bash
make install   # pnpm install (web) + uv sync (api)
make dev       # runs both concurrently:
               #   web    -> http://localhost:3000
               #   api    -> http://localhost:8000
```

`make dev` runs `next dev` and `uvicorn --reload` together via `concurrently`.
Each service reads its own `apps/<svc>/.env` (copy from the per-app
`.env.example`; both are optional) — web natively via Next, the api via
`load_local_env()` at startup. Ambient/shell env always wins
over `.env` values; containers never ship `.env` files (`.dockerignore`).

### Other tasks

```bash
make test              # run all tests (web + api); make test-cov for coverage
make fmt               # prettier (JS/TS/JSON/MD) + ruff (Python)
```

Alembic (database migrations) has no `make` target on purpose — see
[Database](#database-sqlalchemy-2-async--alembic) for the
`uv run --directory apps/api alembic …` commands.

---

## Testing

Test stacks per app (details in [`.claude/rules/40-testing.md`](.claude/rules/40-testing.md)):

| App              | Stack                             | Run                                              | Coverage                      |
| ---------------- | --------------------------------- | ------------------------------------------------ | ----------------------------- |
| `apps/web`       | Vitest (lib + BFF route handlers) | `pnpm -C apps/web test`                          | `apps/web/coverage/lcov.info` |
| `apps/web` (e2e) | Playwright — **manual/local**     | `pnpm -C apps/web test:e2e` (needs the stack up) | —                             |
| `apps/api`       | pytest + Starlette `TestClient`   | `uv run --directory apps/api pytest`             | `apps/api/coverage.xml`       |

- **All at once:** `make test` (fast) or `make test-cov` (with coverage, as CI runs it).
- **Run model = a mix:** run locally for fast feedback; **CI is the gate** — [`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs every suite with coverage on each PR and uploads the reports as the `coverage-reports` artifact (no external code-quality service is wired up). Playwright e2e is **not** in CI — run it manually before releases against `make up`.
- Every suite asserts the two invariants: **trace_id propagation** (adopt / regenerate / echo `x-trace-id`) and **fail-safe degraded observability** (`/health` reports `disabled` with no Azure connection string). Tests run **offline** — no real DB (the api overrides `get_session` / `get_external_session` via `app.dependency_overrides` and asserts `pyodbc.connect` is never called), no Azure, upstreams mocked.

---

## How it works: the BFF flow

**The browser only ever talks to the Next.js server.** The backend base URL
(`API_BASE_URL`) is **server-side env only** — never `NEXT_PUBLIC_*`. The UI
has two button rows — **Ping** (liveness) and **Info** (health · version ·
server). Every button calls a same-origin Next.js **route handler** (the BFF),
which calls the api service server-side — one hop.

```
Ping — liveness (returns { service, message, trace_id }):
   browser ──▶ web BFF (/api/ping-backend) ──▶ api (/ping) ──▶ back

Info — health · version · server (returns { status, service, version, env,
        uptime_seconds, runtime, system, observability, reason, trace_id }):
   browser ──▶ web BFF (/api/info-backend) ──▶ api (/info) ──▶ back
           ◀──────────────────────────────  response bubbles back through the hop
```

The Ping endpoint returns JSON including `service`, `message`, and the active
`trace_id`. The Info endpoint adds a consolidated status/version/runtime report.
The UI renders every response plus its `trace_id`.

The service-to-service URL resolves via Compose DNS inside the network
(`http://api:8000`); locally it defaults to `http://localhost:8000`.

---

## API versioning

**Every business HTTP endpoint is URI-versioned (`/v1`, then `/v2`, …)** — mandatory
in both services and enforced structurally. Decided in
[`docs/adr/0001-api-versioning.md`](docs/adr/0001-api-versioning.md); the working
convention (and per-framework how-to) is
[`.claude/rules/05-api-versioning.md`](.claude/rules/05-api-versioning.md).

- **`apps/api` (FastAPI):** business routers attach to `v1_router`
  (`app/routers/v1.py`) → `/v1/<feature>`.
- **`apps/web` (BFF):** business handlers live under
  `src/app/api/v1/<feature>/route.ts` (→ `/api/v1/<feature>`) and call the matching
  `/v1` upstream.

**Exemption — operational endpoints stay unversioned:** `/ping`, `/info`, `/health`
keep their root paths (container/Azure health probes target them). They are the only
exception; adding another is an ADR change.

---

## `trace_id` — the invariant

**No request anywhere may exist without a `trace_id`.** It is generated at the
true origin and **propagated downstream unchanged**.

```
0eb0 0 f8e2c9a7b4d16035e9c2a8f4712
└┬─┘ │ └────────────┬────────────┘
 │   │              └─ 27 hex — 108 bits CSPRNG random
 │   └─ env (1 hex)
 └───── origin (4 hex)        →  32 hex chars total, regex ^[0-9a-f]{32}$
```

| Field  | Width  | Values                                                                                                                                                                             |
| ------ | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| origin | 4 hex  | `web=0eb0` · `api=0c70` (the FastAPI api; kept across the rename, ADR-0005) · (`0a71` retired — the former **NestJS** `apps/api`, removed in ADR-0003; reserved, never reassigned) |
| env    | 1 hex  | `local=0` · `dev=1` · `staging=2` · `prod=3` · (`sandbox=4` reserved/unused)                                                                                                       |
| random | 27 hex | CSPRNG (Node `randomBytes(14)` / Python `secrets.token_hex(14)`, sliced)                                                                                                           |

**Behavior in both services** (a dedicated, reusable tracing module):

- Canonical header: **`x-trace-id`**.
- **Inbound:** adopt the inbound `x-trace-id` if present **and valid**; otherwise
  **generate** one using that service's own origin + the current env.
- Stored **request-scoped** (Node `AsyncLocalStorage`, Python `contextvars`) so
  every log line, span, and outbound call within the request can see it.
- **Every outbound call forwards `x-trace-id`** unchanged → one id across the
  hop (in the BFF flows, **web** is the origin, so the api sees `0eb0…`).
- The `x-trace-id` is **echoed on the response**.
- Correlated with OpenTelemetry as a `trace_id` **span attribute** and on every
  structured log line.

---

## Observability & logging

OpenTelemetry → **Azure Application Insights / Azure Monitor / Log Analytics**.
The **same code path runs locally and when deployed** — config comes from
`APPLICATIONINSIGHTS_CONNECTION_STRING`. There is **no local monitoring stack**.

- **Node (`web`):** `@azure/monitor-opentelemetry` (`useAzureMonitor`),
  initialized in `src/instrumentation.ts` via `register()`.
- **Python (`api`):** `azure-monitor-opentelemetry` (`configure_azure_monitor`),
  plus explicit FastAPI + httpx + SQLAlchemy instrumentation.
- **Structured JSON logs to stdout, always.** Every line carries: `timestamp`,
  `level`, `service`, `origin`, `env`, `trace_id`, `message`
  (Node: `pino`; Python: `structlog`). Telemetry export is **batched /
  non-blocking** — never in the request hot path.
- **Log export bridge (Phase 1).** The distros do NOT collect pino, and structlog
  bypasses stdlib `logging` — so each service bridges its logs explicitly: Node
  tees every serialized line through the **OTel Logs API**; Python mirrors every
  event into the stdlib `app.telemetry` logger the distro's handler watches.
  Bridged records inherit the active span context (`AppTraces.operation_Id`
  matches the request) and the bridge is fail-safe: no-op when degraded, and an
  export error can never break local stdout logging.
- **Redaction at source.** A default list of secret-bearing fields
  (`authorization`, `cookie`, `token`, `password`, `secret`, `connectionString`,
  …) is replaced with `[redacted]` during serialization — **before any sink**
  (local or remote) sees the line; extensible per logger. Details + the purge
  runbook for accidental leaks:
  [`.claude/rules/60-observability.md`](.claude/rules/60-observability.md) →
  _Log pipeline_ and
  [`docs/operations/runbooks/pii-purge.md`](docs/operations/runbooks/pii-purge.md).
- **Non-blocking log sinks.** stdout writes are buffered off the request path
  (pino async destination / a queue + writer thread in Python) with a
  best-effort synchronous flush at process exit.
- **Dependency spans on every hop (Phase 2).** The traced wrappers
  (`fetchUpstream` / `traced_client`) are the ONLY sanctioned
  HTTP clients; below them, web registers the **undici** instrumentation at
  init (the Azure distro does not cover global `fetch`) and the api uses the
  httpx instrumentation — so every hop carries W3C `traceparent` + the repo's
  `x-trace-id` and emits an `AppDependencies` span. DB spans come from
  `opentelemetry-instrumentation-sqlalchemy`, registered explicitly (without an
  engine, so both lazy engines are covered) in `apps/api/app/observability.py`
  because the Azure distro's default instrumentation set has nothing for the
  `mssql+aioodbc` engines
  ([ADR-0008](docs/adr/0008-azure-sql-data-layer.md), which supersedes
  [ADR-0004](docs/adr/0004-sqlalchemy-async-alembic-db-layer.md)).
- **Metrics & custom events (Phase 3).** `getMeter(scope)` / `get_meter(scope)`
  returns namespaced meters (`ai-accelerator.<scope>`; silent no-op in degraded
  mode). Starter set: request-duration histogram (by route class + status
  class), upstream-hop duration histogram (target label set `api | other`),
  BFF upstream-failure counter. Runtime
  health metrics (event-loop/GC/heap, or CPython GC/memory/CPU) register at
  init. `trackEvent(name, attrs)` / `track_event(...)` emits App Insights
  `customEvents` (first wired event: `service.start`). **Metric/event
  attributes use bounded value sets only** — never ids, emails, or
  parameterized paths; see the cardinality rule in
  [`.claude/rules/60-observability.md`](.claude/rules/60-observability.md).

### Init order, idempotency, sampling, identity

Full contract (incl. the per-service auto-instrumentation inventory) in
[`.claude/rules/60-observability.md`](.claude/rules/60-observability.md).

### Operating it

- **[KQL starter pack](docs/operations/kql-starter-pack.md)** — trace-by-id,
  request+logs join, error rate, dependency latency, ingestion volume, custom
  metrics/events checks.
- **[Post-deploy smoke](docs/operations/runbooks/post-deploy-smoke.md)** — one
  BFF request through to the api, then prove every pillar table-by-table (App
  Insights fails silent; never assume).
- **[Degraded-mode triage](docs/operations/runbooks/observability-degraded.md)**
  — every `/health` `reason` string and its fix, plus enabled-but-silent causes.
- **[PII purge](docs/operations/runbooks/pii-purge.md)** ·
  **[Platform log tables](docs/operations/runbooks/platform-log-tables.md)**.

- **Init-order discipline (per runtime):** `web` — Next.js can't use a
  first-import, so init runs in the framework's hook `src/instrumentation.ts`
  `register()` (nodejs runtime only); `api` — instrumentation is **explicit**
  (`configure_azure_monitor` + `FastAPIInstrumentor.instrument_app` +
  `HTTPXClientInstrumentor` + `SQLAlchemyInstrumentor`) inside `create_app()`,
  before requests are served.
- **Idempotent init:** both services guard init behind a process-global
  flag — calling init twice (or loading a second module copy) never
  double-registers the SDK. Covered by unit tests in each service.
- **Sampling is pinned explicitly (never trust the distro default).** Current
  Azure Monitor distros (Node ≥ 1.16.0, Python ≥ 1.8.6) default to
  **rate-limited sampling (~5 traces/sec)** — a silent telemetry cap. Every
  service pins a **fixed-percentage sampler at 100%** by default, tunable via
  `TRACE_SAMPLING_RATIO` (0..1). The standard `OTEL_TRACES_SAMPLER` /
  `OTEL_TRACES_SAMPLER_ARG` env vars take precedence when set.
- **Cloud role identity:** each service defaults `service.name` (→ App
  Insights _cloud role name_: `ai-accelerator-web|api`) and
  `service.instance.id` (→ _cloud role instance_: container replica name →
  `HOSTNAME` → os hostname) via the standard OTel env vars. Defaults are
  **append-only** — operator-provided `OTEL_SERVICE_NAME` /
  `OTEL_RESOURCE_ATTRIBUTES` are never overridden; `service.namespace` is
  deliberately not set.

### Fail-safe / degraded mode

The system **runs without monitoring**. If `APPLICATIONINSIGHTS_CONNECTION_STRING`
is missing/empty (or init throws), each service:

- skips remote export, **does not crash**,
- prints a clear startup **WARNING**:
  `Observability disabled: no Azure connection string — running with local stdout logging only`,
- reports it on its health endpoint:

```bash
curl http://localhost:8000/health
# {"status":"ok","service": "api","trace_id":"0c70…","observability":"disabled","reason":"no Azure connection string"}
```

`GET /health` on each service returns `{ status, service, trace_id,
observability: "enabled"|"disabled", reason }`.

---

## Database (SQLAlchemy 2 async + Alembic)

`apps/api` owns the database
([ADR-0008](docs/adr/0008-azure-sql-data-layer.md), superseding ADR-0004's
Postgres driver choices; the layer itself replaced the Prisma layer that left
with the former **NestJS** `apps/api`, ADR-0003). The stack is **SQLAlchemy 2.0
asyncio** (`create_async_engine`, `AsyncSession`, 2.0-style `DeclarativeBase` /
`Mapped[]` models) on the **`mssql+aioodbc`** driver (aioodbc → pyodbc →
Microsoft ODBC Driver 18, installed in the api image) against **Azure SQL
Database**, with **Alembic** for migrations:

- `app/db/base.py` — `Base` (`DeclarativeBase`) with the naming convention every
  constraint/index follows.
- `app/db/engine.py` — `get_engine()`, a **lazy** process-wide singleton: no
  connection is opened until the first query, so the service boots with the
  placeholder `DATABASE_URL` (the baseline path issues no queries).
  `dispose_engine()` is awaited in the FastAPI lifespan shutdown.
- `app/db/session.py` — `get_session()`, the FastAPI dependency and the **only**
  way route code gets a DB handle:
  `session: Annotated[AsyncSession, Depends(get_session)]`.
- `app/db/external.py` — a second, **read-only** lazy engine for an external
  database (`EXTERNAL_DATABASE_URL`; `Depends(get_external_session)`); no
  Alembic, and any non-`SELECT` statement is refused before it reaches the driver.
- `app/models/__init__.py` — the model set, **empty on purpose** (one commented
  example model to start from).
- `alembic.ini` + `alembic/env.py` — the async Alembic environment; the URL is
  not in the ini, it comes from `DATABASE_URL` via `app.config.get_settings()`.
  `alembic/versions/` is **empty**.

`DATABASE_URL` uses the aioodbc scheme with the ODBC keywords in the query
string —
`mssql+aioodbc://USER:PASSWORD@host:1433/db?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no`.
Deployed apps get the managed-identity form (`Authentication=ActiveDirectoryMsi`,
username = identity client id) that `infra/main.bicep` writes to Key Vault. **There is no
local database**: point the dev `.env` at the dev Azure SQL database (URL from
Key Vault, your IP on the firewall allowlist).

**Migrations are never run by this platform or its agents.** Applying one
(`alembic upgrade`) is the Environment-gated
[`migrate.yml`](.github/workflows/migrate.yml) workflow or a deliberate human
step; the api Docker image ships `alembic.ini` + `alembic/` (and the ODBC
driver) so it can be run from the container too.

### Extending the model set

1. Add a module under `apps/api/app/models/` (e.g. `widget.py`) with a
   2.0-style model subclassing `app.db.Base`, and import it in
   `app/models/__init__.py` so it registers on `Base.metadata` (autogenerate only
   sees imported models).
2. Use it from a `/v1` router through the dependency:
   `async def list_widgets(session: Annotated[AsyncSession, Depends(get_session)])`.
3. With a **reachable dev database**, generate a revision and review it:
   `uv run --directory apps/api alembic revision --autogenerate -m "add widget"`.
4. Review the SQL offline (no database needed):
   `uv run --directory apps/api alembic upgrade head --sql` — today this
   prints only `BEGIN;`/`COMMIT;` because there are no revisions
   (`uv run --directory apps/api alembic heads` prints nothing).
5. Apply it yourself, when ready: `alembic upgrade head` against the target
   database. `uv run --directory apps/api alembic check` (needs a DB) reports
   model/migration drift.

Conventions for the layer: [`.claude/rules/25-sqlalchemy.md`](.claude/rules/25-sqlalchemy.md).

---

## Environment variables

Documented in `.env.example` (root) and `apps/<svc>/.env.example`:

| Variable                                | Used by   | Notes                                                                                                                                                                                                      |
| --------------------------------------- | --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `APP_ENV`                               | all       | `local`\|`dev`\|`staging`\|`prod` → trace env nibble + logs                                                                                                                                                |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | all       | empty ⇒ degraded mode (stdout only)                                                                                                                                                                        |
| `TRACE_SAMPLING_RATIO`                  | all       | 0..1 fixed-percentage trace sampling; empty ⇒ 1.0 (100%); `OTEL_TRACES_SAMPLER*` wins                                                                                                                      |
| `TELEMETRY_AUTH_MODE`                   | all       | empty/`connection_string` (default) or `managed_identity` (Entra ID ingestion); a mistyped value disables observability **visibly** — no silent unauthenticated fallback                                   |
| `TELEMETRY_MANAGED_IDENTITY_CLIENT_ID`  | all       | client id of a user-assigned managed identity (empty ⇒ system-assigned)                                                                                                                                    |
| `OTEL_SERVICE_NAME`                     | all       | `ai-accelerator-web` / `-api` (defaulted in code; never overridden)                                                                                                                                        |
| `DATABASE_URL`                          | api       | Azure SQL Database — `mssql+aioodbc://…?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no` (SQLAlchemy 2 async; lazy engine; never local)                                         |
| `EXTERNAL_DATABASE_URL`                 | api       | optional read-only external Azure SQL database (empty ⇒ not configured)                                                                                                                                    |
| `API_BASE_URL`                          | web (BFF) | → the FastAPI `api` service, e.g. `http://api:8000` (default `http://localhost:8000`). Same name as the former NestJS service's variable (retired in ADR-0003, reintroduced for the new `api` in ADR-0005) |
| `PORT`                                  | all       | 3000 / 8000                                                                                                                                                                                                |

---

## Infrastructure

The platform's committed scope is deployment on **Microsoft Azure** via **Bicep**, in two tiers
([ADR-0012](docs/adr/0012-bicep-shared-platform.md)). The **platform tier** — Azure AI Foundry
with its model deployments, the Container Apps Environment, the Container Registry and the AI
Search service — pre-exists per environment, is owned by the cloud team and is **shared by every
use case**; it is described by `infra/platform/<env>.json` and only ever referenced. The
**use-case tier** — this project's two container apps, Azure SQL server + database, storage
account, Key Vault, Log Analytics + Application Insights + alerts, and its AI Search index — is
[`infra/main.bicep`](infra/main.bicep) with names per environment in `infra/main.<env>.bicepparam`,
composed from the infra team's **vendored building blocks** in `infra/modules/`. GitHub Actions
runs `what-if` on pull requests and deploys on merge in every environment; developers may
deploy locally to `dev` only; agents may only `bicep build`/`lint`. Roles the project needs on
shared resources are **requested** (`infra/grant-request.md`), never assigned here. Nothing is
deployed yet — the first `dev` deploy is a human step once the cloud team's manifests and
building blocks are in. Everything else: [`infra/README.md`](infra/README.md).
#   D i r i y a h _ T e m p l a t e _ V 0  
 #   D i r i y a h _ T e m p l a t e _ V 0  
 