# ADR-0005: Name services by role — the FastAPI backend is `apps/api`

|        |            |
| ------ | ---------- |
| Status | Accepted   |
| Date   | 2026-09-20 |

## Context

After ADR-0003 the platform had two services named `web` (Next.js BFF + UI) and `python`
(FastAPI). `web` is named for its role; `python` was named for its runtime. That asymmetry leaked
everywhere a service is addressed — `PYTHON_BASE_URL`, the compose DNS name `python`, the OTel
cloud role `ai-accelerator-python`, the metric target label `python`, the `service` field on
`/ping` and `/health`, and the directory `apps/python` — and it would all have to change if the
backend were ever rewritten in another runtime. It also read oddly next to the language itself
("the python service runs on Python 3.14"). The name `api` had just been freed by ADR-0003, but
that removed service was a different thing (NestJS + Prisma) and its trace origin `0a71` is
retired, so reusing the name needs to be explicit about the history.

## Decision

We name services by **role**, not runtime. The FastAPI backend is **`apps/api`**: compose service
`api` (`http://api:8000`), env var **`API_BASE_URL`** in the BFF, OTel cloud role
**`ai-accelerator-api`**, service identity `"api"` on `/ping`, `/health` and `/info`, metric target
label `api`, and the directory `apps/api`. Its trace origin stays **`0c70`** — origins identify
a service instance across renames; **`0a71` remains retired** and never returns. "Python" is now
only ever the language (Python 3.14, pytest, `python-dotenv`, `uv run python`).

## Consequences

- Good: symmetric, role-based names (`web → api`); a future runtime change touches no
  identifiers.
- Good: conventional names — `API_BASE_URL`, `api` DNS — that new joiners expect.
- Bad: history has two different `apps/api` services. Every mention of the removed one now says
  "the former NestJS `apps/api` (ADR-0003, origin `0a71`)" so it cannot be confused with the
  current FastAPI `apps/api` (origin `0c70`).
- Bad: previously built images (`ai-accelerator-python`) and App Insights filters on the old
  cloud role name no longer match; the rename happened before any deployment.
- Neutral: `/info` still reports `"runtime": {"name": "python", ...}` — that field describes the
  interpreter, not the service, and is unchanged.

## Alternatives considered

- **Keep `python`** — rejected: runtime-named, asymmetric with `web`, and couples every
  identifier to the implementation language.
- **`backend`** — rejected: generic; the BFF is also a backend from the browser's point of view.
- **A brand-new origin for the renamed service** — rejected: origins mark a service instance,
  not its name; changing `0c70` would break correlation with telemetry already emitted and add a
  third origin to explain.

## References

- Related ADRs: ADR-0003 (removed the NestJS `apps/api`, retired `0a71`), ADR-0004 (the DB layer
  this service owns)
- Docs: `.claude/rules/00-architecture.md`; `.claude/rules/60-observability.md`;
  `apps/api/CLAUDE.md`; `docs/architecture/tracing.md`
