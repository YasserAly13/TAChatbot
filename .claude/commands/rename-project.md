---
description: Rename the Team Assistant placeholders to the real project name, repo-wide.
argument-hint: <new project display name>
---

**Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

Use the `rename-project` skill to rename the project to: `$ARGUMENTS`.

1. Validate/derive the names (display name → kebab slug) per the skill's rules; ask if the
   display name is missing or invalid.
2. Run `node .claude/skills/rename-project/rename.mjs "<Display Name>" <slug>`.
3. Regenerate `apps/api/uv.lock` (`uv lock`), clear stale build output.
4. Offer to remove the template apparatus (the README _Using this template_ section, this
   command, and the skill) — it's meaningless after the rename.
5. Verify zero placeholder leftovers and run `make test`.
