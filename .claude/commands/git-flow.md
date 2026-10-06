---
description: Branch/commit/PR for one roadmap item — feat/<layer>-<id>-<slug> off development, Conventional Commits with the item id, PR template via gh. Push and PR creation need an explicit yes.
argument-hint: <layer> <item id> [branch|commit|pr]
---

Use the `git-flow` skill for: `$ARGUMENTS`.

Run the checks first (`make test`, `make fmt`) — nothing is committed on red. Branch + commit when asked; `git push` and `gh pr create` only after an explicit "yes" each. Never touch `development`/`staging`/`main` directly, never force-push.
