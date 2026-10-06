# Runbook — Purging accidental PII / secrets from Log Analytics

**When to use:** a log line containing personal data (emails, names, user ids) or a secret
(token, password, connection string) was exported to Application Insights / Log Analytics —
i.e. it slipped past the redaction-at-source list (see
[`.claude/rules/60-observability.md`](../../../.claude/rules/60-observability.md) → _Log
pipeline_) and now sits in `AppTraces` (or another table) in the workspace.

**Severity framing:** a leaked **secret** is an incident — rotate it immediately (step 2);
purging the log copy is cleanup, not mitigation. Leaked **personal data** is a
compliance/GDPR matter — purge is the sanctioned mechanism.

> Purge is **destructive and non-reversible**, throttled at **50 requests/hour**, and its
> formal completion **SLA is 30 days** (most finish much faster; it cannot be expedited).
> Microsoft authorizes the Purge API for **GDPR compliance** purposes; for routine deletions
> they point to the (more performant) Delete Data API. Source:
> [Manage personal data in Azure Monitor Logs](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/personal-data-mgmt).

## Escalation steps

### 1. Stop the leak at the source (always first)

1. Identify the offending log call (the exported line carries `service`, `trace_id`, and the
   message — grep the codebase for the message).
2. Fix the call site, **and** add the field to the redaction list so the class of leak is
   closed, not just the instance:
   - Node (`apps/web`): `DEFAULT_REDACTED_FIELDS` in `src/lib/logger.ts` (or per-logger
     `buildLogger({ redactPaths })`).
   - Python (`apps/api`): `DEFAULT_REDACTED_FIELDS` in `app/logging_config.py` (or
     `configure_logging(extra_redacted_fields={...})`).
3. Deploy the fix before purging — purging while the leak is live is pointless.

### 2. If the leaked value is a secret — rotate it now

Treat the value as compromised (telemetry pipelines cache and index). Rotation is
maintainer-owned (Key Vault / connection strings — see `CLAUDE.md` → _What you cannot do_).

### 3. Scope the damage (query BEFORE purging)

Run the exact predicate you intend to purge with, and record the row count in the incident
notes. Logs land in `AppTraces` (workspace-based App Insights):

```kusto
AppTraces
| where TimeGenerated between (datetime(<start>) .. datetime(<end>))
| where Message contains "<leaked-value-or-marker>"
| summarize count() by AppRoleName
```

### 4. Execute the purge (maintainer — needs Azure RBAC)

**Required permission:** `Microsoft.OperationalInsights/workspaces/purge/action` — carried by
the built-in **Data Purger** or **Log Analytics Contributor** roles on the workspace.

**Request** ([Workspace Purge REST API](https://learn.microsoft.com/en-us/rest/api/loganalytics/workspace-purge/purge)):

```http
POST https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroupName}/providers/Microsoft.OperationalInsights/workspaces/{workspaceName}/purge?api-version=2025-02-01

{
  "table": "AppTraces",
  "filters": [
    { "column": "TimeGenerated", "operator": "between",
      "value": ["2026-07-20T00:00:00", "2026-07-21T00:00:00"] },
    { "column": "Message", "operator": "==", "value": "<the leaked line's message>" }
  ]
}
```

- Supported filter operators: `==`, `=~`, `in`, `in~`, `>`, `>=`, `<`, `<=`, `between` (KQL
  semantics). Batch identities into ONE request with `in` — remember the 50 req/hour throttle.
- Response is `202 Accepted` with an `operationId` and an `x-ms-status-location` header.

### 5. Track completion

`GET` the URL from the `x-ms-status-location` header (a
`.../operations/purge-{operationId}?api-version=...` URL) until status reports completed.
Plan around the 30-day SLA; there is no expedite path.

### 6. Close out

- Verify with the step-3 query that 0 rows remain (after completion).
- If the data also reached other tables (e.g. `AppRequests` attributes, `AppDependencies`),
  repeat steps 3–5 per table. Note: purge does **not** touch Basic/Auxiliary-plan tables or
  data mirrored outside the workspace.
- Record: what leaked, the trace window, the purge `operationId`(s), the redaction-list
  change that closes the class, and (for secrets) the rotation confirmation.

## Prevention (the actual control)

Purge is the last resort. The platform's controls, in order of preference:

1. **Redaction at source** (implemented): the default secret-field list is censored in every
   service before any sink — extend it as fields appear.
2. **No-PII-in-telemetry rule** (`.claude/rules/60-observability.md` → _Forbidden_): no
   emails, names, tokens in span attributes or log fields; enforced in `/code-review`.
3. Azure-side **data collection transformations** for anything the app layer can't catch
   (Microsoft's preferred approach per the personal-data guidance).
