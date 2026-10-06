# KQL starter pack

Copy-paste queries for the Team Assistant's telemetry (roadmap Phase 6). Run them
in the **Log Analytics workspace** (`log-<baseName>`) or the App Insights
component's _Logs_ blade — both hit the same workspace tables because the
component is workspace-based.

**Table/column cheat sheet (workspace-based names):** `AppRequests`,
`AppDependencies`, `AppTraces`, `AppExceptions`, `AppEvents` (classic
`customEvents`), `AppMetrics` (classic `customMetrics`),
`AppPerformanceCounters`, `AppAvailabilityResults`. Correlation column is
`OperationId` (classic `operation_Id`); service identity is `AppRoleName`
(classic `cloud_RoleName`); custom attributes — including the repo's
**`trace_id`** — live in the dynamic `Properties` column (classic
`customDimensions`). Telemetry lands with **~1–5 min ingestion delay**; counts
under sampling need `sum(ItemCount)`, not `count()`.

CLI alternative to the portal (maintainer):

```bash
az monitor log-analytics query \
  --workspace <workspace-customer-GUID> \
  --analytics-query "<paste a query below>" -o table
```

---

## 1. Trace-by-id lookup (the repo `trace_id`, end to end)

Everything one request produced, across all services and signal types:

```kusto
let tid = "<32-hex trace_id from the x-trace-id response header>";
union AppRequests, AppDependencies, AppTraces, AppExceptions, AppEvents
| where tostring(Properties.trace_id) == tid or OperationId in (
    (union AppRequests, AppTraces
     | where tostring(Properties.trace_id) == tid
     | distinct OperationId))
| project TimeGenerated, Type, AppRoleName, OperationId,
          Detail = coalesce(column_ifexists("Name", ""), column_ifexists("Message", "")),
          DurationMs = column_ifexists("DurationMs", real(null)), Properties
| order by TimeGenerated asc
```

The chain is healthy when ONE `OperationId` covers rows from both
`AppRoleName`s (`team-assistant-web|api`).

## 2. A request and its logs together (Phase 1 acceptance join)

```kusto
AppRequests
| where TimeGenerated > ago(1h)
| join kind=inner (AppTraces) on OperationId
| project TimeGenerated, AppRoleName, RequestName = Name,
          ResultCode, DurationMs, SeverityLevel, Message,
          trace_id = tostring(Properties1.trace_id)
| order by TimeGenerated desc
| take 100
```

## 3. Error rate by service

```kusto
AppRequests
| where TimeGenerated > ago(24h)
| summarize requests = sum(ItemCount),
            failed   = sumif(ItemCount, Success == false)
  by AppRoleName, bin(TimeGenerated, 15m)
| extend error_rate_pct = round(100.0 * failed / requests, 2)
| order by TimeGenerated desc
```

Error-severity log volume (what the Phase 5 spike alert watches):

```kusto
AppTraces
| where TimeGenerated > ago(24h) and SeverityLevel >= 3
| summarize errors = count() by AppRoleName, bin(TimeGenerated, 15m)
| order by TimeGenerated desc
```

## 4. Dependency latency (service-to-service hops + DB)

```kusto
AppDependencies
| where TimeGenerated > ago(24h)
| summarize count(), p50 = percentile(DurationMs, 50),
            p95 = percentile(DurationMs, 95), p99 = percentile(DurationMs, 99),
            failures = countif(Success == false)
  by AppRoleName, DependencyType, Target
| order by p95 desc
```

The custom upstream-hop histogram (bounded `target`/`outcome` attributes; `target` is
`api | other`) lives in `AppMetrics` as `team-assistant.http.client.hop.duration` — see
query 6. DB calls (once real queries exist) appear here as `mssql` dependencies (SQLAlchemy
instrumentation over aioodbc) under `team-assistant-api`.

## 5. Ingestion volume by table (cost triage)

```kusto
Usage
| where TimeGenerated > ago(7d) and IsBillable == true
| summarize GB = round(sum(Quantity) / 1000.0, 3) by DataType, bin(TimeGenerated, 1d)
| order by TimeGenerated desc, GB desc
```

Crossing the Phase 4 alert threshold? Tune `TRACE_SAMPLING_RATIO` first; the
workspace daily cap is the emergency brake (`infra/README.md` → _Cost
guardrails_).

## 6. Custom metrics are flowing (Phase 3 starter set)

```kusto
AppMetrics
| where TimeGenerated > ago(1h) and Name startswith "team-assistant."
| summarize samples = count() by Name, AppRoleName
| order by Name asc
```

Expected names: `team-assistant.http.server.duration`,
`team-assistant.http.client.hop.duration`, `team-assistant.bff.upstream.failures`
(web only). Runtime metrics (event-loop/GC/heap, CPython runtime) land in
`AppMetrics`/`AppPerformanceCounters` under their OTel names.

## 7. Custom events (Phase 3 — `service.start` et al.)

```kusto
AppEvents
| where TimeGenerated > ago(24h)
| summarize count() by Name, AppRoleName, bin(TimeGenerated, 1h)
| order by TimeGenerated desc
```

## 8. Availability webtests (Phase 5)

```kusto
AppAvailabilityResults
| where TimeGenerated > ago(24h)
| summarize total = count(), failed = countif(Success == false),
            p95_ms = percentile(DurationMs, 95)
  by Name, Location
| order by Name asc, failed desc
```
