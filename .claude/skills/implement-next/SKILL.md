---
name: implement-next
description: Execute one roadmap item end-to-end — pick the next unblocked item (or the given id) in roadmaps/<layer>/ROADMAP.md, implement every layer it touches through the project's skills, run the tests, update docs/env/changelog/version and telemetry, then stop at awaiting-test with exact "How to test" steps and the "Needs a human" list. Marks done only after the developer confirms. One item at a time; hard stops respected.
---

# Implement the next roadmap item

> **Scope gate:** Approval of a roadmap item (the item's existence in a `/plan-roadmap`-produced file that the team accepted, or the developer naming the id) authorises implementing that item end-to-end. Say which item you picked and the files it will touch, then proceed. Hard stops always apply: never `az deployment group create`, never `alembic upgrade`/`migrate.yml`, never push/commit unless asked via `/git-flow`, never touch secrets, never delete without confirmation.

## 1. Pick the item

- With an id: that item. Otherwise the first `todo` item, in phase order, whose `depends_on`
  are all `done` (cross-layer deps checked in the other roadmap). If none is unblocked, say
  which items are waiting on what and stop.
- Read the item, its phase, `ARCHITECTURE.md` Part B and the design file(s) it references.
  If acceptance is unclear, ask **one** batch of questions before touching code.
- Set `status: in-progress`, append a dated note ("started by Claude").

## 2. Implement — through the project's skills, per `layers`

| Layer tag            | Do                                                                                                                                                                                                                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `infra`              | `infra-scaffold` → use-case-tier Bicep only: a vendored block called from `infra/main.bicep`, params in **all three** `.bicepparam`, `make infra-build` clean (+ `what-if` if the developer asks). Deploy, role grants (`grant-request.md`) and anything on the shared platform = `needs_human`. |
| `model`, `migration` | model under `app/models/` + `write-migration` (autogenerate against dev if reachable, else hand-written) → offline SQL in the PR. Apply via `migrate.yml` = `needs_human`.                                                                                                                       |
| `endpoint`           | `feature-scaffold` target `api` → router under `/v1`, repository, `Depends(get_session)`, tests with the dependency override.                                                                                                                                                                    |
| `ai`                 | `feature-scaffold` target `ai`/`rag` → route on `build_graph()`, prompt file + eval case, tool with fake-backed test; telemetry via `model_call_span`.                                                                                                                                           |
| `bff`, `ui`          | `feature-scaffold` target `web` → `/api/v1/...` route with `fetchUpstream` (or `stream.ts`), page/components; if the api item is not `done`, wire `MOCK_UPSTREAM` fixtures typed from `openapi.json` and say so.                                                                                 |
| `docs`               | the docs the item names, in the same PR.                                                                                                                                                                                                                                                         |

Always: `x-trace-id` on every new route/outbound call (`observability-instrumenter` if in
doubt), structured logs, bounded metrics, no content/PII in telemetry.

## 3. Definition of Done — run it, don't recite it

1. Tests written (happy + error paths) and **green**: `make test` (or the per-app command).
   Red tests ⇒ fix or stop and report; never continue to step 4 with red tests.
2. Docs updated in the same change: `README.md` / per-app `CLAUDE.md` / `.env.example`s /
   `docs/reference/*` / `docs/architecture/ARCHITECTURE.md` Part B **proposal** if the item
   changed the architecture (propose, don't rewrite).
3. `make openapi` if the api surface changed (the contract the web layer depends on).
4. Changelog entry + SemVer bump for the touched service(s).
5. `make fmt`; `/code-review`; `/security-review` if the item touched the BFF boundary, env,
   external HTTP, the DB layer or an AI tool. Fix what they flag.

## 4. Hand over — stop here

- Set `status: awaiting-test`. Fill `how_to_test` with **exact commands and expected results**
  (a test command, a `curl`/UI action, what the logs/telemetry should show). Fill `needs_human`.
  Append a dated note listing the files changed and the reviews run.
- Reply with the same two sections plus "Reply **done** to close the item, or tell me what to
  change." **Do not** continue to the next item.

## 5. On feedback

- "done" ⇒ `status: done`, dated note "confirmed by <name>". Suggest `/git-flow` (if not yet
  committed) and the next unblocked item.
- Changes requested ⇒ stay `awaiting-test`, apply, re-run step 3, re-hand over.
- Blocked (a human step must happen first) ⇒ `status: blocked` + reason in `notes`, and say
  exactly what unblocks it.

## Hard rules

- One item per run. Never edit another layer's roadmap.
- Never mark `done` yourself. Never skip tests or docs "for now".
- Everything you could not do goes in `needs_human`, never silently dropped.
