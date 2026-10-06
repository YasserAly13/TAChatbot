---
description: Next.js + BFF conventions. Loaded when editing apps/web/**.
paths:
  - 'apps/web/**'
---

# Next.js conventions (apps/web)

> **Graded autonomy:** these are conventions to apply _within_ an approved plan or roadmap item — not a licence to act outside one. Hard stops (infra apply, migration apply, push, secrets, deletes) always need explicit confirmation — see [`CLAUDE.md`](../../CLAUDE.md) → _Graded autonomy_.

Next.js 16 App Router, React 19, port 3000, trace origin `0eb0`. This app is the **BFF**.
See [`apps/web/CLAUDE.md`](../../apps/web/CLAUDE.md).

## The BFF rule (non-negotiable)

- The browser only calls **same-origin** route handlers under `src/app/api/*`. Those handlers
  call `apps/api` (the sole backend, ADR-0003) server-side using `API_BASE_URL`.
- **Never** expose a service base URL or secret to client code, and **never** use `NEXT_PUBLIC_*`
  for one. Service URLs are server-side env only.

## App Router

- Routes under `src/app/`: `page.tsx`, `layout.tsx`, route handlers `route.ts`.
- React Server Components by default; add `'use client'` only for state/effects/refs/browser APIs.

## BFF route handlers

- Wrap the handler body in **`withBff`** (`src/lib/trace.ts`): it adopts/generates `x-trace-id`,
  runs inside the AsyncLocalStorage scope, and echoes the header on the response.
- Call upstream services with **`fetchUpstream`** (forwards `x-trace-id`) — never bare `fetch`.
  A model-backed endpoint routinely exceeds its 10 s default: pass `signal: AbortSignal.timeout(…)`.
- **Streaming (SSE) upstreams** use **`streamUpstream` + `proxyStream`** (`src/lib/stream.ts`) —
  never `fetchUpstream` (JSON accept header, 10 s timeout, buffered read). The browser reads it
  with `askStream` (`src/lib/chat-client.ts`); frames are parsed by `src/lib/sse.ts`.
- On upstream failure, return a `502` JSON body including `trace_id` so the UI degrades gracefully
  (a streaming route returns a terminal `error` SSE frame with a bounded `error_kind`).
- **Mocks (working ahead of the api):** inside the handler, `if (isMockUpstream()) return
mockJson(fixture, traceId)` / `mockSse(frames, traceId)` (`src/lib/mocks.ts`), fixtures in
  `src/mocks/<feature>.ts` typed against `src/lib/api-types.ts`. `MOCK_UPSTREAM` is server-side
  only, refused in `prod`, and every mocked response carries `x-mock-upstream: true`. Removing
  the mock is deleting that branch — the real call stays in the same handler. Both modes are
  tested.
- **The API contract** is `docs/reference/openapi.json` → `src/lib/api-types.ts` (`make
openapi`); CI fails when it is stale. Type request/response shapes from it, never by hand.
- **API versioning (mandatory — `05-api-versioning.md`):** business BFF handlers live under
  `src/app/api/v1/<feature>/route.ts` (→ `/api/v1/<feature>`) and call the matching versioned
  upstream (`${API_BASE_URL}/v1/…`). Next has no global versioning primitive, so the folder
  **is** the rule. The existing demo routes (`/api/ping-backend`, `/api/info-backend`, `/health`)
  are not business endpoints and stay as-is.

## Logging & observability

- Log via `src/lib/logger.ts` (pino → JSON stdout) — never `console.log`.
- OTel initializes in `src/instrumentation.ts` `register()`, guarded to the nodejs runtime;
  `@azure/monitor-opentelemetry` is in `serverExternalPackages`. See `60-observability.md`.

## Build / config

- `next.config.ts`: `output: 'standalone'`, and `turbopack.root` + `outputFileTracingRoot`
  pinned to the app dir (sibling lockfiles otherwise confuse Next's root inference).
- After a local production `next build`, **don't** then run `next dev` against the same `.next`
  (dev-cache pollution). Delete `.next` if you switch modes.

## UI foundation (ADR-0010 / ADR-0011)

- **Tailwind CSS v4** utilities (`@tailwindcss/postcss`, `@import 'tailwindcss'` in
  `globals.css`) for component styling; CSS modules only when utilities can't express it.
- Components live in `src/components/<area>/` — small, typed props, presentational where
  possible (`'use client'` only for state/effects). The chat set (`ChatThread`, `MessageInput`,
  `ChatPanel`) is the reference shape; `src/app/chat/page.tsx` is the example page.
- **Every component ships a test** next to it (`*.test.tsx`, `// @vitest-environment jsdom`,
  React Testing Library, `afterEach(cleanup)`); pages stay under the manual Playwright smoke.
- A component kit (e.g. shadcn/ui) or a client-state library is a project decision — add it via
  an ADR; it composes with, not replaces, this foundation.

## Not present yet

No auth (the planned module is **Okta**, roadmap Phase 8) and no global client-state library.
Introduce either via an ADR (auth also needs a threat model).
