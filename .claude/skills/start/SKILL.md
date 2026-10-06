---
name: start
description: Session resume for a developer — read the roadmaps and tell them, in plain language, where the project stands, what is next for their layer, what is waiting on a human, and the one command to run. Read-only. Use at the start of every session and whenever someone asks "what now?".
---

# Start here

> **Scope gate:** Read-only — reads `roadmaps/*/ROADMAP.md`, `docs/template-roadmap.md` (if present), `git status`/`git log -5`. Nothing is changed.

## Steps

0. Sanity: `.github/workflows/ci.yml`, `.claude/settings.json`, `infra/main.bicep` and
   `infra/platform/dev.json` exist (a copy without hidden folders loses them — say so and point
   to `bash scripts/doctor.sh`). If `infra/platform/*.json` still hold the template placeholders
   (`00000000-…`, `rg-ai-<env>`), list "platform manifests from the cloud team" under _Waiting on a human_.
1. If `roadmaps/` has no `ROADMAP.md` files: the project is not planned yet. Say whether
   `ARCHITECTURE.md` Part B and `docs/design/` are filled in, and point to `/init-project`
   (fresh clone), `/architecture-review`, then `/plan-roadmap <layer>`.
2. Otherwise, for each layer (`api`, `web`, `infra`): count items by status; list
   `in-progress` and `awaiting-test` items (someone is mid-way — say who, from `notes`); list
   `blocked` items with their reason; compute the next **unblocked** `todo` item.
3. Collect every open `needs_human` line across layers into one list — this is what the
   admin has to do.
4. `git status --short` / `git log -5 --oneline`: uncommitted work or a branch mid-flight? Say
   so and suggest `/git-flow`.
5. Ask which layer the developer works on if not obvious from the branch name
   (`feat/<layer>-…`) or their words.

## Output (short — this is a briefing, not a report)

```
## Where we are — <date>
- api:   N done · N awaiting-test · N in-progress · N todo · N blocked
- web:   …
- infra: …

### Waiting on you (developer)
- <layer> <id> — awaiting-test: run the "How to test" steps and reply done/changes

### Waiting on a human (admin)
- <layer> <id> — <needs_human line>

### Next for <your layer>
- <id> — <title> (unblocked). Command: `/implement-next <layer> <id>`

### Repo
- branch <name>, <clean | N uncommitted files> — `/git-flow` when ready
```

Never edit a roadmap from here; never start implementing — that is `/implement-next`.
