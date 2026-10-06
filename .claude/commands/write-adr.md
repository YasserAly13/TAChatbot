---
description: Write a numbered ADR in docs/adr/ from a decision summary.
argument-hint: <decision summary>
---

**Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

Use the `write-adr` skill (or delegate to the `adr-writer` agent for a heavier, cross-referenced ADR) for: `$ARGUMENTS`.

1. Find the next number from `docs/adr/`.
2. Copy `docs/adr/0000-template.md` to `docs/adr/NNNN-<kebab-title>.md`.
3. Fill in Status (default `Proposed`), Date (today), Context, Decision, Consequences, Alternatives considered, References.
4. Append a row to `docs/adr/README.md`.

Ask one clarifying question first if the topic is ambiguous (e.g. "Is this superseding ADR-NNNN, or new?"). Never record a decision the human hasn't actually made — leave it `Proposed` and ask.
