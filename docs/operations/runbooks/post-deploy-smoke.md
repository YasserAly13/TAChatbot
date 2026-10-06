# Runbook — Post-deploy observability smoke

**When to use:** right after deploying the infra stack (`infra/main.bicep`) and
pointing the apps at the new `APPLICATIONINSIGHTS_CONNECTION_STRING` — and after
any change that touches telemetry init, the log bridges, or instrumentation.
This procedure closes the runtime proofs the roadmap marks **⏳ [HUMAN]**
(App Insights fails **silent, not loud** — never assume a pillar works because
the code compiles).

**Prereqs:** both services running (deployed, or locally via
`docker compose up` with the real connection string in `.env`); one
`/health` per service returns `"observability": "enabled"` — if not, stop and
run [`observability-degraded.md`](observability-degraded.md) first.

## 1. Fire the probes

```bash
WEB=http://localhost:3000        # or the deployed web FQDN

# One full hop (web → api) — capture the trace id:
curl -si "$WEB/api/ping-backend" | grep -i x-trace-id
curl -s  "$WEB/api/info-backend" | head -c 400; echo

# Burst of 20 (sampling proof — ratio 1.0 must yield ALL of them):
for i in $(seq 20); do curl -s -o /dev/null "$WEB/api/ping-backend"; done
```

Note the `x-trace-id` value, then **wait 2–5 minutes** (batched export +
ingestion latency) before querying.

## 2. Verify in Log Analytics

Queries by number from [`../kql-starter-pack.md`](../kql-starter-pack.md)
(portal _Logs_ blade or `az monitor log-analytics query`):

| #   | Check                     | Query                                                                                                        | Pass condition                                                                                                                                                                   | Roadmap proof closed                    |
| --- | ------------------------- | ------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| 1   | **End-to-end chain**      | pack #1 with your trace id                                                                                   | ONE `OperationId`; rows from `ai-accelerator-web` and `-api`; an `AppDependencies` row for web→api                                                                               | Phase 2 chain proof; Phase 0 init-order |
| 2   | **Trace-correlated logs** | pack #2                                                                                                      | request rows join their `AppTraces` lines; `trace_id` present on both                                                                                                            | Phase 1 log export + correlation        |
| 3   | **Sampling pinned**       | `AppRequests \| where Name has "ping-backend" \| where TimeGenerated > ago(15m) \| summarize sum(ItemCount)` | = 20 (the full burst)                                                                                                                                                            | Phase 0 sampling                        |
| 4   | **Cloud role identity**   | pack #3 (or Application Map)                                                                                 | exactly two `AppRoleName`s (`ai-accelerator-web`, `ai-accelerator-api`), correctly named                                                                                         | Phase 0 identity                        |
| 5   | **Custom metrics**        | pack #6                                                                                                      | all `ai-accelerator.*` names present per service; runtime metrics rows in `AppMetrics`/`AppPerformanceCounters`                                                                  | Phase 3 metrics                         |
| 6   | **Custom events**         | pack #7                                                                                                      | `service.start` for both services                                                                                                                                                | Phase 3 events                          |
| 7   | **DB dependency span**    | pack #4                                                                                                      | an `mssql` dependency (SQLAlchemy instrumentation over aioodbc) under its parent `ai-accelerator-api` request — **only once a real query exists** (the model set is empty today) | Phase 2 DB spans (ADR-0008)             |
| 8   | **Availability**          | pack #8                                                                                                      | results from all configured locations — only after `webTests` is filled in                                                                                                       | Phase 5 webtests                        |

## 3. Application Map (portal)

App Insights → **Application Map**: two distinctly named nodes with the edge
`web → api` (plus `api → <azure sql>` once queries exist).
A missing edge = a hop whose dependency span never arrived → re-check the
undici/httpx instrumentation notes in rule 60 → _Distributed traces_.

## 4. Close out

- Tick the corresponding **⏳ [HUMAN]** statuses in
  [`OBSERVABILITY-ROADMAP.md`](../../../OBSERVABILITY-ROADMAP.md) (Phases 0–3)
  and attach the KQL results (or a Map screenshot) to the PR.
- Any failed check: [`observability-degraded.md`](observability-degraded.md)
  for enabled-but-silent triage; [`platform-log-tables.md`](platform-log-tables.md)
  when the app itself never started.
