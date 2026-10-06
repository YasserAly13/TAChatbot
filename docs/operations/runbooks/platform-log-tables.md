# Runbook — Platform log tables (Container Apps → Log Analytics)

**When to use:** you're looking for container **stdout/stderr** or platform
lifecycle events (scaling, probes, image pulls) in Log Analytics and can't find
them — or you're configuring a new Container Apps environment and must pick a
log destination.

## The two destinations (pick once, per environment)

Azure Container Apps ships console + system logs to Log Analytics **on its
own**, independent of the app's OpenTelemetry pipeline. The environment's
`logsConfiguration` destination decides WHICH tables the data lands in:

| Destination                               | Tables                                                                   | Verdict                                                                                              |
| ----------------------------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------- |
| **`azure-monitor`** (diagnostic settings) | `ContainerAppConsoleLogs`, `ContainerAppSystemLogs` (resource-specific)  | **Preferred** — schema owned by the platform, survives renames, supports table-level RBAC/retention. |
| `log-analytics` (legacy)                  | `ContainerAppConsoleLogs_CL`, `ContainerAppSystemLogs_CL` (custom `_CL`) | Avoid — legacy custom tables; platform renames strand saved queries and dashboards.                  |

Standardize saved queries on the **resource-specific** names. If a workspace
contains BOTH (destination was switched at some point), query the union during
the transition window and note the switch date.

## Triage queries

Console (your services' raw stdout — the structured JSON lines):

```kusto
ContainerAppConsoleLogs
| where ContainerAppName == "<app>"
| order by TimeGenerated desc
| take 100
```

Platform lifecycle (scheduling, scaling, probe failures):

```kusto
ContainerAppSystemLogs
| where ContainerAppName == "<app>"
| order by TimeGenerated desc
| take 100
```

## Relationship to the app telemetry (don't confuse the two)

- **`AppTraces`** — the application's structured logs via the OTel log bridges
  (trace-correlated, redacted at source; rule 60 → _Log pipeline_). This is
  the primary debugging surface.
- **`ContainerAppConsoleLogs`** — the same stdout lines as raw text, captured
  by the platform. Useful when the app is so broken the OTel pipeline never
  started (crash loops, bad image, missing env) — i.e. exactly when
  `AppTraces` is silent.
- **`ContainerAppSystemLogs`** — has no app-level equivalent; this is where
  scheduling/probe/scale problems surface.

If a service is "silent" in `AppTraces`, check `ContainerAppConsoleLogs` for
its degraded-mode WARNING (`Observability disabled: …`) — that line prints to
stdout even when remote export is off.
