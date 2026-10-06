---
description: Testing conventions. Loaded when editing test files or test config.
paths:
  - '**/*.spec.ts'
  - '**/*.test.ts'
  - '**/e2e/**'
  - '**/test_*.py'
  - 'apps/api/tests/**'
  - '**/vitest.config.*'
  - '**/playwright.config.*'
---

# Testing conventions

> **Graded autonomy:** these are conventions to apply _within_ an approved plan or roadmap item — not a licence to act outside one. Hard stops (infra apply, migration apply, push, secrets, deletes) always need explicit confirmation — see [`CLAUDE.md`](../../CLAUDE.md) → _Graded autonomy_.

## Configured stacks

| App              | Stack                                                                                         | Location                                      | Run                                              | Coverage             |
| ---------------- | --------------------------------------------------------------------------------------------- | --------------------------------------------- | ------------------------------------------------ | -------------------- |
| `apps/web`       | Vitest (`node` env by default)                                                                | `src/**/*.test.ts` (lib + BFF route handlers) | `pnpm -C apps/web test` / `test:cov`             | `coverage/lcov.info` |
| `apps/web` (UI)  | Vitest + React Testing Library, **jsdom per file** (`// @vitest-environment jsdom`, ADR-0011) | `src/components/**/*.test.tsx`                | same                                             | same                 |
| `apps/web` (e2e) | Playwright — **manual/local only**                                                            | `e2e/*.spec.ts`                               | `pnpm -C apps/web test:e2e` (needs web + api up) | —                    |
| `apps/api`       | pytest + Starlette `TestClient`                                                               | `apps/api/tests/test_*.py`                    | `uv run --directory apps/api pytest`             | `coverage.xml`       |

Run everything: **`make test`** (fast) / **`make test-cov`** (coverage, as CI does). CI (`.github/workflows/ci.yml`) runs the coverage variants on every PR and uploads the two reports as the `coverage-reports` artifact (no external code-quality service is wired up); **Playwright e2e is not in CI**.

## What to assert

- Happy path **and** error/edge paths — not just the happy path.
- **The trace contract:** a valid inbound `x-trace-id` is adopted and echoed; an absent/invalid one is regenerated with the service origin (`web=0eb0`, `api=0c70`) and matches `^[0-9a-f]{32}$`.
- **Fail-safe observability:** with no `APPLICATIONINSIGHTS_CONNECTION_STRING`, the service still boots and `/health` reports `"observability": "disabled"`.
- New outbound calls: assert the traced helper forwards `x-trace-id`.

## Rules

- **Offline always** — no real DB, no Azure, no network. Mock outbound `fetch`/`httpx`.
- **Database tests (api, `25-sqlalchemy.md`):** unit tests never need a database — the engine is lazy, route tests override the session dependency (`app.dependency_overrides[get_session] = fake`), and DB-layer tests assert `pyodbc.connect` is never called (`tests/test_db_*.py`, `tests/test_alembic.py` show the pattern; Alembic is exercised in **offline** mode only, rendering T-SQL). The external read-only engine follows the same pattern (`tests/test_db_external.py`; override `get_external_session`). A real-DB integration tier is **opt-in**: gate it on a reachable `DATABASE_URL` (the dev Azure SQL database — there is no local one) and `pytest.skip` otherwise — never make CI depend on a database.
- Don't pad: if a change has one testable layer, write only that layer. Favor the pyramid (many unit, fewer integration, e2e only for journeys).
- Silence logs in tests via `LOG_LEVEL=silent` (Node setup files already do this).
- Run tests and show results; never report done with unrun/failing tests (CLAUDE.md rule 3).
- Introducing a **new** test framework or a major test-infra change → ADR + confirmation first.

## Coverage scope

- **Components are covered** (`src/components/**/*.tsx`, ADR-0011): every component ships a `*.test.tsx` beside it — RTL `render`/`screen`/`userEvent`, `// @vitest-environment jsdom` on line 1, `afterEach(cleanup)` (Vitest globals are off, so RTL does not auto-clean). Streaming UI is tested with a mocked same-origin `fetch` returning `sseStreamFromFrames(...)`.
- **Pages** (`src/app/**/*.tsx`) stay **out of unit coverage by design** — exercised by the **manual Playwright e2e** suite. Keep them thin: state and fetch logic live in components or `src/lib/`.
- Generated `src/lib/api-types.ts` and the fixtures in `src/mocks/**` are excluded from coverage; the BFF routes that use fixtures are tested in **both** modes (`MOCK_UPSTREAM` on and off).
- **AI code** (`apps/api/app/ai/**`, rule 70): fakes from `tests/ai/fakes.py`; never a live model/index; `tests/evals/` pins prompts. **OpenAPI:** `tests/test_openapi_export.py` fails when `docs/reference/openapi.json` is stale — run `make openapi`.
- Test files are excluded from coverage by the tools themselves (Vitest `coverage.exclude`; `[tool.coverage.run] omit = ["tests/*"]`). Covering pages in CI would mean automating Playwright + merging its lcov — an **ADR-level** change.
- No external code-quality service or coverage gate is wired up; adding one is an ADR-level decision.
