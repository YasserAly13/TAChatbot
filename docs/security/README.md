# Security — AI Accelerator

This is the security posture overview for the **AI Accelerator**: what the platform actually
does today to protect the BFF boundary, secrets, outbound calls, the database layer, and
containers, and what still needs work before a project built on it can add its own auth. It
summarizes and links to the enforced rule file rather than duplicating it — if this page and
[`.claude/rules/50-security.md`](../../.claude/rules/50-security.md) ever disagree, the rule
file (and the code behind it) wins; file an issue against this page.

## Status: pre-auth template

The repo ships **no authentication or authorization**. There are no user accounts, no
sessions, no tokens, and no per-route access control anywhere in `apps/web` or `apps/api`.
Concretely, that means:

- Every HTTP endpoint either service exposes is reachable by anyone who can reach it over the
  network — the only thing standing between callers and `apps/api` is network topology.
  Locally, Compose publishes both ports to the host (`3000`, `8000` — convenient for
  development, and a reminder that the services themselves enforce nothing); in a real
  deployment, restricting who can reach the backend is a networking decision that hasn't been
  made yet — see
  [`../operations/deployment.md`](../operations/deployment.md).
- There is no concept of a "user" to attribute a request to. The `x-trace-id` correlates a
  request across services for **debugging**, not for authorization — do not repurpose it as
  an identity or access-control signal.
- The attack surface today is therefore everything that does **not** depend on knowing who's
  calling: the BFF boundary, secret handling, outbound HTTP, the database layer, and
  container hardening — the sections below.

**Adding auth is not a normal feature PR.** Per root
[`CLAUDE.md`](../../CLAUDE.md) → _What you cannot do_ and
[`.claude/rules/50-security.md`](../../.claude/rules/50-security.md), it requires, in order:

1. A design-time **STRIDE threat model**, written by the `threat-modeler` agent, filed under
   [`threat-models/`](threat-models/) (see conventions below — the directory is **empty by
   design** until the first non-trivial feature, auth included, is threat-modeled).
2. An **ADR** recording the chosen approach ([`docs/adr/`](../adr/)).
3. Explicit user confirmation before implementation starts.

Only after that does auth work begin. Until then, treat "no auth" as the model, not a gap to
route around.

## Controls in place today

### (a) BFF boundary

The browser talks to **exactly one** origin: the Next.js `apps/web` server. Route handlers
under `src/app/api/*` are the BFF — they run server-side and are the only code allowed to call
`apps/api`.

- The backend base URL (`API_BASE_URL`) and any secret are **server-side env only** — never
  `NEXT_PUBLIC_*`, never echoed back to the client.
- BFF handlers validate and shape what they forward; they do not proxy an arbitrary
  client-supplied URL or pass through unvalidated request bodies verbatim.
- Every outbound call from a handler goes through `fetchUpstream` (`apps/web/src/lib/trace.ts`)
  — the one sanctioned client, which also carries `x-trace-id`.

This is the platform's primary control today: `apps/api` is not designed to be called
directly by untrusted clients, and nothing about its current implementation assumes it will be.

### (b) Secrets

- Local secrets live in `.env` files, which are gitignored; every `.env.example` (root and
  per-app) ships **placeholders only** (e.g. `DATABASE_URL=mssql+aioodbc://USER:PASSWORD@...`)
  — never a real value. The same applies to `alembic.ini`: it holds **no** `sqlalchemy.url`;
  Alembic reads `DATABASE_URL` through `app.config` (asserted by `tests/test_alembic.py`).
- In deployed environments, real values are meant to come from **Azure Key Vault**, wired into
  each app as a Container Apps secret (the wiring is planned alongside app hosting — see
  [`../operations/deployment.md`](../operations/deployment.md) and
  [`../../infra/README.md`](../../infra/README.md)).
- `APPLICATIONINSIGHTS_CONNECTION_STRING` empty is a valid, expected state (degraded mode) —
  never hard-fail on its absence.
- Review your own diff for high-entropy strings before committing (`AKIA`, `sk-`, `ghp_`,
  `eyJ…`-style JWTs, connection strings). No secret should ever reach a commit.

### (c) Log redaction at source

Every structured log line is redacted **before any sink** — local stdout or the Azure export —
ever sees it. The default secret-bearing field list
([`.claude/rules/60-observability.md`](../../.claude/rules/60-observability.md) → _Log
pipeline_) is:

```
authorization, cookie, set-cookie, x-api-key, token, access_token, refresh_token,
id_token, password, secret, client_secret, api_key / apiKey, connection_string / connectionString
```

- Node (`apps/web`): pino `redact` matches these paths at the top level and one level deep;
  extend per logger via `buildLogger({ redactPaths: [...] })`.
- Python (`apps/api`): structlog matches case-insensitively with `-`/`_` normalized,
  recursively; extend via `configure_logging(extra_redacted_fields={...})`.
- If something leaks anyway — a secret or PII reaches Log Analytics despite this — the
  sanctioned response is the
  [`pii-purge` runbook](../operations/runbooks/pii-purge.md), which also covers rotating a
  leaked secret (purge is cleanup, not mitigation for a live credential).

### (d) Outbound HTTP discipline

- **Bare HTTP clients are forbidden.** Every outbound call goes through the traced wrapper for
  its service — `fetchUpstream` (`apps/web`), `traced_client()` (`apps/api`) — which carries
  `x-trace-id` and is where a timeout belongs. Never issue an unbounded/no-timeout request.
- **No SSRF surface today by construction:** the only outbound calls in the codebase target the
  fixed, env-configured upstream (`API_BASE_URL`) — none are built from
  unvalidated user input. If a future feature needs to call a URL supplied by a caller,
  allowlist the hosts it may reach; don't forward an arbitrary URL to a traced client.

### (e) Database

`apps/api` owns the only database access — SQLAlchemy 2 async on `mssql+aioodbc` against
**Azure SQL Database** (never local), Alembic wired, **no migrations run** and an empty model set
([ADR-0008](../adr/0008-azure-sql-data-layer.md),
[`.claude/rules/25-sqlalchemy.md`](../../.claude/rules/25-sqlalchemy.md)). A second engine
(`app/db/external.py`) reaches an external database **read-only**: SELECT-only login from the
owner, plus an in-code guard that refuses any non-`SELECT` statement. The rules are
unconditional:

- Query through ORM constructs (`select(...)`, `insert(...)`) — they parameterize through the
  driver — or `text()` **with bound parameters** (`.bindparams(...)`).
- **Never** f-string / `%`-interpolate user input into SQL.
- Routes obtain a session only via `Depends(get_session)`; no module-level or shared sessions.
- `DATABASE_URL` / `EXTERNAL_DATABASE_URL` are TLS-only with certificate validation
  (`Encrypt=yes`, `TrustServerCertificate=no`) and are never logged — the engines log the host at
  most. Neither is ever written into `alembic.ini`. Deployed apps authenticate with their managed
  identity (`Authentication=ActiveDirectoryMsi`) — no database password exists in production.
- Applying a migration (`alembic upgrade`) is the Environment-gated `migrate.yml` workflow or a
  named human; agents author and review offline (`--sql`) only.

There are no models and no queries in the codebase today, so this is a standing rule for what
gets added, not a report on existing code.

### (f) CORS / transport

`apps/api` does not enable CORS today (confirmed — no `CORSMiddleware` or CORS config
exists in `apps/api/app`), which is consistent with the BFF model: the browser never calls
it directly, so there's currently nothing to allowlist. If CORS is ever turned on (e.g. for a future
non-browser consumer), the origin **must** be an explicit allowlist, never `'*'`, whenever
credentials are involved.

### (g) Containers

Both Dockerfiles run their final stage as a **non-root** user — verified directly against each
Dockerfile:

| Service    | Base image              | Final-stage user                                                                                  |
| ---------- | ----------------------- | ------------------------------------------------------------------------------------------------- |
| `apps/web` | `node:24-bookworm-slim` | `node` (`USER node`, `apps/web/Dockerfile`)                                                       |
| `apps/api` | `python:3.14-slim`      | `appuser` — a dedicated system user created at build time (`USER appuser`, `apps/api/Dockerfile`) |

`apps/api`'s runtime stage copies the synced `.venv`, `app/`, `alembic.ini`, and `alembic/`
owned by `appuser`; shipping the Alembic environment in the image is deliberate, so a human can
run `alembic upgrade head` from the container with `DATABASE_URL` injected at run time — the
image itself carries no credentials.

`.dockerignore` (root) excludes `node_modules/`, `dist/`, `.next/`, `**/generated/`, `.venv/`,
`__pycache__/`, `*.pyc`, `.git/`, `**/.env` / `**/.env.*` (while explicitly re-including
`**/.env.example`), `*.log`, test files, and tool caches — so build contexts don't carry
secrets, dev artifacts, or the git history into an image layer.

### (h) Telemetry ingestion hardening

This isn't a runtime app control, but it's part of the platform's security posture: telemetry
ingestion can be locked to **Microsoft Entra ID-authenticated senders only**, so a leaked App
Insights connection string alone becomes useless.

- `TELEMETRY_AUTH_MODE` (all services): empty/`connection_string` = default;
  `managed_identity` = Entra ID ingestion via `ManagedIdentityCredential`, paired with
  `DisableLocalAuth` on the Application Insights component once verified.
- **Visible-never-silent failure:** a mistyped `TELEMETRY_AUTH_MODE` value disables
  observability with the reason on `/health` — it never silently falls back to unauthenticated
  ingestion. Unit-tested in both services.
- Rollout order and the exact `az`/Bicep steps: [`../operations/deployment.md`](../operations/deployment.md)
  and [`../../infra/README.md`](../../infra/README.md) (§ Ingestion hardening).

## Review process

A diff warrants a security review — run the `security-review` skill or the
`security-reviewer` agent, and consult any relevant threat model first — whenever it touches:

- a BFF route handler (`apps/web/src/app/api/**`),
- a new outbound `fetch` / `httpx` call, or a change to a traced HTTP wrapper,
- a new environment variable (does it need a placeholder in `.env.example`? does it carry a
  secret?),
- a Dockerfile or `.dockerignore`,
- CORS configuration (currently absent — introducing it is itself a security-relevant change),
- or the database layer (`apps/api/app/db/**`, `apps/api/app/models/**`,
  `apps/api/alembic/**`, `apps/api/alembic.ini`).

The repo ships tooling for this rather than relying on memory: the `security-reviewer` agent
and the lighter-weight `security-review` skill both run an OWASP-aligned checklist adapted to
this template's actual shape (no auth yet — BFF boundary, secrets, external HTTP, the
SQLAlchemy/Alembic layer, CORS, containers), grounded in [`.claude/rules/50-security.md`](../../.claude/rules/50-security.md).
Run one of them before opening a PR that touches any of the above, per the root
[`CLAUDE.md`](../../CLAUDE.md) → _Definition of Done_.

## Threat models

Design-time STRIDE threat models live in [`threat-models/`](threat-models/), one file per
non-trivial feature, written **before** implementation by the `threat-modeler` agent and
consulted by `security-reviewer` at diff time. The directory currently holds only its
[conventions file](threat-models/README.md) and an empty table — that's expected: no
non-trivial feature (auth included) has been built yet. The first feature that needs one
should follow the conventions there, not invent a new format.
