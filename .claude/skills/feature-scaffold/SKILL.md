---
name: feature-scaffold
description: Scaffold a complete feature in one pass following Team Assistant conventions, in whichever service applies — a Next.js BFF route + UI (apps/web), a FastAPI router with an optional SQLAlchemy model + repository (apps/api), an AI feature on the LangGraph runtime (target ai), or a RAG corpus + retrieval feature (target rag). Every scaffold ends with a "How to test" and a "Needs a human" section.
---

# Feature scaffold

> **Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

First decide the **target service** from the request. If ambiguous, ask. Then generate all the files for that target in one pass, following the path-scoped rules (`.claude/rules/30-nextjs.md` / `35-fastapi.md` / `25-sqlalchemy.md`) and each app's `CLAUDE.md`.

Naming: default to plural for URL paths/resources, singular for an entity/class. Ask if a name is plural/singular ambiguous.

**API versioning is mandatory** (`.claude/rules/05-api-versioning.md` / ADR-0001): every business endpoint you scaffold is served under `/v1`. Never scaffold an unversioned business endpoint, and never add one to the operational `routes.py` (that's only for `ping`/`info`/`health`).

## Target: apps/web (Next.js BFF route, optionally a page)

```
apps/web/src/app/api/v1/<feature>/route.ts   # BFF (/api/v1/<feature>): wrap in withBff; call ${API_BASE_URL}/v1/<feature> via fetchUpstream; 502 + trace_id on failure
apps/web/src/app/<feature>/page.tsx           # (optional) UI; client component only if interactive; calls the same-origin /api/v1 route
```

- Server-side only for the service URL (`API_BASE_URL`); never `NEXT_PUBLIC_*`.
- Log via `src/lib/logger.ts`. Verify: `pnpm -C apps/web build` and `pnpm -C apps/web test`.

## Target: apps/api (FastAPI router, optionally a model + repository)

```
apps/api/app/routers/<feature>.py     # APIRouter(prefix="/<feature>"); attach in app/routers/v1.py → /v1/<feature>
apps/api/app/models/<feature>.py      # (optional) 2.0-style model subclassing app.db.Base; import it in app/models/__init__.py
apps/api/app/repositories/<feature>.py# (optional) query functions taking an AsyncSession — keep SQL out of the router
```

- Attach the router to `v1_router` in `app/routers/v1.py` (`v1_router.include_router(<feature>.router)`). Don't add business routes to the operational `routes.py`.
- DB access only via the session dependency — `session: Annotated[AsyncSession, Depends(get_session)]` — and ORM constructs (`select(...)`); no module-level sessions, no sync engine (`.claude/rules/25-sqlalchemy.md`). A new model needs an Alembic revision → `write-migration` (confirmed, separate step; never `alembic upgrade` from here).
- Outbound calls via `traced_client()`; log via `get_logger(...)`; read the id with `get_trace_id()`. Raise `HTTPException`, not bare exceptions.
- Verify: `uv run --directory apps/api python -c "import app.main"`, `uv run --directory apps/api ruff format app && ruff check app`, `uv run --directory apps/api pytest`. Route tests override `get_session` via `app.dependency_overrides` — no database needed.

## Target: ai (an AI feature on the runtime in `app/ai/` — rule 70, ADR-0009)

```
apps/api/app/routers/<feature>.py            # /v1/<feature>: build_graph() once (lazy), POST /ask → ask(), POST /ask/stream → sse_response(stream_answer())
apps/api/app/ai/prompts/<feature>.md         # (optional) feature prompt file; render with render_prompt()
apps/api/app/ai/tools/<tool>.py              # (optional) a @tool + register_tool(); fake-backed test; threat-model note if it reaches new data
apps/api/tests/test_<feature>.py             # route tests with build_graph(chat_model=fake_chat_model(...), retriever=FakeRetriever(...)) — tests/ai/fakes.py
apps/api/tests/evals/cases.json              # + an eval case per new prompt
apps/web/src/app/api/v1/<feature>/route.ts   # BFF: fetchUpstream with a longer `signal` (model calls exceed 10 s); stream route uses src/lib/stream.ts
```

- Never construct `AzureChatOpenAI` outside `app/ai/client.py`; every call sits inside `model_call_span()`.
- Never log prompts/completions/retrieved text; return a bounded `error_kind` to clients, not exception text.
- Tools must be read-only and allow-listed (`app/ai/tools/queries.py`); anything else needs `threat-modeler` + an ADR first.

## Target: rag (a corpus + retrieval-backed feature)

```
docs/design/corpus-<name>.md                  # what is ingested, from where, refresh cadence, PII class, owner
apps/api/app/ai/tools/queries.py              # (optional) allow-listed queries if the feature also reads the external DB
apps/api/app/routers/<feature>.py             # as target ai, with retriever=get_default_retriever()
```

- The index definition lives in `app/ai/ingest.py` (`build_index`) — extend it there, never ad hoc, and keep `tools/retrieve.py` field names in sync.
- Ingestion is a human-triggered job: `uv run --directory apps/api python -m app.ai.ingest <path>` with `AZURE_SEARCH_*` + `AZURE_AI_EMBEDDING_*` set (needs _Search Index Data Contributor_ + _Search Service Contributor_). Bicep's `ai-search` module grants the api identity those roles; a dev key works locally.
- `AZURE_AI_EMBEDDING_DIMENSIONS` must match the deployment (1536 small / 3072 large) or the index build fails.

## After scaffolding (any target)

- Build the touched app to confirm it compiles.
- Invoke `test-writer` to add tests (Vitest for web, pytest for api — `.claude/rules/40-testing.md`).
- Invoke `observability-instrumenter` if the feature adds an outbound/cross-service call.
- Invoke `security-reviewer` before committing if it touches a BFF route, env, external HTTP, or an AI tool.
- Update `README.md` / the app's `.env.example` if you added a command, route, or env var (rule 14).
- **Always end with two sections** the developer can act on:
  - **How to test** — exact commands (`make test`, a `curl` against `/v1/...`, what the UI should show) and the expected result.
  - **Needs a human** — anything the scaffold could not do: a Bicep deploy, a cloud-team role grant, a Key Vault secret, a firewall IP, a model deployment, an ingestion run, a migration via `migrate.yml`.
