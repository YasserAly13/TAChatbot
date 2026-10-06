# Environment variables reference

Consolidated from `.env.example` (root), `apps/web/.env.example`, `apps/api/.env.example`,
`docker-compose.yml`, and a code grep for `process.env.` / `os.environ` / `os.getenv` usage
across both services. Mismatches between the examples and
the code are called out explicitly — see [Mismatches found](#mismatches-found-in-code-but-not-in-envexample-or-vice-versa).

## Master table

| Variable                                                | Consumed by       | Default / example                                                                                                                                              | Required? | Effect                                                                                                                                                                                                                                                                                                                                                            |
| ------------------------------------------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `APP_ENV`                                               | web, api, compose | `local`                                                                                                                                                        | No        | Env nibble in `trace_id` (`local=0 dev=1 staging=2 prod=3 sandbox=4`) + `env` field on every log line. Unknown/missing → treated as `local`.                                                                                                                                                                                                                      |
| `APPLICATIONINSIGHTS_CONNECTION_STRING`                 | web, api, compose | _(empty)_                                                                                                                                                      | No        | Empty ⇒ degraded mode (local stdout logging only, never crashes). Set ⇒ ships telemetry to Azure Monitor.                                                                                                                                                                                                                                                         |
| `TRACE_SAMPLING_RATIO`                                  | web, api, compose | _(empty)_ → `1.0`                                                                                                                                              | No        | Fixed-percentage OTel trace sampling, `0..1`. Invalid value ⇒ warn + fall back to `1.0`. Ignored if `OTEL_TRACES_SAMPLER` is set.                                                                                                                                                                                                                                 |
| `TELEMETRY_AUTH_MODE`                                   | web, api, compose | _(empty)_                                                                                                                                                      | No        | `""`/`connection_string` = default ingestion; `managed_identity` = Entra ID via `ManagedIdentityCredential`; any other value disables observability **visibly** (reason on `/health`), never a silent fallback.                                                                                                                                                   |
| `TELEMETRY_MANAGED_IDENTITY_CLIENT_ID`                  | web, api          | _(empty)_                                                                                                                                                      | No        | Client ID of a **user-assigned** managed identity; empty ⇒ system-assigned. Only meaningful with `TELEMETRY_AUTH_MODE=managed_identity`. **Not passed through by `docker-compose.yml`** — see mismatches below.                                                                                                                                                   |
| `OTEL_SERVICE_NAME`                                     | web, api          | `team-assistant-web`\|`-api`                                                                                                                                   | No        | App Insights cloud role name. Code defaults it only if unset **and** `service.name` isn't already in `OTEL_RESOURCE_ATTRIBUTES`; an operator-set value is never overridden.                                                                                                                                                                                       |
| `OTEL_RESOURCE_ATTRIBUTES`                              | web, api          | _(unset)_                                                                                                                                                      | No        | Standard OTel resource-attribute list. Code appends `service.instance.id=<CONTAINER_APP_REPLICA_NAME\|HOSTNAME\|hostname()>` if not already present; existing attributes are never overwritten. Not in any `.env.example` (append-only code default, not normally hand-set locally).                                                                              |
| `OTEL_TRACES_SAMPLER` / `OTEL_TRACES_SAMPLER_ARG`       | web, api          | _(unset)_                                                                                                                                                      | No        | Standard OTel env vars; when `OTEL_TRACES_SAMPLER` is set it **takes precedence** over `TRACE_SAMPLING_RATIO`. Not in any `.env.example` (standard OTel knob, documented in prose comments only).                                                                                                                                                                 |
| `DATABASE_URL`                                          | api, compose      | `mssql+aioodbc://USER:PASSWORD@your-server.database.windows.net:1433/your-database?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no` | No (lazy) | SQLAlchemy 2 async (`mssql+aioodbc`) URL to the **Azure SQL Database** `infra/main.bicep` created — there is **no local database**; get the dev URL from Key Vault. The engine is lazy — the api boots fine with the placeholder. Deployed apps use `Authentication=ActiveDirectoryMsi` with the identity client id as username. Also read by Alembic's `env.py`. |
| `EXTERNAL_DATABASE_URL`                                 | api, compose      | _(empty)_                                                                                                                                                      | No        | Optional **read-only** external Azure SQL database (`mssql+aioodbc://…`, the SELECT-only login the owner provides; add `ApplicationIntent=ReadOnly` when read replicas exist). Empty ⇒ not configured: `get_external_engine()` raises `ExternalDatabaseNotConfigured`. Non-SELECT statements are refused in code.                                                 |
| `AZURE_AI_ENDPOINT`                                     | api, compose      | _(empty)_                                                                                                                                                      | No        | AI Services (Foundry) account endpoint (set by `infra/main.bicep`). Unset ⇒ any AI feature raises `AINotConfigured`; the service itself boots fine. ADR-0009.                                                                                                                                                                                                     |
| `AZURE_AI_DEPLOYMENT` / `AZURE_AI_EMBEDDING_DEPLOYMENT` | api, compose      | _(empty)_                                                                                                                                                      | No        | Chat / embedding deployment names (keys of `infra/main.bicep` `ai_deployments`).                                                                                                                                                                                                                                                                                  |
| `AZURE_AI_EMBEDDING_DIMENSIONS`                         | api, compose      | `1536`                                                                                                                                                         | No        | Vector width of the embedding deployment; drives the AI Search index definition and query vectors (3072 for `text-embedding-3-large`).                                                                                                                                                                                                                            |
| `AZURE_AI_API_VERSION`                                  | api, compose      | `2024-10-21`                                                                                                                                                   | No        | Azure OpenAI API version passed to `langchain-openai`.                                                                                                                                                                                                                                                                                                            |
| `AZURE_AI_AUTH_MODE`                                    | api, compose      | `managed_identity`                                                                                                                                             | No        | `managed_identity` (deployed: `DefaultAzureCredential` + `AZURE_CLIENT_ID`) or `api_key` (dev). Any other value raises — never a silent fallback.                                                                                                                                                                                                                 |
| `AZURE_AI_API_KEY`                                      | api, compose      | _(empty)_                                                                                                                                                      | No        | Only with `AZURE_AI_AUTH_MODE=api_key`; from Key Vault `AZURE-AI-API-KEY`. Dev only.                                                                                                                                                                                                                                                                              |
| `AZURE_SEARCH_ENDPOINT` / `AZURE_SEARCH_INDEX`          | api, compose      | _(empty)_                                                                                                                                                      | No        | Azure AI Search service + index (built by `python -m app.ai.ingest`). Both unset ⇒ the graph uses `NullRetriever` (answers without context).                                                                                                                                                                                                                      |
| `AZURE_SEARCH_API_KEY`                                  | api, compose      | _(empty)_                                                                                                                                                      | No        | Dev only (Key Vault `AZURE-SEARCH-API-KEY`); empty ⇒ the app identity (`Search Index Data Reader`).                                                                                                                                                                                                                                                               |
| `AI_MAX_OUTPUT_TOKENS`                                  | api, compose      | `1024`                                                                                                                                                         | No        | Cap on each answer's length and cost — sent to Azure OpenAI as `max_completion_tokens`. `0` removes the cap (and with it the per-answer cost limit); an invalid or negative value falls back to `1024`.                                                                                                                                                           |
| `AI_REQUEST_TIMEOUT_SECONDS` / `AI_MAX_RETRIES`         | api, compose      | `60` / `2`                                                                                                                                                     | No        | Per-call model timeout and retry count (`langchain-openai` `timeout` / `max_retries`). Invalid values fall back to the defaults.                                                                                                                                                                                                                                  |
| `AI_ALLOW_TEXT_TO_SQL`                                  | api, compose      | `false`                                                                                                                                                        | No        | Lets `run_readonly_sql` execute model-written `SELECT`s on the external DB. A threat-modelled project decision; the engine guard and SELECT-only login still apply.                                                                                                                                                                                               |
| `API_BASE_URL`                                          | web               | `http://localhost:8000` (compose: `http://api:8000`)                                                                                                           | No        | Server-side only — **never** `NEXT_PUBLIC_*`. Base URL the BFF calls for the FastAPI `api` service (`apps/api`), the sole backend. Reintroduced for it in ADR-0005; the former NestJS service's identically named variable was retired in ADR-0003.                                                                                                               |
| `PORT`                                                  | web, api          | `3000` / `8000`                                                                                                                                                | No        | Port the service's HTTP server listens on.                                                                                                                                                                                                                                                                                                                        |
| `LOG_LEVEL`                                             | web               | `info` (pino default)                                                                                                                                          | No        | Pino log level (`debug`/`info`/`warn`/`error`/…). **Not present in any `.env.example`** — see mismatches below. Not read by `apps/api` at all (structlog's level is hardcoded to `INFO` in `logging_config.py`).                                                                                                                                                  |

## Per-variable notes

- **`APPLICATIONINSIGHTS_CONNECTION_STRING`** — empty ⇒ degraded mode: each service prints a
  startup WARNING, skips remote export, and reports `"observability": "disabled"` on `/health` —
  it never crashes. Same code path locally and deployed.
- **`TRACE_SAMPLING_RATIO`** — `0..1`, default `1.0` (100%). Distros default to a silent
  rate-limited sampler (~5 traces/sec) that this repo explicitly overrides; an invalid value
  (non-numeric or outside `[0,1]`) logs a warning and falls back to `1.0`. **`OTEL_TRACES_SAMPLER`
  / `OTEL_TRACES_SAMPLER_ARG` take precedence** when set — Node's distro merges env config after
  code options; Python's `resolve_sampling_ratio()` returns `None` (skips the kwarg entirely) so
  the standard OTel env config isn't shadowed.
- **`TELEMETRY_AUTH_MODE`** — `""` / `connection_string` / `managed_identity` are the only valid
  values. A **mistyped value disables observability VISIBLY**: `enabled: false` with a reason
  string `invalid TELEMETRY_AUTH_MODE "<value>" — expected "connection_string" or "managed_identity"`
  surfaced on `/health` and a loud startup warning — **never** a silent fallback to unauthenticated
  ingestion. Validated _before_ the connection-string check in both services.
- **`TELEMETRY_MANAGED_IDENTITY_CLIENT_ID`** — only read when `TELEMETRY_AUTH_MODE=managed_identity`;
  passed to `ManagedIdentityCredential({ clientId })`. Requires the identity to hold **Monitoring
  Metrics Publisher** on the App Insights component (granted via `infra/main.bicep`).
- **`OTEL_SERVICE_NAME` / `OTEL_RESOURCE_ATTRIBUTES`** — defaults are **appended, never
  overridden**: code checks whether `OTEL_SERVICE_NAME` is unset _and_ `service.name=` isn't
  already present in `OTEL_RESOURCE_ATTRIBUTES` before defaulting it; same logic for
  `service.instance.id` (sourced from `CONTAINER_APP_REPLICA_NAME` → `HOSTNAME` → OS hostname).
- **`APP_ENV`** — drives both the trace_id env nibble (`local=0 dev=1 staging=2 prod=3
sandbox=4`) and the `env` field on every log line. Both services implement the `sandbox=4`
  mapping (not merely reserved in code, despite the "reserved" wording in some comments/CLAUDE.md)
  — it's simply not emitted unless `APP_ENV=sandbox` is actually set.
- **`DATABASE_URL`** — consumed only by `apps/api`: `app/db/engine.py` builds the lazy
  `AsyncEngine` from it (via `app.config.get_settings()`), and `alembic/env.py` reads it through
  the same settings object (the URL is never in `alembic.ini`). Nothing connects until the first
  query, so the placeholder in `.env.example` never blocks boot. No migrations are run against it
  by the project. **Spelling matters:** `mssql+aioodbc://` and the ODBC keywords in the query
  string (`driver=ODBC+Driver+18+for+SQL+Server`, `Encrypt=yes`, `TrustServerCertificate=no`,
  optionally `Authentication=…`) — SQLAlchemy forwards them to the ODBC connection string.
- **`EXTERNAL_DATABASE_URL`** — consumed only by `apps/api/app/db/external.py`, the second
  read-only engine. No placeholder on purpose; unset means "this project has no external
  source". Same URL shape; never logged.
- **`API_BASE_URL`** — the BFF's upstream base URL for the FastAPI `api` service. Server-side
  only, by the BFF rule (`.claude/rules/30-nextjs.md`) — never expose as `NEXT_PUBLIC_*`.
  **History:** the former **NestJS** `apps/api` (removed in
  [ADR-0003](../adr/0003-remove-nestjs-api-layer.md)) used an identically named variable, which
  was retired with it; [ADR-0005](../adr/0005-name-services-by-role.md) reintroduced the name
  for the new `api` (replacing `PYTHON_BASE_URL`). A value carried over in a local `.env` from
  before ADR-0003 points at the old NestJS port (`:3001`) — set it to `http://localhost:8000`
  (or drop it and take the default).
- **`PORT`** — each service's own listen port; `docker-compose.yml` hardcodes it per service
  (`3000`/`8000`) rather than templating from `.env`.

## Mismatches found (in code but not in `.env.example`, or vice versa)

- **`LOG_LEVEL`** — read by `apps/web/src/lib/logger.ts` (`process.env.LOG_LEVEL ?? 'info'`) to
  set the pino log level, but it appears in **no** `.env.example` (root or web) and is **not**
  passed through by `docker-compose.yml`. Currently only exercised via the test setup file
  (`apps/web/vitest.setup.ts` sets it to silence logs during tests). `apps/api` has no
  equivalent — structlog's level is hardcoded to `INFO`.
- **`TELEMETRY_MANAGED_IDENTITY_CLIENT_ID`** — documented in every `.env.example` file but
  **not forwarded by any service block in `docker-compose.yml`** (only `TELEMETRY_AUTH_MODE` is
  passed through). A compose deployment with `TELEMETRY_AUTH_MODE=managed_identity` and a
  user-assigned identity would need this added to the relevant service's `environment:` block.
- **`API_BASE_URL` in `apps/api`** — `apps/api/app/metrics.py` reads it via
  `os.environ.get(...)` to resolve the bounded `target` label (`api` | `other`) for the
  (currently unused) hop-duration metric, but it appears neither in `apps/api/.env.example`
  nor in the `api` service block of `docker-compose.yml`. Harmless today (the api makes no
  downstream calls in the baseline, so `resolve_target()` always collapses to `"other"`), but
  worth adding to the example if/when the api gains outbound calls.
- **`WEB_BASE_URL`** — read by `apps/web/playwright.config.ts:17` (`http://localhost:3000`
  default) to target the manual Playwright e2e suite. Not a service runtime var and not in any
  `.env.example` — it's a local test-harness convenience, not part of the app's env contract.
- **`OTEL_RESOURCE_ATTRIBUTES`, `OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG`,
  `CONTAINER_APP_REPLICA_NAME`** — all read in code (see table above) but intentionally absent
  from the `.env.example` files; they're standard OTel/Azure-platform knobs documented only in
  source comments, not part of the local-dev quick-start.
- **`NEXT_RUNTIME`** — read by `apps/web/src/instrumentation.ts:10` to gate observability init to
  the Node.js runtime. This is a **Next.js-provided** variable, not user-configurable, so it's
  intentionally absent from `.env.example` and the master table above.

## `.env` handling

- **Precedence** — ambient/shell environment always wins over a loaded `.env` file, in both
  services (verified: Next's `.env` loading and the api's `load_local_env()` — `python-dotenv`
  with `override=False` — both skip already-set keys). This is why deployed environments (Docker Compose `environment:`, Azure
  Container Apps) always take effect even if a stray `.env` were present.
- **`apps/web`** — Next.js' native `.env.local` / `.env` loading (no custom loader code).
- **`apps/api`** — `app/main.py` calls `load_local_env()` (`app/config.py`) first thing,
  which loads `apps/api/.env` **if it exists** and is a no-op otherwise; the file is
  optional, so `make dev` / `just dev` run without it. Compose supplies env through its
  `environment:` block instead.
- **Containers never ship a `.env`** — each app's `.dockerignore` excludes `.env` / `.env.*`
  (keeping `!.env.example`), so only the placeholder example ever reaches a build context; real
  values are injected by the container platform (Docker Compose `environment:`, Azure Container
  Apps / Key Vault in deployed environments).
- **`docker-compose.yml`** reads the root `.env` (copied from root `.env.example`) for `${VAR}`
  substitution and passes the resolved values into each service's `environment:` block — not
  every var is forwarded to every service (see the master table's "compose" column and the
  mismatches above for exceptions).
