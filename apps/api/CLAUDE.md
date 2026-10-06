# apps/api — CLAUDE.md

Python 3.14 + FastAPI service for the **AI Accelerator** (the brandless starter template
Orion Digital Solutions built for the Diriyah Company AI team), managed by **uv**. Port **8000**,
trace origin **`0c70`**, OTEL service `ai-accelerator-api`. Project-wide rules and the
shared `trace_id` / observability contract live in the root [CLAUDE.md](../../CLAUDE.md) and
[README.md](../../README.md); service overview in [README.md](README.md) (this folder). Treat
this as a starting map; read the actual files when you need detail.

## Layout (`app/`)

- `main.py` — app factory + module-level `app` (so `uvicorn app.main:app` works). Bootstrap
  order: configure **structlog first** → `init_observability` (fail-safe) → `install_error_handlers`
  + `UnhandledErrorMiddleware` → add `TraceMiddleware` (outermost) → include routers. The lifespan hook logs the degraded WARNING at startup if disabled and
  awaits `dispose_engine()` on shutdown.
- `routers/v1.py` — the **mandatory `/v1` business router** (`v1_router`, `prefix="/v1"`); feature
  routers attach here (ADR-0001 / rule 05). `main.py` includes it alongside `routes.py`.
- `routes.py` — **operational, unversioned** `/ping`, `/health` and `/info` (`/ping` → `{service, message, trace_id}`;
  `/health` adds `status`, `observability`, `reason`; `/info` → consolidated
  `{status, service, version, env, uptime_seconds, runtime, system, observability, reason,
  trace_id}`, version via `config.get_version()` / `importlib.metadata`).
- `errors.py` — **the error contract**: every non-2xx body is `{error, trace_id}` (`ErrorBody`);
  raise `ApiError` subclasses (`NotFound`, `Conflict`, `AIUnavailable`, or your own with a
  snake_case code); handlers map `HTTPException`/`RequestValidationError`/`AINotConfigured`;
  `UnhandledErrorMiddleware` makes any other exception a `500 internal_error`. Never echo
  exception text, validation values or stack traces — log the kind + location instead.
- `tracing.py` — `TraceMiddleware` (adopt valid inbound `x-trace-id` else generate, set the
  `contextvar`, echo the header, record the request-duration metric by route pattern),
  `generate_trace_id` / `is_valid_trace_id` / `get_trace_id` (origin `0c70`), and
  `traced_client` / `forward_headers` (the ONLY sanctioned outbound client: httpx, forwards
  `x-trace-id`, explicit default timeout `DEFAULT_UPSTREAM_TIMEOUT_SECONDS` (10 s, override with
  `timeout=`), hop-duration event hooks; traceparent + dependency span via httpx
  instrumentation).
- `observability.py` — `configure_azure_monitor` (fail-safe + **idempotent**, process-wide
  guard), FastAPI + httpx + **SQLAlchemy** (DB dependency spans for both lazy engines — the
  distro's default set lacks it, ADR-0008) + **system-metrics** (runtime-only selection: GC/memory/CPU/threads)
  instrumentation, `get_observability_state()`. Pins **fixed-percentage sampling**
  (`TRACE_SAMPLING_RATIO`, default 1.0; skipped when `OTEL_TRACES_SAMPLER` is set so the
  standard env config wins) and defaults the cloud role identity
  (`service.name`/`service.instance.id`, append-only). Ingestion auth via
  **`TELEMETRY_AUTH_MODE`** (`managed_identity` → Entra ID credential; a mistyped value
  disables observability VISIBLY — rule 60 → _Ingestion auth_). See
  `.claude/rules/60-observability.md`.
- `metrics.py` — `get_meter(scope)` (namespaced `ai-accelerator.<scope>`, no-op when degraded),
  `status_class`/`resolve_target` (bounded labels), starter instruments: request-duration +
  chain-hop histograms. **Bounded attributes only** — rule 60 → _Metrics & events_.
- `events.py` — `track_event(name, attrs)` → App Insights `customEvents` (via the
  `microsoft.custom_event.name` record marker through the stdlib `app.telemetry` logger);
  local structured line always prints; `service.start` wired in the `main.py` lifespan.
- `logging_config.py` — structlog → JSON stdout (`timestamp/level/service/origin/env/trace_id/message`);
  **redaction at source** (`DEFAULT_REDACTED_FIELDS`, extensible via
  `configure_logging(extra_redacted_fields=...)`), **Azure bridge** mirroring every event into
  the stdlib `app.telemetry` logger when enabled (opt out per logger by binding
  `telemetry_export=False`), **async stdout sink** (queue + writer thread, `flush_logs()` at
  exit). See rule 60 → _Log pipeline_.
- `config.py` — env-driven `Settings` (`APP_ENV`, `OTEL_SERVICE_NAME`, `PORT`, connection string,
  `DATABASE_URL` with the Azure SQL placeholder default, optional `EXTERNAL_DATABASE_URL`).
  `load_local_env()` loads the OPTIONAL `apps/api/.env` at startup (no-op when absent, never
  overrides ambient env) — no uvicorn `--env-file` flag anywhere.
- `db/` — the SQLAlchemy 2 **async** layer on **Azure SQL** (`mssql+aioodbc`, ADR-0008):
  `base.py` (`Base` + constraint naming convention), `engine.py` (`get_engine()` **lazy
  singleton**, `dispose_engine()`), `session.py` (`get_session()` FastAPI dependency — the ONLY
  way routes get a handle on the project DB), `external.py` (second lazy **read-only** engine
  for `EXTERNAL_DATABASE_URL`: `get_external_session()`, non-SELECT statements refused).
- `models/` — 2.0-style `Mapped[]` models subclassing `app.db.Base`; **empty placeholder** today
  (one commented example). Import new model modules in `models/__init__.py` so Alembic sees them.
- `../alembic/` + `../alembic.ini` — Alembic (async `env.py`, URL from `DATABASE_URL` via
  `app.config`, never from the ini); `versions/` is **empty** — migrations are not run.
- `ai/` — the AI runtime (ADR-0009, rule 70): `config.py` (`AZURE_AI_*`/`AZURE_SEARCH_*`/`AI_*`),
  `client.py` (**the mock seam** — `get_chat_model()`/`get_embeddings()`, managed identity when
  deployed), `graph.py` (`build_graph()` → `retrieve → answer` LangGraph, `ask()`),
  `streaming.py` (SSE frames + `sse_response()`), `tools/` (registry; `retrieve.py` Azure AI
  Search; `query_external_db.py` allow-listed read-only SQL via `queries.py`), `prompts/`
  (files, `load_prompt`), `telemetry.py` (`model_call_span`, content-free), `ingest.py`
  (`python -m app.ai.ingest <path>`; owns the index definition). Ships **no route** — a project
  adds `/v1/...` routes that call it (`docs/architecture/ai.md`).

## Conventions

- Request-scoped trace id via `contextvars` — read it with `get_trace_id()`.
- New outbound HTTP → use `traced_client()` so `x-trace-id` propagates.
- Log via the structlog logger (`get_logger(...)`) so lines carry `trace_id` + the standard fields.
- New **business** endpoint → `app/routers/<feature>.py`, attached to `v1_router` → `/v1/<feature>`
  (mandatory — ADR-0001 / rule 05). `routes.py` is operational-only (`/ping`, `/health`, `/info`).
- Model calls → only through `app.ai.client` and inside `model_call_span()`; never log prompts,
  completions or retrieved text; tools are read-only and allow-listed (rule 70).
- DB access → `session: Annotated[AsyncSession, Depends(get_session)]` in the route; models
  subclass `app.db.Base`. Never a sync engine, never a module-level session
  (`.claude/rules/25-sqlalchemy.md`).

## Database (ADR-0008 — Azure SQL, never local)

- **Lazy engine.** `get_engine()` builds the `AsyncEngine` on first use and never connects at
  import/startup — the service boots with the placeholder `DATABASE_URL`
  (`mssql+aioodbc://…?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no`).
  Deployed apps get the managed-identity form (`Authentication=ActiveDirectoryMsi`, username =
  identity client id) from Key Vault; developers get the dev database's URL from Key Vault too —
  **there is no local database.**
- **Session per request** via `Depends(get_session)`; tests override it with
  `app.dependency_overrides[get_session]` and never need a database. External read-only data:
  `Depends(get_external_session)` (`EXTERNAL_DATABASE_URL`; unset ⇒ `ExternalDatabaseNotConfigured`).
- **Alembic is wired, idle.** `alembic/versions/` is empty; the URL comes from `DATABASE_URL`
  through `app.config` (never `alembic.ini`). Autogenerate/`check` target the **dev** database;
  **applying is `.github/workflows/migrate.yml` (Environment-gated) or a named human** — agents
  only use offline/`heads`/`check` modes (root `CLAUDE.md` → _What you cannot do_).
- **DB spans** = `opentelemetry-instrumentation-sqlalchemy` (0.61b0, distro line) registered in
  `init_observability` **without an engine**, so it wraps `create_async_engine` for both lazy
  engines — which is why `engine.py`/`external.py` resolve it via `sa_asyncio.create_async_engine`
  at call time.

## Commands (uv)

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
uv run ruff format app alembic tests && uv run ruff check app alembic tests
uv run pytest                  # pytest + Starlette TestClient (--cov=app --cov-report=xml for coverage)
uv run alembic heads                              # head revisions (none today)
uv run alembic upgrade head --sql                 # offline SQL for review (no DB)
uv run alembic revision --autogenerate -m "<msg>" # needs a reachable dev DB
uv run alembic check                              # model/migration drift (needs a DB)
# from the repo root: uv run --directory apps/api ...
```

## Gotchas

- **OTel versions are pinned by the Azure distro:** `azure-monitor-opentelemetry==1.8.8`
  hard-pins `opentelemetry-sdk==1.40`, all instrumentation packages to `==0.61b0`, and
  `opentelemetry-api==1.40.0`. Don't bump the instrumentation pins independently — let the
  distro drive them.
- **Renaming the project** in `pyproject.toml` requires re-running `uv lock` (the lockfile
  records the project's own package name), or Docker's `uv sync --frozen` will fail.
- **Degraded mode:** empty `APPLICATIONINSIGHTS_CONNECTION_STRING` → stdout-only logging, a
  clear WARNING, `/health` reports `"observability": "disabled"`. Never crashes.
- **Docker** installs uv via **`pip`** (the GHCR `astral-sh/uv` image can be denied in some
  environments). Runtime carries the synced `.venv` + `app/` + `alembic/`/`alembic.ini` (so a
  human can run migrations from the image), runs as a non-root user.
- **ruff + `alembic/`:** the migrations dir shares its name with the `alembic` package, so
  `pyproject.toml` pins `known-third-party = ["alembic"]` for isort — don't remove it.
- **ODBC keywords ride in the URL query string** (`driver`, `Encrypt`, `TrustServerCertificate`,
  `Authentication`, `ApplicationIntent`) — SQLAlchemy forwards them to the ODBC connection
  string. `driver` is mandatory (URL-encode spaces as `+`); never ship `TrustServerCertificate=yes`.
  The runtime image installs ODBC Driver 18 (`Dockerfile`); pyodbc imports fine without a driver,
  so offline tests need nothing installed.
