# Testing

Two services, two frameworks, one set of expectations. This is the deep version; the
quick reference table lives in the root [README](../../README.md#testing), and the shortest
statement of the rules is [`.claude/rules/40-testing.md`](../../.claude/rules/40-testing.md).

---

## Philosophy

**Offline, always.** No real database, no Azure, no network. The SQLAlchemy engine stays lazy
and never connects (the DB tests assert `pyodbc.connect` is never called); route tests that
need a session override `get_session` through `app.dependency_overrides`; outbound `fetch` /
`httpx` is mocked. A test that reaches something real is a broken test —
it will be flaky in CI and slow everywhere. The observability layer cooperates: with no
`APPLICATIONINSIGHTS_CONNECTION_STRING` the services run in degraded mode, which is exactly
the state tests run in.

**Favour the pyramid.** Many unit tests, fewer integration tests, end-to-end only for real
user journeys. In this repo that maps to: colocated unit specs, a small number of HTTP-level
suites per service, and one manual Playwright smoke.

**Happy path _and_ error path.** Every piece of new logic gets both. A handler that returns
`200` also has an upstream-failure branch; a validator that accepts also rejects. Testing only
the success case is the most common gap in review.

**Don't pad.** If a change has one testable layer, test that layer — do not manufacture
symmetrical tests across both services to look thorough. Coverage is a signal, not a target.

**Run them, show the results.** A change is not done with unrun or failing tests.

---

## The stacks

| App              | Framework                            | File locations                                         | Run                                                 | Coverage output               |
| ---------------- | ------------------------------------ | ------------------------------------------------------ | --------------------------------------------------- | ----------------------------- |
| `apps/web`       | Vitest (`node` environment)          | `src/**/*.test.ts` — `src/lib/` and BFF route handlers | `pnpm -C apps/web test` · `test:cov` · `test:watch` | `apps/web/coverage/lcov.info` |
| `apps/web` (e2e) | Playwright — **manual / local only** | `e2e/*.spec.ts`                                        | `pnpm -C apps/web test:e2e` (needs the stack up)    | —                             |
| `apps/api`       | pytest + Starlette `TestClient`      | `tests/test_*.py`                                      | `uv run --directory apps/api pytest`                | `apps/api/coverage.xml`       |

Everything at once:

```bash
make test        # fast — both suites, no coverage
make test-cov    # with coverage, exactly the commands CI runs
```

---

## The two cross-cutting invariants

Every suite in every service asserts these. They are the contracts that make the template a
template; a change that quietly breaks one is the failure mode this repo most wants to catch.

### 1. The trace contract

- A **valid** inbound `x-trace-id` is **adopted unchanged**.
- An **absent or invalid** one is **regenerated** with _that service's_ origin —
  `web=0eb0`, `api=0c70` — and matches `^[0-9a-f]{32}$`.
- The id is **echoed** on the response `x-trace-id` header.
- A new **outbound** call **forwards** the current id via the traced helper.

Real examples to model on:

| What                                         | File                                                                                                                                               |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| Adopt / regenerate / echo, at the HTTP level | [`apps/api/tests/test_routes.py`](../../apps/api/tests/test_routes.py)                                                                             |
| Same, through the BFF handlers               | [`apps/web/src/app/api/routes.test.ts`](../../apps/web/src/app/api/routes.test.ts) (also asserts the upstream call forwarded the id)               |
| The primitives themselves                    | [`apps/web/src/lib/trace.test.ts`](../../apps/web/src/lib/trace.test.ts), [`apps/api/tests/test_tracing.py`](../../apps/api/tests/test_tracing.py) |

The regex to assert against is per-service and origin-anchored — `/^0eb0[0-9a-f]{28}$/` in
`web`, `^0c70[0-9a-f]{28}$` in the `api` — which checks the origin nibble and the total 32-hex
length at once.

### 2. Fail-safe observability

With no `APPLICATIONINSIGHTS_CONNECTION_STRING` the service must still **boot**, must not
crash, and `/health` must report `"observability": "disabled"` with a human-readable `reason`.
Tests naturally run in this state, so asserting it costs nothing and catches an entire class
of regression (a telemetry init that throws, or that hard-fails on a missing connection
string).

Init is also **idempotent** — calling it twice must never double-register the SDK. Covered by
[`apps/web/src/lib/observability.test.ts`](../../apps/web/src/lib/observability.test.ts) and
[`apps/api/tests/test_observability_config.py`](../../apps/api/tests/test_observability_config.py).

A third invariant applies to any new business endpoint: **it is served under `/v1` and 404s
unversioned** — see [`apps/api/tests/test_versioning.py`](../../apps/api/tests/test_versioning.py).

And a fourth, for anything touching the database layer: **no test connects to a database.**
[`apps/api/tests/test_db_engine.py`](../../apps/api/tests/test_db_engine.py) and
[`test_db_session.py`](../../apps/api/tests/test_db_session.py) (and
[`test_db_external.py`](../../apps/api/tests/test_db_external.py) for the read-only engine)
monkeypatch `pyodbc.connect` to raise and prove the engines, the session dependencies, and the
lifespan never call it;
[`test_alembic.py`](../../apps/api/tests/test_alembic.py) proves `alembic.ini` holds no URL,
the history is linear with a real `downgrade()`, and offline `upgrade`/`downgrade --sql` render
the conversations tables without a database;
[`test_models.py`](../../apps/api/tests/test_models.py) compiles the models for SQL Server and
fails if the migration's `CREATE TABLE` differs from the model.

---

## Per-app specifics

### `apps/web` — Vitest in the node environment

[`vitest.config.ts`](../../apps/web/vitest.config.ts): `environment: 'node'`,
`include: ['src/**/*.{test,spec}.ts']`, `setupFiles: ['./vitest.setup.ts']`, and the `@` alias
resolving to `./src`.

**The node environment is deliberate.** What is tested here is the _server_ half of the app:
`src/lib/` (trace, logger, metrics, events, observability) and the BFF route handlers. A route
handler is just an exported `GET(req: Request)` function — call it with a plain `Request` and
assert on the returned `Response`, its status, its JSON body, and its `x-trace-id` header. No
React renderer, no jsdom.

[`vitest.setup.ts`](../../apps/web/vitest.setup.ts) sets `LOG_LEVEL=silent` — pino writes to
stdout directly, so the runner cannot capture it, and `logger.ts` reads `LOG_LEVEL` at import
time (setup files run first).

Coverage (v8 provider) includes `src/**/*.ts` and excludes the test files, `src/**/*.d.ts`,
and `src/instrumentation.ts`.

### `apps/api` — pytest + `TestClient`

Configured in [`pyproject.toml`](../../apps/api/pyproject.toml): `testpaths = ["tests"]`,
`addopts = "-q"`, coverage `source = ["app"]` with `tests/*` omitted.

Tests import the real application (`from app.main import app`) and drive it through
Starlette's `TestClient`, so the full middleware stack — including `TraceMiddleware` — runs.
Because tests live in `tests/` (outside the `app` package), they never mix with production
code and are omitted from the coverage denominator by `[tool.coverage.run] omit`.

**Database tests need no database.** The pattern (`tests/test_db_*.py`):

- monkeypatch `pyodbc.connect` to raise (aioodbc runs it in a thread pool), so any accidental
  connection fails the test loudly;
- for a route that takes `session: Annotated[AsyncSession, Depends(get_session)]` (or
  `Depends(get_external_session)`), register a fake with
  `app.dependency_overrides[get_session] = fake_session` and clear it afterwards;
- call `_reset_for_tests()` on `app.db.engine` / `app.db.session` / `app.db.external` when a
  test needs a fresh singleton.

A real-database integration tier would be **opt-in**: gate it on a reachable `DATABASE_URL`
(the dev Azure SQL database — there is no local one) and skip otherwise. None exists today.

`relative_files = true` under `[tool.coverage.run]` makes `coverage.xml` emit repo-relative
paths (`app/config.py`) instead of an absolute machine path, so the report is portable across
CI runners and any coverage consumer you later attach can map entries back to source files.

---

## Coverage

CI produces two coverage reports — `apps/web/coverage/lcov.info` (Vitest, v8 provider) and
`apps/api/coverage.xml` (pytest-cov) — and uploads them together as the `coverage-reports`
artifact (see [workflow → CI](workflow.md#ci)). **No external code-quality service is wired
up**; the reports are there for humans and for
whatever consumer you choose to attach later (an ADR-level decision). Coverage scope is
controlled by the test tools themselves, not by scanner properties.

### What is excluded, and why

| Excluded from coverage                   | Where                                                             | Why                                                                                                                                                 |
| ---------------------------------------- | ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `src/**/*.{test,spec}.ts`                | `apps/web/vitest.config.ts` (`coverage.exclude`)                  | Colocated test files carry no coverage of their own; counted as main source they would read as 0%-covered and tank the percentage.                  |
| `src/app/page.tsx`, `src/app/layout.tsx` | `apps/web/vitest.config.ts` (`coverage.include` is `src/**/*.ts`) | The **presentational layer** has no unit tests by design — it is React view code exercised by the manual Playwright suite, not by CI unit coverage. |
| `src/instrumentation.ts`                 | `apps/web/vitest.config.ts` (`coverage.exclude`)                  | Framework init hook; its logic is tested through `src/lib/observability.ts`.                                                                        |
| `tests/*`                                | `apps/api/pyproject.toml` (`[tool.coverage.run] omit`)            | Test files are omitted from the coverage denominator; they also sit outside the `app` package.                                                      |

### The consequence you must design around

**Logic that needs coverage must live in `src/lib/`**, not in `page.tsx` / `layout.tsx`.
Branching, fetching, formatting, and error handling put in the excluded view files will never
count toward the (new-code) coverage gate — and, more importantly, will never be
unit-tested. Keep views thin and push logic into `src/lib/` where node-env Vitest can reach
it.

Bringing the view layer into CI coverage would mean automating Playwright and merging its
lcov — an **ADR-level** change, not an ad-hoc manual upload.

---

## Playwright end-to-end

`apps/web/e2e/` holds a browser smoke suite. It is **manual and local by design** —
[`playwright.config.ts`](../../apps/web/playwright.config.ts) says so in a header comment, and
the CI workflow explicitly does not run it.

It needs the **whole stack** running, because it clicks the real buttons and asserts on real
responses coming back through the BFF:

```bash
make up                        # or: make dev
pnpm -C apps/web test:e2e
```

`baseURL` defaults to `http://localhost:3000` and can be overridden with `WEB_BASE_URL`. The
project runs Chromium, `fullyParallel`, with `trace: 'on-first-retry'`.

**When to run it:** before cutting a release, after any change to the UI or the BFF wiring,
and after a dependency bump that touches Next.js or React. It is the only thing that exercises
the presentational layer, so treat it as a required manual gate rather than an optional extra.

---

## CI's role

Run tests locally for fast feedback; **CI is the gate**. Every PR into `main`, `staging`, or
`development` runs both suites with coverage and publishes the `coverage-reports` artifact. If a
suite is green locally and red in CI, suspect a lockfile drift (CI installs with
`--frozen-lockfile` / `--frozen`) or a test that depends on local state.

Exactly what runs, in what order: [workflow → CI](workflow.md#ci).

---

## Changing the test setup

Introducing a **new test framework**, or making a major test-infrastructure change, needs an
[ADR](workflow.md#adr-process) and explicit agreement first — the two stacks here are a
deliberate choice, not an accident. Adding a test file, a fixture, or a helper inside an
existing stack does not.
