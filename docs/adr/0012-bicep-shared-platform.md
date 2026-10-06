# ADR-0012: Bicep on a shared platform — use-case-scoped infrastructure, cloud-team-owned building blocks

|            |                                              |
| ---------- | -------------------------------------------- |
| Status     | Proposed                                     |
| Date       | 2026-10-04                                   |
| Supersedes | [ADR-0007](0007-terraform-infrastructure.md) |

## Context

ADR-0007 made the template the owner of **all** infrastructure: Terraform modules for
observability, Key Vault, Azure SQL, the container registry, the Container Apps environment,
the container apps, AI Foundry and AI Search, with one root per environment, remote state in
pre-existing storage accounts and a service principal per environment applying from GitHub.

The first developer dry run (2026-10-04, `docs/development/walkthrough-team-assistant.md`
Part 9) showed the cost of that model: the developer spent most of a session on platform
administration (state accounts, constrained RBAC Administrator grants, provider registration,
eight plan-time module bugs) before writing a line of the use case. The project owners then
set a different operating model:

- Infrastructure is written in **Bicep**, the Azure-native language the cloud team uses.
- The **platform tier** already exists per environment and is **shared by every use case**
  built on this template: Azure AI Foundry (with its model deployments), the Container Apps
  Environment, the Container Registry and the AI Search service.
- Developers deploy only the **use-case tier**: their container apps inside the shared
  environment, their own database, storage account, Key Vault, Application Insights and their
  AI Search index.
- The infra team **provides the Bicep building blocks** (container app, database, storage
  account, …); developers supply names and parameters, not resource definitions.

## Decision

1. **Bicep replaces Terraform.** `infra/terraform/` is deleted; `infra/` holds `main.bicep`
   (the use case), `main.<env>.bicepparam` (names and sizes per environment), vendored
   building blocks under `infra/modules/`, and the platform manifests under `infra/platform/`.
2. **Two tiers, one boundary.** `main.bicep` references the platform tier **only** through
   `existing` resources whose names/IDs come from `infra/platform/<env>.json`, a small manifest
   supplied by the cloud team (Container Apps Environment id, registry login server and id,
   Foundry endpoint, resource id and deployment names, AI Search endpoint and id, location,
   tags). The template never creates, modifies or deletes a platform-tier resource.
3. **Vendored building blocks.** The infra team's Bicep files live under `infra/modules/` and
   are **never edited in a project** — they are replaced wholesale when the team ships a new
   version. Until the first delivery, the template ships modules with an **assumed interface**
   (`name`, `location`, `tags`, the shared IDs as parameters, identity/env/secrets for the
   container app) and marks each file as a placeholder to swap.
4. **Deployment.** GitHub Actions deploys the use-case tier in every environment: `bicep
build` + `lint` and `az deployment group what-if` on pull requests (posted as a comment),
   `az deployment group create` on merge, in the GitHub Environment of the target (required
   reviewers). Developers may deploy to **dev** from their machines. One service principal per
   environment with Contributor on that environment's resource group and **AcrPush** on the
   shared registry; it needs no rights on other shared resources.
5. **Cross-tier grants are requests.** A use case's managed identities need roles on shared
   resources — AcrPull on the registry, Cognitive Services OpenAI User on Foundry, Search
   Index Data Reader/Contributor and Search Service Contributor on AI Search. The deployment
   **outputs** the principal IDs and the repo generates `infra/grant-request.md`; the cloud
   team grants. No role assignment on a shared resource is ever authored here.
6. **Images.** CI builds both images and pushes them to the shared registry; the Bicep
   deployment takes `apiImage` and `webImage` parameters, so a deploy is "new image tag +
   `what-if` + create".
7. **Application contract unchanged.** The container apps receive exactly the environment
   variables the Terraform roots set (`AZURE_AI_*` including `AZURE_AI_EMBEDDING_DIMENSIONS`,
   `AZURE_SEARCH_*` including the use case's index, `DATABASE_URL` as a Key Vault secret
   reference, telemetry variables, `APP_ENV`). No application code changes.
8. **Agent permissions.** Agents may run the standalone `bicep` CLI (`build`, `lint`,
   `format`). Every `az` invocation **prompts the developer** and is approved for that one call;
   irreversible operations (`az group delete`, `az resource delete`, `az deployment group
delete`, database/server/vault/registry/account deletes and Key Vault purge) stay denied.
   Applying infrastructure remains a hard stop in `CLAUDE.md`.

## Consequences

**Positive**

- A developer's infrastructure work shrinks to "name the resources, fill three param files,
  read the what-if". No state backends, no provider registration, no RBAC Administrator.
- Shared Foundry/registry/environment/search means one quota, one bill, one hardening effort
  for the cloud team, and a known shape for every use case.
- The building blocks are the cloud team's — they carry their policies (SKUs, networking,
  diagnostics) and the template inherits improvements by re-vendoring.
- `what-if` replaces `terraform plan` as the review artefact without a state file to manage.

**Negative / accepted**

- The template depends on files it does not own: until the cloud team ships the modules and
  manifests, it carries an assumed interface and the first real deploy will need a reconciling
  pass (roadmap revision 2, item 6.2).
- Cross-tier grants are asynchronous — a use case cannot run end to end until the cloud team
  has acted on `grant-request.md`. The roadmap models this as a human step that blocks
  "switch mocks off", never as something an agent tries to do.
- Every `az` call now prompts instead of being refused outright; the safety moves from a deny
  list to the developer reading the prompt. Deletes and purges remain denied as a backstop.
- Shared AI Search means index names must be unique per use case (`<slug>-docs` convention)
  and the cloud team's search tier bounds every use case's index size.
- ADR-0007's Terraform modules, which encoded several hard-won fixes (unknown-at-plan
  `for_each`, sensitive conditions), are discarded; the equivalent Bicep concerns are the
  infra team's.

## Alternatives considered

- **Keep Terraform, add `data` sources for the shared tier.** Rejected: the cloud team works
  in Bicep and provides Bicep; two toolchains for one resource group double the operational
  surface for a team that is not infrastructure-first.
- **Template-owned Bicep for everything, including the platform tier.** Rejected: the platform
  tier is deliberately shared; duplicating Foundry/registry/environment per use case defeats
  the owners' quota and cost model.
- **Let agents assign cross-tier roles.** Rejected: it requires RBAC Administrator on shared
  resources for every use case's identity — the exact permission the dry run showed developers
  do not and should not have.
- **Blanket `az` allow for agents.** Rejected: too broad. Per-invocation approval with denied
  deletes is the balance the owners chose.

## References

- [`docs/template-roadmap-bicep.md`](../template-roadmap-bicep.md) — the implementation backlog
  (revision 2).
- [`docs/template-roadmap.md`](../template-roadmap.md) — decisions D3–D5 (superseded) and
  everything still in force.
- [`docs/development/walkthrough-team-assistant.md`](../development/walkthrough-team-assistant.md)
  Part 9 — the dry-run findings that motivated the change.
- [`infra/README.md`](../../infra/README.md) — the hub for the Bicep layout (rewritten in
  revision 2, Phase 2).
