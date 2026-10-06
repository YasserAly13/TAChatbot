---
name: lsp-refactor
description: Type-safe, verification-driven refactors (rename / change signature / move file) across the Team Assistant. Uses the TypeScript compiler (and ruff for Python) as the source of truth instead of freeform regex edits. Use whenever a change crosses files.
---

# Verification-driven refactor

> **Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

The compiler is the authority on whether a refactor is safe. Discipline: locate every reference, edit with intent, then prove it with a typecheck. Don't declare done until the check is green in every touched app. There is **no pnpm workspace** — run checks per app with `pnpm -C apps/<app>`.

## TypeScript (apps/web)

1. **Locate every reference first**: `rg -n --word-regexp 'OldName' apps/web/src apps/web/e2e`. Read each match; distinguish definition / use sites / incidental string matches (log messages, comments).
2. **Edit with intent.** Single file → `Edit` with unique context. Many audited identical matches → `Edit replace_all: true` is acceptable **only after** step 1 confirmed every match is real. Never `replace_all` a symbol unaudited (partial-match collisions are how silent breakage happens).
3. **Typecheck immediately:** `pnpm -C apps/web exec tsc --noEmit` (or `pnpm -C apps/web build`), then `pnpm -C apps/web test`. A green typecheck is the proof; a red one gives you the exact files/lines you missed. (A stale `apps/web/.next` can report deleted routes — delete it and re-run.)
4. **Format/lint:** `make fmt` (prettier). Re-run typecheck if it reformatted imports.

## Python (apps/api)

- `rg -n --word-regexp 'old_name' apps/api/app apps/api/alembic apps/api/tests`, edit, then `uv run --directory apps/api ruff check app alembic tests` + `ruff format app alembic tests`, `uv run --directory apps/api python -c "import app.main"` to catch import/eval breakage, and `uv run --directory apps/api pytest`. (No type checker is configured; adding pyright/mypy is an ADR-worthy choice.)

## Project-specific refactor notes

- Renaming a service method that's tied to a log message string → update the log string too (grep finds it; the compiler won't).
- Renaming a SQLAlchemy model/column → edit the model (and its import in `app/models/__init__.py`), fix use sites, and author the matching Alembic revision via `write-migration` (autogenerate does NOT detect renames — it emits drop + add; write `op.rename_table` / `op.alter_column(new_column_name=…)` by hand, with a mirroring `downgrade()`). Never apply it yourself.
- Moving a file → `git mv` (preserve blame) if git is initialized, then fix every importer (`rg 'from .*<old-stem>'`) and typecheck.

## Don't

- Refactor symbols with `sed` or unscoped `replace_all`.
- Skip the typecheck because "it's a small change" — that's the whole point.
- Change a public signature without updating every consumer in the same change.

## Optional upgrade

True AST-level renames via `ts-morph` or `typescript-language-server` aren't wired up — adding one is a deliberate ADR. The discipline above covers the vast majority of refactors.
