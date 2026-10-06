---
description: Implement the next unblocked roadmap item (or a given id) end-to-end — code, tests, docs, telemetry, changelog — then stop at awaiting-test with "How to test" and "Needs a human". One item per run.
argument-hint: <api|web|infra> [item id]
---

Use the `implement-next` skill for: `$ARGUMENTS` (layer required; item id optional — otherwise the next unblocked `todo`).

Picking the item is the approval to implement it end-to-end. Run the Definition of Done (tests green, docs, openapi, changelog/version, reviews), set the item to `awaiting-test`, write the exact test steps and the human steps into the roadmap, and stop. Hard stops: no apply, no migration run, no push, no secrets, no deletes without confirmation.
