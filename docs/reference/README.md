# Reference

Lookup-grade reference material for the AI Accelerator's foundation surface — the HTTP
endpoints, environment variables, and task-runner commands that exist today. This is
reference (exact/exhaustive), not a tutorial; for narrative/how-to material see the sibling
`docs/` sections linked below.

## In this section

| Doc                                                    | Covers                                                                                                                                                          |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`http-api.md`](http-api.md)                           | Every HTTP route across `web`/`api`: the two BFF demo routes, each service's `/ping`, `/info`, `/health`, response shapes, error behavior, headers, versioning. |
| [`environment-variables.md`](environment-variables.md) | Every environment variable read by any service or `docker-compose.yml`: consumer, default, required?, effect; `.env` precedence and loading per app.            |
| [`commands.md`](commands.md)                           | `make`/`just` targets (parity table), each app's package/task scripts (`pnpm`, `uv`), and the Alembic migration commands.                                       |

## Service identity

Derived from `apps/web/package.json`, `apps/api/pyproject.toml`, and the trace/observability
source (`apps/web/src/lib/trace.ts`, `apps/api/app/tracing.py`, each service's
`observability.*`).

| Service    | Package / dist name             | Stack + version                                                                                                                                 | Port   | Trace origin | OTel service name (cloud role) |
| ---------- | ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------ | ------------ | ------------------------------ |
| `apps/web` | `@ai-accelerator/web` @ `0.0.0` | Next.js **16.2.6** (App Router, React 19.2.7) — BFF                                                                                             | `3000` | `0eb0`       | `ai-accelerator-web`           |
| `apps/api` | `ai-accelerator-api` @ `0.1.0`  | Python **>=3.14** + FastAPI **0.136.3** + SQLAlchemy **2.0.54** (aioodbc 0.5.0 / pyodbc 5.3.0 on Azure SQL) + Alembic **1.20.0**, managed by uv | `8000` | `0c70`       | `ai-accelerator-api`           |

Notes:

- `apps/web` is at `0.0.0` (pre-release, no features shipped); `apps/api` is at `0.1.0` — the
  Azure SQL driver change (ADR-0008) is a consumer-facing configuration break, recorded in
  `apps/api/CHANGELOG.md` (see [`CLAUDE.md`](../../CLAUDE.md) rule 15).
- Trace origin `0a71` belonged to the former **NestJS** `apps/api` service, removed in
  [ADR-0003](../adr/0003-remove-nestjs-api-layer.md); it is **retired and reserved** — never
  reassigned. Today's FastAPI `apps/api` is a different service: it took the `api` name in
  [ADR-0005](../adr/0005-name-services-by-role.md) and kept its origin `0c70`.
- `OTEL_SERVICE_NAME` values above are code defaults (`DEFAULT_SERVICE_NAME` /
  `DEFAULT_OTEL_SERVICE_NAME` in each service's observability module); an operator-supplied
  `OTEL_SERVICE_NAME` env var overrides them and is never clobbered (append-only resource
  defaulting — see `environment-variables.md`).
- Trace origin values are hard-coded constants (`ORIGIN` in `apps/web/src/lib/trace.ts` and in
  `apps/api/app/tracing.py`), not env-configurable.

## See also

- [`../../README.md`](../../README.md) — full architecture, run instructions, trace_id schema,
  observability, the SQLAlchemy + Alembic database section.
- [`../../CLAUDE.md`](../../CLAUDE.md) — project constitution / stack-at-a-glance.
- [`../adr/`](../adr/) — architecture decisions (e.g.
  [`0001-api-versioning.md`](../adr/0001-api-versioning.md)).
- [`../architecture/overview.md`](../architecture/overview.md),
  [`../development/testing.md`](../development/testing.md) — the narrative counterparts to this
  section's lookup tables.
