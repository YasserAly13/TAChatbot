# Observability Roadmap — Application Insights completion

> **Update 2026-10-04 — the Bicep stack is the implementation (ADR-0012).** The Phase 4/5
> modules (`infra/modules/{observability,alerts,availability}.bicep`) are now called from the
> use-case `infra/main.bicep` on the cloud team's shared platform; the 2026-09-28 Terraform port
> was reverted with the rest of Terraform. Parameter names below are the Bicep ones
> (`dailyIngestionAlertThresholdGb`, `logAnalyticsDailyCapGb`, `disableLocalTelemetryAuth`, …).
> The database alert rules still target Postgres and are skipped (`postgresServerId: ''`) —
> Azure SQL rules are tracked in [`docs/template-roadmap-bicep.md`](docs/template-roadmap-bicep.md) → 2.8.
>
> **Status 2026-08-02 — implementation complete; execution proofs in progress.** Every
> implementable item in Phases 0–6 is done, tested, and documented. The infra template was
> deployed against a real sandbox resource group (2026-08-02) and the apps ran locally against
> the resulting Application Insights resource. Still open: the Phase 2 **end-to-end chain
> proof** (run [`docs/operations/runbooks/post-deploy-smoke.md`](docs/operations/runbooks/post-deploy-smoke.md)
> and record the results — it also closes every ⏳ runtime-proof note below) and the
> **[GATED: auth]** user-attribution item (blocked until auth exists). This file stays until
> those close; it is also the acceptance-criteria record for the implemented surface.
>
> **Update 2026-09-20 — two-layer platform.** The former **NestJS** `apps/api` service (origin
> `0a71`, retired) was removed ([ADR-0003](docs/adr/0003-remove-nestjs-api-layer.md)); the
> FastAPI service — since renamed from `apps/python` to `apps/api` by
> [ADR-0005](docs/adr/0005-name-services-by-role.md), a different service from the removed one —
> is the sole backend and owns the database via SQLAlchemy 2 async + Alembic, with DB spans from
> the asyncpg driver instrumentation
> ([ADR-0004](docs/adr/0004-sqlalchemy-async-alembic-db-layer.md), superseding ADR-0002). Status
> notes below were rewritten for the current `web → api` surface; the remaining runtime proofs
> apply to those two services.

**Audience: Claude Code working in this repo.** This roadmap takes the existing observability
baseline (`trace_id` contract, structured logs, fail-safe Azure Monitor export — see
[`README.md`](README.md) → _Observability & logging_ and
[`.claude/rules/60-observability.md`](.claude/rules/60-observability.md)) to a **complete,
production-grade Application Insights surface**.

It is deliberately **technology-agnostic**: every item states the _outcome and its acceptance
criteria_, not the library or package. You (Claude in this repo) choose the idiomatic
implementation per service, following the repo's existing stacks and conventions — and verify
library choices with the `docs-lookup` skill (repo rule 8).

Ground rules for executing this roadmap:

- **One phase at a time, plan-first** (repo rules 1, 5): propose the plan for the phase, get
  approval, implement, test, update docs (rules 2, 3, 14), then check the boxes here.
- Items tagged **[HUMAN]** require Azure provisioning, secrets, or deploys — forbidden to you
  by [`CLAUDE.md`](CLAUDE.md) → _What you cannot do_. Prepare the IaC/docs, then hand the
  execution to the maintainer.
- Items tagged **[GATED: …]** are blocked on a feature that doesn't exist yet (e.g. auth);
  record them, don't force them.
- The guiding meta-lesson (learned the hard way on a sibling project): **App Insights fails
  silent, not loud.** Wrong init order, an uncollected logging library, an incompatible
  instrumentation package, or default sampling all produce a perfectly working app with
  quietly missing telemetry. That is why Phase 0 and Phase 6 are _verification_ phases —
  never assume a pillar works because the code compiles; prove it by querying the actual
  tables.

---

## Phase 0 — Audit the baseline (verify, don't trust)

The baseline claims below are documented; this phase _proves_ each one against a real
Application Insights resource (or records precisely why it can't be proven yet).

- [x] **Init-order discipline.** Telemetry init must run **before any HTTP-server, HTTP-client,
      or DB library loads** in each service — otherwise auto-instrumentation patches nothing
      and there is no error. The mechanism is runtime-specific (first synchronous import,
      framework instrumentation hook, or an interpreter preload flag — module systems that
      evaluate all imports before any module body runs **cannot** use a "first import").
      _Accept:_ for each service, document the mechanism used and demonstrate a
      server-request span reaching `AppRequests`.
      _Status 2026-07-25:_ mechanisms documented per service in
      [`.claude/rules/60-observability.md`](.claude/rules/60-observability.md) → _Init-order
      discipline_ (web = Next `instrumentation.ts` `register()` hook; api = explicit
      instrumentation in `create_app()`, now including the asyncpg instrumentor). ⏳ The
      `AppRequests` span demo is **pending a real App Insights resource** — no connection
      string exists in this environment **[HUMAN]**: run the Phase 6 smoke query after the
      Phase 4 resource lands.
- [x] **Idempotent init.** Calling init twice must be harmless.
      _Accept:_ a test or documented guard (process-global flag or equivalent).
      _Status 2026-07-25:_ done in both services — process-global guard
      (Node: `Symbol.for` on `globalThis`, shared across module copies/graphs; Python: module
      flag) + unit tests (`apps/web/src/lib/observability.test.ts`,
      `apps/api/tests/test_observability_config.py`).
- [x] **Pin sampling explicitly.** Set a fixed-percentage sampler at init — default 100%,
      tunable via one documented env var (0..1), with the standard `OTEL_TRACES_SAMPLER*` env
      vars taking precedence. **Never rely on the distro default** — current Azure Monitor
      distros silently rate-limit to a few traces/second.
      _Accept:_ env var documented in `.env.example` + README; a burst of N requests yields N
      rows in `AppRequests` at ratio 1.0.
      _Status 2026-07-25:_ implemented + tested. **The rate-limit default was confirmed live in
      the pinned distros** (Node 1.18.1: `tracesPerSecond` defaults to 5 and `samplingRatio`
      only applies with `tracesPerSecond: 0`; Python 1.8.8: `RateLimitedSampler` 5/sec default).
      `TRACE_SAMPLING_RATIO` (0..1, default 1.0, invalid → warn + 1.0) documented in all
      `.env.example`s + README + compose; `OTEL_TRACES_SAMPLER*` precedence verified against
      distro source (Node merges env after code options; Python skips the kwarg when the env
      var is set). ⏳ The N-requests-→-N-rows burst proof is **pending a real App Insights
      resource** **[HUMAN]**.
- [x] **Cloud role identity.** Each service's OTel resource carries `service.name` (→ App
      Insights _cloud role name_) and `service.instance.id` (→ _cloud role instance_: container
      replica name, hostname fallback). Do not set `service.namespace` unless the
      `namespace.name` display format is wanted. Operator-provided `OTEL_RESOURCE_ATTRIBUTES`
      must never be overridden.
      _Accept:_ Application Map shows one distinctly named node per service.
      _Status 2026-07-25:_ implemented + tested — append-only env defaults
      (`OTEL_SERVICE_NAME`, `service.instance.id` = `CONTAINER_APP_REPLICA_NAME` → `HOSTNAME` →
      os hostname) read by both distros' env resource detectors; operator values never
      overridden; `service.namespace` not set. ⏳ The Application-Map per-service-node proof is
      **pending a real App Insights resource** **[HUMAN]**.
- [x] **Auto-instrumentation inventory.** Write down (in the observability rule/README) exactly
      which signals each service gets automatically vs. manually — server spans, HTTP-client
      spans, DB spans, logs, runtime metrics. This inventory drives Phases 1–3.
      _Accept:_ a coverage table per service, each cell marked _auto / manual / missing_.
      _Status 2026-07-25:_ done — table in
      [`.claude/rules/60-observability.md`](.claude/rules/60-observability.md) → _Auto-
      instrumentation inventory_. Key findings against the installed distros: pino is **not**
      collected (Node distro bridges bunyan/winston only) and structlog bypasses stdlib
      `logging` → **Phase 1 log bridges required in both services**; undici/global `fetch`
      is **not** instrumented → **Phase 2 gap for `fetchUpstream`**; DB spans need the asyncpg
      driver instrumentor registered explicitly (the distro's default set lacks it — see
      ADR-0004) → verify in Phase 2.

## Phase 1 — Log pipeline completeness

Structured JSON logs exist in both services. This phase makes them _complete and safe_.

- [x] **Prove log export.** Telemetry distros collect only _specific_ logging libraries — a
      structured logger that isn't on the distro's list writes beautiful local lines that
      **never reach App Insights**. For each service, verify its logger's records land in
      `AppTraces` with severity mapped; if not, tee every serialized line through the **OTel
      Logs API** as a bridge.
      _Accept:_ one log line per service visible in `AppTraces`.
      _Status 2026-07-25:_ verified against the installed distros that **neither**
      logger was collected (Node distro bridges bunyan/winston only — not pino; structlog
      bypasses stdlib `logging`, so `logger_name="app"` captured nothing). Bridges built:
      web tees every serialized pino line through the OTel Logs API
      (`@opentelemetry/api-logs`, whose global LoggerProvider the distro's NodeSDK registers);
      the api mirrors every structlog event into the stdlib `app.telemetry` logger under the
      distro's handler. Severity mapped in both (pino level → OTel SeverityNumber; structlog
      level → stdlib levelno). ⏳ The `AppTraces` row proof is **pending a real App Insights
      resource [HUMAN]** — run the Phase 6 smoke after Phase 4 provisioning.
- [x] **Trace-correlated logs.** Exported log records must inherit the active request span's
      context so `AppTraces.operation_Id` matches the enclosing `AppRequests` row (in addition
      to the `trace_id` field the contract already mandates).
      _Accept:_ a KQL join on `operation_Id` returns the request and its logs together.
      _Status 2026-07-25:_ built into the bridge design — bridged records are emitted
      synchronously inside the request context (Node: OTel Logs API reads the active context;
      Python: the distro's `LoggingHandler` attaches the current span), and the `trace_id`
      field rides along as a log attribute. ⏳ KQL-join proof **pending a real resource
      [HUMAN]**.
- [x] **Bridge is fail-safe.** In degraded mode the export bridge is a no-op; a bridge/export
      failure must never break local logging. Allow per-logger opt-out.
      _Accept:_ degraded-mode tests still pass; a forced bridge error leaves stdout logging intact.
      _Status 2026-07-25:_ done + tested in both services — local write happens first,
      degraded mode short-circuits, a throwing exporter is swallowed (tests force it), and
      per-logger opt-out exists (`buildLogger({telemetryBridge:false})` in Node; bind
      `telemetry_export=False` in Python). Tests: `apps/web/src/lib/logger.test.ts`,
      `apps/api/tests/test_logging_config.py`.
- [x] **Redaction at source.** A default list of secret-bearing fields (authorization/cookie
      headers, `token`, `password`, `secret`, `connectionString`, …) is replaced with
      `[redacted]` **before any sink sees the line** — local or remote — and is extensible per
      logger.
      _Accept:_ unit tests logging each default-redacted field; list documented.
      _Status 2026-07-25:_ done + tested — every default field is covered by a parametrized
      unit test in each service (top-level + nested), redaction provably runs before the
      export bridge, and per-logger extension exists (`buildLogger({redactPaths})` /
      `configure_logging(extra_redacted_fields=...)`). List documented in
      [`.claude/rules/60-observability.md`](.claude/rules/60-observability.md) → _Log
      pipeline_.
- [x] **Non-blocking sinks.** Log writes are asynchronous (never block the request path) with a
      best-effort synchronous flush at process exit so shutdown lines aren't lost.
      _Accept:_ documented + a shutdown test or manual demonstration.
      _Status 2026-07-25:_ done — Node: `pino.destination({sync:false})` + `process.on('exit')`
      → `flushAllLogSinks()` (flush unit-tested incl. a throwing sink); Python: queue + daemon
      writer thread + `atexit` → `flush_logs()` (writer + drain unit-tested incl. a broken
      stream). Documented in rule 60 → _Log pipeline_.
- [x] **Stream discipline.** Logs go to the correct stream per execution mode; if any service
      ever uses stdout as a protocol channel, logs must move to stderr there.
      _Accept:_ noted in the observability rule (currently both services are stdout-safe).
      _Status 2026-07-25:_ noted in rule 60 → _Log pipeline_ (both services use stdout as
      a pure log channel today; the stderr requirement is recorded for any future stdio-protocol
      mode).
- [x] **PII purge runbook.** Document the Log Analytics **purge API** as the
      accidental-PII/secret removal process, in `docs/operations/runbooks/`.
      _Accept:_ runbook exists with the exact escalation steps.
      _Status 2026-07-25:_ done —
      [`docs/operations/runbooks/pii-purge.md`](docs/operations/runbooks/pii-purge.md)
      (fix-at-source → rotate secrets → scope with KQL → Workspace Purge REST call
      (api-version 2025-02-01, Data Purger role, 50 req/h, 30-day SLA) → status tracking →
      close-out; API details verified against the Microsoft REST reference).

## Phase 2 — Distributed trace completeness

- [x] **One traced outbound wrapper per service.** Every outbound HTTP call goes through a
      single wrapper that propagates W3C `traceparent` **and** the repo's `x-trace-id`. Audit
      especially framework-native fetch/HTTP clients: several are **not** covered by default
      auto-instrumentation and silently emit no dependency spans — close each gap with the
      matching instrumentation and _verify at runtime_.
      _Accept:_ `AppDependencies` rows exist for every service-to-service hop; bare/untraced
      HTTP clients are forbidden in the lint/convention rules.
      _Status 2026-07-26:_ the wrappers already existed (`fetchUpstream`/`traced_client`);
      the audit confirmed the Node gap — the distro does NOT instrument
      undici/global `fetch` (its set: azureSdk/http/mongoDb/mySql/postgreSql/redis) — so
      web registers `@opentelemetry/instrumentation-undici@0.28.0` at init (pinned to
      the distro's `instrumentation@0.218.0` line; `diagnostics_channel`-based, so safe after
      Next loads undici). Python's httpx instrumentation was already in place (Phase 0). The
      bare-client ban is explicit in rule 60 → _Distributed traces_ (rules 30/35 already
      said it per service). ⏳ `AppDependencies` row proof pending a real resource [HUMAN].
- [x] **DB dependency spans.** Database operations appear as client-kind dependency spans with
      db-system, operation, and entity attributes. If the ORM's official instrumentation is
      incompatible with the OTel SDK version the distro registers (a real, observed failure
      mode — it can _throw inside the query path_), wrap the ORM's middleware/interception
      layer with manual client spans instead, and record the decision as an ADR.
      _Accept:_ a DB query shows in `AppDependencies` under its parent request; incompatibility
      decision (if any) captured in `docs/adr/`.
      _Status 2026-09-20:_ decision recorded in
      [ADR-0004](docs/adr/0004-sqlalchemy-async-alembic-db-layer.md) (supersedes ADR-0002,
      which covered the removed Node/ORM layer) — `opentelemetry-instrumentation-asyncpg`
      on the distro's `0.61b0` line is registered explicitly in `apps/api/app/observability.py`
      under the lazy SQLAlchemy 2 async engine; no ORM-level instrumentation package (avoids the
      version-pin failure mode entirely). ⏳ Runtime proof needs a real DB + resource — no
      queries exist in the placeholder model set; prove during the Phase 6 smoke [HUMAN].
- [ ] **End-to-end chain proof.** One request through the `web → api` (and `api → db`)
      chain shares one `operation_Id`, and Application Map draws every edge.
      _Accept:_ screenshot or KQL result attached to the PR; the BFF's `/api/ping-backend`
      route is the natural probe.
      _Status 2026-09-20:_ **[HUMAN]** — everything code-side is in place; this box needs a
      provisioned App Insights resource (Phase 4) and one `/api/ping-backend` run (Phase 6
      smoke).
- [ ] **[GATED: auth] User attribution.** Once authentication exists, tag authenticated request
      spans with the user identity (`enduser.id` → `user_AuthenticatedId`) so telemetry
      attributes to real users — and keep all _other_ PII out of attributes per the existing
      rule.
      _Accept:_ deferred; revisit when auth lands (auth itself needs a threat model + ADR).
      _Status 2026-07-26:_ recorded in rule 60 → _Distributed traces_ as a GATED item; still
      blocked on auth (threat model + ADR first).

## Phase 3 — Metrics & events

- [x] **Runtime metrics.** Each service exports its runtime health metrics (event-loop lag /
      GC / heap, or the runtime's equivalents), registered automatically on successful init.
      _Accept:_ rows in `AppPerformanceCounters`/`AppMetrics` per service.
      _Status 2026-07-26:_ distro perf counters were already on (Phase 0); added at init —
      Node: `@opentelemetry/instrumentation-runtime-node@0.31.0` (event-loop lag/utilization,
      GC, heap; pinned to the distro's line); api:
      `opentelemetry-instrumentation-system-metrics==0.61b0` with a **runtime-only** selection
      (`process.*`/`cpython.*` — host-wide disk/network series excluded). ⏳ Table-row proof
      pending a real resource [HUMAN].
- [x] **Custom-metric helper.** A shared accessor returns namespaced meters
      (`<project>.<scope>`), silently no-op in degraded mode, so feature code never
      null-checks telemetry.
      _Accept:_ helper + tests in each service; usage documented.
      _Status 2026-07-26:_ `getMeter(scope)` / `get_meter(scope)` → `team-assistant.<scope>` in
      `apps/web/src/lib/metrics.ts`, `apps/api/app/metrics.py`;
      degraded mode rides the OTel no-op proxy meter (verified); all record helpers are
      best-effort (throwing provider tests). Documented in rule 60 → _Metrics & events_.
- [x] **Cardinality discipline (written rule).** Metric attributes use **bounded value sets
      only** (kinds, formats, status classes, outcomes) — never ids, names, emails, or paths
      with parameters. App Insights bills each attribute combination as its own series and
      caps at 5,000 series/metric/day.
      _Accept:_ rule added to the observability contract; reviewed in `/code-review`.
      _Status 2026-07-26:_ written into rule 60 → _Metrics & events_ (always-loaded, and the
      `/code-review` agent reviews against the rules); enforced in code by bounded label
      helpers (`statusClass`, `resolveTarget`, route patterns not raw paths, `unmatched`
      collapse for 404s).
- [x] **Starter metric set.** Instrument what exists today: request-duration histogram by
      route-class + status-class per service, BFF upstream-failure counter, chain-hop
      duration. Extend per feature later.
      _Accept:_ metrics visible in `customMetrics` after a local run against a real resource.
      _Status 2026-07-26:_ implemented — `team-assistant.http.server.duration` (both trace
      middlewares/wrappers, route PATTERN as route_class), `team-assistant.http.client.hop.duration`
      (in `fetchUpstream`/`traced_client` event hooks),
      `team-assistant.bff.upstream.failures` (web; `network_error`/`http_5xx`). ⏳ `customMetrics`
      visibility check pending a real resource [HUMAN].
- [x] **Custom events for milestones.** A `trackEvent(name, attrs)` helper emitting App
      Insights `customEvents` (request-correlated, no identifying attributes), ready for
      business milestones (`X.created`, `X.exported`, `user.provisioned`) as features arrive.
      _Accept:_ helper + one wired event (e.g. service-start) visible in `customEvents`.
      _Status 2026-07-26:_ `trackEvent` / `track_event` in both services via the
      `microsoft.custom_event.name` log-record marker (verified in BOTH exporters' source:
      Node `logUtils` EventData mapping, api `_MICROSOFT_CUSTOM_EVENT_NAME`); fail-safe +
      local structured line always prints (bridge opt-out prevents double export);
      `service.start` wired in each bootstrap. ⏳ `customEvents` visibility pending a real
      resource [HUMAN].

## Phase 4 — Azure resources & guardrails **[HUMAN + IaC]**

Prepare everything as IaC in `infra/`; the maintainer deploys.

_Phase status 2026-07-26: IaC authored and compiling clean (Bicep CLI 0.45.15) —
`infra/main.bicep` + `modules/{observability,alerts,availability}.bicep` +
`main.example.bicepparam`; deploy commands in `infra/README.md`. Every box below is
**prepared**; the deployment itself is the [HUMAN] step._

_Update 2026-08-02: the template **deployed successfully to a real sandbox resource group**
(action group + workspace + workspace-based component + alert rules), the `connectionString`
output was wired into the apps, and the services ran locally against it with
`/health → "observability": "enabled"`. That validates the Phase 4 IaC end to end for the
observability core; production-environment deployment (and later the hardening flip) remains
[HUMAN]. One RBAC note from the sandbox run, now expected: deploying needs **Contributor** on
the target RG (Reader + deployment rights alone fail with `Microsoft.Insights/*/write`
authorization errors)._

- [x] **Workspace-based Application Insights** resource (never classic), backed by a Log
      Analytics workspace, wired to the apps via the single connection-string env var — same
      code path locally and deployed, no local collector stack.
      _Status 2026-07-26:_ `modules/observability.bicep` — `Microsoft.OperationalInsights/workspaces`
      → `Microsoft.Insights/components@2020-02-02` with `WorkspaceResourceId` +
      `IngestionMode: LogAnalytics`; the module outputs `connectionString` for the apps'
      single env var. ⏳ Deployment [HUMAN].
- [x] **Cost guardrails:** a daily billable-ingestion alert on the workspace (pick a GB/day
      threshold), knowledge of the workspace daily-cap switch, and the sampling env var from
      Phase 0 documented as the tuning knob.
      _Status 2026-07-26:_ scheduled-query alert on `Usage | where IsBillable` (default
      5 GB/day, `dailyIngestionAlertThresholdGb`); the daily-cap switch is exposed as
      `logAnalyticsDailyCapGb` (default -1 = off) and documented as the emergency brake —
      with `TRACE_SAMPLING_RATIO` documented as the first-line tuning knob
      (`infra/README.md` → _Cost guardrails_). ⏳ Deployment [HUMAN].
- [x] **Ingestion hardening (optional but recommended):** switch telemetry ingestion to the
      app's **managed identity** (Monitoring Metrics Publisher role on the component) and set
      `DisableLocalAuth` so connection-string-only senders are rejected. A mistyped auth-mode
      value must degrade _visibly_ — never fall back silently to unauthenticated ingestion.
      _Status 2026-07-26:_ BOTH halves done — IaC: `telemetryPublisherPrincipalIds` → role
      assignments (GUID verified: `3913510d-42f4-4e42-8a64-420c390055eb`) + `disableLocalAuth`
      param; app side: `TELEMETRY_AUTH_MODE` (+`TELEMETRY_MANAGED_IDENTITY_CLIENT_ID`) in
      both services passing `ManagedIdentityCredential` to the distros (option names verified
      against the Entra-auth docs), and a mistyped value **disables observability with the
      reason on `/health`** — unit-tested per service. Rollout order documented
      (`infra/README.md` → _Ingestion hardening_). ⏳ Role grants + flip [HUMAN].
- [x] **Platform log tables.** If the hosting platform ships container console logs to Log
      Analytics on its own, prefer the **resource-specific** tables over legacy custom (`_CL`)
      tables and note the table names in the runbook — platform renames strand saved queries.
      _Status 2026-07-26:_ runbook written —
      [`docs/operations/runbooks/platform-log-tables.md`](docs/operations/runbooks/platform-log-tables.md)
      (`ContainerAppConsoleLogs`/`ContainerAppSystemLogs` resource-specific tables preferred
      over `_CL`, triage queries, and how they relate to `AppTraces`).

## Phase 5 — Alerting & availability **[HUMAN + IaC]**

All as IaC with sensible defaults; maintainer sets recipients and deploys.

_Phase status 2026-07-26: all rules authored in `modules/alerts.bicep` +
`modules/availability.bicep`, compiling clean; every metric name verified against the Azure
Monitor supported-metrics references (Microsoft.App/containerapps,
Microsoft.DBforPostgreSQL/flexibleServers). Deployment + recipients are the [HUMAN] step; the
per-app/db/webtest rules self-skip on empty parameters until hosting exists._

- [x] **Action group** (email/webhook) that every rule below notifies.
      _Status 2026-07-26:_ `ag-<baseName>` in `main.bicep` — `alertEmails` array + optional
      `alertWebhookUrl`, common alert schema; every rule references it. ⏳ Recipients + deploy
      [HUMAN].
- [x] **Per-app resource alerts:** CPU, memory, restart/replica-health.
      _Status 2026-07-26:_ per entry in `containerApps`: `CpuPercentage` > 80%,
      `MemoryPercentage` > 80%, `Replicas` < `minReplicas`, `RestartCount` ≥ 5 (cumulative
      semantics documented in the module). ⏳ Fill `containerApps` once the apps are deployed
      [HUMAN].
- [x] **Database alerts:** CPU, worker/connection saturation, storage.
      _Status 2026-07-26:_ against `postgresServerId`: `is_db_alive` < 1 (sev 0),
      `cpu_percent` > 80, `memory_percent` > 85, `active_connections` > threshold (absolute —
      set ≈ 80% of the SKU `max_connections`; metric alerts can't divide by the max metric),
      `connections_failed` > 10/15 min, `storage_percent` > 80 (sev 1 — Postgres goes
      read-only when full). ⏳ Set `postgresServerId` [HUMAN].
- [x] **Error alert on the logs table** (error-severity spike) + **Service Health / Resource
      Health** activity-log alerts (free).
      _Status 2026-07-26:_ scheduled-query rule on `AppTraces | where SeverityLevel >= 3`
      (> 25 rows / 15 min default) + subscription-scoped `ServiceHealth` and `ResourceHealth`
      activity-log alerts (toggle `enableServiceHealthAlerts`). ⏳ Deploy [HUMAN].
- [x] **Availability webtests:** a standard test per public endpoint (the unversioned
      `/health` endpoints exist for exactly this), multi-location, alerting when several
      locations fail simultaneously.
      _Status 2026-07-26:_ `modules/availability.bicep` — one **standard** webtest per
      `webTests` entry (5 probe locations by default, hidden-link tag to the component,
      SSL check on https URLs) + a `WebtestLocationAvailabilityCriteria` metric alert firing
      at ≥ 2 failed locations. ⏳ Fill `webTests` with the deployed `/health` FQDNs [HUMAN].

## Phase 6 — End-to-end verification & ops docs

- [x] **Post-deploy smoke procedure** (scripted or runbook): fire one request through the full
      chain, then confirm — one `operation_Id` across `AppRequests` + `AppDependencies` +
      `AppTraces`; role names correct; `customMetrics`/`customEvents` flowing; Application Map
      fully connected.
      _Status 2026-07-26:_ runbook authored —
      [`docs/operations/runbooks/post-deploy-smoke.md`](docs/operations/runbooks/post-deploy-smoke.md):
      probe commands (chain + 20-request sampling burst), an 8-row verification table mapping
      each KQL check to the roadmap proof it closes, the Application-Map check, and close-out
      steps. ⏳ **Executing it needs the deployed resource [HUMAN]** — running it also closes
      every remaining ⏳ runtime proof in Phases 0–3.
- [x] **KQL starter pack** in `docs/operations/`: trace-by-id lookup, request+logs join,
      error-rate by service, dependency latency, ingestion-volume by table.
      _Status 2026-07-26:_ done —
      [`docs/operations/kql-starter-pack.md`](docs/operations/kql-starter-pack.md): the five
      required queries plus custom-metrics, custom-events, and availability checks, written
      for the workspace-based tables (`OperationId`/`AppRoleName`/`Properties.trace_id`,
      `sum(ItemCount)` under sampling) with the classic-name cheat sheet and an
      `az monitor log-analytics query` invocation.
- [x] **Degraded-mode triage runbook:** what `/health → "observability": "disabled"` means,
      the reasons it reports, and the fix per reason.
      _Status 2026-07-26:_ done —
      [`docs/operations/runbooks/observability-degraded.md`](docs/operations/runbooks/observability-degraded.md):
      the exact `reason` strings each service emits (no connection string, invalid
      `TELEMETRY_AUTH_MODE`, per-service init-failure wordings, api `not initialized`) with
      fixes, the web module-graph quirk, and the enabled-but-silent causes (ingestion lag,
      `DisableLocalAuth` without roles, `TRACE_SAMPLING_RATIO=0`, daily cap, wrong resource).
- [x] **Docs sweep (repo rule 14):** README, `.env.example`s, per-app `CLAUDE.md`s, and the
      observability rule all reflect the final surface; this roadmap's boxes are checked with
      links to the implementing PRs.
      _Status 2026-07-26:_ swept — README (observability section, env table, ops links, infra
      status), all `.env.example`s + compose, the per-app `CLAUDE.md`s, rule 60
      (init/sampling/identity/inventory/log-pipeline/traces/metrics/ingestion-auth/fail-safe +
      runbook links), `infra/README.md`, and the runbook index. Boxes link to the implementing
      **files** — the repo is not under git yet, so no PRs exist to link.

---

## Remaining [HUMAN] steps (everything code-side is done)

1. ~~Deploy `infra/main.bicep` and wire the `connectionString` output into the apps~~ —
   **validated 2026-08-02** against a sandbox resource group (the services ran locally
   with observability enabled). Repeat per real environment when hosting lands
   (`infra/README.md`; deploying needs Contributor on the target RG).
2. Run [`post-deploy-smoke.md`](docs/operations/runbooks/post-deploy-smoke.md) — it closes
   every ⏳ runtime proof above (Phases 0–3) and the Phase 2 chain-proof box in one pass.
3. As hosting lands: fill `containerApps` / `postgresServerId` / `webTests`, then walk the
   ingestion-hardening rollout before flipping `disableLocalAuth`.
4. Gated: Phase 2 user attribution waits for auth (threat model + ADR first).

---

## Already in the baseline (do not rebuild — re-verify in Phase 0)

| Concern                                                                                                                    | Status                           |
| -------------------------------------------------------------------------------------------------------------------------- | -------------------------------- |
| `trace_id` invariant — origin(4)+env(1)+random(27), adopt-or-mint, propagate unchanged, echo on response                   | ✅ implemented + tested          |
| Request-scoped ambient context (no manual trace_id passing)                                                                | ✅ implemented                   |
| Structured JSON logs with `timestamp, level, service, origin, env, trace_id, message`                                      | ✅ implemented                   |
| Fail-safe degraded mode — no connection string ⇒ warn, local logs only, `/health` reports `disabled` + reason, never crash | ✅ implemented + tested          |
| Batched, non-blocking telemetry export; no sync flush in request paths                                                     | ✅ documented contract           |
| No-PII-in-telemetry and no-`console.log`/`print` rules                                                                     | ✅ in the observability contract |
