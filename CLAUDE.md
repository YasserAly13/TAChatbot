# CLAUDE.md — Team Assistant

Project-wide constitution for Claude. Follow the rules below on every task unless I explicitly
override them. This file is the **map**, not the manual: load the deeper docs (per-app
`CLAUDE.md`, `README.md`, `.claude/rules/`, `docs/`) **on demand** — don't bloat this file or
assume it's the only source of truth.

**What it is:** **Team Assistant** (slug `team-assistant`, npm scope `@team-assistant/*`) — an
internal chat assistant that answers the team's questions from its own documentation
(`docs/**/*.md`, indexed in Azure AI Search) with citations, and keeps conversation history in
Azure SQL. Internal-only, no user auth (Okta later). Built on the **AI Accelerator** — the
starter monorepo the **Diriyah Company AI team** uses for its AI projects, built and maintained
by **Orion Digital Solutions** for the Diriyah Company. **Infrastructure:** `dev` only, every Azure
resource is **pre-provisioned** (Foundry, AI Search, Azure SQL — names in
[`ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) → B1) and this project **deploys no
infrastructure in any environment**; the template's Bicep tier (ADR-0012, `infra/`) is kept but
not used. The repo is a polyglot
monorepo of two independent services — `apps/web` (Next.js BFF + UI) and `apps/api`
(FastAPI, the **sole backend** — ADR-0003) — wired with **end-to-end `trace_id` propagation**
and **Azure Monitor / OpenTelemetry** observability in both. The browser only talks to the `web`
BFF, which calls `api` server-side; the chain `web → api` carries one `x-trace-id`
unchanged. **SQLAlchemy 2 async + Alembic** on **Azure SQL Database** via `mssql+aioodbc`
(ADR-0008; models `Conversation`/`Message`, revision `7c1d4e2a9b30`, lazy engine, migrations
applied by a named human only — ADR-0013, **never a local database**) plus an
optional **read-only** second engine for an external database. Business features so far:
`/v1/conversations` create + list (api; progress in `roadmaps/`); no auth. The living architecture is
[`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md); the template's own
backlog is [`docs/template-roadmap.md`](docs/template-roadmap.md).

> **⚖️ Graded autonomy (governs this entire `.claude/` setup):** approval is given at the level
> of a **plan or roadmap item**, not at every step. Once the user approves an item (or says "go"
> to a plan), implement it **end-to-end** — code, tests, docs, observability, changelog/version —
> invoking whatever agents/skills it needs **without re-asking**, then report what was done and
> how to test it. Invoked **ad hoc** (no approved item), an agent/skill states what it will touch
> and waits for a "yes". **Hard stops — always ask, every time, whatever was approved:** applying
> infrastructure (`az deployment group create`, any delete), applying migrations to any database, `git push` /
> commits / merges, reading or writing real secrets, deleting files or data, deployments, and
> anything outside the approved item's scope. Auto-_loading_ context (the path-scoped
> `.claude/rules/`, the per-app `CLAUDE.md`) is always fine.

## Stack at a glance

| Concern            | Choice                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Recorded in                                                   |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| Monorepo           | Independent packages — **no pnpm workspace, no Turborepo**; per-app lockfiles & Dockerfiles                                                                                                                                                                                                                                                                                                                                                                                                                 | `.claude/rules/00-architecture.md`                            |
| `apps/web`         | Next.js **16.2.6** App Router, **BFF** (:3000, origin `0eb0`); Tailwind v4 + chat components, SSE pass-through, `MOCK_UPSTREAM` fixtures typed from the OpenAPI contract, RTL component tests (ADR-0010/0011)                                                                                                                                                                                                                                                                                               | `apps/web/CLAUDE.md`, `.claude/rules/30-nextjs.md`            |
| `apps/api`         | Python **3.14** + FastAPI, **uv** (:8000, origin `0c70`) — the sole backend                                                                                                                                                                                                                                                                                                                                                                                                                                 | `apps/api/CLAUDE.md`, `.claude/rules/35-fastapi.md`           |
| ORM / DB           | SQLAlchemy **2.0.54** async + aioodbc **0.5** / pyodbc **5.3** (ODBC Driver 18) + Alembic **1.20** → **Azure SQL Database**, **never local** (no container; DB created by the use-case Bicep deployment; no migrations run; `migrate.yml` applies). Optional read-only external engine (`EXTERNAL_DATABASE_URL`). Origin `0a71` of the former NestJS api stays retired — ADR-0005                                                                                                                           | `.claude/rules/25-sqlalchemy.md`, ADR-0008, `README.md`       |
| Runtime / pkg mgrs | Node **24**, pnpm **11.5.2** (web), uv (api), TypeScript **5.9**                                                                                                                                                                                                                                                                                                                                                                                                                                            | `.nvmrc`, each `package.json`/`pyproject.toml`                |
| Tracing            | `x-trace-id` = origin(4)+env(1)+random(27); ALS (Node) / contextvars (Python)                                                                                                                                                                                                                                                                                                                                                                                                                               | `.claude/rules/60-observability.md`, `README.md`              |
| Observability      | OTel → Azure Monitor; pino (Node) / structlog (Python); **fail-safe degraded mode**                                                                                                                                                                                                                                                                                                                                                                                                                         | `.claude/rules/60-observability.md`                           |
| Tooling            | `Makefile` + `justfile` (parity); prettier + ruff (`make fmt`); `docker-compose.yml`                                                                                                                                                                                                                                                                                                                                                                                                                        | `README.md`                                                   |
| Infra              | **Bicep, two tiers (ADR-0012):** platform tier pre-exists per env and is shared (Foundry + deployments, Container Apps Environment, Container Registry, AI Search service — described by `infra/platform/<env>.json`); the use-case tier is `infra/main.bicep` + `main.<env>.bicepparam` composed from the infra team's **vendored** blocks in `infra/modules/`; GitHub deploys every env (`what-if` on PR), developers deploy `dev` locally; cross-tier roles are **requested** (`infra/grant-request.md`) | `infra/README.md`, `docs/template-roadmap-bicep.md`           |
| AI runtime         | `apps/api/app/ai/`: LangChain + LangGraph on **Azure AI Foundry** (managed identity), **Azure AI Search** retrieval, allow-listed read-only DB tool, content-free `gen_ai` telemetry, SSE streaming, ingestion job — no use case shipped                                                                                                                                                                                                                                                                    | `.claude/rules/70-ai.md`, ADR-0009, `docs/architecture/ai.md` |
| Tests              | Vitest (web; Playwright manual) · pytest (api; DB + AI tests offline, `tests/evals/` prompt harness) — `make test`                                                                                                                                                                                                                                                                                                                                                                                          | `.claude/rules/40-testing.md`                                 |

## Where deeper context lives (load on demand)

- **`docs/architecture/ARCHITECTURE.md`** — the living architecture: **Part A** template baseline (template-owned, never edited in a project), **Part B** project architecture (team-maintained; read it before planning, only _propose_ edits — ADR-0006).
- **`docs/design/`** — the team's design inputs (DB design, external systems, wireframes); planning never invents what is missing here — it asks.
- **`roadmaps/`** — **the plan of record** (`roadmaps/README.md` = the item schema; `roadmaps/<api|web|infra>/ROADMAP.md` = the items). State lives here, not in chat: `/start` reads it, `/plan-roadmap` writes it, `/implement-next` executes one item and stops at `awaiting-test`.
- **`docs/template-roadmap.md`** — the template's own backlog and the team's locked decisions (D1–D8).
- **`apps/<svc>/CLAUDE.md`** — per-service layout, conventions, commands, gotchas (auto-loads in that app).
- **`README.md`** — full architecture, run instructions, the trace_id schema, observability, the SQLAlchemy + Alembic database section, env reference.
- **`.claude/rules/*.md`** — path-scoped conventions that auto-load when you edit matching files.
- **`docs/README.md`** — the documentation hub (getting-started · architecture · development · reference · operations · security), for humans; start there for any deep-dive doc.
- **`docs/adr/`** — architecture decisions · **`docs/security/threat-models/`** · **`docs/operations/runbooks/`**.

These orient you fast; they are **not** the one-and-only place — read/search the actual code when you need detail, and if a doc disagrees with the code, the **code wins** (then fix the doc, rule 14).

## The `.claude/` toolkit

**Agents** (`.claude/agents/`, invoke by name or via a command):
`code-reviewer` (diff review before a PR) · `security-reviewer` (OWASP + BFF/secrets/HTTP/SQLAlchemy/CORS/containers) · `test-writer` (writes tests; Vitest / pytest) · `migration-author` (Alembic revisions; autogenerate needs a real DB, never applies) · `observability-instrumenter` (trace_id + logs + spans) · `adr-writer` (decision → ADR) · `dependency-updater` (safe per-package bumps) · `threat-modeler` (design-time STRIDE) · `incident-responder` (live triage from Azure Monitor signals).

**Workflow skills** (the day-to-day loop, in order): `setup-dev-env` (fresh machine → every required tool checked via `scripts/doctor.sh`, installed via winget/brew/apt on a "yes", with numbered manual steps when an install fails) · `init-project` (fresh clone → named project, landing zone, roadmaps; supersedes `rename-project` alone) · `architecture-review` (Part B + design vs the baseline; proposes, never rewrites) · `plan-roadmap <layer>` (writes `roadmaps/<layer>/ROADMAP.md`) · `implement-next <layer> [id]` (one item end-to-end → `awaiting-test`, "How to test", "Needs a human") · `start` (session briefing) · `git-flow` (branch/commit/PR; push needs a yes) · `infra-scaffold` (a use-case-tier Bicep change, build/lint only).

**Skills** (`.claude/skills/`, auto-discovered): `rename-project` · `feature-scaffold` (targets `web` · `api` · `ai` · `rag`) · `security-review` · `write-adr` · `write-migration` · `lsp-refactor` · `docs-lookup` (verify library APIs via live docs — a hard preference) · `release-notes-writer` · `runbook-writer` · `db-introspector`.

**Commands** (`.claude/commands/`): `/setup-dev-env` · `/init-project` · `/start` · `/architecture-review` · `/plan-roadmap` · `/implement-next` · `/git-flow` · `/infra-scaffold` · `/rename-project` · `/scaffold-feature` · `/code-review` · `/security-review` · `/write-adr` · `/write-migration` · `/observability`.

---

## Rules

1. **Ask, don't assume.** If a request is ambiguous, underspecified, or has >1 reasonable reading, stop and ask before acting. Better one more question than the wrong deliverable.
2. **Docs in the same task.** Any new/changed feature, command, route, config, or env var updates the docs that describe it (README, `.env.example`, per-app `CLAUDE.md`, inline comments). No "docs later."
3. **Tests in the same task.** New/changed logic gets tests covering happy + error paths, in the configured stacks (Vitest · pytest). Run them (`make test`), show results; never report done with unrun/failing tests. Introducing a _new_ framework or major test-infra change still needs an ADR + confirmation.
4. **Parallelize with subagents** when work splits into genuinely independent units; don't parallelize tightly coupled or trivial steps.
5. **Plan before non-trivial work.** Lay out scope, files, and approach; get approval before implementing.
6. **Confirm destructive/irreversible actions** (delete, DB drop/migrate, force-push, history rewrite, prod deploy) — explain why it's irreversible first.
7. **Read before editing.** Understand how a thing is used before changing it; never edit blind.
8. **Never fabricate** paths, APIs, results, or library behavior. Verify (use `docs-lookup`) or say you're unsure.
9. **Report honestly.** Broken/untested/uncertain → say so plainly. Never hide errors.
10. **Justify non-obvious changes** with the file/line, doc, or requirement behind them.
11. **Stop after ~2–3 failed attempts** at the same approach; summarize and ask.
12. **Clean up** temp files, scratch scripts, and debug logging before finishing.
13. **Changelog** user-facing changes (per-service `CHANGELOG.md`, if present), following its format.
14. **Keep orientation/context files in sync.** The Repo map (this file), per-app `CLAUDE.md`, `README.md`, `.env.example`s, and `docs/` are the **initial source of truth** — but **not the only place** (it's normal to read/search the code; if a doc disagrees with the code, the code wins — then fix the doc). Any change to architecture / layout / commands / env / ports / the trace-observability contract / the HTTP surface updates the affected file(s) in the same task.
15. **Versioning — SemVer, per service.** `apps/web` and `apps/api` version independently (both currently `0.0.0` — pre-release, no features shipped yet); the root is the tooling wrapper, not a release unit. Bump from the **consumer's** perspective: MAJOR = breaking (removed/renamed endpoint/field, changed shape, broken trace/observability contract); MINOR = backward-compatible feature; PATCH = fix. Ask if unsure.

## Definition of Done

A change is done only when: ambiguities were clarified up front (1); docs + orientation files are updated (2, 14); tests are written and passing — or their absence is explicitly justified (3); the affected service's version (and changelog, if present) is bumped (13, 15); the plan was approved (5); the trace/observability contract still holds for any touched request path (`.claude/rules/60`); and cleanup is done (12). Run `/code-review` (and `/security-review` if it touches the BFF boundary, env, external HTTP, or the SQLAlchemy/Alembic layer) before opening a PR.

## What you cannot do — ask the human

These touch the environment, credentials, or infra. Stop and ask; do not attempt them yourself:

- **Cloud/infra:** you may author the use-case Bicep (`infra/main.bicep`, `main.<env>.bicepparam`) and run `bicep build` / `lint` / `format` (allowed in `.claude/settings.json`); you never deploy — `az deployment group create` is the GitHub pipeline's job (every environment) or a developer's, locally, for `dev` only. **Every `az` command prompts the developer and is approved for that one call**; deletes and purges are denied. Never author a platform-tier resource (Foundry, Container Apps Environment, registry, AI Search service) and never assign a role on one — append the need to `infra/grant-request.md`. Never edit the vendored blocks under `infra/modules/`.
- **Secrets:** setting, reading, or rotating real connection strings / API keys / SP credentials. Only ever edit `.env.example` placeholders, `infra/main.<env>.bicepparam` (names, never values) and `infra/platform/<env>.json` (the cloud team's names).
- **Database:** **there is no local database — ever.** Databases are Azure SQL, created by infrastructure before any model work. Running migrations against any database (`alembic upgrade` / `downgrade` without `--sql`) or any destructive DDL — `migration-author` autogenerates against the **dev** database and reviews offline SQL; applying is the migration pipeline or a named human, with explicit confirmation.
- **Git/release:** `git push`, force-push, or history rewrite (denied); commits, checkouts, merges, package publishes, and image pushes (ask first).
- **Stack changes:** introducing a new framework (e.g. a test runner), a major dependency bump, or **adding auth** (the planned module is **Okta**) — confirm first; auth also needs a threat model + ADR.
- **The architecture baseline:** `docs/architecture/ARCHITECTURE.md` Part A is template-owned; Part B is the team's — propose changes, never rewrite it silently.
