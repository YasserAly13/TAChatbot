# ADR-0011: Component tests with React Testing Library in Vitest (per-file jsdom)

|        |            |
| ------ | ---------- |
| Status | Proposed   |
| Date   | 2026-09-28 |

## Context

Rule 40 excluded the web presentational layer from unit coverage: Vitest ran in the `node`
environment for `src/lib/*` and BFF route handlers, `.tsx` files were out of the coverage
denominator, and the only check on UI was a manual Playwright smoke. With ADR-0010 the web
app gains real components (chat thread, input, streaming panel) that a low-experience
developer will change often; "no automated check on UI" is no longer acceptable, and rule 40
required an ADR to change the test infrastructure.

## Decision

Component tests run in **Vitest with React Testing Library** (`@testing-library/react`,
`@testing-library/user-event`, `@testing-library/jest-dom`) in a **jsdom** environment
selected **per file** with `// @vitest-environment jsdom`; the default environment stays
`node` so lib and route tests are unchanged. `vitest.setup.ts` loads the jest-dom matchers;
each component test calls `cleanup()` in `afterEach` (Vitest globals stay off). Coverage now
includes `src/components/**/*.tsx`; pages (`src/app/**/*.tsx`) stay excluded and remain the
Playwright smoke's job; generated `src/lib/api-types.ts` and `src/mocks/**` fixtures are
excluded.

## Consequences

- Good: every component ships with a behaviour test (render states, user events, streaming
  via a mocked same-origin fetch) that runs in CI in seconds.
- Good: no second test runner; the per-file environment keeps the fast node suite fast.
- Bad: jsdom is not a browser — layout, CSS and real network are still Playwright's domain.
- Bad: `cleanup()` is manual; forgetting it leaks DOM between tests (documented in rule 40).

## Alternatives considered

- **Playwright component testing / in CI** — rejected for the unit tier: slower, needs
  browsers in CI; kept as the manual e2e smoke.
- **`environmentMatchGlobs` / Vitest projects** — rejected: the per-file docblock is simpler
  and explicit; revisit if the split grows.
- **`globals: true` for auto-cleanup** — rejected: implicit globals hide imports; an explicit
  `afterEach(cleanup)` is one line.

## References

- Related ADRs: ADR-0010
- Docs: `.claude/rules/40-testing.md`, `apps/web/vitest.config.ts`, `apps/web/vitest.setup.ts`
- External: Vitest environments (`https://vitest.dev/guide/environment`), Testing Library
  (`https://testing-library.com/docs/react-testing-library/intro/`)
