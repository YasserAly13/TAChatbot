# ADR-0006: Living architecture document with a template-owned baseline

|        |            |
| ------ | ---------- |
| Status | Proposed   |
| Date   | 2026-09-28 |

## Context

The template is meant to be the base of every AI project's architecture, with Claude doing
most of the implementation under human approval. Today the architecture is spread across four
explanatory documents (`overview.md`, `tracing.md`, `observability.md`, `data.md`) that
describe the template only; a project has no designated place to record _its_ architecture,
and the planning/scaffolding skills have no single, structured input to read. Without one,
agents infer architecture from code and chat, the team's intent drifts from what gets built,
and the template's baseline can be edited away inside a project by accident. The team decided
(2026-09-28) that the template ships an initial architecture that is the base of any project
architecture, and that the project layer is updated by the team by hand.

## Decision

We keep **one living architecture file**, `docs/architecture/ARCHITECTURE.md`, in two parts:
**Part A — Template baseline**, owned by the template and not edited inside a project, and
**Part B — Project architecture**, maintained by the project team by hand. Agents and skills
read both before planning and may only _propose_ changes to Part B (as a diff or a `Proposed`
ADR); the team's structured design inputs live beside it in `docs/design/`.

## Consequences

- Good: one place to look; planning skills get a structured, human-approved input.
- Good: the baseline's principles (BFF, `/v1`, trace contract, Azure-only data, Terraform,
  tests/docs/telemetry per change) survive project customisation because they are marked
  template-owned.
- Good: Part A states honestly which baseline slots are implemented vs planned, so the doc
  never over-claims what the code does.
- Bad: two owners in one file requires discipline — reviewers must reject project PRs that
  touch Part A.
- Bad: Part A must be updated on every template release, and projects must pull that change
  deliberately (it is not automatic).

## Alternatives considered

- **Keep architecture only in the existing per-topic docs** — rejected: no project layer, no
  single planning input, and nothing marks what is baseline vs project.
- **Two separate files (baseline vs project)** — rejected: readers and agents then need to
  reconcile two documents; a single file with clear ownership markers is simpler to keep in
  sync and to link from `CLAUDE.md`.
- **Let agents maintain the architecture document** — rejected: the team wants the project
  layer to reflect human intent, not what an agent inferred from code; proposals are fine,
  silent rewrites are not.

## References

- Related ADRs: ADR-0001 (versioning), ADR-0003 (sole backend), ADR-0004 (data layer)
- Docs: `docs/architecture/ARCHITECTURE.md`, `docs/design/README.md`,
  `docs/template-roadmap.md` (Phase 1), `.claude/rules/00-architecture.md`
