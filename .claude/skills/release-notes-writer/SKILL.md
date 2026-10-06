---
name: release-notes-writer
description: Generate CHANGELOG entries from Conventional Commits since the last tag, per service (apps/web and apps/api are independently versioned). Cross-references ADRs. Run before cutting a release. NOTE — no release tags exist yet, so the first run summarizes all commits.
---

# Release notes writer

> **Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

The two services are versioned independently (SemVer; both currently `0.0.0`). Generate notes per service that actually changed.

## Prereqs

- A git history with Conventional Commits. **No release tags exist yet**, so the first run falls back to all commits (workflow step 1). If the log is empty, say so — there's nothing to summarize.

## Workflow

1. Last tag: `git describe --tags --abbrev=0` (or all commits if none).
2. Commits since: `git log <last-tag>..HEAD --pretty=format:'%h %s'`.
3. Group by Conventional Commit type: `feat:` → Added · `fix:` → Fixed · `perf:` → Performance · `refactor:` → Internal · `docs:` → Docs · `chore/ci/build/test` → omit unless user-visible.
4. Scope to the affected service from the commit scope / changed paths (`apps/web`, `apps/api`).
5. For each commit also note: a new ADR introduced (link it); a new Alembic revision under `apps/api/alembic/versions/` or a model change ("DB migration required — `alembic upgrade head`"); a change to the trace/observability contract or env vars (call it out — it's consumer-facing).
6. Propose the next version per SemVer: `BREAKING CHANGE:`/`!` → MAJOR · `feat:` → MINOR · else PATCH. Judge from the consumer's perspective (CLAUDE.md rule 15).
7. Prepend a section to that service's `CHANGELOG.md` (Keep-a-Changelog format); create the file if absent.

## Output shape

```
## [0.2.0] — YYYY-MM-DD  (apps/api)
### Added
- <feature> (`GET /…`). Adopted ADR-NNNN.
### Fixed
- <fix>.
### Internal
- <refactor>.
```

## Hard rules

- Never invent commits. Empty log → say so.
- Never drop a `BREAKING CHANGE:` from the notes, even if "internal".
- Propose the version bump; never tag — tagging is a human action.
