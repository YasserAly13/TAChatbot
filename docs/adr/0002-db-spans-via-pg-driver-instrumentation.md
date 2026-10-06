# ADR-0002: DB dependency spans via pg driver instrumentation, not @prisma/instrumentation

|        |                                                                                  |
| ------ | -------------------------------------------------------------------------------- |
| Status | Superseded by [ADR-0004](0004-sqlalchemy-async-alembic-db-layer.md) (2026-09-20) |
| Date   | 2026-07-26                                                                       |

## Context

Roadmap Phase 2 requires database operations to appear as client-kind dependency spans in
`AppDependencies`. `apps/api` uses Prisma 7 with the driver-adapter model (`@prisma/adapter-pg`),
so every query ultimately executes through the `pg` driver. Two instrumentation paths exist:
Prisma's own OTel package (`@prisma/instrumentation`, emitting `prisma:*` engine/client spans) or
driver-level instrumentation (`@opentelemetry/instrumentation-pg`). The Azure Monitor distro
(`@azure/monitor-opentelemetry` 1.18.1) already registers the pg instrumentation **enabled by
default** (verified in its `shared/config.js`: `postgreSql: { enabled: true }`), and the api's
init-order (observability first import in `main.ts`) guarantees `pg` is patched before
`PrismaService` loads it. The roadmap also flags a real failure mode: ORM instrumentation
packages that pin incompatible OTel SDK versions can **throw inside the query path**.

## Decision

We rely on the distro's default `pg` driver-level instrumentation for DB dependency spans and do
NOT add `@prisma/instrumentation`. Zero new dependencies, zero version-compatibility surface, and
spans carry the db-system/statement attributes App Insights maps to `AppDependencies`.

## Consequences

- Good: no extra package whose `@opentelemetry/*` pins could drift from the distro's line (the
  observed ORM-instrumentation failure mode is avoided entirely).
- Good: works unchanged if Prisma is ever swapped for another pg-based access layer.
- Good: spans reflect what actually hit the wire (per-query), under the active request span.
- Bad: no Prisma-level semantic spans (`prisma:client:operation`, model/action attributes) —
  a query is visible as SQL against the driver, not as `user.findMany`.
- Bad: runtime proof is still pending — the schema is a placeholder and no real Postgres is
  provisioned; verify a query lands in `AppDependencies` during the Phase 6 smoke ([HUMAN]).

## Alternatives considered

- **`@prisma/instrumentation`** — rejected: adds a second instrumentation stack whose OTel
  dependency line is pinned by Prisma's release cadence, not the Azure distro's; the roadmap
  explicitly records this class of package throwing inside the query path when versions
  mismatch. Revisit only if model-level span semantics become a debugging need.
- **Manual client spans around a Prisma middleware/extension** — rejected while auto driver
  spans suffice; it duplicates what `instrumentation-pg` already emits and adds hand-written
  span lifecycle code to maintain.

## References

- Related ADRs: ADR-0001 (unrelated scheme precedent for structural decisions)
- Docs: `.claude/rules/60-observability.md` → _Distributed traces_; `.claude/rules/20-prisma.md`;
  `OBSERVABILITY-ROADMAP.md` Phase 2
- External: Azure Monitor OTel distro instrumentation set (`@azure/monitor-opentelemetry`
  `shared/config.js`)
