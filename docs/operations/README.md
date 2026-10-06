# Operations

This section is for people running or debugging the **Team Assistant** day to day — deploying
the infrastructure that exists, verifying telemetry after a change, and triaging incidents.
"Operating this platform" today means **observability first**: the only infrastructure that is
actually deployed is the Log Analytics / Application Insights / alerting stack in
[`infra/`](../../infra/README.md), deployed by the maintainer (`az` is intentionally denied to
agents). App hosting (Container Apps), the database, Key Vault, and networking are still
**planned** — see [`deployment.md`](deployment.md) for the full implemented-vs-planned split.
Until hosting lands, "operations" mostly means: keep telemetry healthy, know how to read it,
and know what to do when a signal goes quiet.

## In this section

| Document                                     | Covers                                                                                                                                                                                 |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [`deployment.md`](deployment.md)             | Deployment posture: what's implemented vs. planned, the deploy flow, environment model, cost guardrails, ingestion hardening order, post-deploy verification, availability monitoring. |
| [`kql-starter-pack.md`](kql-starter-pack.md) | Copy-paste Log Analytics / Kusto queries for this template's telemetry — trace-by-id, request+logs join, error rate, dependency latency, ingestion volume, custom metrics/events.      |
| [`ci-cd-roadmap.md`](ci-cd-roadmap.md)       | Deferred CI/CD hardening tasks (branch-governance backlog) — what's intentionally not implemented yet, and why.                                                                        |
| [`runbooks/`](runbooks/README.md)            | Reusable incident-response playbooks, one file per failure mode.                                                                                                                       |

### Runbooks at a glance

Full detail (symptom, signal, triage, mitigate, verify) is in
[`runbooks/README.md`](runbooks/README.md); the index:

| Runbook                                                      | Symptom                                                                                     |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------- |
| [observability-degraded](runbooks/observability-degraded.md) | `/health` → `"observability": "disabled"`, or telemetry missing despite `enabled`           |
| [post-deploy-smoke](runbooks/post-deploy-smoke.md)           | (procedure, not incident) — prove every telemetry pillar after a deploy / telemetry change  |
| [pii-purge](runbooks/pii-purge.md)                           | PII or a secret leaked into an exported log line (slipped past redaction-at-source)         |
| [platform-log-tables](runbooks/platform-log-tables.md)       | container stdout/platform logs not found in Log Analytics; choosing the ACA log destination |

## Where to start

- **Something looks broken with telemetry right now:** start at
  [`runbooks/observability-degraded.md`](runbooks/observability-degraded.md) — it triages every
  `/health` `reason` string, plus the enabled-but-silent case.
- **You just deployed, or changed anything touching telemetry init/bridges/instrumentation:**
  run [`runbooks/post-deploy-smoke.md`](runbooks/post-deploy-smoke.md) — App Insights fails
  silent, never assume a pillar works because the code compiles.
- **You want the current state of the observability build-out** (what's done, what's still
  `[HUMAN]`-pending, what's gated on auth): the root
  [`OBSERVABILITY-ROADMAP.md`](../../OBSERVABILITY-ROADMAP.md) is the acceptance-criteria
  record for the whole implemented surface.
