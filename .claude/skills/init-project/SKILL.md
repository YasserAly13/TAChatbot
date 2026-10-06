---
name: init-project
description: Turn a fresh clone of the AI Accelerator into a named project in one pass — rename the placeholders (via rename-project), record the project's identity and Azure landing zone (the cloud team's platform manifests per environment, the use case's resource names, auth mode), seed ARCHITECTURE.md Part B, docs/design/ and the roadmaps/ folders, write the three Bicep param files, and remove the template apparatus. Run once, right after cloning, by the project admin. Supersedes running rename-project alone.
---

# Initialise a project

> **Scope gate:** Running this is the approval for every step below; it touches many files. State the answers you collected and the file list before writing, then proceed. Hard stops still apply: nothing is committed, pushed, applied or created in Azure/GitHub — those are listed in the final "Needs a human" section.

## 1. Collect the answers (ask, one block, then confirm)

| Answer                                                                                                                                                                                                                          | Used for                                                                                         |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Display name (e.g. `Acme Assistant`)                                                                                                                                                                                            | `rename-project` display token                                                                   |
| Slug (derived, ≤ 15 chars, kebab)                                                                                                                                                                                               | npm scope, OTEL names, images, **Azure names** (`kv-<slug≤13>-<env>` ≤ 24, `st<slug><env>` ≤ 24) |
| One-paragraph description + domain                                                                                                                                                                                              | `ARCHITECTURE.md` → B1, root `README.md` intro, `CLAUDE.md` "What it is"                         |
| Team: admin, backend dev, frontend dev                                                                                                                                                                                          | `ARCHITECTURE.md` → B1, `CODEOWNERS` suggestion                                                  |
| **Platform manifests** dev / staging / prod — paste the cloud team's JSON, or the values (resource group, Container Apps Environment, registry, Foundry endpoint + deployment names + embedding dimensions, AI Search endpoint) | `infra/platform/<env>.json` (schema `platform.schema.json`)                                      |
| SQL Entra admin per environment (a group: login + object id) · alert e-mail(s) · developer IPs for dev                                                                                                                          | `main.<env>.bicepparam` → `sqlEntraAdmin`, `alertEmails`, `developerIpAllowlist`                 |
| AI: which of the shared Foundry deployments to use (chat, embedding + dimensions)                                                                                                                                               | the manifest's `aiFoundry.deployments` → `AZURE_AI_*`; `.env` hints                              |
| Search index name (default `<slug>-docs`, unique on the shared service)                                                                                                                                                         | `main.<env>.bicepparam` → `searchIndexName`, `AZURE_SEARCH_INDEX`                                |
| External database(s)? (name + owner)                                                                                                                                                                                            | `docs/design/external-systems.md` stub rows                                                      |
| Auth: `none` (default now) or `okta` (later)                                                                                                                                                                                    | `ARCHITECTURE.md` → B7; `.env` hints                                                             |

Validate the slug exactly as `rename-project` does. Refuse to continue on an invalid one.

## 2. Rename

Run the `rename-project` skill with the display name + slug (it runs `rename.mjs`, `uv lock`,
clears `apps/web/.next`, verifies zero leftovers).

## 3. Record the identity

- `docs/architecture/ARCHITECTURE.md` **Part B only**: fill B1 (summary, environments, RG
  naming), the team in B1, B7 (auth posture: "internal-only, no user auth" or "Okta — see
  roadmap Phase 8"), and a first B9 change-log row. Leave every other B section as the guidance
  text — planning fills them.
- `docs/design/db-design.md`, `external-systems.md`, `wireframes/README.md`: replace
  `<slug>`/`<org>` placeholders; add one stub row per external system named.
- `roadmaps/api/ROADMAP.md`, `roadmaps/web/ROADMAP.md`, `roadmaps/infra/ROADMAP.md`: create
  from the schema in `roadmaps/README.md` with a header, an empty `## Phase 1 — Foundation`
  and a first infra item `1.1 — First dev apply` (`needs_human`: the apply itself).
- Root `README.md` first paragraph and `CLAUDE.md` "What it is": the project's name and
  description in place of the template blurb (keep the "built on the AI Accelerator" line).

## 4. Landing-zone files (committed — names only, no secrets)

- `infra/platform/<env>.json` ×3 from the answers (or the pasted manifests); validate against
  `infra/platform/platform.schema.json` (`node -e` with a JSON parse is enough — every required
  key present, `loginServer` ends in `.azurecr.io`, `embeddingDimensions` an integer).
- `infra/main.<env>.bicepparam` ×3: `projectSlug`, `environment`, `sqlEntraAdmin`, `alertEmails`,
  `developerIpAllowlist` (dev only), `searchIndexName`; keep `deployContainerApps = false` (the
  two-step first deployment, `infra/README.md`). Run `make infra-build` — must be clean.
- Rewrite `.github/CODEOWNERS` with the team from step 1 (the template's owners are placeholders).
- Print the **GitHub configuration** the pipeline needs — as a checklist, not values: Environments
  `dev`/`staging`/`prod` with reviewers; repository secrets `<ENV>_AZURE_CLIENT_ID`,
  `<ENV>_AZURE_TENANT_ID`, `<ENV>_AZURE_SUBSCRIPTION_ID` + `<ENV>_AZURE_CREDENTIALS` (or OIDC);
  the SP per environment needs **Contributor on the environment's resource group + AcrPush on the
  shared registry**; `<ENV>_SQL_SERVER_FQDN`, `<ENV>_SQL_DATABASE` for `migrate.yml` after the first
  deploy.

## 5. Remove the template apparatus (ask first, list the deletions)

- `README.md` → _Using this template_ section; `.claude/commands/rename-project.md`,
  `.claude/skills/rename-project/`; this skill and `.claude/commands/init-project.md`.
- `docs/template-roadmap.md` stays only if the team maintains the template from this repo;
  otherwise delete it and keep `roadmaps/`.

## 6. Verify and hand over

- `grep -ri "ai.accelerator" .` (excluding `node_modules`, `.venv`, lockfiles) → nothing;
  `make test` green; `make infra-build` clean.
- **Re-ask anything left unanswered** during the run (the deletion question in step 5, a missing
  manifest value) — list it under "Open" in the hand-over; never default silently.
- End with **How to test** (the commands above) and **Needs a human**: the cloud team's real
  manifests if placeholders were used; GitHub Environments/secrets; the first `dev` deploy
  (`make infra-deploy ENV=dev`, step 1 of two) → `node scripts/grant-request.mjs` → the cloud
  team grants → the contained SQL user → step 2 (`deployContainerApps = true`); `/implement-next
infra 1.1` afterwards.
- Suggest the next step: `/architecture-review` once B2–B6 are written, then
  `/plan-roadmap api` / `web` / `infra`.
