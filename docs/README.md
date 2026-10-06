# Team Assistant — Documentation

The documentation hub for the **Team Assistant** — the brandless starter template built by
[Orion Digital Solutions](https://www.orion360.com/) for the [Diriyah Company](https://www.diriyahcompany.sa/en/) AI team. The root [`README.md`](../README.md) is the
quick orientation (what the template is, how to run it); everything deeper lives here, organized
by what you're trying to do.

> The template ships a cross-service **foundation** (BFF + trace propagation + observability) —
> no business features, no auth. Docs describe that foundation; each AI project built on it
> extends both the platform and these docs.

## Start here

| If you want to…                             | Read                                                                                                           |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Set up and run the stack for the first time | [Getting started](getting-started.md)                                                                          |
| Understand how the system is designed       | [Architecture](architecture/README.md) — start with the living [ARCHITECTURE.md](architecture/ARCHITECTURE.md) |
| Record the project's design before planning | [Design inputs](design/README.md) — DB design, external systems, wireframes                                    |
| See what the template itself still lacks    | [Template roadmap](template-roadmap.md)                                                                        |
| Build, test, and ship a change              | [Development](development/README.md)                                                                           |
| Look up an endpoint, env var, or command    | [Reference](reference/README.md)                                                                               |
| Deploy, monitor, or handle an incident      | [Operations](operations/README.md)                                                                             |
| Review the security posture                 | [Security](security/README.md)                                                                                 |
| See why a decision was made                 | [Architecture Decision Records](adr/README.md)                                                                 |

## Sections

- **[Getting started](getting-started.md)** — prerequisites, Docker and local setup paths,
  verifying the stack, troubleshooting.
- **[`roadmaps/`](../roadmaps/README.md)** — the project's plan of record (one roadmap per
  layer, the item schema, the `/plan-roadmap` → `/implement-next` → `/start` loop).
- **[Architecture](architecture/README.md)** — the living
  [ARCHITECTURE.md](architecture/ARCHITECTURE.md) (template baseline + project layer), the
  system [overview](architecture/overview.md) with diagrams, the
  [`trace_id` contract](architecture/tracing.md), the
  [observability stack](architecture/observability.md), and the
  [data layer](architecture/data.md).
- **[Design inputs](design/README.md)** — the team-authored
  [database design](design/db-design.md), [external systems](design/external-systems.md), and
  [wireframes](design/wireframes/README.md) that planning starts from.
- **[Template roadmap](template-roadmap.md)** — the template's own backlog (what it still needs
  to carry a full AI project), with the team's locked decisions and open questions.
- **[Development](development/README.md)** — the [workflow](development/workflow.md) (CI,
  versioning, ADRs, definition of done),
  [adding a feature end-to-end](development/adding-a-feature.md),
  [testing](development/testing.md), and [coding standards](development/coding-standards.md).
- **[Reference](reference/README.md)** — the [HTTP API](reference/http-api.md),
  [environment variables](reference/environment-variables.md), and
  [commands](reference/commands.md).
- **[Operations](operations/README.md)** — [deployment](operations/deployment.md),
  [runbooks](operations/runbooks/README.md), the
  [KQL starter pack](operations/kql-starter-pack.md), and the
  [CI/CD roadmap](operations/ci-cd-roadmap.md).
- **[Security](security/README.md)** — posture overview and
  [threat models](security/threat-models/README.md).
- **[ADRs](adr/README.md)** — numbered, immutable decision records.

## Documentation that lives elsewhere (by design)

| Location                                                  | What it holds                                                               |
| --------------------------------------------------------- | --------------------------------------------------------------------------- |
| [`README.md`](../README.md) (root)                        | Quick orientation: overview, quick starts, the trace/observability contract |
| [`apps/<svc>/CLAUDE.md`](../apps/api/CLAUDE.md)           | Per-service layout, conventions, commands, gotchas                          |
| [`infra/README.md`](../infra/README.md)                   | Bicep observability/alerting stack — deploy procedure and hardening         |
| [`OBSERVABILITY-ROADMAP.md`](../OBSERVABILITY-ROADMAP.md) | Observability acceptance-criteria record and remaining proofs               |
| [`.claude/rules/`](../.claude/rules/)                     | Path-scoped working conventions (also useful reading for humans)            |

## Conventions for writing docs

- Docs live in the section that matches their purpose: tutorials/onboarding →
  `getting-started.md`, explanations → `architecture/`, how-to guides → `development/`,
  lookup material → `reference/`, procedures/incidents → `operations/`, decisions → `adr/`.
- If a doc disagrees with the code, **the code wins** — fix the doc in the same change.
- Any change to architecture, commands, env vars, ports, the HTTP surface, or the
  trace/observability contract updates the affected docs **in the same task**.
- Keep relative links working from each file's location; prettier formats all Markdown
  (`make fmt`).
