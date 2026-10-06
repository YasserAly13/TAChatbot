---
name: rename-project
description: Rename the AI Accelerator placeholders to the real project name, repo-wide, in one pass. Run this once right after cloning the template for a new AI project — it asks for the display name, derives a valid kebab-case slug, replaces every placeholder token, and regenerates the Python lockfile.
---

# Rename the project

> **Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

The template's project identity is a single placeholder family (documented in
[`README.md`](../../../README.md) → _Using this template_):

| Token              | Becomes          | Used for                                   |
| ------------------ | ---------------- | ------------------------------------------ |
| `AI Accelerator`   | `<Display Name>` | page titles, docs headings, OpenAPI titles |
| `ai-accelerator`   | `<slug>`         | OTEL service names, Docker images, compose |
| `@ai-accelerator/` | `@<slug>/`       | npm package scope (web)                    |

## Steps

1. **Get the display name.** Ask the user if it wasn't provided (e.g. `Acme Portal`).
   Allowed: letters, digits, spaces, `& ( ) . -`. No quotes or backslashes (it lands
   inside JSON strings and YAML values).
2. **Derive the slug** from the display name: lowercase, spaces → hyphens, drop anything
   not `[a-z0-9-]`, collapse repeated hyphens. It must match `^[a-z][a-z0-9-]*[a-z0-9]$`,
   max 40 chars (it becomes an npm scope, OTEL service name, Docker tag, and the
   pyproject distribution name). Show the user all three derived forms and **confirm**.
3. **Run the bundled script** (deterministic, longest-token-first, skips `node_modules`,
   lockfiles, build output, and this skill's own folder):

   ```bash
   node .claude/skills/rename-project/rename.mjs "<Display Name>" <slug>
   ```

   It prints per-file replacement counts and a leftover check that must come back empty.

4. **Regenerate the Python lockfile** — `uv.lock` records the distribution name
   (see `.claude/rules/35-fastapi.md`):

   ```bash
   cd apps/api && uv lock
   ```

   If `uv` is unavailable, edit the single `name = "<slug>-api"` line under the
   project's own `[[package]]` entry in `apps/api/uv.lock` by hand.

5. **Clear stale build output** if present (old names are baked in): `apps/web/.next`. It
   regenerates on the next build.
6. **Remove the template apparatus** (ask first — list the deletions):
   - the _Using this template_ section in `README.md` and the `/rename-project` mentions
     in `CLAUDE.md` (it describes placeholders that no longer exist);
   - `.claude/skills/rename-project/` and `.claude/commands/rename-project.md`.
7. **Verify**: `grep -ri "ai.accelerator" .` (excluding `node_modules`, `.venv`, lockfile
   noise) must return nothing; then run the test suites (`make test`) to confirm nothing
   asserted the old strings.

## Notes

- The trace origins (`0eb0`/`0c70`; `0a71` retired) are project-neutral — do **not** change them.
