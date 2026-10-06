# Coding standards

What code in this repo has to look like and behave like. The cross-service rules are
non-negotiable — they are what makes two services in two languages behave as one system.
The per-service sections are the local expression of those rules plus each framework's own
conventions.

The enforced, path-scoped form of all of this lives in
[`.claude/rules/`](../../.claude/rules/) — `25-sqlalchemy.md`, `30-nextjs.md`, `35-fastapi.md`,
`50-security.md`, `60-observability.md`. This document is the explanation; those are the
checklist.

---

## Cross-service non-negotiables

### 1. Structured logging only

Every log line goes through the service's configured logger — **pino** in `web`
(`src/lib/logger.ts`), **structlog** in the `api` (`get_logger(...)` from
`app/logging_config.py`). Never `console.log`, never `print()`. Both are review-blocking in
committed code.

The loggers emit JSON to stdout carrying `timestamp`, `level`, `service`, `origin`, `env`,
`trace_id`, `message`. The `trace_id` is injected automatically from the request scope (the
`log()` helper reading the async-local store in `web`, a structlog processor in the `api`) —
you do not pass it by hand _inside_ a request. Outside the request scope (a background task,
a shutdown hook) pass `{ trace_id }` explicitly.

### 2. Traced HTTP wrappers only

There is exactly one sanctioned outbound HTTP client per service. Using a bare client is a
review-blocking violation:

| Service    | Wrapper                       | Defined in                                            |
| ---------- | ----------------------------- | ----------------------------------------------------- |
| `apps/web` | `fetchUpstream(url, traceId)` | [`src/lib/trace.ts`](../../apps/web/src/lib/trace.ts) |
| `apps/api` | `traced_client(**kwargs)`     | [`app/tracing.py`](../../apps/api/app/tracing.py)     |

They forward `x-trace-id` unchanged, log both sides of the call, and record the upstream-hop
metric; the W3C `traceparent` header and the dependency span come from the instrumentation
layer beneath them (undici for Node, httpx for Python).

Always give an outbound call a **timeout** — never an unbounded wait. Never build an outbound
URL from unvalidated user input; allowlist hosts (SSRF).

### 3. Redaction happens at source — know what it covers

A default set of secret-bearing fields (`authorization`, `cookie`, `set-cookie`, `x-api-key`,
`token`, `access_token`, `refresh_token`, `id_token`, `password`, `secret`, `client_secret`,
`api_key`/`apiKey`, `connection_string`/`connectionString`) is replaced with `[redacted]`
**during serialization, before any sink** — local stdout or Azure — sees the line.

Two practical consequences:

- **Node matches exact paths**, top level plus one level deep (pino `redact`). A secret nested
  three levels down, or under a non-standard key, will **not** be caught. Extend the list per
  logger: `buildLogger({ redactPaths })` in Node,
  `configure_logging(extra_redacted_fields={...})` in Python (which matches
  case-insensitively with `-`/`_` normalised, recursively).
- Redaction is a safety net, **not a licence to log secrets**. Do not put credentials in a log
  call and rely on the filter.

If something leaks anyway, follow
[`docs/operations/runbooks/pii-purge.md`](../operations/runbooks/pii-purge.md).

### 4. Every new env var is documented

A new variable is not done until it has a **placeholder entry with an explanatory comment** in
every `.env.example` that needs it — root [`.env.example`](../../.env.example) and/or
`apps/<svc>/.env.example` — plus a row in the root README's
[_Environment variables_](../../README.md#environment-variables) table, plus a
`${VAR:-default}` entry in [`docker-compose.yml`](../../docker-compose.yml) if containers need
it.

Never commit a real secret. Local values live in gitignored `.env` files; deployed values come
from Azure Key Vault. Review your own diff for high-entropy strings (`AKIA`, `sk-`, `ghp_`,
`eyJ…`).

Read config via `process.env.*` / the Python `Settings` object (`app/config.py`).

### 5. API versioning is mandatory

Every **business** HTTP endpoint is URI-versioned: `/v1`, later `/v2`. One version segment,
lowercase `v` + integer, as the **first** path segment of the service-local path — no `/v1.0`,
no header or media-type versioning ([ADR-0001](../adr/0001-api-versioning.md)).

The **only** exemption is the operational trio `/ping`, `/info`, `/health`, which stays
unversioned because container and Azure health probes target fixed paths. Adding to that list
is an ADR change, not a code change.

### 6. No PII in logs, span attributes, or metric attributes

No emails, names, tokens, or identifiers in log fields or telemetry attributes. Beyond
privacy, telemetry attributes have a hard technical constraint:

**Cardinality discipline.** Metric _and_ custom-event attributes use **bounded value sets
only** — route patterns/classes, HTTP methods, status classes (`2xx`…`5xx`), outcomes
(`error`, `network_error`, `http_5xx`), bounded targets (`api`/`other`). Never ids,
names, emails, or paths containing parameter values: `/things/42` is a violation,
`/things/{id}` is correct. Application Insights bills every attribute combination as its own
series and caps at 5,000 series per metric per day.

This is why `withBff` accepts a `routeClass` option — a handler under a dynamic segment must
pass its **pattern**, not the concrete URL.

### 7. Telemetry never blocks a request

Export is batched and non-blocking; the local stdout write happens first and can never be
broken by the export bridge. **Never `await` a telemetry export inside a request handler.**
In degraded mode the OTel API returns no-op meters and loggers, so record unconditionally —
do not null-check telemetry.

### 8. Fail-safe over fail-fast for observability

A missing or empty `APPLICATIONINSIGHTS_CONNECTION_STRING` means degraded mode: skip remote
export, print the startup warning, report `"observability": "disabled"` on `/health` — and
**keep running**. Never hard-fail on its absence. Telemetry init is wrapped in try/catch and
guarded by a process-global flag so it is idempotent.

---

## Formatting and linting

One command formats the whole repo:

```bash
make fmt        # or: just fmt   — runs pnpm install, then pnpm run fmt
```

which is:

```
prettier --write .                          # JS / TS / JSON / Markdown
uvx ruff@0.15.16 format apps/api         # Python formatting
uvx ruff@0.15.16 check --fix apps/api    # Python linting, autofixable rules
```

**Prettier** ([`.prettierrc`](../../.prettierrc)): semicolons, single quotes, trailing commas
everywhere, `printWidth: 100`, 2-space tabs, LF line endings.
[`.prettierignore`](../../.prettierignore) excludes lockfiles, build output, generated code —
and **all Python**, which ruff owns exclusively.

**Ruff** (configured in [`apps/api/pyproject.toml`](../../apps/api/pyproject.toml)):
`line-length = 100`, `target-version = "py314"`, rule selection `["E", "F", "I", "UP", "B"]`
(pycodestyle errors, pyflakes, import sorting, pyupgrade, bugbear). Ruff is also a dev
dependency, so `uv run ruff format app && uv run ruff check app` works from `apps/api`.

Prose in Markdown wraps at roughly 100 columns to match.

---

## `apps/web` — Next.js (BFF + UI)

See [`.claude/rules/30-nextjs.md`](../../.claude/rules/30-nextjs.md) and
[`apps/web/CLAUDE.md`](../../apps/web/CLAUDE.md).

**The BFF rule (non-negotiable).** The browser talks **only** to this Next server. Client code
calls **same-origin** route handlers under `src/app/api/*`; those handlers call the `api`
server-side using `API_BASE_URL`. Never expose a service base URL
or a secret to client code, and **never** use `NEXT_PUBLIC_*` for either. BFF handlers
validate and shape what they forward — do not proxy an arbitrary client-supplied URL.

**Server Components by default.** Routes live under `src/app/`: `page.tsx`, `layout.tsx`, and
route handlers `route.ts`. Add `'use client'` **only** when you need state, effects, refs, or
browser APIs — and keep those components as small as possible. Logic that needs test coverage
belongs in `src/lib/`, not in `page.tsx`/`layout.tsx`, which are excluded from the coverage
gate by design (see [testing](testing.md#coverage)).

**Route handlers.** Wrap the handler body in **`withBff`** — it adopts or generates
`x-trace-id`, runs inside the `AsyncLocalStorage` scope, echoes the header on the response,
and records the request-duration metric. Pass `{ routeClass: '/api/v1/things/[id]' }` for
dynamic segments. Call upstreams with **`fetchUpstream`**. On upstream failure return a
**`502` JSON body that includes `trace_id`** so the UI degrades gracefully.

**Init order.** Next.js evaluates its own server before any module of yours, so a first-import
cannot work — observability initialises in the framework hook
[`src/instrumentation.ts`](../../apps/web/src/instrumentation.ts) `register()`, guarded to
`process.env.NEXT_RUNTIME === 'nodejs'`. That file lives in **`src/`** because this is a
src-dir app. Note also that Next can place `instrumentation.ts` and route bundles in
**separate module graphs**, which is why `getObservabilityState` re-derives state from env
inside route handlers rather than trusting an init flag.

**Build config.** [`next.config.ts`](../../apps/web/next.config.ts) sets
`output: 'standalone'`, lists the Azure/OTel/pino packages in `serverExternalPackages` (to
avoid bundling conflicts), and pins `turbopack.root` + `outputFileTracingRoot` to the app
directory — sibling lockfiles otherwise confuse Next's root inference. Do not run a production
`next build` and then `next dev` against the same `.next`; delete it when switching modes.

**Not present yet:** no auth, no global client-state library, no mandated UI kit. Introducing
any of them needs an ADR (auth additionally needs a threat model).

---

## `apps/api` — FastAPI

See [`.claude/rules/35-fastapi.md`](../../.claude/rules/35-fastapi.md) and
[`apps/api/CLAUDE.md`](../../apps/api/CLAUDE.md).

**Structure.** [`app/main.py`](../../apps/api/app/main.py) is an app factory plus a
module-level `app` (so `uvicorn app.main:app` works). Business routers go in
`app/routers/<feature>.py` and attach to `v1_router` (`app/routers/v1.py`, `prefix="/v1"`).
`app/routes.py` is the **operational exemption** — `/ping`, `/health`, `/info` only; never add
a business route there. Cross-cutting modules (`tracing.py`, `observability.py`,
`logging_config.py`, `metrics.py`, `events.py`, `config.py`) implement the cross-service
contract; the database layer lives in `app/db/` with models in `app/models/` and migrations in
`alembic/`.

**`create_app()` order matters.** Inside the factory: `init_observability(app)` runs **before**
instrumentation-aware middleware is added, then `TraceMiddleware`, then the routers
(operational at the root, `v1_router` for business). And `configure_logging()` runs at module
import, **before anything else logs**. Unlike Node, Python instrumentation here is explicit
(`configure_azure_monitor` + `FastAPIInstrumentor.instrument_app` + `HTTPXClientInstrumentor` +
`SQLAlchemyInstrumentor`), so there is no import-order fragility for HTTP — but the sequence
inside `create_app()` still has to hold, and the DB engine factories resolve
`create_async_engine` at call time so the SQLAlchemy wrapper applies to them. The `lifespan`
awaits `dispose_engine()` on shutdown.

**Database (SQLAlchemy 2 async + Alembic).** Routes get a DB handle **only** via
`session: Annotated[AsyncSession, Depends(get_session)]` (`app/db/session.py`). Models are
2.0-style — `class Widget(Base)` from `app.db`, `Mapped[...]` + `mapped_column(...)`, explicit
snake_case plural `__tablename__` — and are imported in `app/models/__init__.py` so Alembic
autogenerate sees them. Query with ORM constructs or `text()` with bound parameters. The engine
(`get_engine()`) is a lazy singleton: **never connect at import or startup**, never create a
sync `create_engine`/`Session`, never hold a module-level session. `DATABASE_URL` is
`mssql+aioodbc://…?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no`
(Azure SQL — never a local database) and is never written into `alembic.ini`. External data is
read through `Depends(get_external_session)` — read-only by construction.
Migrations are authored with `alembic revision --autogenerate` (needs a dev DB), reviewed with
`alembic upgrade head --sql` (no DB), and **applied only by a human**. Details:
[`.claude/rules/25-sqlalchemy.md`](../../.claude/rules/25-sqlalchemy.md),
[architecture → data](../architecture/data.md).

**Style.** Type-hint everything. Start every module with `from __future__ import annotations`.
Ruff formats and lints at line length 100.

**Request scope.** Read the trace id with `get_trace_id()` (a `contextvars` lookup);
`TraceMiddleware` has already adopted or generated it and will echo it.

**Dependencies.** Pin exact versions in `pyproject.toml`; use `uv sync` / `uv run`. The
OpenTelemetry versions are **pinned by the Azure distro** — `azure-monitor-opentelemetry==1.8.8`
hard-pins `opentelemetry-sdk==1.40`, `opentelemetry-api==1.40.0`, and every instrumentation
package to `==0.61b0`. Do not bump those independently; let the distro drive them. Renaming
the project requires re-running `uv lock`, because the lockfile records the project's own
package name.

---

## Forbidden

A consolidated list. Each of these is a blocking review failure.

| Forbidden                                                                                | Do this instead                                                                           |
| ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| `console.log` / `print()` in committed code                                              | The pino logger / structlog `get_logger(...)`                                             |
| Bare `fetch` / `httpx` for an outbound call                                              | `fetchUpstream` · `traced_client()` — with a timeout                                      |
| An unversioned **business** endpoint                                                     | `/v1/...` in every service (only `/ping`, `/info`, `/health` are exempt)                  |
| Adding an endpoint to the unversioned exemption list                                     | Write an ADR first                                                                        |
| `NEXT_PUBLIC_*` for a service base URL or any secret                                     | Server-side env only; the browser calls same-origin BFF routes                            |
| Calling the `api` directly from the browser                                              | Go through a `web` BFF route handler                                                      |
| PII in log fields, span attributes, or metric/event attributes                           | Bounded, non-identifying values only                                                      |
| Unbounded metric/event attribute values (ids, emails, `/things/42`)                      | Route patterns and bounded classes (`/things/{id}`, `2xx`, `api`)                         |
| `await`ing a telemetry export in a request handler                                       | Record and move on — export is batched and non-blocking                                   |
| Hard-failing when `APPLICATIONINSIGHTS_CONNECTION_STRING` is missing                     | Degrade: warn, report `disabled` on `/health`, keep running                               |
| A business route added to `app/routes.py`                                                | A router in `app/routers/<feature>.py` attached to `v1_router`                            |
| A sync `create_engine` / `Session`, or a module-level `AsyncSession`                     | `get_engine()` + `Depends(get_session)` — one `AsyncSession` per request                  |
| Connecting to the database at import or startup                                          | Stay lazy; the first query opens the first connection                                     |
| `TrustServerCertificate=yes` / `Encrypt=no` in `DATABASE_URL`, or a URL in `alembic.ini` | `mssql+aioodbc://…&Encrypt=yes&TrustServerCertificate=no`, read from env via `app.config` |
| String-built SQL with user input (f-strings, `%`)                                        | ORM constructs, or `text()` with bound parameters                                         |
| Running `alembic upgrade` from an agent                                                  | A human applies migrations, after offline `--sql` review                                  |
| `pnpm --filter`                                                                          | `pnpm -C apps/<app> …` — there is no workspace                                            |
| Committing a real secret or a `.env` file                                                | Placeholders in `.env.example`; real values from Key Vault                                |
| Bumping the Python OTel instrumentation pins independently                               | Let `azure-monitor-opentelemetry` drive them                                              |
| Running `next dev` against a `.next` from a production build                             | Delete `.next` when switching modes                                                       |
| A container running as root in the final stage                                           | Keep the non-root user (`node` / `appuser`)                                               |
