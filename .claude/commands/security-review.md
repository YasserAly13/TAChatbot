---
description: Security review of the current diff (BFF boundary, secrets, external HTTP, SQLAlchemy/Alembic, CORS, containers).
argument-hint: [files…]
---

**Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

Review the current diff using the `security-reviewer` subagent (or the `security-review` skill for a quick pass).

If `$ARGUMENTS` is provided, scope the review to those files. There is no auth yet — focus on the BFF boundary (no `NEXT_PUBLIC_*` service URLs / client secrets), secret & env handling, outbound HTTP (timeouts, SSRF, traced helpers), the SQLAlchemy/Alembic layer (parameterised SQL, `DATABASE_URL` handling, no agent-run `alembic upgrade`), CORS, and container hardening.

Output the full CRITICAL / HIGH / MEDIUM / LOW report. Block any merge until CRITICAL items are resolved.
