# Development workflow

How a change moves from an idea to merged code: the repo model that shapes every command you
run, the lifecycle of a change, what CI actually does, how versions are bumped, and when a
decision needs an ADR.

---

## The independent-packages model

The repo is a **polyglot monorepo of two independent packages** — `apps/web` (Next.js BFF +
UI) and `apps/api` (FastAPI + SQLAlchemy 2 async + Alembic). There is **no pnpm workspace
and no Turborepo**. Each app has its own lockfile, its own `Dockerfile`, and its own version, so
`docker build apps/<svc>` is individually buildable and reproducible.

That single decision has consequences you hit daily:

| Consequence                        | What it means in practice                                                                                                                                                          |
| ---------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **No workspace filters**           | `pnpm -C apps/web test` — **never** `pnpm --filter`. Filters do not resolve without a workspace.                                                                                   |
| **Per-app installs**               | `make install` runs `pnpm install` at the root (tooling only), then `pnpm -C apps/web install` and `uv sync --directory apps/api`.                                                 |
| **Per-app lockfiles**              | A dependency bump touches exactly one app's `pnpm-lock.yaml` / `uv.lock`. Never hand-merge them.                                                                                   |
| **No shared code package**         | Services communicate over HTTP only. The tracing/logging/observability modules are deliberately duplicated per service. Introducing a shared package needs an [ADR](#adr-process). |
| **Root is tooling, not a service** | The root `package.json` holds `concurrently` + `prettier` and the `dev`/`build`/`fmt` scripts. It is not a release unit.                                                           |

The task runner exists in two parity implementations — [`Makefile`](../../Makefile) (POSIX,
what CI-style shells use) and [`justfile`](../../justfile) (recommended on Windows; runs
recipes through PowerShell). Same target names in both: `install`, `dev`, `test`, `test-cov`,
`build`, `up`, `down`, `logs`, `clean`, `fmt`. Database migrations deliberately have **no**
target — the Alembic commands are run explicitly (`uv run --directory apps/api alembic …`,
see [reference → commands](../reference/commands.md)).

---

## The change lifecycle

### 1. Clarify before you build

If a request is ambiguous, underspecified, or has more than one reasonable reading, ask before
writing code. One extra question beats the wrong deliverable. This is the first rule in the
project constitution ([`CLAUDE.md`](../../CLAUDE.md)) and it applies to human contributors
just as much.

### 2. Plan non-trivial work

For anything beyond a small fix, lay out scope, the files you will touch, and the approach —
and get agreement before implementing. Cross-service changes especially: a new endpoint that
spans `web → api` touches both packages, both test suites, and possibly several
`.env.example` files; one that adds a model also touches `app/models/` and needs an Alembic
revision.

If the change adopts a tool, introduces a pattern, changes a cross-service contract, or
accepts a significant trade-off, the plan step is also where you decide it needs an
[ADR](#adr-process).

### 3. Implement — with docs and tests in the _same_ change

Three things ship together or the change is not done:

- **Code.** Following [coding standards](coding-standards.md): structured logging only,
  traced HTTP wrappers only, `/v1` on every business endpoint.
- **Tests.** Happy path **and** error/edge paths, in the configured stack for that service.
  Run them; never hand over a change with unrun or failing tests. See
  [testing](testing.md).
- **Docs.** Any new or changed feature, command, route, config, or env var updates whatever
  describes it — the root [`README.md`](../../README.md), the relevant `.env.example`, the
  per-app docs, these development docs, inline comments. There is no "docs later."

New logic must also keep the trace/observability contract intact on every request path it
touches: a `trace_id` on every request, propagated on every outbound call, echoed on every
response, and structured logs throughout
([`.claude/rules/60-observability.md`](../../.claude/rules/60-observability.md)).

### 4. Review

Review your own diff first, then open the PR. Two things worth running before you do:

- a **code review** pass against the constitution, the path-scoped rules, and the ADRs;
- a **security review** pass if the change touches the BFF boundary, environment variables,
  external HTTP, or the database layer (`app/db/`, `app/models/`, `alembic/`)
  ([`.claude/rules/50-security.md`](../../.claude/rules/50-security.md)).

The repo ships tooling for both (`/code-review`, `/security-review`, and the corresponding
agents under [`.claude/`](../../.claude/)) — useful, but the checklists behind them are the
point, and they work equally well read by a human.

### 5. Confirm anything destructive

Deleting data, dropping or migrating a database, force-pushing, rewriting history, deploying
to production — explain why it is irreversible and get explicit confirmation first. Migrations
against a real database are always a deliberate, confirmed step, never an automatic one —
`alembic upgrade` is run by a human, after reviewing the offline `--sql` output
([`.claude/rules/25-sqlalchemy.md`](../../.claude/rules/25-sqlalchemy.md)).

---

## Definition of done

A change is done when **all** of these hold:

- [ ] Ambiguities were clarified up front, and the plan was agreed for non-trivial work.
- [ ] Code follows the [coding standards](coding-standards.md) — no `console.log` / `print()`,
      no bare `fetch`/`httpx`, every business endpoint under `/v1`.
- [ ] Tests exist for the new/changed logic (happy + error paths), they run, and they pass —
      or their absence is explicitly justified.
- [ ] Docs and orientation files are updated in the same change: `README.md`, the relevant
      `.env.example`, per-app docs, `docs/`.
- [ ] The trace/observability contract still holds on every request path the change touches.
- [ ] The affected service's version is bumped per [SemVer](#versioning), and its
      `CHANGELOG.md` updated if one exists.
- [ ] Temporary files, scratch scripts, and debug logging are removed.
- [ ] Code review done; security review done if the change touches the BFF boundary, env,
      external HTTP, or the database layer.

---

## CI

The pipeline is [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml).

**Triggers:** pushes to `main`, `staging`, `development`; pull requests targeting those same
three branches; and `release: created`. Runs are grouped per PR/ref with
`cancel-in-progress: true`, so pushing again cancels the superseded run.

### Job 1 — `promotion-guard` (PRs only)

Enforces the promotion path that GitHub branch rulesets cannot express (rulesets gate the
_target_ branch, not the _source_):

- a PR into **`main`** must come from **`staging`**;
- a PR into **`staging`** must come from **`development`**;
- PRs into **`development`** are unconstrained — any feature branch.

A violation fails the job with an explicit error. For this to actually block a merge, it must
be configured as a **required status check** on `staging` and `main`.

### Job 2 — `test` — "Tests + coverage"

Runs on `ubuntu-latest`. It checks out the repo, sets up **Node 24** and runs `corepack
enable`, runs the web suite, then sets up **Python 3.14** and runs the api suite — each
with coverage:

| Step         | Working directory | Commands                                                                                   |
| ------------ | ----------------- | ------------------------------------------------------------------------------------------ |
| Web tests    | `apps/web`        | `pnpm install --frozen-lockfile` → `pnpm test:cov`                                         |
| Python tests | `apps/api`        | `pip install uv==0.10.9` → `uv sync --frozen` → `uv run pytest --cov=app --cov-report=xml` |

Notes that matter:

- **No database is needed** for the api suite — the SQLAlchemy engine is lazy and the DB
  tests assert nothing ever connects.
- The Python step sets `UV_PYTHON_DOWNLOADS: never`, so it uses the Python provided by
  `setup-python` rather than downloading one.
- **Playwright e2e is deliberately not run here** — it is manual/local only (see below).
- Both reports are uploaded as **one** artifact named `coverage-reports`
  (`apps/web/coverage/lcov.info`, `apps/api/coverage.xml`),
  preceded by a `touch .artifact-root` step. That empty anchor file forces
  `upload-artifact`'s least-common-ancestor to the repo root; without it the shared `apps/`
  prefix is stripped and the two reports land unnamed side by side. The artifact is for
  humans (download it from the run) — no external code-quality service consumes it.

Locally, `make test-cov` runs the same two coverage commands (`pnpm -C apps/web test:cov`,
`uv run --directory apps/api pytest --cov=app --cov-report=xml`).

### No code-quality orchestrator

The workflow has exactly the two jobs above. There is **no external code-quality scan, no
Dockerfile-analysis job and no release automation** wired up; adding any of them is an
explicit, ADR-level decision (the org-level reusable CI workflow was removed on 2026-09-20).

### The run model

Run tests **locally for fast feedback**; **CI is the gate**. Every suite runs with coverage on
every PR; a red suite blocks the merge, and the coverage reports are attached to the run.

### Playwright is not in CI

`apps/web` has a Playwright smoke suite (`apps/web/e2e/`), configured explicitly as
**manual/local only** ([`apps/web/playwright.config.ts`](../../apps/web/playwright.config.ts)).
It needs the whole stack running. Run it before a release:

```bash
make up                       # or make dev
pnpm -C apps/web test:e2e
```

### Deferred CI hardening

Several CI improvements were discussed and intentionally deferred — per-service path filters,
least-privilege per-job permissions, Dependabot, signed commits, GitHub Environments, and
others. They are tracked, with rationale and acceptance criteria, in
[`docs/operations/ci-cd-roadmap.md`](../operations/ci-cd-roadmap.md). Check that file before
proposing a CI change; the reason something is missing is usually written down.

---

## Versioning

**SemVer, per service, independently.** `apps/web` and `apps/api` each carry their own
version and move on their own schedule. Both are at `0.0.0` today — pre-release, no features
shipped. The **root `package.json` is the tooling wrapper, not a release unit**;
its version does not track anything.

Bump from the **consumer's** perspective — what does this change do to someone calling this
service?

| Bump      | When                                                                                                                               |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **MAJOR** | Breaking for a consumer: an endpoint or field removed or renamed, a changed response shape, a broken trace/observability contract. |
| **MINOR** | A backward-compatible feature: a new endpoint, a new optional field, new behaviour that does not disturb existing callers.         |
| **PATCH** | A fix that changes no contract.                                                                                                    |

Where the version lives:

- `apps/web/package.json` — the `version` field.
- `apps/api/pyproject.toml` — `[project] version`. It is also surfaced at runtime by
  `/info` in each service.

Related: a **new API version** (`/v2`) is a different mechanism from a package version bump.
Adding `/v2` alongside `/v1` is additive at the URL level; see
[`.claude/rules/05-api-versioning.md`](../../.claude/rules/05-api-versioning.md) and
[ADR-0001](../adr/0001-api-versioning.md).

If a service has a `CHANGELOG.md`, add an entry for user-facing changes following that file's
existing format. If you are unsure whether something is MAJOR or MINOR, ask — getting it wrong
is worse than asking.

---

## ADR process

Architecture Decision Records live in [`docs/adr/`](../adr/README.md). They are numbered,
immutable records of stack- and architecture-affecting decisions — the team's memory. Without
them the same debates recur every six months.

### When a decision needs an ADR

Write one when you **adopt, remove, or change** a tool, pattern, or standard. Concretely, in
this repo:

- adopting or removing a tool (including a **new test framework** or a major test-infra change);
- introducing a **shared package** between services;
- changing the **trace/observability contract**;
- changing the **API-versioning scheme** (ADR-0001), including adding an endpoint to the
  `/ping` · `/info` · `/health` unversioned exemption;
- adding **auth** — which additionally needs a threat model in
  [`docs/security/threat-models/`](../security/threat-models/) before implementation;
- any other cross-service contract change;
- an explicitly accepted significant trade-off.

**Do not** write one for a bug fix, a refactor, or a style preference.

### How to write one

1. Copy [`docs/adr/0000-template.md`](../adr/0000-template.md).
2. Number it with the next zero-padded 4-digit number (`0006-…`), and give it a short
   noun-phrase title. The current highest is
   [ADR-0005](../adr/0005-name-services-by-role.md).
3. Fill in **Context** (3–6 sentences on the forces and constraints), **Decision** (1–3
   sentences, active voice, present tense — "We use X because Y"), **Consequences** (good and
   bad), **Alternatives considered** (the most valuable section — it stops the debate from
   restarting), and **References**.
4. Add a row to the table in [`docs/adr/README.md`](../adr/README.md), newest last.
5. Set `Status` (`Proposed` → `Accepted`) and the date.

**Never delete an ADR.** Supersede it: mark the old one `Deprecated` or
`Superseded by ADR-NNNN` and write the new one.

The repo has a `/write-adr` command and an `adr-writer` agent that produce a correctly
numbered, correctly formatted ADR from a decision — convenient, but the process above is the
contract.

---

## Keeping docs in sync

The orientation files — root [`README.md`](../../README.md), the per-app docs, the
`.env.example` files, and `docs/` — are the **initial** source of truth, not the only one. It
is normal and expected to read the code.

**When a doc disagrees with the code, the code wins — then fix the doc, in the same change.**

Any change to architecture, layout, commands, environment variables, ports, the
trace/observability contract, or the HTTP surface updates the affected files as part of the
same piece of work. A doc that has drifted is worse than no doc, because it is believed.
