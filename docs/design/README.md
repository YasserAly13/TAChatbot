# `docs/design/` — the team's design inputs

The **human-authored inputs** that planning starts from. The project admin fills these in
(with the developers) _before_ asking Claude to plan a roadmap; the planning and scaffolding
skills read them and the living [`ARCHITECTURE.md`](../architecture/ARCHITECTURE.md) Part B,
and never invent what is missing here — they ask.

| File                                         | What goes in it                                                                                         | Read by                                                     |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| [`db-design.md`](db-design.md)               | The project's **own** database: tables, columns, relations, indexes, retention, PII class               | `plan-roadmap` (api), `feature-scaffold`, `write-migration` |
| [`external-systems.md`](external-systems.md) | Every **external** database/API the app reads: owner, access mode, credentials location, schema pointer | `plan-roadmap` (api), `db-introspector`, AI tool design     |
| [`wireframes/`](wireframes/README.md)        | One file per page/screen: purpose, elements, states, the API calls it needs                             | `plan-roadmap` (web), `feature-scaffold` (web)              |

Conventions:

- Keep these **use-case specific and concrete** — real table names, real page names. The
  template's baseline (Part A of `ARCHITECTURE.md`) is the only generic part.
- No secrets, no connection strings, no production data samples. Point to the Key Vault secret
  name instead.
- When a design changes after a roadmap exists, update the file **and** the affected roadmap
  items (or ask Claude to re-plan those items) in the same change.
