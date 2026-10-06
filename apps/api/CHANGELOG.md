# Changelog — `apps/api`

All notable changes to the **api** service (FastAPI). The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/) from the consumer's perspective (root `CLAUDE.md`, rule 15).
The two services version independently.

## [Unreleased]

## [0.9.0] — 2026-10-06

### Added

- **`AI_MAX_OUTPUT_TOKENS`** (default `1024`, `0` = no cap) — caps each answer's length and
  cost; the chat client sends it as `max_completion_tokens` (verified against
  `langchain-openai` 1.6.6). Closes the "no output cap" cost finding from the 4.1 security
  review; rate limiting stays with the 1.2 threat model. Documented in both `.env.example`s,
  `docker-compose.yml` and `docs/reference/environment-variables.md`.

## [0.8.0] — 2026-10-06

### Added

- **`POST /v1/conversations/{conversation_id}/ask`** (roadmap api 4.1, F1) — `{ "question" }`
  (trimmed, 1–4,000 characters) → `200 { message_id, answer, citations: [{ title, path }] }`.
  The question is stored and committed before the model runs; the last 10 messages are the
  history; the answer is stored with its citations and output token count; the first question
  renames a "New conversation". `404 not_found`, `422 validation_error`, `503 ai_unavailable`
  (question kept, only a bounded `error_kind` logged).
- `get_answer_graph` dependency — the `retrieve → answer` graph built once, overridable in
  tests; repository `title_from_question`.
- One deadline for the whole ask (2 × `AI_REQUEST_TIMEOUT_SECONDS`) — the AI Search SDK call has
  no timeout of its own. Only upstream failures (OpenAI/httpx, Azure SDK, timeout) and an empty
  answer become `503 ai_unavailable`; a missing AI configuration keeps its own 503 handler, and
  a bug is a `500 internal_error` with its location logged. History holds answered turns only,
  so a retried question is not sent twice.

### Fixed

- `touch` never moves `updated_at` backwards, so renaming right after a message cannot make the
  next message's timestamp tie with it.

## [0.7.0] — 2026-10-06

### Changed

- **Sources are `[{title, path}]`** (roadmap api 3.1, B8 #7): `Answer.sources` and the SSE
  `sources` / `done` frames carry one `{title, path}` per cited document instead of a list of
  paths. No `/v1` route streams yet, so no consumer breaks; the web chat components still
  expect strings and change with the web roadmap.
- **Ingestion** stores a searchable `title` per chunk (the first `# ` heading, else the file
  name) and stores `source` relative to the ingested folder's parent — `ingest ../../docs`
  stores `docs/README.md`, not `../../docs/README.md`.

### Added

- Index field `title` (`build_index`); `ensure_index` adds it to an existing index in place.
  Retrieval selects it and falls back to the source's file name for chunks indexed before it
  existed; against an index that does not have the field yet, the first `select=title` 400 is
  caught once and retrieval continues without it (no outage before the re-index).
- Fixed: `python -m app.ai.ingest` now loads `apps/api/.env` like `app.main` (it failed with
  `AINotConfigured` on a developer machine even when `.env` had the search settings).
- Hardening: titles ignore `# ` lines in fenced code and YAML front matter; files that resolve
  outside the ingested folder (symlinks) are skipped; a stored source that could expose a
  machine path (absolute, drive letter, `..`, backslashes) reaches clients as its file name.

## [0.6.0] — 2026-10-06

### Added

- **`GET /v1/conversations/{conversation_id}`** — one conversation with its messages, oldest
  first: `{ id, title, created_at, updated_at, messages: [{ id, role, content, citations,
  created_at }] }`; `citations` parsed to `[{ title, path }]` (or `null`); `404 not_found` for an
  unknown id, `422 validation_error` for a non-UUID (roadmap api 2.2).
- Repository `get_conversation_with_messages` — loads messages explicitly (`selectinload`; the
  relationship is `lazy="raise"`).

### Changed

- Messages read oldest first by `(created_at, id)`, and `add_message` makes each new message's
  `created_at` strictly later than the conversation's last update — a question and its answer
  stored in the same millisecond can no longer read out of order.
- A stored `citations` value that is valid JSON but not `[{title, path}]` reads as `null` and
  logs only the failure kind, never the stored text. `openapi.json` and web `api-types.ts`
  regenerated.

## [0.5.0] — 2026-10-06

### Added

- **`POST /v1/conversations`** — start a conversation; optional `{ "title" }` (trimmed; at most
  200 UTF-16 units — an emoji counts 2 — so it always fits `NVARCHAR(200)`; no control
  characters; blank → "New conversation"); `201 { id, title, created_at, updated_at }`
  (roadmap api 2.1).
- **`GET /v1/conversations?limit=50`** (1–100) — `{ items: [{ id, title, updated_at }], count }`,
  most recently updated first.
- **Conversation repository** (`app/repositories/conversations.py`): create, list, get, add
  message (bumps `updated_at`), rename, touch — used through `Depends(get_session)`.
- Timestamps in responses are UTC with an explicit `Z`. `docs/reference/openapi.json` and the
  web's generated `api-types.ts` regenerated.

## [0.4.0] — 2026-10-06

### Added

- **Conversation and message models** (`app/models/conversation.py`, roadmap api 1.1):
  `conversations` (`id`, `title nvarchar(200)` default "New conversation", `created_at`,
  `updated_at`) and `messages` (`conversation_id` FK, `role` check `user|assistant`,
  `content`/`citations` `nvarchar(max)` with an `ISJSON` check on `citations`, `token_count`,
  `created_at`); `datetime2(3)` timestamps defaulting to `SYSUTCDATETIME()`; indexes for the
  newest-first list and the oldest-first thread (`docs/design/db-design.md`).
- **First Alembic revision** `7c1d4e2a9b30` creating both tables, with a full `downgrade()`.
  Not applied by the project — a named human applies it to dev (ADR-0013).
- `tests/test_models.py` compiles the models for SQL Server and fails if the migration's
  `CREATE TABLE` drifts from the model; `tests/test_alembic.py` now covers offline upgrade and
  downgrade of the real revision.

### Fixed

- `alembic/env.py` now loads `apps/api/.env` (like `app.main`, ambient env wins), so
  `alembic upgrade`/`current` on a developer machine reach the database in `.env` instead of the
  placeholder URL.

No HTTP API change.

## [0.3.0] — 2026-10-04

### Added

- **Error contract** `app/errors.py`: every non-2xx response body is `{"error": <snake_case code>,
  "trace_id": <id>}` with the trace id also echoed in `x-trace-id`. `ApiError` (+ `NotFound`,
  `Conflict`, `AIUnavailable`) for routes and repositories; handlers for `HTTPException`
  (a snake_case `detail` becomes the code, prose maps to a default per status; `Allow` and other
  protocol headers kept), `RequestValidationError` (`422 validation_error` — field locations are
  logged, never returned) and `AINotConfigured` (`503 ai_unavailable`); `UnhandledErrorMiddleware`
  turns anything else into `500 internal_error` logging only the exception kind and location.
  `v1_router` documents 422/500 as `ErrorBody` in OpenAPI (`docs/reference/openapi.json`
  regenerated). Promoted from the first project dry run (`docs/development/walkthrough-team-assistant.md`).

### Changed

- Comments and docstrings that described the Terraform landing zone now describe the use-case
  Bicep deployment (ADR-0012). No behaviour change.

## [0.2.0] — 2026-09-28

### Added

- **AI runtime** `app/ai/` (ADR-0009): LangChain + LangGraph on Azure AI Foundry — client
  factory (`get_chat_model` / `get_embeddings`, managed identity when deployed), a compiled
  `retrieve → answer` graph with an optional tool loop (`build_graph`, `ask`), SSE streaming
  (`stream_answer`, `sse_response`), a tool registry with the allow-listed read-only
  `query_external_db` tool, prompt files (`load_prompt`), content-free `gen_ai` telemetry
  (`model_call_span`), Azure AI Search retrieval (`AzureSearchRetriever`) and the ingestion job
  (`python -m app.ai.ingest`). No route or use case is shipped.
- New optional env vars: `AZURE_AI_ENDPOINT`, `AZURE_AI_DEPLOYMENT`,
  `AZURE_AI_EMBEDDING_DEPLOYMENT`, `AZURE_AI_EMBEDDING_DIMENSIONS`, `AZURE_AI_API_VERSION`,
  `AZURE_AI_AUTH_MODE`, `AZURE_AI_API_KEY`, `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_INDEX`,
  `AZURE_SEARCH_API_KEY`, `AI_REQUEST_TIMEOUT_SECONDS`, `AI_MAX_RETRIES`, `AI_ALLOW_TEXT_TO_SQL`.
- Dependencies: `langchain-core`, `langgraph`, `langchain-openai`, `azure-search-documents`
  (OTel pins unchanged). Tests: `tests/ai/` + the `tests/evals/` prompt regression harness.
- `python -m app.openapi_export` writes the API contract to `docs/reference/openapi.json`
  (`make openapi` also regenerates the web's TS types); `tests/test_openapi_export.py` fails
  when the committed contract is stale.

## [0.1.0] — 2026-09-28

### Changed — **BREAKING** (consumer-facing configuration)

- **Database engine is Azure SQL Database**, not Postgres (ADR-0008, supersedes ADR-0004):
  `DATABASE_URL` must now be an `mssql+aioodbc://…?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no`
  URL. `postgresql+asyncpg://…?ssl=require` URLs are no longer accepted.
- Dependencies: `asyncpg` and `opentelemetry-instrumentation-asyncpg` removed; `aioodbc`,
  `pyodbc` and `opentelemetry-instrumentation-sqlalchemy` (0.61b0) added. The runtime image now
  installs Microsoft ODBC Driver 18 for SQL Server.
- DB dependency spans come from the SQLAlchemy instrumentation (registered without an engine, so
  every lazily created engine is covered) instead of the asyncpg driver instrumentation.

### Added

- `EXTERNAL_DATABASE_URL` (optional) + `app/db/external.py`: a second, lazy, **read-only**
  engine for an external Azure SQL database (`get_external_session()` dependency); non-`SELECT`
  statements are refused before they reach the driver.

### Internal

- Engine factories resolve `create_async_engine` at call time (`sa_asyncio.create_async_engine`)
  so the OTel wrapper applies regardless of import order.
- Offline tests now guard on `pyodbc.connect`; Alembic offline mode renders T-SQL.

## [0.0.0] — 2026-09-20

- Template baseline. No features shipped.
