# `infra/platform/` — the shared tier, as the cloud team describes it

One manifest per environment (`dev.json`, `staging.json`, `prod.json`), validated by
[`platform.schema.json`](platform.schema.json). It names the resources that **already exist**
and are **shared by every use case** built on this template (ADR-0012, decision D4′):

| Key                        | What it is                                                                    | Consumed by                                                          |
| -------------------------- | ----------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| `resourceGroup`            | the environment's resource group where this use case's **owned** resources go | `infra.yml`, `make infra-whatif/deploy`                              |
| `containerAppsEnvironment` | the shared Container Apps Environment the container apps are created in       | `main.bicep` (`existing`)                                            |
| `containerRegistry`        | the shared registry images are pushed to and pulled from                      | `infra.yml` (`az acr login`), `main.bicep` (registry + image names)  |
| `aiFoundry`                | the shared Foundry account, its endpoint and the deployment names to use      | `main.bicep` → `AZURE_AI_*` on the api                               |
| `aiSearch`                 | the shared search service; each use case owns **one index** on it             | `main.bicep` → `AZURE_SEARCH_ENDPOINT`; index name is the use case's |

## Rules

- **The cloud team owns the values.** When they change a shared resource, they send a new
  manifest; replace the file, open a PR, read the `what-if`.
- **Never put anything secret here** — names, endpoints and IDs only. The files are committed.
- **Nothing in `main.bicep` creates or changes these resources** — they are referenced with
  `existing`. Roles a use case needs on them are requested, not assigned
  (`infra/grant-request.md`).
- The committed files in a fresh template are **placeholders** (`00000000-…` subscription,
  `rg-ai-<env>`, `cae-ai-<env>`, …). `/init-project` asks you to paste the real ones; until then
  `bicep build` works but `what-if`/deploy cannot.

## Getting the values (cloud team)

```bash
az containerapp env show -g <rg> -n <cae> --query "{name:name, rg:resourceGroup}"
az acr show -g <rg> -n <acr> --query "{name:name, loginServer:loginServer}"
az cognitiveservices account show -g <rg> -n <foundry> --query "{name:name, endpoint:properties.endpoint}"
az cognitiveservices account deployment list -g <rg> -n <foundry> --query "[].name"
az search service show -g <rg> -n <search> --query name     # endpoint = https://<name>.search.windows.net
```
