# ADR-0007: Terraform for all infrastructure, on pre-existing resource groups, applied by GitHub per environment

|        |                                                                      |
| ------ | -------------------------------------------------------------------- |
| Status | Superseded by [ADR-0012](0012-bicep-shared-platform.md) (2026-10-04) |
| Date   | 2026-09-28                                                           |

## Context

The template's infrastructure is authored in Bicep (`infra/main.bicep` + three modules: the
observability/alerting stack) and deployed by a maintainer running `az deployment group create`
by hand; app hosting, databases, Key Vault and AI resources are not authored at all. The team
that owns the projects built on this template works differently: it has **three resource groups**
(`dev`, `staging`, `prod`) that host **every** application, **one Terraform state storage account
per resource group** (created by hand), and **one app registration (service principal) per
environment** with Contributor on _only_ its own resource group. It deploys and updates
resources with **Terraform**, from **GitHub Actions in every environment**, and developers may
also run Terraform locally against `dev`. The template must therefore stop assuming Bicep, stop
assuming it owns resource groups, and let agents help with infrastructure without ever being
able to apply it.

## Decision

We author all infrastructure in **Terraform (`azurerm` provider)** under `infra/terraform/`, as
reusable modules plus one root per environment (`envs/dev|staging|prod`). Resource groups and the
state storage accounts are **never created by Terraform**: each environment root takes the
resource-group name as a variable and reads it with `data "azurerm_resource_group"`, and its
backend is configured with a per-environment `backend.hcl` pointing at that environment's
existing account (`st<org>tfstate<env>`, container `tfstate`, key
`<project-slug>/terraform.tfstate`, Entra ID auth). **GitHub Actions plans on pull request and
applies on merge, per environment, using that environment's service principal and a GitHub
Environment approval**; developers may run `terraform plan`/`apply` locally against `dev` only.
Agents (Claude) may run `terraform fmt`/`validate`/`init`/`plan`; `apply`, `destroy`, `import`
and state commands are denied to them. The Bicep observability stack is ported 1:1 to a
Terraform module and the Bicep files are removed.

## Consequences

- Good: one IaC toolchain that matches how the team already deploys; agents can author and
  plan infrastructure safely, humans/pipelines apply.
- Good: per-environment SPs with single-RG scope + per-environment state make a mistake in
  `dev` incapable of touching `staging`/`prod`.
- Good: state per project inside a shared account gives the team one place to look, with no
  per-project storage to provision.
- Bad: the Bicep port is real work and must be verified against a live subscription before the
  Bicep files are deleted (the alerting rules are the riskiest part).
- Bad: `backend.hcl` and `terraform.tfvars` carry environment-identifying values and must stay
  out of git (only `*.example` files are committed); `init-project` has to generate them.
- Bad: local `apply` to `dev` by a developer can drift from what the pipeline last applied;
  the pipeline's plan-on-PR surfaces the drift, but it is a discipline, not a lock.

## Alternatives considered

- **Keep Bicep** — rejected: the team's SPs, pipelines and habits are Terraform; two toolchains
  for one platform doubles the surface agents must know.
- **Terraform creates the resource groups and state storage** — rejected: the groups pre-exist
  and are shared by all applications; letting a project's Terraform own them would let one
  project's `destroy` take down every other app in the environment.
- **One state file per environment for all projects** — rejected: unrelated projects would lock
  and plan against each other's state; a per-project key inside the shared account isolates
  them at zero cost.
- **A single SP with Contributor on all three groups** — rejected by the team's security model:
  a leaked `dev` credential must not reach `prod`.
- **Applies only from the pipeline, never locally** — rejected for `dev`: developers need a
  fast loop while iterating on infrastructure; `staging`/`prod` remain pipeline-only.

## References

- Related ADRs: ADR-0006 (living architecture document), ADR-0008 (Azure SQL data layer,
  which the `sql-database` module provisions)
- Docs: `docs/template-roadmap.md` (decisions D3–D5, Phase 2), `infra/terraform/README.md`,
  `docs/operations/deployment.md`, root `CLAUDE.md` → _What you cannot do_
- External: Terraform `azurerm` backend
  (`https://developer.hashicorp.com/terraform/language/backend/azurerm`), `azurerm` provider
  (`https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs`)
