---
description: PR-style review of the current diff against the constitution, path-scoped rules, and ADRs.
argument-hint: [base-ref]
---

**Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

Review the current diff using the `code-reviewer` subagent.

Diff source: `git diff` — or `git diff $ARGUMENTS...HEAD` if a base ref is given. If `git` can't resolve a diff, ask for the changed paths. Check against `CLAUDE.md`, the path-scoped `.claude/rules/`, the relevant `apps/<svc>/CLAUDE.md`, and `docs/adr/`.

Output the structured review (Summary / Blocking / Should fix / Suggestions / What looks good / Suggested next agents). Never approve — humans approve.
