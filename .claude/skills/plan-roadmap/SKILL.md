---
name: plan-roadmap
description: Produce or update roadmaps/<layer>/ROADMAP.md (layer = api | web | infra) from ARCHITECTURE.md Part B and docs/design — phased, dependency-ordered items in the roadmaps/README.md schema, each one PR-sized with acceptance criteria and the human steps called out. Planning only; nothing is implemented. Re-run when the design changes.
---

# Plan a roadmap

> **Scope gate:** Writes exactly one file, `roadmaps/<layer>/ROADMAP.md` (creating or updating it). Say which layer and which inputs you read, then proceed. No code, no infra, no commits.

## Inputs (read all; ask before inventing)

- `docs/architecture/ARCHITECTURE.md` — Part A constraints; Part B (B2 feature map, B3 AI
  components, B4 data stores, B5 integrations, B6 topology, B7 auth) is the source of items.
- `docs/design/db-design.md` (api: models/migrations), `docs/design/external-systems.md`
  (api: read-only tool + allow-listed queries), `docs/design/wireframes/*.md` (web: pages and
  their **API needs** — the cross-layer dependencies).
- The other layers' roadmaps (for `depends_on: <layer>:<id>` and to avoid duplicates).
- `docs/reference/openapi.json` if present (the current API contract).

If a required input is missing or vague, list the questions and stop — do not guess a schema
or a page.

## How to plan

1. **Phases** = deliverable slices a user could try (e.g. _Foundation_, _Threads & messages_,
   _RAG answers_, _Streaming_, _Hardening_). Phase 1 of every layer is the foundation the
   template needs applied: infra → `1.1 first dev deploy (step 1: identities, SQL, Key Vault,
storage, observability)`, `1.2 cloud-team grants (grant-request.md) + contained SQL user`,
   `1.3 container apps deployed (step 2)`; api → first model + migration; web → the API
   contract + mocks wired. Infra items are **use-case-tier only** (ADR-0012): a need on the
   shared platform (model deployment, search capacity) is a `needs_human` line for the cloud
   team, never an item that authors it.
2. **Items** are one PR each (≤ 1 day). Split by layer boundary: a model+migration item, then
   the endpoint item, then the BFF+UI item. Use ids `<phase>.<n>`.
3. **Dependencies:** only what truly blocks. **Authoring never waits for Azure**: models,
   hand-written migrations (offline SQL), endpoints with fake sessions, AI graphs with fakes and
   mocked web pages are all `todo` from day one. Only _applying_ a migration, _running_ ingestion
   or _switching mocks off_ depends on `infra:1.x`. A web item that needs an api item not yet
   `done` gets `depends_on: [api:x.y]` **and** an explicit mock note in `acceptance` ("works
   against `MOCK_UPSTREAM=true` fixtures until api:x.y lands").
4. **Acceptance** = observable behaviour + the contract: endpoint paths under `/v1`, request
   and response shapes, error cases, `x-trace-id` echoed, the AI guardrails (grounded,
   citations, no content in logs) for AI items, the read-only rule for external data.
5. **Needs a human** — anything an agent cannot do: the Bicep deploy (pipeline or `make
infra-deploy ENV=dev`), the cloud team's role grants (`infra/grant-request.md`), the
   contained SQL user, `migrate.yml`, Key Vault secret values, firewall IPs, shared-platform
   changes (model deployments/quota, search capacity), ingestion runs, Okta config. Put it on
   the item that produces the need.
6. **Layers tags** drive the scaffold: `ai` items use `feature-scaffold` target `ai`/`rag`;
   `infra` items use `infra-scaffold`; `migration` items go through `write-migration`.
7. Tests, docs, telemetry, changelog/version are **implied** by the Definition of Done on every
   item — never list them as separate items.

## Updating an existing roadmap

Never renumber or delete. Edit items in place, append a dated `notes` line explaining the
change, add new items at the end of the relevant phase, mark superseded ones `done` with a
"superseded by" note. Items `in-progress`/`awaiting-test` are not touched without saying so.

## Output

The file, in the `roadmaps/README.md` schema, plus a short summary in chat: phases, item
count, the critical path, the human steps by phase, and open questions. Then suggest
`/implement-next <layer>`.
