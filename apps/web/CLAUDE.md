# apps/web — CLAUDE.md

Next.js 16 (App Router) **BFF + UI** for the **Team Assistant** (the brandless starter
template Orion Digital Solutions built for the Diriyah Company AI team). Port **3000**, trace
origin **`0eb0`**, OTEL service `team-assistant-web`. Project-wide rules and the shared
`trace_id` / observability contract live in the root [CLAUDE.md](../../CLAUDE.md) and
[README.md](../../README.md) — this file is the web-specific context. Treat it as a starting
map; read the actual files when you need detail.

## The BFF rule (non-negotiable)

The browser **only** ever talks to this Next server. The two buttons call **same-origin**
route handlers under `src/app/api/*`; those handlers (the BFF) call the api (FastAPI)
backend **server-side** using `API_BASE_URL` — the sole backend since ADR-0003. **Never**
expose service URLs or secrets to client code, and never use `NEXT_PUBLIC_*` for a service base
URL.

## Layout

- `src/app/page.tsx` — client UI: two button rows over the one path (web → api) — **Ping**
  (`/api/ping-backend`) and **Info** (`/api/info-backend`); renders each response + its
  `trace_id`.
- `src/app/api/ping-backend/route.ts`, `src/app/api/info-backend/route.ts` — BFF route
  handlers (server-side) targeting the api's `/ping` and `/info`. Wrap the handler in
  `withBff`, call upstream with `fetchUpstream`; on upstream failure return `502` with a
  `trace_id` (and `target: 'api'`) so the UI degrades gracefully.
- `src/app/health/route.ts` — `/health`.
- `src/app/api/v1/assistant/ask/route.ts` + `ask/stream/route.ts` — **example business routes**
  (JSON + SSE) that proxy `${API_BASE_URL}/v1/assistant/…` or, with `MOCK_UPSTREAM=true`, serve
  `src/mocks/assistant.ts`. `src/app/chat/page.tsx` — the example chat page on them.
- `src/components/chat/` — `ChatThread`, `MessageInput`, `ChatPanel` (Tailwind, RTL-tested).
- `src/lib/stream.ts` (`streamUpstream`/`proxyStream`), `src/lib/sse.ts` (frame parser/builder),
  `src/lib/chat-client.ts` (`askStream`, browser → BFF), `src/lib/mocks.ts`
  (`isMockUpstream`/`mockJson`/`mockSse`), `src/lib/api-types.ts` (**generated** — `make openapi`).
- `src/lib/trace.ts` — `withBff` (adopt/generate `x-trace-id`, run inside the `AsyncLocalStorage`
  store, echo the header on the response, record the request-duration metric — pass
  `{ routeClass }` for dynamic segments), `fetchUpstream` (the ONLY sanctioned HTTP client:
  forwards `x-trace-id`, bounds every call with `AbortSignal.timeout(UPSTREAM_TIMEOUT_MS)` (10 s)
  unless the caller passes its own `signal`, records hop-duration + upstream-failure metrics; traceparent +
  dependency span via the undici instrumentation), `getTraceId`, origin `0eb0`.
- `src/lib/metrics.ts` — `getMeter(scope)` (namespaced `team-assistant.<scope>`, no-op when
  degraded), `statusClass`/`resolveTarget` (bounded labels: `api` | `other`), starter instruments:
  request-duration + chain-hop histograms, upstream-failure counter. **Bounded attributes
  only** — rule 60 → _Metrics & events_.
- `src/lib/events.ts` — `trackEvent(name, attrs)` → App Insights `customEvents` (via the
  `microsoft.custom_event.name` log-record marker); local structured line always prints;
  `service.start` wired in `instrumentation.ts`.
- `src/lib/logger.ts` — pino → JSON stdout (`service/origin/env/trace_id/message`);
  **redaction at source** (`DEFAULT_REDACTED_FIELDS`/`buildLogger({redactPaths})`), **OTel
  Logs bridge** teeing every line to Azure when enabled (opt out with
  `buildLogger({telemetryBridge: false})`), **async stdout sink** + exit flush. See rule 60 →
  _Log pipeline_.
- `src/lib/observability.ts` — `initObservability` (fail-safe `useAzureMonitor`, **idempotent**
  via a `globalThis` Symbol.for guard shared across Next's module graphs) +
  `getObservabilityState` (env-derived when not yet initialized — see gotchas). Pins
  **fixed-percentage sampling** (`TRACE_SAMPLING_RATIO`, default 1.0; `OTEL_TRACES_SAMPLER*`
  wins) and defaults the cloud role identity (`service.name`/`service.instance.id`,
  append-only). On success registers the **undici** (fetch dependency spans — safe post-load:
  `diagnostics_channel`) + **runtime-node** (event-loop/GC/heap metrics) instrumentations.
  Ingestion auth via **`TELEMETRY_AUTH_MODE`** (`managed_identity` → Entra ID credential; a
  mistyped value disables observability VISIBLY — rule 60 → _Ingestion auth_).
  See `.claude/rules/60-observability.md`.
- `src/instrumentation.ts` — `register()` → `if (process.env.NEXT_RUNTIME === 'nodejs')` →
  `initObservability()`, then `trackEvent('service.start')`.
- `next.config.ts` — `output: 'standalone'`, `serverExternalPackages`
  (`@azure/monitor-opentelemetry`, the `@opentelemetry/*` api/instrumentation packages, `pino`),
  and `turbopack.root` + `outputFileTracingRoot` pinned to this directory.

## Conventions

- New **business** BFF endpoint → `src/app/api/v1/<feature>/route.ts` (→ `/api/v1/<feature>`),
  wrapped in `withBff`, calling the matching `${API_BASE_URL}/v1/…` upstream — API versioning
  is mandatory (ADR-0001 / rule 05). The demo routes (`/api/ping-backend`, `/api/info-backend`)
  are exempt and stay as-is.
- Any upstream call from a route → `fetchUpstream` (trace propagation + echo), never bare `fetch`;
  SSE upstreams → `streamUpstream` + `proxyStream` (`src/lib/stream.ts`).
- Server-only secrets/URLs; client components only call same-origin Next routes.
- **Working ahead of the api:** `MOCK_UPSTREAM=true` in `.env.local` makes a route serve its
  `src/mocks/<feature>.ts` fixture (`isMockUpstream()` / `mockJson` / `mockSse` in
  `src/lib/mocks.ts`); fixtures are typed against `src/lib/api-types.ts` (generated — `make
openapi`). Example: `/api/v1/assistant/ask[/stream]` + the `/chat` page.
- **UI (ADR-0010/0011):** Tailwind v4 utilities; components in `src/components/<area>/` with a
  `*.test.tsx` beside each (`// @vitest-environment jsdom`, RTL, `afterEach(cleanup)`); the
  browser-side streaming client is `src/lib/chat-client.ts` (`askStream`), SSE parsing in
  `src/lib/sse.ts`.

## Commands

```bash
pnpm -C apps/web install
pnpm -C apps/web dev            # next dev :3000 on 127.0.0.1 only  (MOCK_UPSTREAM=true in .env.local to use the /chat page without the api)
pnpm -C apps/web build          # next build (standalone output)
pnpm -C apps/web test           # Vitest (lib + BFF routes in node; components in jsdom); test:cov for coverage
pnpm -C apps/web typecheck      # tsc --noEmit
pnpm -C apps/web api-types      # regenerate src/lib/api-types.ts from docs/reference/openapi.json (or: make openapi)
pnpm -C apps/web test:e2e       # Playwright smoke — MANUAL/local, needs web + api up
```

## Gotchas

- **Dev cache:** do **not** run a local production `pnpm build` and then `next dev` against the
  same `.next` — it mixes prod + dev artifacts and throws
  `components.ComponentMod.handler is not a function`. Delete `.next` to recover. (Docker builds
  are isolated, so `just build` / `just dev` never collide.)
- `instrumentation.ts` lives in **`src/`** (this is a src-dir app). The Azure OTel package is a
  `serverExternalPackage` to avoid bundling conflicts.
- `getObservabilityState` re-derives state from env inside route handlers because Next can put
  `instrumentation.ts` and route bundles in **separate module graphs** (the init flag isn't
  shared), so `/health` still reports the correct reason.
- **pnpm 11:** `pnpm-workspace.yaml` here carries the build-script settings; the `Dockerfile`
  must COPY it into the deps stage.
