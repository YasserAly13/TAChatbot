---
name: infra-scaffold
description: Add or change a resource this use case OWNS in the Bicep stack the repository's way (ADR-0012) — call a vendored building block from infra/modules/ in infra/main.bicep, add its parameters to all three main.<env>.bicepparam files, wire env vars/outputs, bicep build + lint, docs — and hand what-if/deploy to the pipeline or a human. Never a platform-tier resource (Foundry, Container Apps Environment, registry, AI Search service), never a role assignment (those go to infra/grant-request.md), never an edit to a vendored block.
---

# Infra scaffold (Bicep, two tiers)

> **Scope gate:** Say the resource, the building block you will call and the files you will touch, then proceed. You may run `bicep build`, `bicep lint`, `bicep format`, `bicep build-params` (`make infra-build`). Every `az` command prompts the developer — ask for `what-if` only when they have `az login` and rights on the environment's resource group; **you never run `az deployment group create`** (hard stop — the pipeline's or a human's). Deleting a resource from `main.bicep` is a delete: confirm first.

## The model you are working in

- **Platform tier — read-only.** Azure AI Foundry (+ deployments), the Container Apps
  Environment, the Container Registry and the AI Search **service** pre-exist per environment,
  owned by the cloud team, shared by every use case, described by `infra/platform/<env>.json`.
  They appear in `main.bicep` **only** as `existing` resources. You never declare, change,
  delete or grant on them.
- **Use-case tier — ours.** `infra/main.bicep` composes **vendored building blocks** from
  `infra/modules/` (the infra team's files; the ones marked ⚠ are placeholders with an assumed
  interface until theirs arrive). Names and sizes live in `main.dev|staging|prod.bicepparam`
  — **always all three, in parity**.
- **No role assignments, anywhere.** The deployment identity is Contributor; it cannot write
  `Microsoft.Authorization/roleAssignments`. A role a new resource needs → a row in the
  `grantRequest` output of `main.bicep` (rendered to `infra/grant-request.md`). Key Vault uses
  access policies for the same reason.
- **No secrets in param files or manifests.** Connection strings are computed in `main.bicep`
  and stored in the use case's Key Vault; apps read them through their identity.

## Steps

1. **Classify the request.**
   - Platform tier (a new model deployment, more search capacity, a registry change, environment
     settings) → **stop**: write the request for the cloud team (what, why, which environment)
     and say so. Do not scaffold.
   - A resource the use case owns (storage container, second database, queue, extra container
     app, alert, Key Vault secret, index name) → continue.
2. **Pick the building block.** Prefer an existing file in `infra/modules/`. If none fits, do
   **not** write a new module silently: ask whether the infra team provides one; only on "no"
   add a template-owned module (header: `// Template-owned — replace when the infra team ships
an equivalent`) with the same shape as the others (`name`, `location`, `tags`, outputs
   `id`/`name`).
3. **Verify resource properties against the ARM reference** (`docs-lookup` →
   `https://learn.microsoft.com/azure/templates/<provider>/<type>`) before writing — never guess
   property names or API versions; `bicep build` is the second check.
4. **Wire it in `main.bicep`:** module call in the right section; a `names.<x>` entry following
   the naming convention (`<prefix>-<slug>-<env>[-<service>]`, length limits respected with
   `take()`); env vars on the container app(s) that need it (`env`/`keyVaultEnvRefs`); outputs;
   a `grantRequest` row for every role it needs (ours or shared).
5. **Parameters:** new `param`s with `@description` and sane defaults in `main.bicep`; values in
   **all three** `.bicepparam` files (dev small, prod hardened). Never a secret value.
6. **Check:** `make infra-build` (build + lint + the three param files) must be clean — fix
   warnings, don't silence them. If the developer has `az login` + rights on the dev resource
   group, ask whether to run `make infra-whatif ENV=dev` and paste the summary.
7. **Docs, same change:** `infra/README.md` (layout/naming/troubleshooting rows),
   `docs/reference/environment-variables.md` for any new env var, `apps/*/.env.example`
   placeholders, `ARCHITECTURE.md` Part B6 **proposal** (never rewrite it), the roadmap item's
   `notes`.
8. **Hand over** with **How to test** (`make infra-build`; `make infra-whatif ENV=dev` and the
   expected resource list; what the app should show afterwards) and **Needs a human** (the deploy
   — pipeline on merge, or `make infra-deploy ENV=dev`; the grant request if a role was added; any
   one-time step such as a contained SQL user or a Key Vault secret value).

## Never

- `Microsoft.App/managedEnvironments`, `Microsoft.ContainerRegistry/registries`,
  `Microsoft.CognitiveServices/accounts`, `Microsoft.Search/searchServices` as **resources**.
- `Microsoft.Authorization/roleAssignments`, `az role assignment …`, `az ad …`.
- Editing a file under `infra/modules/` that carries the infra team's header; editing
  `infra/platform/*.json` (the cloud team's values — a PR replaces the file).
- A param file that differs from the other two in structure, or a value that only exists in one.
- `az deployment group create`, `az … delete`, `az keyvault purge` — denied or human-only.
