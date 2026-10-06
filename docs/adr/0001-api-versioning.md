# ADR-0001: Mandatory API versioning (URI `/v1`)

|        |            |
| ------ | ---------- |
| Status | Accepted   |
| Date   | 2026-06-10 |

## Context

The platform is at its base-repo/foundation stage: the only HTTP endpoints today
are operational (`/ping`, `/info`, `/health`), and no business AI modules exist yet.
This is the cheapest possible moment to fix the public HTTP contract, before any
consumer (the Unified Enterprise AI Portal, future agents, external integrations)
depends on an unversioned shape — once a shape ships unversioned, changing it is a
breaking change with no escape hatch. The platform spans three independently
deployed services (`apps/api` NestJS, `apps/api` FastAPI, `apps/web` Next.js BFF)
wired by the `x-trace-id` contract, so the versioning approach must be uniform across
all three and survive the `web → api → python` chain. We want versioning to be hard
to forget, not merely documented.

## Decision

We **mandate URI path versioning** (`/v{n}`, starting at `v1`) for **every business
HTTP endpoint** across all services, enforced structurally: NestJS enables global URI
versioning with `defaultVersion: '1'`; FastAPI mounts business routers under a `/v1`
router; the Next.js BFF places business route handlers under `src/app/api/v1/…`.
Operational endpoints (`/ping`, `/info`, `/health`) are the **only** exemption and stay
unversioned (NestJS `VERSION_NEUTRAL`; FastAPI's root operational router), because
container/Azure health probes target fixed paths.

## Consequences

- Good: the version is visible everywhere it matters — URLs, logs, traces, `curl`,
  proxy/cache keys — and is trivially greppable, so a CI gate can be added later.
- Good: with NestJS `defaultVersion` and the FastAPI `/v1` router, a new endpoint is
  versioned **by construction**; forgetting requires actively opting out.
- Good: uniform scheme across the three stacks and through the BFF chain.
- Bad: introducing a future `v2` means running two versions in parallel for a
  deprecation window (the cost of doing versioning properly).
- Bad: FastAPI and the Next.js BFF have no framework-level "force a version" primitive
  the way NestJS does, so their guarantee is the router/folder convention plus
  scaffold + code-review enforcement — weaker than NestJS's structural default.

## Alternatives considered

- **Header versioning (`X-API-Version`)** — rejected: the version is invisible in
  logs/`curl`/traces, is harder to test and grep, and is awkward to thread through the
  BFF chain. Poor fit for an observability-first, polyglot platform.
- **Accept media-type versioning (`application/vnd.team-assistant.v1+json`)** — rejected: the
  most REST-purist option but by far the most complex to implement, document, and
  enforce consistently across three stacks, for no benefit at this stage.
- **No versioning / "add it when we need it"** — rejected: retrofitting a version
  segment after consumers exist is itself a breaking change; the whole point is to do
  it before the first business endpoint ships.
- **Version the operational endpoints too** — rejected: health/liveness probes target
  fixed paths (`/health` in `docker-compose.yml`, Azure Container Apps), and moving them
  under `/v1` buys nothing while breaking those probes.

## References

- Related ADRs: none.
- Rule: `.claude/rules/05-api-versioning.md` (the enforced convention).
- Docs: `README.md` → _API versioning_; `apps/<svc>/CLAUDE.md` conventions.
- External: [NestJS Versioning](https://docs.nestjs.com/techniques/versioning).
