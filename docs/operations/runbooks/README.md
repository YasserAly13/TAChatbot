# Runbooks

Reusable incident-response playbooks, captured from postmortems by the `runbook-writer`
skill and consulted live by the `incident-responder` agent.

- One file per failure mode, kebab-case slug (accessed by name during an incident, not number).
- Each has: what it looks like (symptom + signal + a Log Analytics KQL query), triage,
  mitigate, verify-recovery, root-cause patterns.
- No credentials, PII, or "ping <person>" steps — a runbook must work without a specific human.

| Runbook                                             | Symptom                                                                                     | Last updated |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------- | ------------ |
| [observability-degraded](observability-degraded.md) | `/health` → `"observability": "disabled"`, or telemetry missing despite `enabled`           | 2026-07-26   |
| [post-deploy-smoke](post-deploy-smoke.md)           | (procedure, not incident) — prove every telemetry pillar after a deploy / telemetry change  | 2026-07-26   |
| [pii-purge](pii-purge.md)                           | PII or a secret leaked into an exported log line (slipped past redaction-at-source)         | 2026-07-25   |
| [platform-log-tables](platform-log-tables.md)       | container stdout/platform logs not found in Log Analytics; choosing the ACA log destination | 2026-07-26   |
