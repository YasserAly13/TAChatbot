# Template roadmap — revision 2: Bicep on a shared platform

> **What this is.** The second backlog of changes to the **template itself**, triggered by the
> project owners' decisions of 2026-10-04 (below). It supersedes the infrastructure part of
> [`template-roadmap.md`](template-roadmap.md) (Phase 2 and decisions D3–D5) and carries over the
> findings of the first developer dry run (`docs/development/walkthrough-team-assistant.md`,
> Part 9). Everything else in the first roadmap stands.
>
> **Status markers:** `[ ]` todo · `[~]` in progress · `[x]` done · `[!]` blocked on a human.
> One branch for all phases: `feat/bicep-shared-platform`.

---

## 0. Decisions (project owners, 2026-10-04)

| #   | Decision                                                                                                                                                                                                                                                                                                                                                                                                                                             | Replaces |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| D3′ | Infrastructure is authored in **Bicep**, not Terraform.                                                                                                                                                                                                                                                                                                                                                                                              | D3       |
| D4′ | **Two tiers.** The **platform tier** — Azure AI Foundry (with model deployments), the Container Apps Environment, the Container Registry and the **AI Search service** — exists per environment (dev/staging/prod), is owned by the cloud team and **shared by every use case**. The **use-case tier** — the use case's own container apps, database, storage account, Key Vault, App Insights, AI Search **index** — is deployed by the developers. | D4       |
| D5′ | **GitHub Actions deploys the use-case tier to every environment**; developers may deploy to **dev** from their machines. One service principal per environment (unchanged from A3).                                                                                                                                                                                                                                                                  | D5       |
| D9  | The infra team **provides the Bicep building blocks** (container app, database, storage account, …). The template **vendors** them under `infra/modules/` and never edits them; the developer supplies **names and parameters** per environment. Until the files arrive, the template ships an assumed interface clearly marked as such.                                                                                                             | —        |
| D10 | Shared-resource names/IDs come from a **per-environment manifest** `infra/platform/<env>.json` supplied by the cloud team; everything reads from it.                                                                                                                                                                                                                                                                                                 | —        |
| D11 | **Cross-tier grants are requests, not deployments.** A use case's identities need roles on shared resources (AcrPull on the registry, Cognitive Services OpenAI User on Foundry, Search Index Data Reader/Contributor on AI Search). The template outputs the principal IDs and generates `infra/grant-request.md`; the cloud team grants.                                                                                                           | —        |
| D12 | **Images:** CI builds and pushes to the shared registry (pipeline SP holds AcrPush); the Bicep deployment takes `apiImage` / `webImage` parameters.                                                                                                                                                                                                                                                                                                  | —        |
| D13 | **Agent permissions:** the standalone `bicep` CLI (`build`, `lint`, `format`) is allowed; **every `az` command prompts the user and is approved for that one invocation** (no blanket allow, no blanket deny) — except irreversible deletes/purges, which stay denied.                                                                                                                                                                               | settings |

Still in force: D1 (living architecture document), D2 (Azure-only databases), D6 (Azure SQL),
D7 (AI Search), D8 (Okta later), A3 (one SP per environment).

---

## Phase 0 — Decide and record

| Status | ID  | Change                                                                                                                                                                                                                    |
| ------ | --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `[x]`  | 0.1 | ADR-0012 _"Bicep on a shared platform; use-case-scoped infrastructure"_ (supersedes ADR-0007; records D3′–D5′, D9–D13).                                                                                                   |
| `[x]`  | 0.2 | `docs/template-roadmap.md`: D3–D5 marked superseded with a pointer here; Phase 2 marked superseded; 8.1 no longer reserves ADR-0012.                                                                                      |
| `[x]`  | 0.3 | `docs/architecture/ARCHITECTURE.md` Part A: A2 principle, A3 diagram, A6 environments, A7 status rows rewritten for the two tiers; B6 slot asks for platform references + owned resources.                                |
| `[x]`  | 0.4 | Memory + `CLAUDE.md` stack table / "What you cannot do" rewritten for Bicep (full sweep in Phase 4).                                                                                                                      |
| `[x]`  | 0.5 | `.gitattributes` (`* text=auto eol=lf`): Windows `core.autocrlf=true` rewrote every file as CRLF at checkout, breaking `bash scripts/doctor.sh`, `prettier --check` and the hooks — found while branching for revision 2. |

## Phase 1 — Remove Terraform

| Status | ID  | Change                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ------ | --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `[x]`  | 1.1 | **Delete `infra/terraform/`** (confirmed by the owner before deletion).                                                                                                                                                                                                                                                                                                                                                 |
| `[x]`  | 1.2 | `Makefile` / `justfile`: `tf-*` → `infra-build`, `infra-lint`, `infra-whatif ENV=dev`, `infra-deploy ENV=dev` (humans; refuses other envs); `just` loads `infra/.env` for the humans' targets.                                                                                                                                                                                                                          |
| `[x]`  | 1.3 | `.github/workflows/infra.yml` → Bicep: lint + build on PR, `what-if` posted as a PR comment, `deployment group create` on merge per GitHub Environment with `apiImage`/`webImage`; `ci.yml` quality job → `bicep build`/`lint`; PR template wording.                                                                                                                                                                    |
| `[x]`  | 1.4 | `.claude/settings.json`: drop `terraform *`; allow `bicep build/lint/format`; `az` moves from blanket deny to **ask** with explicit denies for `az group delete`, `az resource delete`, `az deployment group delete`, `az sql server/db delete`, `az containerapp delete`, `az storage account delete`, `az keyvault delete/purge`, `az acr delete`, `az cognitiveservices account delete`, `az search service delete`. |
| `[x]`  | 1.5 | `.claude/hooks/format-changed.mjs`: `.bicep`/`.bicepparam` → `bicep format`; `scripts/doctor.sh` + `setup-dev-env`: Terraform row → **Bicep CLI** (required), `az` (required for developers); `.gitignore` sweep.                                                                                                                                                                                                       |
| `[x]`  | 1.6 | Terraform wording sweep: tooling/config done in Phase 1 (Make/just, CI, hooks, doctor, settings, PR template, compose, migrate.yml); skills/agents/rules in Phase 3, docs in Phase 4.                                                                                                                                                                                                                                   |

## Phase 2 — The Bicep layout

| Status | ID  | Change                                                                                                                                                                                                                                                                                                          |
| ------ | --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `[x]`  | 2.1 | `infra/platform/{dev,staging,prod}.json` + `README.md` + `platform.schema.json` — the manifest contract: Container Apps Environment id, registry login server + id, Foundry endpoint + resource id + deployment names, AI Search endpoint + resource id, location, tags.                                        |
| `[x]`  | 2.2 | `infra/modules/` — vendored building blocks with the **assumed interface** (`container-app.bicep`, `sql-database.bicep`, `storage-account.bicep`, `key-vault.bicep`, `user-assigned-identity.bicep`, existing `observability.bicep`/`alerts.bicep`); header marks each as "replace with the infra team's file". |
| `[x]`  | 2.3 | `infra/main.bicep` — the use case: `existing` references from the manifest, module calls for the owned tier, api/web container apps with the **same env-var wiring as before** (AI, Search incl. index, embedding dimensions, Key Vault secret refs, telemetry), outputs (URLs, principal IDs).                 |
| `[x]`  | 2.4 | `infra/main.{dev,staging,prod}.bicepparam` — names only; `.example` committed, real files gitignored only where they carry per-developer values; **no secrets ever**.                                                                                                                                           |
| `[x]`  | 2.5 | `infra/grant-request.md` generated from outputs (template + script) — the cloud-team request for D11.                                                                                                                                                                                                           |
| `[x]`  | 2.6 | `infra/README.md` rewritten as the hub: tiers, who owns what, deploy flow, local dev deploy, troubleshooting. Interim `infra/main.bicep` observability stack folded into 2.3.                                                                                                                                   |
| `[x]`  | 2.7 | `bicep build` + `bicep lint` clean for `main.bicep` with each `.bicepparam`.                                                                                                                                                                                                                                    |
| `[ ]`  | 2.8 | Azure SQL metric alerts in `alerts.bicep` (the module still carries the Postgres rules, skipped via `postgresServerId: ''`); Entra-only telemetry ingestion as a grant-request option.                                                                                                                          |

## Phase 3 — Skills, commands, agents, rules

| Status | ID  | Change                                                                                                                                                                                                                                                                                  |
| ------ | --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `[x]`  | 3.1 | `infra-scaffold` (+ command): Bicep flow — call a vendored module, params in all three `.bicepparam`, build/lint, docs; never a platform-tier resource; cross-tier roles → `grant-request.md`.                                                                                          |
| `[x]`  | 3.2 | `init-project`: landing-zone questions → paste/fill the platform manifest + use-case resource names; writes `platform/<env>.json` + the three `.bicepparam`; "Needs a human" = grants, first dev deploy, GitHub config. CODEOWNERS rewrite; unanswered questions re-asked at hand-over. |
| `[x]`  | 3.3 | `plan-roadmap`: infra items = owned tier only; standard first items "1.1 first dev deploy", "1.2 grants requested/confirmed"; **model/migration authoring never depends on the deploy**.                                                                                                |
| `[x]`  | 3.4 | `implement-next`, `start`, `architecture-review`, `git-flow`, `feature-scaffold`, `write-migration`, `db-introspector`, `docs-lookup`, `setup-dev-env`: wording + Bicep hard stops.                                                                                                     |
| `[x]`  | 3.5 | Agents `code-reviewer`, `security-reviewer`, `migration-author`, `dependency-updater`, `test-writer`; skill `security-review`: Bicep checks (no secrets in params, `existing` for platform resources, three param files in parity, what-if reviewed).                                   |
| `[x]`  | 3.6 | Rules: `00-architecture.md`, `25-sqlalchemy.md`, `50-security.md` updated; new **`.claude/rules/80-bicep.md`** scoped to `infra/**`.                                                                                                                                                    |

## Phase 4 — Docs and the walkthrough

| Status | ID  | Change                                                                                                                                                                                                                                                                                                          |
| ------ | --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `[x]`  | 4.1 | `README.md`, `CLAUDE.md`, `docs/getting-started.md`, `docs/operations/deployment.md` (rewrite), `docs/operations/ci-cd-roadmap.md`, `docs/reference/{commands,environment-variables}.md`, `docs/architecture/{overview,data,ai}.md`, `roadmaps/README.md`, `apps/api/README.md`, `docker-compose.yml` comments. |
| `[x]`  | 4.2 | ADR-0007 → Superseded by 0012; ADR index.                                                                                                                                                                                                                                                                       |
| `[x]`  | 4.3 | `docs/development/walkthrough-team-assistant.md` Part 8 rewritten: manifest → `.bicepparam` → `what-if` → deploy → grant request → migration → ingest.                                                                                                                                                          |

## Phase 5 — Dry-run findings carried over (infra-agnostic)

| Status | ID  | Change                                                                                                                                       |
| ------ | --- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `[x]`  | 5.1 | `apps/api/app/errors.py` — the `/v1` error contract `{error, trace_id}`, handlers, mid-stream abort — into the template with tests and docs. |
| `[x]`  | 5.2 | Repo-integrity check (`.github/`, `.claude/`, `.nvmrc`, `scripts/`, `infra/platform/`) in `scripts/doctor.sh` and `/start`.                  |
| `[x]`  | 5.3 | Skills: a question left unanswered mid-run is re-asked in the hand-over, never silently defaulted (`init-project`, `setup-dev-env`).         |

## Phase 6 — Verify

| Status | ID  | Change                                                                                                                                                                |
| ------ | --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `[x]`  | 6.1 | `bicep build`/`lint` ×3 param files; api + web suites green; `prettier --check`; doctor; hooks; `grep -ri terraform` → only ADR-0007 and the first roadmap's history. |
| `[!]`  | 6.2 | **Human:** cloud team supplies the real manifest + Bicep files → swap the assumed modules; first `what-if` + deploy on dev.                                           |

## Needs a human

| ID  | Action                                                                                                                                                    | Blocks   |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| H1  | Confirm deletion of `infra/terraform/` (1.1).                                                                                                             | Phase 1  |
| H2  | Cloud team: per-environment manifest values; the Bicep building blocks (D9); pipeline SP with Contributor on the env RG + AcrPush on the shared registry. | 2.1, 6.2 |
| H3  | Cloud team: grant the roles listed in `infra/grant-request.md` after the first deploy.                                                                    | runtime  |
| H4  | GitHub Environments + `<ENV>_AZURE_*` secrets, `<ENV>_RESOURCE_GROUP` variables.                                                                          | 1.3      |

## Order

0 → 1 → 2 → 3 → 4 → 6; Phase 5 in parallel with 3–4. Commit per phase on the owner's "yes".
