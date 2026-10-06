# infra roadmap — Team Assistant

Infrastructure for this use case. **No Bicep is applied in any environment:** every Azure
resource (Foundry, AI Search, Azure SQL) is pre-provisioned in `dev` and named in
[`ARCHITECTURE.md`](../../docs/architecture/ARCHITECTURE.md) → B1. The template's `infra/` tier
(ADR-0012) is kept but unused. Schema: [`roadmaps/README.md`](../README.md).

## Phase 1 — Foundation

### 1.1 — Pre-provisioned dev resources (no apply)

- **status:** done
- **depends_on:** []
- **layers:** [infra, docs]
- **acceptance:**
  - the dev Foundry endpoint, AI Search service + index `team-assistant-docs` and Azure SQL database exist and are reachable from a developer machine via `apps/api/.env`
  - `ARCHITECTURE.md` → B1 names every resource the app uses
- **how_to_test:**
  - `just dev` (or `make dev`), then `curl localhost:8000/health` → `200`
- **needs_human:** []
- **notes:**
  - 2026-10-06 — replaces the template's "First dev apply": Yasser Aly confirmed at `/init-project` that all resources already exist in dev and no infrastructure is deployed by this project in any environment.
