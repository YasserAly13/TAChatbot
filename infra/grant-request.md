# Role grant request — `<env>` (not generated yet)

> This file is **generated** by `node scripts/grant-request.mjs <deployment.json> --env <env>` from
> the outputs of the first deployment (`grantRequest`). It lists the roles this use case's managed
> identities need on **shared, cloud-team-owned** resources (ADR-0012, D11) — AcrPull on the
> registry, Cognitive Services OpenAI User on Foundry, the three Search roles on the AI Search
> service — plus Storage Blob Data Contributor on the use case's own storage account (the
> deployment identity cannot assign roles). The cloud team grants; nothing here is a secret.

Steps:

1. `make infra-deploy ENV=dev` with `deployContainerApps = false` (or let the pipeline do it).
2. `az deployment group show -g <rg> -n <deployment-name> --output json > deployment.json`
   (or download the `deployment-<env>-<sha>` artifact from the Infrastructure workflow).
3. `node scripts/grant-request.mjs deployment.json --env dev` → this file is rewritten.
4. Send it to the cloud team; when granted, set `deployContainerApps = true` and deploy again.
