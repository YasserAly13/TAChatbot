# ADR-0003: Remove the NestJS `api` layer; FastAPI is the sole backend

|        |            |
| ------ | ---------- |
| Status | Accepted   |
| Date   | 2026-09-20 |

## Context

The template shipped three independent services: `apps/web` (Next.js BFF + UI), `apps/api`
(NestJS + Prisma 7) and `apps/python` (FastAPI — renamed `apps/api` later by ADR-0005), chained `web → api → python` under one
`x-trace-id`. At the baseline stage the two backends were functionally identical: each exposed
`/ping`, `/info`, `/health` and an empty `/v1` surface, each carried the full observability stack
(trace middleware, traced outbound client, Azure Monitor OTel init, log bridge, metrics, events),
and neither held business logic. Keeping both meant two runtimes, two lockfiles, two Dockerfiles,
two Sonar projects, two test stacks and two copies of every cross-cutting change, for a second hop
that added latency and a second place for the trace contract to break. Client work at Orion is
increasingly Python-first (data, AI and automation), so the team decided the Python service should
be the single backend and own the database.

## Decision

We remove `apps/api` entirely. The platform is two layers — `web (Next.js BFF) → python (FastAPI)`
— and `apps/python` (the FastAPI service, since renamed `apps/api` by ADR-0005) owns the database (see ADR-0004). The BFF calls python only, via
`API_BASE_URL`; the browser still talks only to `web`. Trace origin `0a71` is **retired and
reserved**: it is never reassigned, so historical telemetry stays unambiguous.

## Consequences

- Good: one backend runtime, one lockfile/Dockerfile/Sonar project fewer, one hop fewer per
  request, and every cross-cutting change (tracing, logging, metrics) lands once.
- Good: business logic has one home (`app/routers/*` of the FastAPI service, under `/v1`), so the
  vertical-specific playbooks the template exists for are written in one language.
- Good: the observability contract is unchanged — the python service already had parity with the
  api on every row of the capability matrix (trace middleware, traced client, fail-safe OTel init,
  redacting log bridge, bounded metrics, custom events, `/v1` surface).
- Bad: no Node/TypeScript backend option in the template; a client that mandates a Node backend
  would re-add one deliberately (new ADR) rather than inherit it.
- Bad: the demo `/ping/chain` and `/info/chain` endpoints and the BFF's `-python`/`-chain` routes
  are gone (there is no second hop to demonstrate); the two remaining BFF demo routes
  (`/api/ping-backend`, `/api/info-backend`) target python.
- Bad: the SonarCloud project `orion-digital-solutions_team-assistant-api` and any Azure alert /
  availability-test parameters that named `api` must be retired by a human (org-level actions).

## Alternatives considered

- **Keep NestJS, remove python** — rejected by the team: the Python service is where the data /
  AI work happens, and Prisma-on-Node would have left the database in the layer with the least
  business logic.
- **Keep both (status quo)** — rejected: duplicated cross-cutting code, a second hop with no
  functional value at this stage, and double the surface for the trace contract to drift.
- **Keep `apps/api` as a thin gateway in front of python** — rejected: the Next.js BFF already
  plays the gateway role for the browser; a second gateway is pure overhead.

## References

- Related ADRs: ADR-0001 (versioning scheme still applies to the two remaining services),
  ADR-0002 (superseded by ADR-0004), ADR-0004 (the database layer that replaces Prisma)
- Docs: `README.md` → _Architecture_; `.claude/rules/00-architecture.md`; `apps/api/CLAUDE.md`;
  `apps/web/CLAUDE.md`
- Playbook that executed this change: `REMOVE-API-LAYER.md` (executed 2026-09-20 and since
  removed from the repo; the outcome is recorded in this ADR, ADR-0004 and ADR-0005)
