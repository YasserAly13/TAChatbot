---
name: runbook-writer
description: Convert a postmortem or debugging session into a reusable runbook in docs/operations/runbooks/. Use after an incident is resolved so the response is captured for next time. Pairs with the incident-responder agent.
---

# Runbook writer

> **Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

Every incident produces tribal knowledge; a runbook is the team's memory of how to respond next time.

## Inputs

- The incident (1–3 sentences). The detection signal (alert / customer report / log line). The mitigation steps in order. The root cause if known.

## Workflow

1. Slug, not number: `ls docs/operations/runbooks/` then `docs/operations/runbooks/<kebab-slug>.md` (runbooks are found by name during an incident).
2. Write it from the template below.
3. Add a row to `docs/operations/runbooks/README.md`.
4. If the root cause maps to a recurring failure mode, note it; if it exposes a missing decision, propose an ADR via `/write-adr`.

## Template

````
# Runbook: <slug>

## What it looks like
- Symptom: <user-visible behavior>
- Signal: <which alert / log line surfaces it>
- KQL (Log Analytics): ```<query>```   # pivot on our trace_id field to follow a request web→api

## Triage (5 min)
1. …
2. …

## Mitigate (5–30 min)
1. …  # restore service first (roll back / scale / config), fix after

## Verify recovery
- [ ] …

## Root cause
- <one paragraph>

## References
- Incident: <link/issue>   ·   Related ADR: ADR-NNNN
````

## Hard rules

- No credentials, customer PII, or sensitive screenshots.
- No "ping <person>" steps — a runbook must work without a specific human.
- Distill, don't paste a chat log verbatim.
