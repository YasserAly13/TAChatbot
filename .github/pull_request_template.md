<!-- Title: Conventional Commit subject, e.g. `feat(api): conversation threads` -->

## Roadmap item

`<layer> <id>` — <title> (`roadmaps/<layer>/ROADMAP.md`)

## What changed

<!-- 2–5 bullets: behaviour, not files. Link the ADR if a decision was made. -->

## How to test

<!-- Copy the item's `how_to_test` — exact commands + expected results a reviewer can run. -->

## Definition of Done (root `CLAUDE.md`)

- [ ] Tests written (happy + error paths) and green — `make test` (or: `tests-not-needed` label with a reason below)
- [ ] Docs updated in this PR: README / per-app `CLAUDE.md` / `.env.example`s / `docs/reference/*` / ADR (if a decision) / `ARCHITECTURE.md` Part B proposal (if the architecture changed)
- [ ] API contract regenerated if the `/v1` surface changed — `make openapi` (CI fails otherwise)
- [ ] Changelog entry + SemVer bump for the touched service(s)
- [ ] Trace/observability contract holds on every touched request path (`x-trace-id`, structured logs, bounded metrics; AI calls inside `model_call_span()`, content-free)
- [ ] No secrets, no `TrustServerCertificate=yes`, no writes through the external engine, no free-form SQL without `AI_ALLOW_TEXT_TO_SQL` + a threat model
- [ ] Infra: the three `main.<env>.bicepparam` in parity; `bicep build` + `lint` clean; `what-if` reviewed; the deploy is a human/pipeline step listed below; no platform-tier resource authored; cross-tier roles added to `infra/grant-request.md`
- [ ] `/code-review` run; `/security-review` run if the BFF boundary, env, external HTTP, DB layer, an AI tool or the Bicep changed
- [ ] `make fmt` clean; temp files and debug logging removed

## Needs a human

<!-- Bicep deploy, cloud-team role grant, migrate.yml run, Key Vault secret, firewall IP, model deployment, ingestion run — or "nothing". -->

🤖 Generated with [Claude Code](https://claude.com/claude-code)
