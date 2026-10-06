---
name: git-flow
description: Branch, commit and open a pull request for one roadmap item the repository's way — branch feat/<layer>-<id>-<slug> off development, Conventional Commits carrying the item id, the Definition-of-Done PR template via gh, promotion path development → staging → main. Commits and PR creation on request; pushing needs an explicit yes every time.
---

# Git flow for a roadmap item

> **Scope gate:** Say the branch name, the files to be committed and the commit message, then proceed with branch + commit when the developer asked for them. **`git push` and `gh pr create` need an explicit "yes" each time** (hard stop — outward-facing). Never force-push, never rewrite history, never commit to `development`/`staging`/`main` directly.

## Conventions

- **Branches:** `feat/<layer>-<id>-<slug>` (e.g. `feat/api-2.3-conversation-threads`),
  `fix/…` for fixes, `infra/…` for Bicep-only changes. Always off `development`
  (`git switch -c … development`). One roadmap item per branch.
- **Commits:** [Conventional Commits](https://www.conventionalcommits.org) with the service as
  scope and the item id in the body: `feat(api): create/list conversation threads` /
  `Roadmap: api 2.3`. `BREAKING CHANGE:` footer when the change is breaking (consumer view —
  root `CLAUDE.md` rule 15). Include the attribution trailer the session provides, if any.
- **PRs:** target `development` (the promotion path `development → staging → main` is
  enforced by CI; never open a feature PR against `staging`/`main`). Title = the commit
  subject; body = the repository PR template (`.github/pull_request_template.md`) with every
  Definition-of-Done box either ticked or explained, the roadmap item id, and the "How to
  test" steps copied from the roadmap.

## Steps

1. `git status --short`, `git branch --show-current`. Refuse if on `development`/`staging`/
   `main` with changes — create the feature branch first. Refuse if unrelated changes are
   mixed in; ask what to leave out.
2. Run the checks before committing: `make test` (or the per-app commands) and `make fmt`.
   Red ⇒ stop and report; nothing is committed on red.
3. Stage the item's files (`git add` by path — never `-A` blindly), show the diff summary,
   commit with the message above.
4. On "yes": `git push -u origin <branch>`; on a second "yes": `gh pr create --base development
--title … --body-file <tmp>` (body from the template). Report the PR URL.
5. After merge (human): the developer marks the roadmap item `done` if it was confirmed, or it
   stays `awaiting-test` until tested on `dev`.

## Never

- `git push --force`, `git rebase -i`, `git reset --hard` on shared branches, amending pushed
  commits, deleting branches, committing `.env*`, `infra/.env`, `*.local.bicepparam`, `infra/.build/`,
  deployment output files, or anything `git status` shows as ignored-but-forced.
