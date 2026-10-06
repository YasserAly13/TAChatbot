---
name: architecture-review
description: Review the team's project architecture (docs/architecture/ARCHITECTURE.md Part B) and design inputs (docs/design/*) against the template baseline (Part A), the rules and the ADRs — before planning. Reports gaps, conflicts and missing decisions, proposes edits as a diff the team applies, and drafts Proposed ADRs. Never rewrites Part B itself, never touches Part A.
---

# Architecture review

> **Scope gate:** Read-only on the architecture files: this produces a report + proposed diffs + `Proposed` ADR drafts. Say what you'll read and proceed. Applying the proposed edits to `ARCHITECTURE.md` Part B is the team's action (ADR-0006).

## Inputs

1. `docs/architecture/ARCHITECTURE.md` — Part A (the constraints) and Part B (what to review).
2. `docs/design/db-design.md`, `docs/design/external-systems.md`, `docs/design/wireframes/*.md`.
3. `docs/adr/*.md` (decisions already made), `.claude/rules/*.md` (what code must obey).
4. Existing `roadmaps/*/ROADMAP.md` if any (a change here may invalidate items).

If Part B is still the guidance text, stop and say which sections must be written first
(B2 feature map and B4 data stores are the minimum for planning).

## What to check

1. **Baseline conflicts** — anything in Part B that contradicts Part A: a second backend,
   browser → api calls, a local database, a non-Azure-SQL engine without an ADR, writes to an
   external database, secrets outside Key Vault, unversioned business endpoints, model calls
   outside `app/ai/client.py`, prompt content in logs, a vector store other than AI Search.
2. **Completeness** — every feature in B2 names its services; every store in B4 has an access
   mode, owner, environment and PII class; every external system in `external-systems.md`
   has a read-only login and a schema pointer; every page in `wireframes/` lists its API needs;
   AI components (B3) name deployment, tools and guardrails; B6 names the three RGs and state
   accounts; B7 states the auth posture.
3. **Decisions without an ADR** — a new tool/service/pattern, a trade-off accepted, an
   exception to a rule. Draft each as a `Proposed` ADR (via `write-adr`) and reference it.
4. **Risks that need a threat model** — new data flows, tools reaching new data, any auth.
   Name the `threat-modeler` inputs.
5. **Planning readiness** — can `/plan-roadmap` produce items with clear acceptance for each
   feature? If not, list the questions to answer.

## Output

```
## Architecture review — <date>
### Blocking (conflicts with the baseline / rules)   — file:section → what → the rule/ADR
### Gaps (planning cannot proceed without)           — file:section → what is missing
### Proposed edits to Part B                         — one fenced diff block per section
### ADRs to record                                   — title → drafted at docs/adr/NNNN-… (Proposed)
### Threat models to write                           — feature → why
### Questions for the team                           — numbered, answerable in one line
### Ready to plan?                                   — yes / no (what first)
```

## Hard rules

- Never edit `ARCHITECTURE.md` Part A. Never apply Part B edits — propose them.
- Never invent a decision the team has not made; mark it as a question or a `Proposed` ADR.
- Cite the rule/ADR for every blocking finding.
