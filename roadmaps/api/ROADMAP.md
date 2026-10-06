# api roadmap — Team Assistant

Backend: models, migrations, `/v1` endpoints, AI graphs/tools, ingestion (`apps/api`).
Schema: [`roadmaps/README.md`](../README.md). Planned from
[`ARCHITECTURE.md`](../../docs/architecture/ARCHITECTURE.md) Part B, its complementary
[`TAChatbot/architecture.md`](../../docs/architecture/TAChatbot/architecture.md) (B3, B4, B4a, B8)
and [`docs/design/`](../../docs/design/) by `/plan-roadmap api`.

Runs locally against pre-provisioned dev resources (ADR-0013): there is no deploy step, and
migrations are applied by Yasser Aly from a developer machine.

## Phase 1 — Foundation

### 1.1 — Conversation and message models + first migration

- **status:** todo
- **depends_on:** [infra:1.1]
- **layers:** [model, migration]
- **acceptance:**
  - SQLAlchemy models `Conversation` and `Message` in `app/models/` match `docs/design/db-design.md`: `uniqueidentifier` PKs, `conversations.title nvarchar(200)` default "New conversation", `messages.role` `CHECK IN ('user','assistant')`, `messages.citations` `CHECK (citations IS NULL OR ISJSON(citations)=1)`, FK `messages.conversation_id → conversations.id` `ON DELETE NO ACTION`, indexes on `conversations.updated_at` and `messages(conversation_id, created_at)`, `datetime2(3)` timestamps with server defaults
  - the first Alembic revision creates both tables with a working `downgrade`; `alembic upgrade head --sql` renders valid T-SQL offline
- **how_to_test:**
- **needs_human:**
  - review the offline SQL, then run `uv run --directory apps/api alembic upgrade head` against the dev database (ADR-0013)
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`

### 1.2 — Threat model: conversation store and ingest endpoint

- **status:** todo
- **depends_on:** []
- **layers:** [docs]
- **acceptance:**
  - `docs/security/threat-models/conversations-and-ingest.md` (STRIDE) covers: every user reads every conversation (ADR-0014); unauthenticated `POST /v1/admin/ingest` (cost / denial of service, single-flight); prompt injection through the corpus; the public repository naming the resources while the dev SQL firewall is open to every IP (ADR-0013)
  - each threat has a mitigation already in the design or an explicit accepted risk
- **how_to_test:**
- **needs_human:**
  - read and accept the accepted-risk list
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`; required before 3.2 (an unauthenticated trigger)

## Phase 2 — Conversations (F2)

### 2.1 — Create and list conversations

- **status:** todo
- **depends_on:** [1.1]
- **layers:** [endpoint]
- **acceptance:**
  - `POST /v1/conversations` with `{ "title"?: string }` (≤ 200 characters) → `201 { id, title, created_at, updated_at }`; no title → "New conversation"
  - `GET /v1/conversations?limit=50` (1–100) → `200 { items: [{ id, title, updated_at }], count }`, newest `updated_at` first
  - bad input → `422 validation_error`; every response echoes `x-trace-id`; errors use `{ error, trace_id }`
  - a conversation repository (create, list, get, add message, rename, touch `updated_at`) used through `Depends(get_session)`; no titles or ids in logs or metric attributes
- **how_to_test:**
- **needs_human:** []
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`; tests use a fake session, so authoring does not wait for the migration to be applied

### 2.2 — Read one conversation with its messages

- **status:** todo
- **depends_on:** [2.1]
- **layers:** [endpoint]
- **acceptance:**
  - `GET /v1/conversations/{id}` → `200` the conversation + `messages: [{ id, role, content, citations, created_at }]` oldest first, `citations` parsed as `[{title, path}]` or `null`
  - unknown id → `404 not_found`; malformed id → `422 validation_error`; `x-trace-id` echoed
- **how_to_test:**
- **needs_human:** []
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`

## Phase 3 — Knowledge base (F3)

### 3.1 — Document titles in the index and `[{title, path}]` sources

- **status:** todo
- **depends_on:** []
- **layers:** [ai]
- **acceptance:**
  - the index definition (`app/ai/ingest.py`) gains a retrievable `title` field; ingestion sets it to the document's first `# ` heading, else the file name; `ensure_index` adds the field to the existing `team-assistant-docs` index without dropping it
  - retrieval returns `title` with each chunk; `unique_sources` and the streaming `sources` / `done` frames carry `[{ "title", "path" }]` instead of a list of paths (B8 #7)
  - no retrieved text or titles in logs, spans or metrics
- **how_to_test:**
- **needs_human:**
  - re-index the corpus against dev: `uv run --directory apps/api python -m app.ai.ingest ../../docs`
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`; changes the template's stream frame shape — the web `/chat` items consume the new shape

### 3.2 — Ingest endpoint (api only)

- **status:** todo
- **depends_on:** [1.2, 3.1]
- **layers:** [endpoint, ai]
- **acceptance:**
  - `POST /v1/admin/ingest` (no body) → `202 { "status": "started" }` and ingestion of `INGEST_CORPUS_PATH` runs in the background; a second call while one runs → `409 ingest_running`
  - new setting `INGEST_CORPUS_PATH` (default: the repo's `docs/`) documented in `apps/api/.env.example` and `docs/reference/environment-variables.md`
  - **not** mirrored in the BFF (B8 #2); the CLI `python -m app.ai.ingest <path>` still works
  - outcome logged as counts, duration and status only; `x-trace-id` echoed
- **how_to_test:**
- **needs_human:**
  - trigger it once against dev (`curl -X POST localhost:8000/v1/admin/ingest`) and confirm the index is populated
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`

## Phase 4 — Chat answers (F1)

### 4.1 — Ask a question (JSON)

- **status:** todo
- **depends_on:** [2.2, 3.1]
- **layers:** [endpoint, ai]
- **acceptance:**
  - `POST /v1/conversations/{id}/ask` with `{ "question": string }` → stores the user message, sends the last 10 messages as history to the `retrieve → answer` graph (`top_k = 5`), stores the assistant message with `citations` and `token_count`, and returns `200 { message_id, answer, citations }`
  - the first ask on a conversation still titled "New conversation" renames it to the question cut to 200 characters; every ask bumps `updated_at`
  - unknown id → `404 not_found`; empty or > 4,000 characters → `422 validation_error`; model/search failure → `503 ai_unavailable` with the user message kept
  - answers are grounded in retrieved context with citations; no question, answer or context in logs, spans, metrics or events; every model call inside `model_call_span()`
- **how_to_test:**
- **needs_human:** []
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`; tests use the fake model + retriever seams (rule 70)

### 4.2 — Ask with streaming (SSE)

- **status:** todo
- **depends_on:** [4.1]
- **layers:** [endpoint, ai]
- **acceptance:**
  - `POST /v1/conversations/{id}/ask/stream` → SSE `sources` (`[{title, path}]`) → `token`\* → `done`; same storage, history and title rules as 4.1; the assistant message is stored on `done`
  - failure before the stream starts → `503 ai_unavailable` JSON; failure after → an `event: error` frame `{ error_kind }` ends the stream; a client disconnect before `done` stores no assistant message
  - `x-trace-id` on the response; no content in telemetry
- **how_to_test:**
- **needs_human:**
  - ask one real question against dev with `just dev` and confirm a cited, streamed answer
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`

## Phase 5 — Hardening

### 5.1 — Evaluation cases for Team Assistant answers

- **status:** todo
- **depends_on:** [4.1]
- **layers:** [ai]
- **acceptance:**
  - `tests/evals/cases.json` gains Team Assistant cases: answers from context with citations, says it does not know when context is empty, ignores instructions inside retrieved text
  - any system-prompt change for citation wording is a prompt file with a matching eval case
- **how_to_test:**
- **needs_human:** []
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`
