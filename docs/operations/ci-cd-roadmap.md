# CI/CD Hardening — Deferred Tasks (Roadmap / Backlog)

> Tasks that were **discussed and intentionally deferred** during the branch-governance
> setup (June 2026). They are **not implemented yet** — this file exists so they are not
> forgotten. Pick one up by opening a PR that implements it and removing its entry here.
>
> **Update 2026-09-28 (template roadmap Phase 7):** `ci.yml` now has four jobs — the promotion
> guard, a **quality** job (prettier, ruff, `tsc`, `bicep build`/`lint` + the three param files,
> OpenAPI-contract freshness), a **tests-changed gate** on PRs (code without tests fails unless
> the PR carries the `tests-not-needed` label), the **tests + coverage** job, and a **build** job
> (`next build` + the api Docker image). Workflow `permissions` are least-privilege (**F4 done**).
> `infra.yml` and `migrate.yml` use GitHub Environments (**E1–E3 done**, human setup in
> `infra/README.md`). A PR template carries the Definition-of-Done checklist.

## Committed-but-deferred

### F5 — Per-service path filters in CI (selected, deferred)

**What:** Make `.github/workflows/ci.yml` run only the test job(s) for the service(s) that
actually changed in a PR, instead of always running Web + Python.

**Why deferred:** It complicates the **required-status-check** names used by the branch
rulesets. If a service's job is skipped, its check context never reports, and a required
check that never runs will **block the PR forever** unless handled correctly (skipped jobs
must still emit a passing/neutral check, e.g. via a path-filter + a "required check shim"
job, or `dorny/paths-filter` driving a matrix with a always-green aggregate gate).

**Acceptance criteria when picked up:**

- A PR touching only `apps/api/**` does **not** run the Web tests, and vice-versa.
- The branch-ruleset required checks still resolve to **success** for skipped services
  (use an aggregate "CI required" gate job that depends on the matrix and is the single
  required context — never require the per-service jobs directly).
- Document the new required-check name(s) and update the ruleset(s) accordingly.
- Verify against the trace/observability contract is unaffected (CI behavior only).

**References:** current workflow [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml);
the two independent packages per `.claude/rules/00-architecture.md`.

---

## Other candidates discussed but not selected (not committed — review later)

These came up while designing the branch-governance model and may be worth revisiting.
Listed for memory only; none are scheduled.

- **A7** — Require conversation resolution before merge.
- **A9** — Require approval from someone other than the last pusher.
- **B2** — Auto-delete head branches after merge.
- **B3** — Merge queue on `development` (once it gets busy).
- **C2** — Replace hard-coded usernames in rulesets with GitHub **Teams** (more maintainable;
  also the cleanest way to do per-branch merge allowlists in rulesets).
- **E1/E2/E3** — GitHub **Environments** (`dev` / `staging` / `prod`) with deployment
  protection rules + required reviewers — **now required** by
  [`.github/workflows/infra.yml`](../../.github/workflows/infra.yml) (the Bicep deploy job
  runs inside the Environment of the target branch; ADR-0012). Per-environment SP credentials
  are repository secrets prefixed `DEV_` / `STAGING_` / `PROD_` so the plan job can read them
  without tripping the gate. Creating the Environments and secrets is a human step
  ([`docs/template-roadmap.md`](../../docs/template-roadmap.md) → 2.14).
- ~~**F4** — Least-privilege `permissions:` per job in CI~~ — **done 2026-09-28** (`contents: read`,
  `pull-requests: read` workflow-wide; nothing in `ci.yml` writes).
- **G1** — Dependabot (pairs with the `dependency-updater` agent).
- **G2** — Require signed commits on protected branches.
- **G4** — Tag/release protection ruleset (only release-leads create `v*` tags).
- **G3** — Secret-scanning push protection — **not available**: requires GitHub Advanced
  Security, which is not included on the Team plan for private repos.
