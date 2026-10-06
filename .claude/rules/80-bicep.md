---
description: Infrastructure conventions — Bicep on a shared, cloud-team-owned platform (ADR-0012). Loaded when editing infra/** or the infrastructure workflow.
paths:
  - 'infra/**'
  - '.github/workflows/infra.yml'
  - 'scripts/grant-request.mjs'
---

# Infrastructure rules (Bicep, two tiers)

> **Graded autonomy:** these are conventions to apply _within_ an approved plan or roadmap item — not a licence to act outside one. Hard stops (deploy, deletes, secrets, role grants) always need explicit confirmation — see [`CLAUDE.md`](../../CLAUDE.md) → _Graded autonomy_.

Decided in [ADR-0012](../../docs/adr/0012-bicep-shared-platform.md). The hub is
[`infra/README.md`](../../infra/README.md).

## The two tiers

| Tier         | What                                                                                                                    | Owner      | In this repo                                                                                   |
| ------------ | ----------------------------------------------------------------------------------------------------------------------- | ---------- | ---------------------------------------------------------------------------------------------- |
| **Platform** | Azure AI Foundry + model deployments · Container Apps Environment · Container Registry · AI Search **service**          | cloud team | `infra/platform/<env>.json` (manifest) → `existing` references in `main.bicep`. **Read-only.** |
| **Use case** | container apps · Azure SQL server + db · storage · Key Vault · Log Analytics + App Insights + alerts · Search **index** | this team  | `infra/main.bicep` + `main.<env>.bicepparam`, composed from `infra/modules/`                   |

## Rules

- **Platform resources are never declared.** No `Microsoft.App/managedEnvironments`,
  `Microsoft.ContainerRegistry/registries`, `Microsoft.CognitiveServices/accounts` or
  `Microsoft.Search/searchServices` resource in any file here — `existing` only, names from the
  manifest. A need on that tier is a **request to the cloud team**, written down, not scaffolded.
- **No role assignments.** Not on shared resources (D11) and not on ours (the deployment
  identity is Contributor). Every role goes into the `grantRequest` output →
  `node scripts/grant-request.mjs` → `infra/grant-request.md`. Key Vault uses **access
  policies**, not RBAC, for the same reason.
- **Vendored blocks are not edited.** Files under `infra/modules/` with the infra team's header
  are replaced wholesale when they ship a new version; the ⚠ placeholders carry an **assumed
  interface** and are swapped, not patched. Template-owned modules (`observability`, `alerts`,
  `availability`, `user-assigned-identity`) say so in their header.
- **Three param files in parity.** `main.dev|staging|prod.bicepparam` have the same parameters;
  values differ (dev small + developer IPs, prod hardened: purge protection, ZRS, no IPs). A new
  `param` lands in all three in the same change.
- **No secrets in `.bicepparam`, manifests, outputs or logs.** Connection strings are computed
  in `main.bicep` (`DATABASE-URL` is managed-identity, passwordless) and stored in the use
  case's Key Vault; apps read them via `keyVaultEnvRefs`. Object IDs, names and endpoints are
  not secrets. `@secure()` on any param that carries a value.
- **The app contract does not change.** The env vars `main.bicep` sets are the ones in
  `apps/*/.env.example` (`AZURE_AI_*` incl. `AZURE_AI_EMBEDDING_DIMENSIONS` from the manifest,
  `AZURE_SEARCH_*`, `DATABASE_URL`, telemetry). A new env var is added to `.env.example`,
  `docs/reference/environment-variables.md` and here in the same change.
- **Naming:** `<prefix>-<slug>-<env>[-<service>]`; respect Azure limits with `take()` (Key Vault
  ≤ 24 → `kv-<slug≤13>-<env>`; storage ≤ 24 lowercase alphanumerics). Index name `<slug>-docs`
  must be unique on the shared search service.
- **Two-step first deployment.** `deployContainerApps = false` until the cloud team has granted
  AcrPull (an app cannot pull before that); the roadmap models the grant as a human step.
- **Verify properties against the ARM reference** (`learn.microsoft.com/azure/templates/...`) and
  keep API versions current; never guess. `make infra-build` (build + lint + param binding) must
  be clean — fix warnings, do not suppress them.

## What agents may run

`bicep build` · `bicep build-params` · `bicep lint` · `bicep format` (`make infra-build`,
`make fmt`). Every `az` command prompts the developer and is approved for that one call;
`az deployment group what-if` is fine when they ask; **`az deployment group create` is never
run by an agent** — `make infra-deploy ENV=dev` is the developer's (dev only), merges deploy
staging/prod through `infra.yml`. Deletes, purges, `az role assignment`, `az ad` are denied.

## Review checklist (code-reviewer / security-reviewer)

No platform-tier resource · no role assignment · vendored blocks untouched · three param files
in parity · no secret values anywhere · env-var contract intact · `grantRequest` updated for
new roles · TLS floors (`minimalTlsVersion 1.2`, `Encrypt=yes`, HTTPS-only) untouched · prod
params hardened · `make infra-build` clean · `what-if` reviewed before merge.
