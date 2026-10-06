# `roadmaps/` — the plan of record

**State lives here, not in chat.** A conversation resets; these files don't. Every workflow
skill reads and writes them:

| Skill             | Reads                                                        | Writes                                           |
| ----------------- | ------------------------------------------------------------ | ------------------------------------------------ |
| `/plan-roadmap`   | `ARCHITECTURE.md` Part B, `docs/design/*`, existing roadmaps | `roadmaps/<layer>/ROADMAP.md`                    |
| `/implement-next` | the roadmap of the chosen layer                              | item status, `how_to_test`, `needs_human`, notes |
| `/start`          | all roadmaps                                                 | nothing                                          |
| `/git-flow`       | the item being worked on (branch/commit naming)              | nothing                                          |

## Layout

```
roadmaps/
├── README.md          this file — the schema
├── api/ROADMAP.md     backend: models, migrations, /v1 endpoints, AI graphs/tools, ingestion
├── web/ROADMAP.md     frontend: pages, BFF routes, components, mocks
└── infra/ROADMAP.md   Bicep (use-case tier): blocks called, param files, grants requested, deploy steps
```

One roadmap per layer so two developers can work in parallel without editing the same file.
Cross-layer dependencies point at the other file's item id (`web: depends_on: [api:2.3]`).

## Item schema

A roadmap is Markdown with **phases** (`## Phase N — <name>`) and **items** (`### <id> — <title>`).
Every item has exactly these fields, in this order, as a bullet list; the skills parse them by
name, so keep the spelling:

```markdown
### 2.3 — Conversation threads (create/list)

- **status:** todo
- **depends_on:** [2.1, infra:1.4]
- **layers:** [model, migration, endpoint]
- **acceptance:**
  - `POST /v1/threads` creates a thread and returns its id; `GET /v1/threads` lists the caller's threads
  - both endpoints echo `x-trace-id`; failures return the standard error shape
- **how_to_test:**
  - `make test` — `tests/test_threads.py` green
  - `curl -X POST localhost:8000/v1/threads -d '{"title":"t"}'` → `201` with `{"id": "<uuid>"}`
- **needs_human:**
  - run `migrate.yml` on `dev` after the revision is reviewed
- **notes:**
  - 2026-10-02 — implemented; awaiting test by <name>
```

| Field         | Values / rules                                                                                                                                                                                                                        |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `status`      | `todo` → `in-progress` → `awaiting-test` → `done`; or `blocked` (with the reason in `notes`). Only a human's confirmation moves `awaiting-test` → `done`.                                                                             |
| `depends_on`  | Item ids in this file, or `<layer>:<id>` for another layer. An item is **unblocked** when every dependency is `done`.                                                                                                                 |
| `layers`      | Any of `model`, `migration`, `endpoint`, `bff`, `ui`, `ai`, `infra`, `docs`. Drives which scaffold target and which reviewers run.                                                                                                    |
| `acceptance`  | Observable behaviour — what a reviewer checks, not how it is built. Tests, docs, telemetry and the changelog are implied by the Definition of Done and are **not** listed here.                                                       |
| `how_to_test` | Exact commands and expected results a low-context developer can run. Filled in by `implement-next` when the item reaches `awaiting-test`.                                                                                             |
| `needs_human` | Everything an agent cannot do: the Bicep deploy, the cloud team's role grants, the contained SQL user, `migrate.yml`, Key Vault secrets, firewall IPs, model deployments, ingestion runs, a merge. Empty list when nothing is needed. |
| `notes`       | Dated, append-only log: decisions, test feedback, why something was blocked.                                                                                                                                                          |

Sizing: an item is **one PR** — roughly half a day to a day of work. Split anything larger.
Ordering inside a phase follows dependencies: infra → database → api → web.

## Rules

- **Never edit another layer's roadmap** from an item; propose the change in `notes` and let
  that layer's owner (or `/plan-roadmap`) apply it.
- **Never mark `done` without a human's confirmation** and green tests. `implement-next`
  stops at `awaiting-test`.
- **Never delete an item.** Superseded → `status: done` with a note "superseded by X", or
  `blocked` with the reason.
- A design change (`docs/design/*`, `ARCHITECTURE.md` Part B) that invalidates items is
  handled by re-running `/plan-roadmap` for that layer; it edits the affected items in place
  and appends a note.
