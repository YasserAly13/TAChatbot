---
description: OpenTelemetry + structured-logging contract. Always loaded.
paths:
  - '**/*'
---

# Observability contract

> **Graded autonomy:** these are conventions to apply _within_ an approved plan or roadmap item — not a licence to act outside one. Hard stops (infra apply, migration apply, push, secrets, deletes) always need explicit confirmation — see [`CLAUDE.md`](../../CLAUDE.md) → _Graded autonomy_.

OpenTelemetry → **Azure Monitor / Application Insights / Log Analytics**. Same code path local
and deployed; config from `APPLICATIONINSIGHTS_CONNECTION_STRING`. **No local monitoring stack.**
Full detail in [`README.md`](../../README.md).

## The contract (every request, every service)

1. **trace_id** — adopt valid inbound `x-trace-id` else generate with the service origin
   (`web=0eb0`, `api=0c70`; `0a71` is retired — it belonged to the former NestJS api removed in ADR-0003, not to today's FastAPI `api`, see ADR-0005); store request-scoped (Node
   `AsyncLocalStorage`, Python `contextvars`); forward on every outbound call; echo on the
   response.
2. **Structured JSON logs to stdout, always** — every line carries `timestamp`, `level`,
   `service`, `origin`, `env`, `trace_id`, `message`. Node: **pino** (`src/lib/logger.ts`,
   `trace_id` via `mixin`). Python: **structlog** (`logging_config.py`).
3. **trace_id on the active span** — set as the `trace_id` span attribute (the OTel trace id is
   distinct; we correlate via this attribute + the log field).

There is **no `@Span` decorator** here. Spans come from framework auto-instrumentation
(`@azure/monitor-opentelemetry` for Node, `configure_azure_monitor` + FastAPI/httpx/SQLAlchemy
instrumentation for Python). Inbound/outbound logging is done in the trace middleware and the
traced HTTP helpers.

## Init-order discipline (per runtime — Phase 0)

Telemetry init must run **before any HTTP-server / HTTP-client / DB library loads**, or
auto-instrumentation silently patches nothing. The mechanism per service:

| Service | Mechanism                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `web`   | **Framework hook**: Next.js evaluates its own server first, so a first-import can't work — init runs in `src/instrumentation.ts` `register()` (nodejs runtime only), which Next runs once per server instance before serving requests.                                                                                                                                                                                                                                                                                               |
| `api`   | **Explicit instrumentation**: `init_observability(app)` inside `create_app()` calls `configure_azure_monitor()` then `FastAPIInstrumentor.instrument_app(app)` + `HTTPXClientInstrumentor().instrument()` + `SQLAlchemyInstrumentor().instrument()` — no import-order fragility for HTTP; for the DB the instrumentor is registered WITHOUT an engine so it wraps `create_async_engine`, and both lazy engines resolve that function at call time (`sa_asyncio.create_async_engine`), so DB spans are covered from the first query). |

**Idempotent init (required):** init is guarded by a process-global flag in both services
(Node: `Symbol.for` registry on `globalThis`; Python: module flag) — calling init twice, or a
second module copy/graph loading, must never double-register the SDK. Covered by unit tests
(`observability.test.ts` / `test_observability_config.py`).

## Sampling — pinned explicitly (required)

**Never rely on the distro default.** `@azure/monitor-opentelemetry` ≥ 1.16.0 and
`azure-monitor-opentelemetry` ≥ 1.8.6 default to **rate-limited sampling (~5 traces/sec)** — a
silent telemetry cap. Every service pins a **fixed-percentage sampler** at init:

- Default ratio **1.0 (100%)**, tunable via **`TRACE_SAMPLING_RATIO`** (0..1, documented in the
  `.env.example`s). Invalid values warn and fall back to 1.0.
- Node passes `samplingRatio` **and `tracesPerSecond: 0`** (without the 0, the rate-limited
  default still wins). Python passes `sampling_ratio`.
- The standard **`OTEL_TRACES_SAMPLER` / `OTEL_TRACES_SAMPLER_ARG` env vars take precedence**:
  Node's distro merges env config after code options; Python skips the kwarg when
  `OTEL_TRACES_SAMPLER` is set (a kwarg would otherwise shadow it).

## Cloud role identity (required)

Each service's OTel resource carries `service.name` (→ App Insights **cloud role name**) and
`service.instance.id` (→ **cloud role instance**), defaulted via the standard env vars
(`OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES`) that both distros' env resource detectors
read:

- Defaults: `service.name` = `team-assistant-web|api`; `service.instance.id` = container
  replica name (`CONTAINER_APP_REPLICA_NAME`) → `HOSTNAME` → os hostname.
- **Append-only:** operator-provided `OTEL_SERVICE_NAME` / `OTEL_RESOURCE_ATTRIBUTES` values are
  **never overridden**. Do **not** set `service.namespace` (it would switch App Insights to the
  `namespace.name` display format).

## Auto-instrumentation inventory (Phase 0 — drives roadmap Phases 1–3)

What each service gets automatically vs. what is missing, with the installed distros
(`@azure/monitor-opentelemetry` 1.18.1, `azure-monitor-opentelemetry` 1.8.8). _auto_ = expected
from code inspection; runtime proof against a real App Insights resource is still pending
(roadmap Phase 0/6 [HUMAN]).

| Signal                                                  | `web` (Next.js BFF)                                                                                                                             | `api` (FastAPI)                                                                                                                                                                                                                                                                                                                                                                                                 |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Server request spans (`AppRequests`)                    | **auto** — distro `http` instrumentation (init via `register()`)                                                                                | **auto** — explicit `FastAPIInstrumentor.instrument_app`                                                                                                                                                                                                                                                                                                                                                        |
| Outbound HTTP spans (`AppDependencies`)                 | **closed (manual, Phase 2)** — undici instrumentation registered at init covers global `fetch` (`fetchUpstream`)                                | **auto** — `HTTPXClientInstrumentor` covers `traced_client` (httpx)                                                                                                                                                                                                                                                                                                                                             |
| DB spans (`AppDependencies`)                            | n/a (no DB)                                                                                                                                     | **closed (manual, unverified at runtime)** — `opentelemetry-instrumentation-sqlalchemy` (0.61b0, distro line) registered explicitly at init without an engine (covers the project + external `mssql+aioodbc` engines); the distro's default set has nothing for them. Decision in [ADR-0008](../../docs/adr/0008-azure-sql-data-layer.md); prove during Phase 6 (no queries exist in the placeholder model set) |
| Logs (`AppTraces`)                                      | **bridged (manual, Phase 1)** — pino is not collected by the distro, so every line is teed through the OTel Logs API (`src/lib/logger.ts`)      | **bridged (manual, Phase 1)** — structlog bypasses stdlib `logging`, so every event is mirrored into the stdlib `app.telemetry` logger where the distro's handler sits (`app/logging_config.py`)                                                                                                                                                                                                                |
| Runtime metrics (`AppPerformanceCounters`/`AppMetrics`) | **auto + manual (Phase 3)** — distro perf counters, plus runtime-node instrumentation (event-loop lag/utilization, GC, heap) registered at init | **auto + manual (Phase 3)** — distro perf counters, plus system-metrics instrumentation (runtime-only selection: GC, memory, CPU, threads)                                                                                                                                                                                                                                                                      |
| Custom metrics/events                                   | **implemented (Phase 3)** — `src/lib/metrics.ts` + `src/lib/events.ts`                                                                          | **implemented (Phase 3)** — `app/metrics.py` + `app/events.py`                                                                                                                                                                                                                                                                                                                                                  |

## Log pipeline (Phase 1 — required)

The structured stdout line is the source of truth; export is a **tee**, never a replacement.

- **Export bridge (per service).** The distros don't collect our loggers, so each service
  bridges explicitly — Node (`web`): every serialized pino line is re-emitted through the
  **OTel Logs API** (`@opentelemetry/api-logs`; the distro's NodeSDK registers the global
  LoggerProvider). Python: every structlog event is mirrored into the stdlib logger
  **`app.telemetry`**, which propagates to `app` where
  `configure_azure_monitor(logger_name="app")` attached its handler. Bridged records are
  emitted synchronously inside the request context, so they inherit the **active span context**
  (`AppTraces.operation_Id` matches `AppRequests`) in addition to the mandatory `trace_id`
  field.
- **Fail-safe.** The bridge is a no-op in degraded mode and any bridge/export error is
  swallowed — the local stdout write happens first and can never be broken by the bridge.
  Per-logger opt-out: `buildLogger({ telemetryBridge: false })` (Node) / bind
  `telemetry_export=False` (Python).
- **Redaction at source (required).** The default secret-bearing fields — `authorization`,
  `cookie`, `set-cookie`, `x-api-key`, `token`, `access_token`, `refresh_token`, `id_token`,
  `password`, `secret`, `client_secret`, `api_key`/`apiKey`,
  `connection_string`/`connectionString` — are replaced with **`[redacted]`** during
  serialization, **before any sink** (stdout or Azure) sees the line. Node matches exact paths
  (top level + one level deep, via pino `redact`); Python matches case-insensitively with
  `-`/`_` normalized, recursively. Extend per logger via `buildLogger({ redactPaths })` (Node)
  or `configure_logging(extra_redacted_fields={...})` (Python). Never log `DATABASE_URL`.
  Accidental leak anyway? →
  [`docs/operations/runbooks/pii-purge.md`](../../docs/operations/runbooks/pii-purge.md).
- **Non-blocking sinks.** Node writes stdout through `pino.destination({ sync: false })`;
  Python hands rendered lines to a queue drained by a daemon writer thread. Both flush
  synchronously best-effort at process exit (`process.on('exit')` → `flushSync` / `atexit` →
  `flush_logs`) so shutdown lines aren't lost. Remote export stays batched (distro defaults).
- **Stream discipline.** Both services use stdout as a pure log channel today — neither
  speaks a protocol over stdout. If a future mode ever does (e.g. an MCP-style stdio server),
  its logs MUST move to stderr. (The Alembic CLI logs plain text to stderr via `alembic.ini`;
  it never runs inside the service process.)

## Distributed traces (Phase 2 — required)

- **One traced outbound wrapper per service — bare HTTP clients are FORBIDDEN** (a
  review-blocking violation): `fetchUpstream` (web, `src/lib/trace.ts`), `traced_client()`
  (api, `app/tracing.py`). The wrapper carries the repo's `x-trace-id`; the W3C
  `traceparent` header and the `AppDependencies` span come from the instrumentation layer
  below it.
- **Node fetch gap is closed manually.** The Azure distro does NOT instrument undici/global
  `fetch` (verified in 1.18.1 — its set is azureSdk/http/mongoDb/mySql/postgreSql/redis), so
  web registers `@opentelemetry/instrumentation-undici` (+ `instrumentation-runtime-node`)
  at init, pinned to the distro's `@opentelemetry/instrumentation@0.218.0` line. It hooks
  `diagnostics_channel`, so registering after undici has loaded (the Next.js case) still works.
- **DB spans come from SQLAlchemy engine instrumentation** (`opentelemetry-instrumentation-sqlalchemy`
  on the distro's `0.61b0` line, registered in `app/observability.py` **without an engine**) over
  the lazy `mssql+aioodbc` engines (project + external read-only). Never register it per engine
  (`engine=`): the instrumentor's singleton guard would silently skip the second engine. Decision
  - trade-offs: [ADR-0008](../../docs/adr/0008-azure-sql-data-layer.md) (supersedes ADR-0004's
    driver-level approach).
- **End-to-end proof pending [HUMAN]:** one `/api/ping-backend` request (web → api) must
  show a single `operation_Id` across `AppRequests`/`AppDependencies`/`AppTraces` with the
  Application Map edge drawn — run during the Phase 6 smoke once a real resource exists.
- **[GATED: auth] user attribution:** when auth lands, tag authenticated request spans with
  `enduser.id` (→ `user_AuthenticatedId`) — and keep all other PII out of attributes.

## Metrics & events (Phase 3 — required)

- **Meter accessor:** `getMeter(scope)` / `get_meter(scope)` returns the namespaced meter
  `team-assistant.<scope>` (`src/lib/metrics.ts` · `app/metrics.py`). In degraded mode the OTel
  API returns a no-op meter — record unconditionally, never null-check telemetry. All record
  helpers are best-effort and never throw into the request path.
- **CARDINALITY DISCIPLINE (written rule — enforced in `/code-review`):** metric AND event
  attributes use **bounded value sets only** — route patterns/classes, methods, status classes
  (`2xx`..`5xx`), outcomes (`error`, `network_error`, `http_5xx`), bounded targets
  (`api`/`other`). **Never** ids, names, emails, or paths with parameter values
  (`/things/42` is a violation; `/things/{id}` is correct). App Insights bills every attribute
  combination as its own series and caps at 5,000 series/metric/day.
- **Starter set (implemented):** `team-assistant.http.server.duration` histogram (ms; per-service
  request duration by `route_class`/`method`/`status_class` — recorded in each trace
  middleware/wrapper) · `team-assistant.http.client.hop.duration` histogram (hop duration by
  `target`/`outcome` — recorded in the traced outbound wrappers) ·
  `team-assistant.bff.upstream.failures` counter (web only; `target` × `network_error`/`http_5xx`).
- **Runtime metrics:** Node registers `instrumentation-runtime-node` (event-loop lag/utilization,
  GC, heap) at init; the api registers the system-metrics instrumentor with a **runtime-only**
  selection (`process.*`/`cpython.*` — host-wide disk/network series are deliberately excluded).
- **Custom events:** `trackEvent(name, attrs)` / `track_event(name, attrs)` (`src/lib/events.ts`
  · `app/events.py`) emits an App Insights `customEvents` row via a log record carrying
  `microsoft.custom_event.name` (both exporters map it). Fail-safe: degraded mode → local
  structured line only; the local line always prints (bridge opt-out prevents double export).
  One event is wired: `service.start` in each service's bootstrap. Attributes follow the
  cardinality/no-PII rules above.

## Ingestion auth (Phase 4 hardening)

- **`TELEMETRY_AUTH_MODE`** (both services): empty/`connection_string` = default
  connection-string ingestion; `managed_identity` = Microsoft Entra ID ingestion via
  `ManagedIdentityCredential` (user-assigned via `TELEMETRY_MANAGED_IDENTITY_CLIENT_ID`).
  Requires **Monitoring Metrics Publisher** on the App Insights component — granted by
  `infra/main.bicep` (`telemetryPublisherPrincipalIds`), which can then set `DisableLocalAuth`
  to reject unauthenticated senders entirely.
- **A mistyped value degrades VISIBLY:** observability is disabled with the reason
  (`invalid TELEMETRY_AUTH_MODE …`) on `/health` and a loud startup warning — **never** a
  silent fallback to unauthenticated ingestion. Unit-tested in both services.
- Rollout order (before flipping `DisableLocalAuth`): grant roles → set the env var → verify
  telemetry flows → flip. Full procedure: [`infra/README.md`](../../infra/README.md).

## Fail-safe (required)

- Wrap telemetry init in try/catch. Missing/empty connection string ⇒ skip remote export, **do
  not crash**, print the WARNING `Observability disabled: no Azure connection string — running
with local stdout logging only`, and report `"observability": "disabled"` on `/health`.
- Export is **batched / non-blocking** — telemetry never sits in the request hot path.
- Triaging a degraded/silent service:
  [`docs/operations/runbooks/observability-degraded.md`](../../docs/operations/runbooks/observability-degraded.md)
  (reason-by-reason fixes) · verification after deploys:
  [`docs/operations/runbooks/post-deploy-smoke.md`](../../docs/operations/runbooks/post-deploy-smoke.md)
  · queries: [`docs/operations/kql-starter-pack.md`](../../docs/operations/kql-starter-pack.md).

## Forbidden

- `console.log` / `print()` in committed code — use the structured logger.
- PII in span attributes or log fields (no emails, names, tokens, `DATABASE_URL`).
- Blocking `await` on a telemetry export in a request handler.

## When to invoke `observability-instrumenter`

Any new HTTP route, outbound call, DB-backed operation, or background operation that isn't yet
logged + trace-propagated.
