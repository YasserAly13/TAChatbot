---
description: Create or update roadmaps/<layer>/ROADMAP.md (api | web | infra) from ARCHITECTURE.md Part B and docs/design — phased, dependency-ordered, one-PR-sized items with acceptance and human steps. Planning only.
argument-hint: <api|web|infra> [phase or feature to (re)plan]
---

Use the `plan-roadmap` skill for layer: `$ARGUMENTS` (ask if the layer is missing).

Read the architecture and design inputs first; stop with questions if they are missing. Write only `roadmaps/<layer>/ROADMAP.md`, then summarise phases, critical path, human steps and open questions, and suggest `/implement-next <layer>`.
