# ADR-0010: UI foundation — Tailwind CSS v4 utilities, hand-written chat components, streaming via SSE pass-through, mocks behind `MOCK_UPSTREAM`

|        |            |
| ------ | ---------- |
| Status | Proposed   |
| Date   | 2026-09-28 |

## Context

`apps/web` shipped a demo page styled with hand-written CSS variables and no component
layer; rule 30 said "no UI kit is mandated — introduce one via an ADR". A frontend developer
with limited experience has to build chat surfaces (a thread, an input, streamed tokens,
sources) and work ahead of the backend without inventing a stack each time. Two constraints
shape the choice: the BFF rule (the browser only talks to same-origin Next routes) and the
api's streaming contract (Server-Sent Events from `app/ai/streaming.py`), which `fetchUpstream`
cannot forward (JSON accept header, 10 s timeout, buffered read).

## Decision

We adopt **Tailwind CSS v4** (via `@tailwindcss/postcss`, `@import 'tailwindcss'` in
`globals.css`) as the styling foundation and ship a **small set of hand-written chat
components** in `src/components/chat/` (`ChatThread`, `MessageInput`, `ChatPanel`) plus a
framework-free browser client (`src/lib/chat-client.ts`) and SSE helpers (`src/lib/sse.ts`).
The BFF forwards streams with **`streamUpstream` + `proxyStream`** (`src/lib/stream.ts`, a
5-minute whole-answer bound, `x-trace-id` forwarded). **`MOCK_UPSTREAM=true`** (server-side,
refused in `prod`, every mocked response marked `x-mock-upstream: true`) lets BFF routes serve
fixtures from `src/mocks/` typed against the generated API contract (`src/lib/api-types.ts` ←
`docs/reference/openapi.json`, `make openapi`). An example page `/chat` with the
`/api/v1/assistant/ask[/stream]` BFF routes demonstrates all of it; the api ships no
`/v1/assistant` route — a project adds one on `app/ai/`.

## Consequences

- Good: a working streaming chat surface exists on day one; the frontend developer works
  against typed fixtures and deletes one `if (isMockUpstream())` branch when the api lands.
- Good: the API contract is a committed artefact both developers see in every PR diff.
- Good: no design-system lock-in — Tailwind utilities compose with a component kit (e.g.
  shadcn/ui) a project may add later without rewriting these components.
- Bad: no markdown rendering, no virtualised list, no design tokens beyond Tailwind's defaults
  — deliberately minimal; projects extend.
- Bad: Tailwind's preflight resets some element defaults the old demo CSS relied on; the demo
  page keeps its variable-based styles and is visually acceptable, not pixel-identical.

## Alternatives considered

- **A full component library (MUI, Chakra, Ant)** — rejected: heavy, opinionated theming,
  slow to customise; not needed for a template whose UI is a starting point.
- **shadcn/ui from the start** — rejected as a baseline: it copies dozens of files and adds
  Radix dependencies before a project needs them; it remains the recommended next step.
- **Keep hand-written CSS only** — rejected: every component would re-invent spacing, colour
  and dark mode; utilities remove that tax.
- **Stream through `fetchUpstream`** — rejected: wrong accept header, wrong timeout, buffered.
- **WebSockets** — rejected: SSE fits one-way token streaming, works through the BFF and
  Container Apps ingress without extra infrastructure.

## References

- Related ADRs: ADR-0009 (the SSE contract), ADR-0011 (component tests), ADR-0001 (`/api/v1`)
- Docs: `.claude/rules/30-nextjs.md`, `apps/web/CLAUDE.md`, `apps/web/src/mocks/README.md`
- External: Next.js CSS guide (`https://nextjs.org/docs/app/getting-started/css`),
  openapi-typescript (`https://openapi-ts.dev/cli`)
