# ADR-0013: Run locally against pre-provisioned dev resources — no project infrastructure

|        |            |
| ------ | ---------- |
| Status | Accepted   |
| Date   | 2026-10-06 |

## Context

Part A (A2.7, A6) expects every project to deploy its use-case tier with Bicep (container apps,
Azure SQL, Key Vault, App Insights, Search index) across `dev`/`staging`/`prod`, with secrets in
Key Vault and managed identity when deployed (ADR-0012, ADR-0008, ADR-0009). Team Assistant is a
one-person internal project whose Azure resources — a Foundry endpoint with `gpt-4.1` and
`text-embedding-3-large`, an AI Search service with index `team-assistant-docs`, and an Azure SQL
database — were created by hand in a sandbox before the project started (`ARCHITECTURE.md` → B1).
The owner has stated that no infrastructure is to be deployed by this project in any environment.

## Decision

Team Assistant runs only on developer machines (`APP_ENV=local`) against the pre-provisioned `dev`
resources, configured through the gitignored `apps/api/.env` with `AZURE_AI_AUTH_MODE=api_key` and
search/database credentials held there; the template's `infra/` tier and `infra.yml` stay in the
repo unused, and migrations are applied by the named owner from their machine.

## Consequences

- Good: no infrastructure work, grants or pipeline secrets before the first feature ships.
- Good: the app code is unchanged — the same env-var contract works later with Key Vault and
  managed identity (ADR-0012) if the project is ever deployed.
- Bad: API keys and a database password live in a local `.env` instead of Key Vault; rotating
  them is manual and every developer machine holds them.
- Bad: no hosted environment — nobody but the developer can use the assistant; no staging/prod.
- Bad: the dev Azure SQL firewall is open to all IP addresses (stated at setup) and the repository
  is public with the resource names in `ARCHITECTURE.md`, so the database relies on its
  credentials alone.
- Bad: `migrate.yml` is not used; migration discipline rests on one named human.

## Alternatives considered

- **Deploy the use-case tier with the template's Bicep (ADR-0012)** — rejected for now by the
  owner: resources already exist and the project is a demo.
- **Managed identity locally via `az login` + `DefaultAzureCredential`** — not chosen yet; would
  remove the model and search API keys from `.env` once the owner's account has the data-plane
  roles. Revisit before anyone else runs the project.

## References

- Related ADRs: ADR-0008, ADR-0009, ADR-0012
- Docs: `docs/architecture/ARCHITECTURE.md` → B1, B6, B7; `roadmaps/infra/ROADMAP.md` → 1.1
