---
description: Security baseline for the AI Accelerator. Always loaded.
paths:
  - '**/*'
---

# Security baseline

> **Graded autonomy:** these are conventions to apply _within_ an approved plan or roadmap item — not a licence to act outside one. Hard stops (infra apply, migration apply, push, secrets, deletes) always need explicit confirmation — see [`CLAUDE.md`](../../CLAUDE.md) → _Graded autonomy_.

There is **no user auth/RBAC yet** — projects run **internal-only** (team decision D8); the
planned module is **Okta** (OIDC on the BFF, JWT validation in the api, `AUTH_MODE=none|okta` —
roadmap Phase 8), which needs an ADR and a threat model (`threat-modeler`) before a line of code.
Until then the attack surface is the BFF boundary, secrets, external HTTP, the database layer,
the AI layer (rule 70) and container hardening.

## BFF boundary (the main control today)

- The browser only reaches same-origin `apps/web` route handlers. Service base URLs and any
  secret are **server-side only** — never `NEXT_PUBLIC_*`, never returned to the client.
- BFF handlers validate/shape what they forward; don't proxy arbitrary client-controlled URLs.

## Secrets

- Local: `.env` (gitignored). Real values come from Azure Key Vault in deployed envs.
- Never commit a real secret. Every new env var needs a placeholder entry in the relevant
  `.env.example`. Review your own diff for high-entropy strings (`AKIA`, `sk-`, `ghp_`, `eyJ…`).
- `APPLICATIONINSIGHTS_CONNECTION_STRING` empty ⇒ degraded mode (never crashes) — don't
  hard-fail on its absence.
- **Infrastructure (rule 80):** no secret values in `infra/main.<env>.bicepparam`,
  `infra/platform/*.json` or deployment outputs; connection strings are computed in Bicep and
  land in the use case's Key Vault. Roles on shared resources are **requests** to the cloud team
  (`infra/grant-request.md`), never assignments authored here.

## Database (SQLAlchemy 2 async — `25-sqlalchemy.md`)

- Use ORM constructs (`select(...)`, `insert(...)`, …) — parameterised by the driver. If raw SQL
  is unavoidable, use `text()` **with bound parameters** (`text("… WHERE id = :id")` +
  `.bindparams(...)` / an execute dict). Never f-string / `%`-format / concatenate user input
  into SQL.
- `DATABASE_URL` / `EXTERNAL_DATABASE_URL` may carry credentials: never log them (log
  `engine.url.host` at most), never put them in `alembic.ini`, never commit a real one. TLS is
  `Encrypt=yes&TrustServerCertificate=no` in the ODBC query string — never ship
  `TrustServerCertificate=yes`. Deployed apps use managed identity
  (`Authentication=ActiveDirectoryMsi`), so no database password exists in production.
- The external engine is **read-only** (SELECT-only login + in-code guard); never write through
  it and never remove the guard.
- Migrations are never run from an agent (`alembic upgrade` is the Environment-gated
  `migrate.yml` workflow or a named human).

## External HTTP

- All outbound calls go through the traced helpers (`fetchUpstream` web, `traced_client`
  api) which carry `x-trace-id`. Give them a timeout; never an unbounded wait.
- Don't build outbound URLs from unvalidated user input (SSRF) — allowlist hosts.

## CORS / transport

- The api service is reached only by the BFF on the internal network; if CORS is ever
  enabled on `apps/api` (`CORSMiddleware`), the origin must be an allowlist, not `'*'`, when
  credentials are involved.

## Containers

- Dockerfiles run as **non-root** in the final stage (we already do: `node` user / `appuser`).
- Keep `.dockerignore` covering `node_modules`, `.next`, `dist`, `.venv`, `__pycache__`, `.env*`,
  `.git`.

## When to invoke `security-reviewer`

Any diff touching: BFF route handlers, a new outbound `fetch`/`httpx` call, a new env var, a
Dockerfile/`.dockerignore`, CORS config, or the SQLAlchemy/Alembic layer (`app/db/**`,
`app/models/**`, `alembic/**`, raw `text()` SQL).
