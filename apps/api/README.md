# AI Accelerator — api service

Python 3.14 + FastAPI service for the [AI Accelerator](../../README.md) — the brandless
starter template built by [Orion Digital Solutions](https://www.orion360.com/) for the [Diriyah Company](https://www.diriyahcompany.sa/en/) AI team — managed by
[uv](https://docs.astral.sh/uv/).

- Service identity: `api` · OTEL service `ai-accelerator-api` · trace origin `0c70`
- Listens on port **8000** (shared contract: web=3000, api=8000)
- The **sole backend**: the Next.js BFF (`apps/web`) is its only consumer (ADR-0003); it owns the
  database via SQLAlchemy 2 async + Alembic on Azure SQL (ADR-0008)

## Develop

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

(`apps/api/.env` — a copy of `.env.example` — is **optional**: `app.main` loads it via
`load_local_env()` when it exists and never overrides ambient env. No `--env-file` flag is
needed; the root `make dev` / `just dev` script works without a `.env`.)

Endpoints:

- `GET /ping` → `{ "service": "api", "message": "...", "trace_id": "<32hex>" }`
- `GET /info` → consolidated status/version/runtime report
- `GET /health` → `{ "status": "ok", "service": "api", "trace_id": "...", "observability": "enabled|disabled", "reason": "..." }`

Both echo the `x-trace-id` response header. Inbound valid `x-trace-id` headers are adopted; otherwise a new id is generated (`0c70` origin).

## Observability

Set `APPLICATIONINSIGHTS_CONNECTION_STRING` to enable Azure Monitor / OpenTelemetry.
When empty, the service runs in degraded mode (local stdout JSON logging only) and never crashes.

See `.env.example` for all environment variables.

## Database (SQLAlchemy 2 async + Alembic on Azure SQL)

`DATABASE_URL` (`mssql+aioodbc://…?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no`)
points at an **Azure SQL Database** created by the use-case Bicep deployment — **there is no local database**; get the
dev URL from Key Vault. The engine (`app/db/engine.py`) is **lazy**: nothing connects until the
first query, so the baseline boots with the placeholder URL. Routes get a session via
`Depends(get_session)` (`app/db/session.py`); models live in `app/models/` and subclass
`app.db.Base`. An optional **read-only** second engine (`app/db/external.py`,
`EXTERNAL_DATABASE_URL`, `Depends(get_external_session)`) reaches an external database and
refuses anything but `SELECT`. DB dependency spans come from the SQLAlchemy instrumentation
registered in `app/observability.py`.

Alembic is wired but idle (`alembic/versions/` is empty). Migrations are **never run by this
project or its agents** — applying one is the Environment-gated `migrate.yml` workflow or a
deliberate human step:

```bash
uv run alembic heads                              # head revisions (none today)
uv run alembic upgrade head --sql                 # offline T-SQL for review — no DB needed
uv run alembic revision --autogenerate -m "msg"   # needs the dev Azure SQL database reachable
uv run alembic check                              # model/migration drift — needs the dev DB
uv run alembic upgrade head                       # HUMAN / migrate.yml ONLY
```

Conventions: `.claude/rules/25-sqlalchemy.md` · decision: `docs/adr/0008-…` (supersedes `0004`).

## AI runtime (LangChain + LangGraph on Azure AI Foundry)

`app/ai/` ships the runtime a project builds its AI features on — no use case included:
`build_graph()` (a `retrieve → answer` LangGraph, optional tool loop), `ask()` /
`stream_answer()` (SSE), the client seam (`get_chat_model()` — managed identity when
deployed), Azure AI Search retrieval, the allow-listed read-only `query_external_db` tool,
prompt files, content-free `gen_ai` telemetry, and the ingestion job:

```bash
uv run python -m app.ai.ingest ./docs   # chunk → embed → upload; needs AZURE_SEARCH_* + AZURE_AI_EMBEDDING_*
uv run pytest tests/ai tests/evals      # offline: fakes for the model, retriever, search client, DB
```

All `AZURE_AI_*` / `AZURE_SEARCH_*` / `AI_*` variables are optional (see `.env.example`); a
feature that calls the AI layer without them raises `AINotConfigured`. Conventions:
`.claude/rules/70-ai.md` · deep-dive: `docs/architecture/ai.md` · decision: `docs/adr/0009-…`.

## Docker

```bash
docker build -t ai-accelerator-api .   # build context = apps/api; installs ODBC Driver 18
docker run -p 8000:8000 ai-accelerator-api
```
