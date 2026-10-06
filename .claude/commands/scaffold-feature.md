---
description: Scaffold a feature (Next.js BFF route / FastAPI router + optional SQLAlchemy model) following project conventions.
argument-hint: <feature-name> [web|api]
---

**Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

Use the `feature-scaffold` skill to scaffold: `$ARGUMENTS`.

1. Determine the target service (apps/web / apps/api). If `$ARGUMENTS` doesn't make it clear, ask.
2. Generate the files for that target per the skill: a `apps/web/src/app/api/v1/<name>/route.ts` BFF handler using `withBff` + `fetchUpstream` against `${API_BASE_URL}/v1/<name>`; or a FastAPI router attached to `v1_router` using `traced_client` + `get_logger`, with an optional SQLAlchemy model (`app/models/<name>.py`) accessed only via `Depends(get_session)`.
3. Build the touched app to confirm it compiles (`pnpm -C apps/web build`, or an api import check + ruff).
4. Invoke `test-writer` (Vitest / pytest) and `observability-instrumenter` if a cross-service/outbound call was added. A new model also needs a confirmed `write-migration` step (never applied automatically).
5. Update `README.md` / the app's `.env.example` if a route, env var, or command changed.

Default plural for URL paths, singular for the entity/class. Ask if the name is plural/singular ambiguous.
