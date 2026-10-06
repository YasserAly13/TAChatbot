# Deployment and environments

How a project built on this template reaches Azure and how its environments behave. The exact
commands and the file layout live in [`infra/README.md`](../../infra/README.md) — this page does
not duplicate them. Decisions: [ADR-0012](../adr/0012-bicep-shared-platform.md) and revision 2
of the template roadmap ([`docs/template-roadmap-bicep.md`](../template-roadmap-bicep.md)).

## The model in one paragraph

The cloud team runs a **platform tier** per environment (`dev`, `staging`, `prod`) that every
use case built on this template shares: Azure AI Foundry with its model deployments, the
Container Apps Environment, the Container Registry and the AI Search service. It is described
by `infra/platform/<env>.json` and never created, changed or granted on from a project. Each
project deploys only its **use-case tier** — its two container apps inside the shared
environment, its Azure SQL server + database, storage account, Key Vault, Log Analytics +
Application Insights + alerts, and its index name on the shared search service — from
`infra/main.bicep` + `infra/main.<env>.bicepparam`, composed from the infra team's building
blocks in `infra/modules/`. **GitHub Actions deploys every environment** (what-if on pull
request, deploy on merge behind the GitHub Environment's reviewers); developers may deploy to
**dev** from their machines. Roles a use case needs on shared resources are **requested**
(`infra/grant-request.md`), never assigned by the project.

## Implemented vs. interim

- **Authored (Bicep, builds and lints clean):** identities, observability core (Log Analytics →
  workspace-based App Insights, daily-ingestion alert, cost cap), action group + alert rules +
  `/health` availability test, Key Vault (access policies), Azure SQL (Entra-only, firewall),
  storage, the two container apps with the full env-var contract, the `grantRequest` output.
- **Placeholders:** the four blocks marked ⚠ in `infra/modules/` carry an **assumed interface**
  until the infra team ships theirs; the three platform manifests hold placeholder names until
  the cloud team's values are pasted in (`/init-project` asks for them).
- **Not yet done anywhere:** a first real deployment (roadmap revision 2, item 6.2).

## Deploy flow

### Pipeline (all environments) — `.github/workflows/infra.yml`

1. A PR into `development` / `staging` / `main` that touches `infra/**` runs `bicep build` +
   `lint`, binds the target environment's param file, then `az deployment group what-if` for
   `dev` / `staging` / `prod` respectively and posts the result as a PR comment.
2. On merge (`infra/**` or `apps/**` changed), the `images` job builds both images and pushes them
   to the **shared registry** as `<registry>/<slug>-api|web:<sha>` (the SP holds **AcrPush**),
   then the `deploy` job runs `az deployment group create` in the GitHub Environment of the same
   name (required reviewers approve) with `apiImage`/`webImage` set to the pushed tags.
3. Authentication: repository secrets `<ENV>_AZURE_CLIENT_ID`, `<ENV>_AZURE_TENANT_ID`,
   `<ENV>_AZURE_SUBSCRIPTION_ID` + `<ENV>_AZURE_CREDENTIALS` (or a federated credential for
   OIDC) — one service principal per environment with **Contributor on that environment's
   resource group + AcrPush on the shared registry**, nothing else. The resource group and the
   registry come from the committed manifest; no other repository variables are needed.
4. `workflow_dispatch` lets a maintainer what-if (and optionally deploy, still gated) any
   environment by hand. The deployment outputs are uploaded as an artifact — they feed the
   grant request.

### Local (developers, `dev` only)

`az login` → `make infra-whatif ENV=dev` → review → `make infra-deploy ENV=dev` (refuses any
other `ENV`). Needs rights on the dev resource group. Agents run `make infra-build` only;
every `az` call an agent attempts prompts the developer, and `deployment group create` is
never an agent's.

### The first deployment is two steps

The apps pull their images with user-assigned identities that need **AcrPull** on the shared
registry first. So: deploy with `deployContainerApps = false` (identities, observability, Key
Vault, SQL, storage) → `node scripts/grant-request.mjs deployment.json --env dev` →
`infra/grant-request.md` to the cloud team (AcrPull ×2, Cognitive Services OpenAI User, the
three AI Search roles, Storage Blob Data Contributor on the project's own account) → the SQL
Entra admin creates the api identity's contained user → `deployContainerApps = true` and
deploy again. Details and the T-SQL: [`infra/README.md`](../../infra/README.md) → _The first
deployment — two steps_.

## Environment model

- `APP_ENV` (`local` | `dev` | `staging` | `prod`) drives two things everywhere: the `env`
  nibble in every `trace_id` (`local=0`, `dev=1`, `staging=2`, `prod=3`; `sandbox=4` is
  reserved/unused) and the `env` field on every structured log line. The container apps get it
  from the `environment` parameter.
- **The same code path runs locally and when deployed** — there is no separate "production
  mode" for observability. Configuration is entirely env-var driven
  (`APPLICATIONINSIGHTS_CONNECTION_STRING`, `TRACE_SAMPLING_RATIO`, `TELEMETRY_AUTH_MODE`, …);
  secrets reach the containers as Key Vault references read by the app's identity, never as
  parameter values.
- **There is no local monitoring stack and no local database.** Locally,
  `APPLICATIONINSIGHTS_CONNECTION_STRING` is either empty (degraded mode) or points at a real
  Azure resource, and `DATABASE_URL` points at the **dev Azure SQL database** (from Key Vault).
- **Degraded mode is the safe default everywhere**, not just locally: if the connection string
  is missing or init throws, a service skips remote export, prints a loud startup WARNING,
  reports `"observability": "disabled"` (with a `reason`) on `/health`, and keeps serving. This
  holds in every `APP_ENV`, including `prod` — a misconfigured or not-yet-provisioned telemetry
  backend never takes the app down. Full contract:
  [`.claude/rules/60-observability.md`](../../.claude/rules/60-observability.md) → _Fail-safe_.

## Cost guardrails

Three layers, in escalation order (parameter names in `infra/main.bicep`, values per environment
in `infra/main.<env>.bicepparam`):

1. **`TRACE_SAMPLING_RATIO`** (app env var, 0..1) — the tuning knob, reduces trace volume at the
   source before it's ever ingested. Default 1.0 (100%); invalid values warn and fall back to
   1.0.
2. **Daily billable-ingestion alert** (`dailyIngestionAlertThresholdGb`, default 5 GB/day; 10 in
   prod) — pages the action group when trailing-24h billable volume crosses the threshold.
   Investigate the cause before reaching for the next layer.
3. **Workspace daily cap** (`logAnalyticsDailyCapGb`, default `-1` = off) — the emergency brake.
   **Data-loss caveat:** once the cap is hit, ingestion stops and data is dropped for the rest of
   the day (a Resource Health event fires). Leave it off until the baseline volume is known;
   never run production against a cap you expect to actually hit.

## Ingestion hardening

Goal: only Microsoft Entra ID-authenticated senders can ingest telemetry, so a leaked connection
string alone becomes useless. **Order matters** — flipping the local-auth switch first silently
kills telemetry with no other symptom:

1. The apps run as user-assigned identities. **Monitoring Metrics Publisher** on the project's
   Application Insights component is a role assignment, which the deployment identity cannot
   create — add it to the grant request (`infra/grant-request.md`) and let the cloud team grant
   it (the role name says "metrics" but it authorizes publishing all telemetry).
2. Set `telemetryAuthMode = 'managed_identity'` in the environment's param file (the apps get
   `TELEMETRY_AUTH_MODE` and `TELEMETRY_MANAGED_IDENTITY_CLIENT_ID`) and **verify telemetry
   still flows** before proceeding.
3. Only then set `disableLocalTelemetryAuth = true` and deploy again.

**App-side guarantee:** this hardening is designed to fail **visibly, never silently** on the
app side. A mistyped `TELEMETRY_AUTH_MODE` value disables observability with the exact reason
surfaced on `/health` (`invalid TELEMETRY_AUTH_MODE …`) instead of silently falling back to
unauthenticated ingestion — implemented and unit-tested in both services.

## Post-deploy verification

**Never assume a pillar works because the code compiles or the deploy succeeded — Application
Insights fails silent, not loud.** After deploying the stack and after any change to telemetry
init, log bridges, or instrumentation:

1. Run [`runbooks/post-deploy-smoke.md`](runbooks/post-deploy-smoke.md) — fires a chain request
   plus a sampling-proof burst, then checks every signal (traces, logs, sampling, cloud role
   identity, metrics, events, DB spans, availability) against real Log Analytics data.
2. Query with [`kql-starter-pack.md`](kql-starter-pack.md) — the same numbered queries the
   smoke runbook references.
3. If a pillar comes back empty: [`runbooks/observability-degraded.md`](runbooks/observability-degraded.md)
   for the enabled-but-silent case, or
   [`runbooks/platform-log-tables.md`](runbooks/platform-log-tables.md) if the app itself never
   started and you're looking for platform-level container logs instead (the shared Container
   Apps environment ships them to the resource-specific `ContainerAppConsoleLogs` /
   `ContainerAppSystemLogs` tables — ask the cloud team which workspace).

## Availability monitoring

The `availability` module deploys **one standard availability webtest per public `/health`
endpoint** — by default the web app's public FQDN, wired automatically once
`deployContainerApps = true`. Each webtest probes over **HTTP GET**, expecting **HTTP 200**,
from five Azure locations by default, every 5 minutes, and alerts the action group when two or
more locations fail. The api has internal ingress only and is covered by the web probe through
the BFF chain.
