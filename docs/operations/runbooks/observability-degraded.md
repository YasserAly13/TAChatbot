# Runbook — Observability degraded / telemetry missing

**Symptom:** a service's `/health` returns `"observability": "disabled"` (the
`reason` field says why), **or** `/health` says `enabled` but nothing arrives
in Log Analytics.

**Signal:** every service prints a loud startup WARNING
(`Observability disabled: …`) on stdout — locally in the terminal / compose
logs, deployed in `ContainerAppConsoleLogs` (see
[`platform-log-tables.md`](platform-log-tables.md)). This line prints even when
remote export is off — it is the one signal that never goes missing.

Degraded mode is a DESIGNED state, not a crash: the service keeps serving with
structured stdout logs only (rule 60 → _Fail-safe_).

## Triage by `reason` (exact strings, both services)

| `reason` on `/health`                                                                        | Meaning                                                                                                                                             | Fix                                                                                                                                                                |
| -------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `no Azure connection string`                                                                 | `APPLICATIONINSIGHTS_CONNECTION_STRING` unset/empty — the default local state.                                                                      | Set it (locally `.env`; deployed via Key Vault / Container Apps secret from the `infra/main.bicep` `connectionString` output) and restart.                         |
| `invalid TELEMETRY_AUTH_MODE "<value>" — expected "connection_string" or "managed_identity"` | Mistyped ingestion-auth mode. **Deliberate hard-stop:** the service refuses to silently fall back to unauthenticated ingestion (Phase 4 hardening). | Correct the env var (empty, `connection_string`, or `managed_identity` — underscores, exact spelling) and restart.                                                 |
| web: `<raw error message>`                                                                   | `useAzureMonitor()` threw at init (malformed connection string, broken package resolution); the reason IS the error message.                        | Read the message; verify the connection-string format (`InstrumentationKey=…;IngestionEndpoint=…`) and that `node_modules` is intact (`pnpm -C apps/web install`). |
| api: `configure_azure_monitor failed: <exc>`                                                 | Same init failure, api wording.                                                                                                                     | As above (`uv sync --directory apps/api`).                                                                                                                         |
| api: `not initialized`                                                                       | `init_observability()` never ran — `create_app()` crashed earlier or a test imported the module in isolation.                                       | Check startup logs for the earlier exception.                                                                                                                      |

**Web quirk:** Next.js can put `instrumentation.ts` and route bundles in
separate module graphs, so web's `/health` may show an env-derived state
(`enabled` + `ok`) rather than the init result. When web looks inconsistent
with its logs, trust the startup WARNING in the logs.

## `/health` says `enabled` but tables stay empty

Silent server-side drops, in likelihood order:

1. **Ingestion latency** — wait 5 minutes before concluding anything.
2. **`DisableLocalAuth` flipped without the app side** — the component rejects
   connection-string senders. Either the app isn't running
   `TELEMETRY_AUTH_MODE=managed_identity`, or its identity lacks
   **Monitoring Metrics Publisher** on the component. Follow the rollout order
   in [`infra/README.md`](../../../infra/README.md) → _Ingestion hardening_.
3. **`TRACE_SAMPLING_RATIO=0`** — valid and means "drop every trace". Check the
   env var; empty means 1.0, `0` means zero.
4. **Workspace daily cap hit** — ingestion stops for the rest of the day
   (`logAnalyticsDailyCapGb` in `infra/main.bicep`; a Resource Health event
   fires). Check volume with [`../kql-starter-pack.md`](../kql-starter-pack.md)
   query #5, then raise/remove the cap or lower sampling.
5. **Wrong resource** — the connection string points at a different component
   /workspace than the one you're querying.
6. **One signal missing, others fine** — a specific pillar regressed; compare
   against the inventory + bridge notes in
   [`.claude/rules/60-observability.md`](../../../.claude/rules/60-observability.md)
   (e.g. pino/structlog are only exported via the Phase 1 bridges; `fetch`
   spans only via the undici instrumentation).

## Verify recovery

`/health` shows `"observability": "enabled"` with the expected reason (web: `ok`;
api: `azure monitor configured` — the api's startup log line also records the
effective sampling ratio and auth mode), then run
[`post-deploy-smoke.md`](post-deploy-smoke.md) — one BFF request must appear
end-to-end (web and api rows) in the tables.
