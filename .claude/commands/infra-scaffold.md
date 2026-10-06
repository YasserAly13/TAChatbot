---
description: Add/change a resource this use case OWNS in the Bicep stack — call a vendored block in infra/main.bicep, parameters in all three main.<env>.bicepparam, env wiring, bicep build + lint, docs. Never a platform-tier resource or a role assignment (→ infra/grant-request.md). Deploy is the pipeline's or a human's step.
argument-hint: <resource or change, e.g. "storage container for exports">
---

Use the `infra-scaffold` skill for: `$ARGUMENTS`.

Classify first: platform tier (Foundry, Container Apps Environment, registry, AI Search service) → write the cloud-team request and stop. Otherwise: verify properties against the ARM reference, call a block from `infra/modules/` (never edit one), keep the three `.bicepparam` files in parity, add any needed role to the `grantRequest` output, run `make infra-build`. End with build/lint results, the `what-if` summary if the developer asked for it, the grant request if any, and the human deploy step. Never `az deployment group create`.
