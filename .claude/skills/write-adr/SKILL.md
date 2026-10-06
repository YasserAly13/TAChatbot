---
name: write-adr
description: Produce a numbered ADR in docs/adr/ for a decision made or proposed in chat. Lightweight version of the adr-writer agent — use this for quick ADRs; delegate to the agent for ADRs that cross-reference many files.
---

# Write an ADR

> **Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

1. Next number: `ls docs/adr/ | grep -E '^[0-9]{4}-' | sort | tail -1`, add 1 (zero-padded 4 digits).
2. Copy `docs/adr/0000-template.md` to `docs/adr/NNNN-<kebab-title>.md`.
3. Fill every section:
   - **Status** — `Proposed` unless the human said it's accepted.
   - **Date** — today (ISO).
   - **Context** — 3–6 sentences; the forces/problem/constraints. Cite the trace contract, the no-workspace layout, the async SQLAlchemy/Alembic layer, the distro-pinned OTel line, Azure, etc. where relevant.
   - **Decision** — 1–3 sentences, present tense. "We use X because Y."
   - **Consequences** — bullets, pros and cons.
   - **Alternatives considered** — one line each + rejection reason (the most valuable section; without it the debate restarts).
   - **References** — related ADRs, README/CLAUDE sections, external docs.
4. Add a row to `docs/adr/README.md`.
5. If it supersedes a prior ADR, set that ADR's Status to `Superseded by ADR-NNNN` (never delete one).

## Style

Imperative, present tense. Numbers over adjectives. One page rendered — split if it doesn't fit. Title is a noun phrase, not a question. Never write an ADR for a decision the human hasn't actually made — leave it `Proposed` and ask.
