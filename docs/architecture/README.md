# Architecture

The deep-dive layer of the AI Accelerator's documentation. The root
[`README.md`](../../README.md) tells you **what the template is and how to run it**; these
documents explain **how it is built and why**, in enough detail to change it safely.

They describe the template itself — the placeholder names (`AI Accelerator`, `ai-accelerator`,
`@ai-accelerator/*`) are intentional and stay until a project runs `/rename-project`.

## Start with the living document

**[ARCHITECTURE.md](ARCHITECTURE.md)** is the one architecture file a project maintains
([ADR-0006](../adr/0006-living-architecture-document.md)): **Part A** is the template-owned
baseline (principles, C4 context/containers, the slots a project fills — not edited inside a
project); **Part B** is the project's own architecture, kept current by the team by hand.
Planning and scaffolding skills read it, together with the team's design inputs in
[`docs/design/`](../design/README.md), before doing anything. The documents below are the
deep-dives behind Part A.

## Documents

| Document                             | What it covers                                                                                                                                                                                             |
| ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [ARCHITECTURE.md](ARCHITECTURE.md)   | The living architecture: template baseline (Part A) + project architecture (Part B)                                                                                                                        |
| [overview.md](overview.md)           | System context & containers, the two services, the BFF pattern and why, request flows, the monorepo-of-independent-packages rationale, what is deliberately absent                                         |
| [tracing.md](tracing.md)             | The `trace_id` contract in depth: id anatomy, the adopt → store → forward → echo lifecycle, per-service implementations, and how it relates to the W3C/OTel trace id                                       |
| [observability.md](observability.md) | The observability stack: init order, sampling, cloud role identity, the log pipeline, dependency spans, metrics & events, ingestion auth, degraded mode                                                    |
| [data.md](data.md)                   | The data layer: SQLAlchemy 2 async + aioodbc + Alembic in `apps/api` on Azure SQL (never local), the read-only external engine, the database lifecycle, the empty model set and how to extend it, DB spans |
| [ai.md](ai.md)                       | The AI runtime: LangChain + LangGraph on Azure AI Foundry, the client seam, the `retrieve → answer` graph, tools, prompts, telemetry, streaming, the Azure AI Search ingestion job, testing                |

## Related material

**Decisions** — [`docs/adr/`](../adr/) records the choices these documents describe:

- [ADR-0001 — Mandatory API versioning (URI `/v1`)](../adr/0001-api-versioning.md)
- [ADR-0002 — DB dependency spans via pg driver instrumentation](../adr/0002-db-spans-via-pg-driver-instrumentation.md)
  (superseded by ADR-0004)
- [ADR-0003 — Remove the NestJS api layer; FastAPI is the sole backend](../adr/0003-remove-nestjs-api-layer.md)
- [ADR-0004 — SQLAlchemy 2 async + Alembic DB layer; DB spans via asyncpg instrumentation](../adr/0004-sqlalchemy-async-alembic-db-layer.md)
- [ADR-0005 — Name services by role; the FastAPI backend is `apps/api`](../adr/0005-name-services-by-role.md)
- [ADR-0006 — Living architecture document with a template-owned baseline](../adr/0006-living-architecture-document.md)

**Working conventions** — the path-scoped rules in `.claude/rules/` are the enforced,
day-to-day form of what is explained here:

- [`00-architecture.md`](../../.claude/rules/00-architecture.md) — boundaries, the trace
  invariant, what needs an ADR
- [`05-api-versioning.md`](../../.claude/rules/05-api-versioning.md) — mandatory `/v1` and its
  per-framework mechanics
- [`25-sqlalchemy.md`](../../.claude/rules/25-sqlalchemy.md) — SQLAlchemy 2 async + Alembic
  conventions and forbidden regressions
- [`60-observability.md`](../../.claude/rules/60-observability.md) — the full telemetry contract
- [`50-security.md`](../../.claude/rules/50-security.md) — the security baseline (BFF boundary,
  secrets, outbound HTTP, containers)

**Operating it** — [`docs/operations/`](../operations/) holds the KQL starter pack and the
runbooks; [`docs/security/threat-models/`](../security/threat-models/) holds design-time threat
models.

> If a document here disagrees with the code, **the code wins** — then fix the document
> (root [`CLAUDE.md`](../../CLAUDE.md), rule 14).
