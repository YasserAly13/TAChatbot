# Development

How work gets done in this repo: the process around a change, the mechanics of building one,
and the standards it has to meet. If you have not run the stack yet, start with
[Getting started](../getting-started.md).

## Documents

| Document                                   | What it covers                                                                                                                      | Read it when                                            |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| [workflow.md](workflow.md)                 | The independent-packages model, the change lifecycle, definition of done, exactly what CI runs, versioning, the ADR process         | Your first week, and again before your first PR         |
| [adding-a-feature.md](adding-a-feature.md) | End-to-end walkthrough of a `/v1/projects` feature across both services — FastAPI router + SQLAlchemy model, BFF route, tests, docs | You are about to add an endpoint                        |
| [testing.md](testing.md)                   | Test philosophy, the two stacks, the two invariants every suite asserts, coverage, manual Playwright                                | You are writing tests, or a coverage gate surprised you |
| [coding-standards.md](coding-standards.md) | Cross-service non-negotiables (logging, traced HTTP, env vars, versioning), formatting, per-service conventions, the forbidden list | Continuously — and definitely before a review           |

## Who these are for

Everyone writing code in this repo, regardless of which service. The template is polyglot on
purpose: the same contracts (`trace_id`, structured logs, `/v1`) hold in TypeScript and in
Python, and the per-service sections tell you how each framework expresses them.

## Related

- [`README.md`](../../README.md) — quick reference for running and operating the stack.
- [`docs/architecture/`](../architecture/README.md) — how the system is built and why.
- [`docs/adr/`](../adr/README.md) — the decision record.
- [`.claude/rules/`](../../.claude/rules/) — the enforced, path-scoped form of these
  conventions; the shortest statement of each rule lives there.
