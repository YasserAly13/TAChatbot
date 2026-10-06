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

- **status:** done
- **depends_on:** [infra:1.1]
- **layers:** [model, migration]
- **acceptance:**
  - SQLAlchemy models `Conversation` and `Message` in `app/models/` match `docs/design/db-design.md`: `uniqueidentifier` PKs, `conversations.title nvarchar(200)` default "New conversation", `messages.role` `CHECK IN ('user','assistant')`, `messages.citations` `CHECK (citations IS NULL OR ISJSON(citations)=1)`, FK `messages.conversation_id → conversations.id` `ON DELETE NO ACTION`, indexes on `conversations.updated_at` and `messages(conversation_id, created_at)`, `datetime2(3)` timestamps with server defaults
  - the first Alembic revision creates both tables with a working `downgrade`; `alembic upgrade head --sql` renders valid T-SQL offline
- **how_to_test:**
  - `just test` → api 217 passed, web 136 passed (`tests/test_models.py`, `tests/test_alembic.py` cover the models, the offline upgrade/downgrade and model-vs-migration drift)
  - `cd apps/api; uv run alembic heads` → `7c1d4e2a9b30 (head)`
  - `cd apps/api; uv run alembic upgrade head --sql` → `CREATE TABLE conversations` and `CREATE TABLE messages` with `NVARCHAR(max)` (never `NTEXT`), `ck_messages_role`, `ck_messages_citations_json`, `fk_messages_conversation_id_conversations` and two `CREATE INDEX` lines; prints SQL only, connects to nothing
  - after you apply it (needs_human): `uv run alembic current` → `7c1d4e2a9b30 (head)`; the dev database has tables `conversations`, `messages` and `alembic_version`
- **needs_human:**
  - review the offline SQL, then run `cd apps/api; uv run alembic upgrade head` against the dev database (ADR-0013) — the first run also creates `alembic_version`
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`
  - 2026-10-06 — started by Claude
  - 2026-10-06 — implemented; awaiting test by Yasser Aly. Files: `app/models/conversation.py` (new), `app/models/__init__.py`, `alembic/versions/20261006_1200-7c1d4e2a9b30_create_conversations_and_messages.py` (new, hand-written — the dev DB was not used), `tests/test_models.py` (new), `tests/conftest.py` (new), `tests/test_alembic.py`; docs: root + api `CLAUDE.md`, api `README.md`, `docs/development/testing.md`, `docs/getting-started.md`; api 0.3.0 → 0.4.0 + `CHANGELOG.md`. `UnicodeText` → `Unicode()` because NTEXT broke `ISJSON`. Reviews: code-reviewer (no blocking; applied ROLES-built check, `lazy="raise"`, shared `_restore_logging`, stronger downgrade test), security-reviewer (no blocking; applied quote-escaped default literal)
  - 2026-10-06 — fix during test: `alembic/env.py` now loads `apps/api/.env` (it used the placeholder URL)
  - 2026-10-06 — confirmed by Yasser Aly: connection test passed, migration `7c1d4e2a9b30` applied to dev

### 1.2 — Threat model: conversation store and ingest endpoint

- **status:** done
- **depends_on:** []
- **layers:** [docs]
- **acceptance:**
  - `docs/security/threat-models/conversations-and-ingest.md` (STRIDE) covers: every user reads every conversation (ADR-0014); unauthenticated `POST /v1/admin/ingest` (cost / denial of service, single-flight); prompt injection through the corpus; the public repository naming the resources while the dev SQL firewall is open to every IP (ADR-0013)
  - each threat has a mitigation already in the design or an explicit accepted risk
- **how_to_test:**
  - open `docs/security/threat-models/conversations-and-ingest.md`: sections 3–4 rate 33 threats (STRIDE + AI) against the current code; section 7 lists 12 accepted risks, section 8 the 12 must-fix items before any shared use, section 9 the 13 controls for 3.2, section 10 where code and docs disagree
  - `docs/security/threat-models/README.md` lists it as "Draft — awaiting acceptance"
- **needs_human:**
  - read and accept the accepted-risk list (section 7), or name the risks to fix instead
  - decide the two 3.2 controls marked "owner decision" in section 9: an off-by-default switch for the ingest route, and a cooldown between runs
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`; required before 3.2 (an unauthenticated trigger)
  - 2026-10-06 — from the 2.1 security review, also cover: unauthenticated `POST /v1/conversations` with no rate limit or row cap, and no request-body size cap (memory/CPU before a 422) — accepted while local-only (ADR-0013), HIGH if ever exposed
  - 2026-10-06 — started by Claude; written by the threat-modeler agent: `docs/security/threat-models/conversations-and-ingest.md` + README row. Verified in code: `just dev` binds the api to `0.0.0.0` (package.json `dev`; also `apps/api/CLAUDE.md`, `README.md`, `main.py` docstring) although ADR-0013 says local-only; `AISettings` repr would print both API keys. Awaiting test by Yasser Aly
  - 2026-10-06 — confirmed by Yasser Aly: all 12 accepted risks (section 7) accepted; quick fixes approved (api bound to 127.0.0.1, API keys hidden from the settings repr)
  - 2026-10-06 — from the 4.1 security review (HIGH, must close before any shared or deployed use): `POST …/ask` is an unauthenticated route that spends model tokens — no output cap (`max_tokens`) — closed in api 0.9.0 by `AI_MAX_OUTPUT_TOKENS` — no rate limit, no concurrency limit; each failed ask still stores the question; the first question becomes a title every user can list; stored answers replay as history (a successful jailbreak persists in a shared conversation)
  - 2026-10-06 — from the 2.2 security review, also cover: `GET /v1/conversations/{id}` returns every message unpaginated (a long thread = a large response; bounded today by the 4,000-character question cap in 4.1 and model-length answers); the conversation id appears in the framework's request span URL and uvicorn's access log (reaches App Insights if the exporter is on) — decide redaction vs accepted risk

## Phase 2 — Conversations (F2)

### 2.1 — Create and list conversations

- **status:** done
- **depends_on:** [1.1]
- **layers:** [endpoint]
- **acceptance:**
  - `POST /v1/conversations` with `{ "title"?: string }` (≤ 200 characters) → `201 { id, title, created_at, updated_at }`; no title → "New conversation"
  - `GET /v1/conversations?limit=50` (1–100) → `200 { items: [{ id, title, updated_at }], count }`, newest `updated_at` first
  - bad input → `422 validation_error`; every response echoes `x-trace-id`; errors use `{ error, trace_id }`
  - a conversation repository (create, list, get, add message, rename, touch `updated_at`) used through `Depends(get_session)`; no titles or ids in logs or metric attributes
- **how_to_test:**
  - `just test` → api 247 passed, web 136 passed (`apps/api/tests/test_conversations.py` — 30 cases)
  - `just dev` (or `cd apps/api; uv run uvicorn app.main:app --port 8000`), then in another terminal:
  - PowerShell: `Invoke-RestMethod -Method Post http://localhost:8000/v1/conversations -ContentType application/json -Body '{"title":"Smoke test"}'` → `id`, `title: Smoke test`, `created_at`/`updated_at` ending in `Z`
  - `Invoke-RestMethod -Method Post http://localhost:8000/v1/conversations` → `title: New conversation`
  - `(Invoke-RestMethod "http://localhost:8000/v1/conversations?limit=5").items` → the two conversations, newest first
  - `Invoke-WebRequest "http://localhost:8000/v1/conversations?limit=0" -SkipHttpErrorCheck` (PowerShell 7) or open the URL in a browser → `422` `{"error":"validation_error","trace_id":"0c70…"}`
  - `http://localhost:8000/docs` shows both operations under **conversations**
- **needs_human:**
  - the smoke test above writes real rows to the dev database (two test conversations stay — there is no delete, B8 #6)
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`; tests use a fake session, so authoring does not wait for the migration to be applied
  - 2026-10-06 — from the 1.1 review: `DATETIME2` values come back naive (they are UTC) — attach UTC so responses serialise with `Z`; nothing bumps `updated_at` automatically — the repository must, with a test; relationships are `lazy="raise"` (use `selectinload`)
  - 2026-10-06 — started by Claude
  - 2026-10-06 — implemented; awaiting test by Yasser Aly. Files: `app/routers/conversations.py`, `app/repositories/{__init__,conversations}.py`, `tests/test_conversations.py` (new); `app/routers/v1.py`; `docs/reference/{openapi.json,http-api.md}`, `apps/web/src/lib/api-types.ts` (generated); root + api `CLAUDE.md`; api 0.4.0 → 0.5.0 + `CHANGELOG.md`. `count` = items in the response, not a total. Reviews: code-reviewer + security-reviewer, nothing blocking; applied: titles measured in UTF-16 units (an emoji counts 2, so 101 emoji no longer overflow `NVARCHAR(200)` as a 500), trimmed before the length check, control characters rejected, `rename` never splits an emoji, `add_message` rejects unknown roles, `Z` assertion tightened. Deferred to 1.2: rate limit / row cap / body-size cap
  - 2026-10-06 — confirmed by Yasser Aly: tests and the dev smoke test passed

### 2.2 — Read one conversation with its messages

- **status:** done
- **depends_on:** [2.1]
- **layers:** [endpoint]
- **acceptance:**
  - `GET /v1/conversations/{id}` → `200` the conversation + `messages: [{ id, role, content, citations, created_at }]` oldest first, `citations` parsed as `[{title, path}]` or `null`
  - unknown id → `404 not_found`; malformed id → `422 validation_error`; `x-trace-id` echoed
- **how_to_test:**
  - `cd apps/api; uv run pytest` → 259 passed (`tests/test_conversations.py` covers the read, 404, malformed ids, empty thread, bad stored citations, message order)
  - `cd apps/web; pnpm test` → 136 passed (run on its own — see the note on the slow `MessageInput` test)
  - start the api (`just dev`), then in PowerShell: `$c = Invoke-RestMethod -Method Post http://localhost:8000/v1/conversations -ContentType application/json -Body '{"title":"Read test"}'` and `Invoke-RestMethod "http://localhost:8000/v1/conversations/$($c.id)"` → `title: Read test`, `messages: {}` (empty — nothing can add messages until 4.1)
  - browser: `http://localhost:8000/v1/conversations/00000000-0000-0000-0000-000000000000` → `{"error":"not_found","trace_id":"0c70…"}`; `…/v1/conversations/abc` → `{"error":"validation_error",…}`
- **needs_human:**
  - the smoke test writes one more test conversation to dev (no delete exists)
- **notes:**
  - 2026-10-06 — from the 2.1 reviews: check that the request metric still uses the route template (`/v1/conversations/{conversation_id}`) and that no conversation id lands in log fields or span attributes beyond the framework's URL
  - 2026-10-06 — planned by `/plan-roadmap api`
  - 2026-10-06 — started by Claude
  - 2026-10-06 — implemented; awaiting test by Yasser Aly. Files: `app/routers/conversations.py` (route + `Citation`/`MessageOut`/`ConversationDetail`, module-level `MessageRole` alias — ruff stripped the quotes from an inline `Literal`), `app/repositories/conversations.py` (`get_conversation_with_messages`, strictly increasing `created_at` in `add_message`), `app/models/conversation.py` (order by `created_at, id`), `tests/test_conversations.py`, `tests/test_models.py`; `openapi.json` + web `api-types.ts` regenerated; `http-api.md`, root + api `CLAUDE.md`; api 0.5.0 → 0.6.0 + changelog. Metric uses the template (verified in `tracing.py`); this code logs no ids or content. Reviews: code-reviewer + security-reviewer, nothing blocking; applied: same-millisecond message order, role type pinned to `ROLES` by a test, content-free warning with a fixed reason. Deferred to 1.2: unpaginated thread size, id in framework URL logs. For the web layer: render citation `title`/`path` as text, never as HTML or an unchecked link
  - 2026-10-06 — observed: the template web test `MessageInput.test.tsx` times out at Vitest's 5 s default when the machine is busy (e.g. right after `just fmt` + the api suite); 136/136 in isolation (4 runs). Not caused by this item; fixed separately by raising the web `testTimeout` to 15 s (`apps/web/vitest.config.ts`)
  - 2026-10-06 — confirmed by Yasser Aly: tests and the dev smoke test passed

## Phase 3 — Knowledge base (F3)

### 3.1 — Document titles in the index and `[{title, path}]` sources

- **status:** done
- **depends_on:** []
- **layers:** [ai]
- **acceptance:**
  - the index definition (`app/ai/ingest.py`) gains a retrievable `title` field; ingestion sets it to the document's first `# ` heading, else the file name; `ensure_index` adds the field to the existing `team-assistant-docs` index without dropping it
  - retrieval returns `title` with each chunk; `unique_sources` and the streaming `sources` / `done` frames carry `[{ "title", "path" }]` instead of a list of paths (B8 #7)
  - no retrieved text or titles in logs, spans or metrics
- **how_to_test:**
  - `cd apps/api; uv run pytest` → 283 passed (`tests/ai/` covers titles, code-block/front-matter skipping, folder-relative paths, the symlink skip, `[{title, path}]` frames, machine-path redaction and the old-index fallback; `tests/evals/` passes with the new shape)
  - count what the index holds now (see needs_human) — `0` or a number
  - after the re-index: the ingest prints `documents=N chunks=M uploaded=M failed=0`; in the Azure portal → Search service → Indexes → `team-assistant-docs` → Fields, `title` is listed; Search explorer with `search=*&$select=title,source&$top=3` shows titles like `Architecture — living document` and sources like `docs/architecture/ARCHITECTURE.md`
- **needs_human:**
  - **check whether the index already holds documents** from an earlier ingest (count command in the hand-over). If it does, **delete the `team-assistant-docs` index in the Azure portal first** (a delete — yours, not an agent's): the old chunks keep their old ids and `../../docs/…` paths and would show as duplicate citations. The ingest recreates the index.
  - re-index the corpus against dev: `cd apps/api; uv run python -m app.ai.ingest ../../docs` (ensure_index adds `title`, then uploads)
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`; changes the template's stream frame shape — the web `/chat` items consume the new shape
  - 2026-10-06 — started by Claude
  - 2026-10-06 — implemented; awaiting test by Yasser Aly. Files: `app/ai/tools/retrieve.py` (`title` selected, `chunk_title` fallback, one-time fallback when the index has no `title`), `app/ai/ingest.py` (`extract_title`, folder-relative `display_path`, outside-folder files skipped, searchable `title` field), `app/ai/graph.py` (`Source`, `unique_sources` → `[{title, path}]`, `client_path` redaction), `app/ai/streaming.py`; tests in `tests/ai/`, `tests/evals/cases.json`; `docs/architecture/ai.md`; api 0.6.0 → 0.7.0 + changelog. The model's context block (`format_context`) is unchanged — not a prompt change. Reviews: code-reviewer + security-reviewer, nothing blocking; applied: old-index fallback (else every question 400s until the re-index), code-block/front-matter titles, symlink skip, machine-path redaction, `Source` declared before `Answer`. Web chat components render sources as text (no raw HTML, no links) — checked
  - 2026-10-06 — fix during test: the ingest CLI did not load `apps/api/.env` (`AINotConfigured` although `.env` was set) — `main()` now calls `load_local_env()`, with a test. The index did not exist yet, so no delete was needed
  - 2026-10-06 — confirmed by Yasser Aly: ingest ran against dev, the index count matches the upload
  - 2026-10-06 — for the web roadmap: `apps/web/src/lib/chat-client.ts`, `components/chat/types.ts` and `ChatThread.tsx` still type sources as `string[]`; they move to `{title, path}` with the `/chat` items (render as text; key by `path`)

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

- **status:** done
- **depends_on:** [2.2, 3.1]
- **layers:** [endpoint, ai]
- **acceptance:**
  - `POST /v1/conversations/{id}/ask` with `{ "question": string }` → stores the user message, sends the last 10 messages as history to the `retrieve → answer` graph (`top_k = 5`), stores the assistant message with `citations` and `token_count`, and returns `200 { message_id, answer, citations }`
  - the first ask on a conversation still titled "New conversation" renames it to the question cut to 200 characters; every ask bumps `updated_at`
  - unknown id → `404 not_found`; empty or > 4,000 characters → `422 validation_error`; model/search failure → `503 ai_unavailable` with the user message kept
  - answers are grounded in retrieved context with citations; no question, answer or context in logs, spans, metrics or events; every model call inside `model_call_span()`
- **how_to_test:**
  - `cd apps/api; uv run pytest` → all green (`tests/test_ask.py`: answer + citations, both messages stored, title from the first question, last 10 answered turns as history, unanswered questions dropped, 404, 422 boundaries, 503 on model failure / timeout / empty answer with the question kept and no content logged, 500 on a bug, missing-config 503)
  - live, with `just dev` running, in PowerShell: `$c = Invoke-RestMethod -Method Post http://localhost:8000/v1/conversations` then `Invoke-RestMethod -Method Post "http://localhost:8000/v1/conversations/$($c.id)/ask" -ContentType application/json -Body '{"question":"How does trace_id propagation work?"}'` → an `answer` that cites `[1]`… and `citations` with titles and `docs/…` paths (allow up to a minute)
  - `Invoke-RestMethod "http://localhost:8000/v1/conversations/$($c.id)"` → the title is now the question; `messages` holds the question and the answer with its citations
  - ask a follow-up (`"And on the api side?"`) → the answer uses the first turn as context
- **needs_human:**
  - the live test calls `gpt-4.1` and the embedding deployment on dev (costs tokens) and writes rows to the dev database; it needs the 3.1 re-index done (it is)
- **notes:**
  - 2026-10-06 — planned by `/plan-roadmap api`; tests use the fake model + retriever seams (rule 70)
  - 2026-10-06 — started by Claude
  - 2026-10-06 — implemented; awaiting test by Yasser Aly. Files: `app/routers/conversations.py` (route, `AskIn`/`AskOut`, `get_answer_graph` async dependency, `_answered_turns`/`_as_history`, `_UPSTREAM_ERRORS`, `_ask_deadline_seconds`), `app/repositories/conversations.py` (`touch` never backwards, `title_from_question`), `tests/test_ask.py` (new), `tests/fakes.py` (shared fakes, moved out of `test_conversations.py`); `openapi.json` + web `api-types.ts`; `http-api.md`, root + api `CLAUDE.md`; api 0.7.0 → 0.8.0 + changelog. No prompt change. Reviews: code-reviewer + security-reviewer, nothing blocking; applied: one deadline for the whole ask (the search SDK has no timeout), only upstream failures → 503 (bugs → 500, missing config keeps its handler), answered turns only in history, empty answer → 503, async graph dependency, shared test fakes, two-turn / deadline / second-commit tests. Output-token cap decided afterwards (see the next note). Deferred to 1.2: rate/concurrency limits and the cost findings
  - 2026-10-06 — confirmed by Yasser Aly: tests and the live ask against dev passed
  - 2026-10-06 — follow-up approved by Yasser Aly: `AI_MAX_OUTPUT_TOKENS` (default 1024, `0` = no cap) caps every answer, sent as `max_completion_tokens` — api 0.9.0
  - 2026-10-06 — for the web roadmap: the BFF ask route needs a hop timeout above 120 s (2 × `AI_REQUEST_TIMEOUT_SECONDS`), and the UI must disable input while an ask is pending (two concurrent asks on one conversation are not serialised)

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
