# Threat models

Design-time **STRIDE** threat models, one per non-trivial feature, written **before**
implementation. Produced by the `threat-modeler` agent; consulted by the
`security-reviewer` at diff time.

- One file per feature: `<feature>.md`.
- Re-run the agent against the real code after implementation and update the file —
  threat models are living documents.

| Feature                                                 | Status                                       | Date       |
| ------------------------------------------------------- | -------------------------------------------- | ---------- |
| [Conversations and ingest](conversations-and-ingest.md) | Accepted by Yasser Aly (all section 7 risks) | 2026-10-06 |
