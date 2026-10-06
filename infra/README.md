# `infra/` — this use case's Azure footprint, in Bicep

> **The model in one paragraph (ADR-0012).** The cloud team runs a **platform tier** per
> environment that every use case shares: Azure AI Foundry (with the model deployments), the
> Container Apps Environment, the Container Registry and the AI Search service. It already
> exists; you never create or change it. You deploy the **use-case tier**: your two container
> apps inside the shared environment, your Azure SQL server + database, storage account, Key
> Vault, Log Analytics + Application Insights + alerts, and your index name on the shared search
> service. You describe it by **naming things in a param file**, not by writing resources — the
> building blocks come from the infra team.

## Layout

```
infra/
├── README.md                 this file
├── platform/                 the SHARED tier, as the cloud team describes it (committed, no secrets)
│   ├── dev.json  staging.json  prod.json
│   ├── platform.schema.json  shape of a manifest
│   └── README.md
├── modules/                  building blocks — the infra team's files, VENDORED, never edited here
│   ├── container-app.bicep      ⚠ assumed interface until the infra team's file arrives (D9)
│   ├── sql-database.bicep       ⚠ assumed interface
│   ├── storage-account.bicep    ⚠ assumed interface
│   ├── key-vault.bicep          ⚠ assumed interface
│   ├── user-assigned-identity.bicep   template-owned (no policy content)
│   ├── observability.bicep      template-owned: Log Analytics + workspace-based App Insights + cost alert
│   ├── alerts.bicep             template-owned: per-app, error-spike, Service Health alert rules
│   └── availability.bicep       template-owned: /health web tests
├── main.bicep                the use case — `existing` references + module calls + outputs
├── main.dev.bicepparam       names and sizes per environment (committed — no secrets, ever)
├── main.staging.bicepparam
├── main.prod.bicepparam
└── grant-request.md          GENERATED: the roles the cloud team must grant (D11)
```

## What a developer actually does

| Want                                   | Do                                                                                                                                                                     |
| -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Check the Bicep compiles               | `make infra-build` (or `just infra-build`) — `bicep build` + `lint` + binds the three param files. **Agents may run this.**                                            |
| Change a name, size, replica count, IP | Edit `main.<env>.bicepparam` — all three environments, kept in parity.                                                                                                 |
| Add a resource the use case owns       | `/infra-scaffold` — calls an existing block in `main.bicep`, adds its params to the three param files, builds, documents. Never a platform-tier resource.              |
| Preview a deployment                   | `az login` → `make infra-whatif ENV=dev`. Pipelines post the same `what-if` on every PR touching `infra/**`.                                                           |
| Deploy to **dev** from a laptop        | `make infra-deploy ENV=dev` (humans only; refuses other environments).                                                                                                 |
| Deploy to staging / prod               | Merge to `staging` / `main` — `.github/workflows/infra.yml` builds and pushes the images to the shared registry and deploys behind the GitHub Environment's reviewers. |
| Need a role on a shared resource       | You don't assign it. `node scripts/grant-request.mjs deployment.json --env dev` → `infra/grant-request.md` → send to the cloud team.                                   |

## The first deployment — two steps

The container apps pull their images with user-assigned identities, and those identities need
**AcrPull on the shared registry** before an app can start. Role assignments on shared resources
are the cloud team's (D11), so:

1. **Step 1 — everything except the apps.** `deployContainerApps = false` in
   `main.dev.bicepparam` (the committed default) → `make infra-whatif ENV=dev` → review →
   `make infra-deploy ENV=dev`. Creates: identities, Log Analytics + App Insights + action group,
   Key Vault (with `APPLICATIONINSIGHTS-CONNECTION-STRING` and `DATABASE-URL`), SQL server +
   database + firewall rules, storage account.
2. **Grant request.** `az deployment group show -g <rg> -n <name> --output json > deployment.json`,
   then `node scripts/grant-request.mjs deployment.json --env dev` and send
   `infra/grant-request.md` to the cloud team: AcrPull (api + web identities), Cognitive Services
   OpenAI User, the three AI Search roles, and Storage Blob Data Contributor on your own storage
   account (the deployment identity cannot assign roles even there).
3. **Database user.** As the SQL Entra admin, in the database:
   `CREATE USER [id-<slug>-<env>-api] FROM EXTERNAL PROVIDER; ALTER ROLE db_datareader ADD MEMBER [id-<slug>-<env>-api]; ALTER ROLE db_datawriter ADD MEMBER [id-<slug>-<env>-api];`
   (and `db_ddladmin` for the migration principal `migrate.yml` runs as — see
   [`docs/architecture/data.md`](../docs/architecture/data.md)).
4. **Step 2 — the apps.** Set `deployContainerApps = true`, deploy again (locally for dev, or
   push images + merge for the pipeline). Alerts and the `/health` availability test attach to
   the apps automatically.

## What `main.bicep` wires into the apps

Exactly the contract the application code expects (`apps/*/.env.example`, no code changes):

| Variable                                                            | api | web | Source                                            |
| ------------------------------------------------------------------- | --- | --- | ------------------------------------------------- |
| `APP_ENV`, `LOG_LEVEL`, `PORT`, `OTEL_SERVICE_NAME`                 | ✓   | ✓   | param file / convention                           |
| `APPLICATIONINSIGHTS_CONNECTION_STRING`                             | ✓   | ✓   | Key Vault secret ref (identity reads it)          |
| `AZURE_CLIENT_ID`, `TELEMETRY_MANAGED_IDENTITY_CLIENT_ID`           | ✓   | ✓   | the app's user-assigned identity                  |
| `AZURE_AI_ENDPOINT`, `AZURE_AI_DEPLOYMENT`, `AZURE_AI_EMBEDDING_*`  | ✓   |     | `platform/<env>.json` → `aiFoundry`               |
| `AZURE_AI_AUTH_MODE=managed_identity`                               | ✓   |     | fixed                                             |
| `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_INDEX`                       | ✓   |     | manifest → `aiSearch.endpoint`; `searchIndexName` |
| `DATABASE_URL` (`Authentication=ActiveDirectoryMsi&UID=<clientId>`) | ✓   |     | Key Vault secret ref, built from the SQL outputs  |
| `AZURE_STORAGE_ACCOUNT`                                             | ✓   |     | storage module output                             |
| `API_BASE_URL`                                                      |     | ✓   | the api's internal ingress FQDN                   |

## Naming

`<slug>` = `projectSlug` (≤ 15 chars, rewritten by `/rename-project`); `<env>` = `dev|staging|prod`.

| Resource        | Name                                      | Resource          | Name                                     |
| --------------- | ----------------------------------------- | ----------------- | ---------------------------------------- |
| identities      | `id-<slug>-<env>-api`, `…-web`            | storage           | `st<slug-no-dashes><env>` (≤ 24)         |
| container apps  | `ca-<slug>-<env>-api`, `…-web`            | Key Vault         | `kv-<slug≤13>-<env>` (≤ 24)              |
| SQL server / db | `sql-<slug>-<env>` / `sqldb-<slug>-<env>` | App Insights / LA | `appi-<slug>-<env>` / `log-<slug>-<env>` |
| action group    | `ag-<slug>-<env>`                         | search index      | `<slug>-docs` (on the shared service)    |

## Rules (enforced by review, `.claude/rules/80-bicep.md`)

- **Platform tier is read-only.** `existing` only; no `Microsoft.App/managedEnvironments`,
  `Microsoft.ContainerRegistry/registries`, `Microsoft.CognitiveServices/accounts` or
  `Microsoft.Search/searchServices` resource is ever declared here.
- **No role assignments.** Not on shared resources (D11), and not on ours either — the
  deployment identity is Contributor. Key Vault uses access policies for that reason. Roles go to
  `grant-request.md`.
- **No secrets in param files or manifests.** Connection strings are computed in `main.bicep` and
  land in Key Vault; the apps read them by identity.
- **Three param files in parity.** A parameter added to one is added to all three.
- **Vendored blocks are not edited.** A block that lacks something → ask the infra team (or
  wrap it from `main.bicep`). Placeholders marked ⚠ are replaced wholesale when their files arrive.
- Agents run `bicep build` / `lint` / `format`; every `az` call prompts you; `deployment group
create` is yours (dev) or the pipeline's.

## Pipelines

- [`infra.yml`](../.github/workflows/infra.yml): `resolve` (branch → env; reads the manifest)
  → `whatif` (build + lint + `az deployment group what-if`, posted on the PR) → `images` (build +
  push `<registry>/<slug>-api|web:<sha>` — the SP needs **AcrPush**) → `deploy` (Environment-gated
  `create` with the pushed tags; outputs uploaded as an artifact for the grant request).
- Secrets per environment (repository-level, prefixed): `<ENV>_AZURE_CLIENT_ID`,
  `<ENV>_AZURE_TENANT_ID`, `<ENV>_AZURE_SUBSCRIPTION_ID`, and either `<ENV>_AZURE_CREDENTIALS`
  (SP secret JSON) or a federated credential for OIDC. The SP: **Contributor on the environment's
  resource group + AcrPush on the shared registry**; nothing else.
- [`migrate.yml`](../.github/workflows/migrate.yml) applies Alembic migrations per environment
  (unchanged).

## Cost guardrails and telemetry hardening

Log Analytics retention/cap and the daily-ingestion alert are parameters (`retentionInDays`,
`logAnalyticsDailyCapGb`, `dailyIngestionAlertThresholdGb`). Ingestion runs on the connection
string; Entra-only ingestion (`TELEMETRY_AUTH_MODE=managed_identity` + Monitoring Metrics
Publisher) needs a role assignment and is therefore a cloud-team step — ask for it in the grant
request when you want it. Azure SQL metric alerts are a follow-up (`alerts.bicep` still carries
the Postgres rules, skipped via `postgresServerId: ''`).

## Troubleshooting

| Symptom                                                             | Cause / fix                                                                                                               |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `what-if` fails with `ResourceNotFound` on the environment/registry | The manifest names don't match the cloud team's resources, or you're logged into the wrong subscription.                  |
| Container app stuck `Provisioning`, revision `Failed` pulling image | AcrPull not granted yet → step 2 above; or the image tag doesn't exist in the registry.                                   |
| Container app can't read Key Vault secrets                          | The identity's access policy is created by `key-vault.bicep`; check the vault's access policies list.                     |
| `Authorization failed … roleAssignments/write`                      | Something tried to assign a role. Remove it; it belongs in `grant-request.md`.                                            |
| `The vault name 'kv-…' is already in use`                           | Key Vault names are global (and soft-deleted vaults keep theirs 7–90 days). Shorten the slug or purge via the cloud team. |
| The api boots but every query fails with a login error              | The contained user for `id-<slug>-<env>-api` does not exist yet (step 3).                                                 |
