---
description: Instrument a route/feature with trace_id propagation, structured logs, and spans per the project contract.
argument-hint: <file or feature>
---

**Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

Use the `observability-instrumenter` agent to make `$ARGUMENTS` observable per `.claude/rules/60-observability.md`.

Ensure: inbound adopts and echoes `x-trace-id`; **every outbound call uses the traced helper** — `fetchUpstream` (web) / `traced_client` (api), never bare `fetch`/`httpx`; DB spans come from the SQLAlchemy instrumentation already registered at init without an engine (ADR-0008) — engine factories resolve `create_async_engine` at call time; one structured JSON log line per inbound + outbound carrying `trace_id` and the standard fields; telemetry stays fail-safe and non-blocking. There is no `@Span` decorator — spans come from auto-instrumentation; you wire trace_id + logging + propagation.

Report files changed, log lines added, outbound calls routed through the traced helper, and confirm the `trace_id` flows end-to-end for the touched path.
