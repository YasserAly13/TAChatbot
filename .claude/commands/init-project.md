---
description: Initialise a fresh clone as a named project — rename, record identity + Azure landing zone, seed ARCHITECTURE.md Part B / docs/design / roadmaps, write the platform manifests + the three Bicep param files, remove the template apparatus.
argument-hint: <display name>
---

**Scope gate:** Invoking this command is the approval for the whole initialisation; collect the answers, show the file list, then proceed. Nothing is committed, pushed, applied or created in Azure/GitHub — those go into the final "Needs a human" list.

Use the `init-project` skill for: `$ARGUMENTS` (the display name; ask for it if missing).

Follow the skill's six steps in order: collect answers → rename (via `rename-project`) → record identity (ARCHITECTURE.md Part B, docs/design, roadmaps) → landing-zone files → remove the template apparatus (ask first) → verify + hand over (How to test / Needs a human / next command).
