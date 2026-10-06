---
name: security-review
description: Run an OWASP-aligned security checklist against the current diff, adapted to the Team Assistant (no auth yet — BFF boundary, secrets, external HTTP, the SQLAlchemy/Alembic layer, CORS, containers). The lightweight on-demand version of the security-reviewer agent.
---

# Security review checklist

> **Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

Run against the current diff (`git diff`, or against the remote base once it exists; if git isn't available, ask for the changed paths). For each item mark PASS / FAIL / N/A with a `file:line` for failures. Grounded in `.claude/rules/50-security.md`.

1. **BFF boundary** — no service base URL or secret in client code; no `NEXT_PUBLIC_*` for a service URL; browser only hits same-origin `apps/web/src/app/api/*`. BFF handlers don't forward client-controlled URLs (SSRF).
2. **Secrets / env** — no high-entropy literal (`/(AKIA|sk-|ghp_|eyJ[A-Za-z0-9_-]{30,})/`); every new `process.env.*` / `os.getenv` has a placeholder in the matching `.env.example`; no secret/PII added to structured log fields.
3. **SQLAlchemy / Alembic** — ORM constructs preferred; no f-string / `%` / concatenated SQL with user input (raw must be `text()` with bound params); `DATABASE_URL` / `EXTERNAL_DATABASE_URL` not logged, not in `alembic.ini`, keep `Encrypt=yes&TrustServerCertificate=no`; sessions only via `Depends(get_session)` / `Depends(get_external_session)`; no writes through the external engine; no `alembic upgrade` from code or an agent.
4. **External HTTP** — outbound goes through `fetchUpstream` / `traced_client` with a timeout; no URL built from unvalidated user input.
5. **CORS** — if enabled on `apps/api`, the origin is an allowlist, not `'*'`, with credentials.
6. **Containers** — Dockerfile final stage non-root; `.dockerignore` covers `node_modules`, `.next`, `dist`, `.venv`, `__pycache__`, `.env*`, `.git`.
7. **Trace header** — `x-trace-id` validated against `^[0-9a-f]{32}$` before adoption.
8. **Auth introduced?** — if the diff adds authentication/authorization, STOP and recommend the `threat-modeler` agent + an ADR before merge.
9. **AI layer** (`app/ai/**`) — clients only from `client.py`; every call in `model_call_span()`; no prompt/completion/retrieved text/user id in telemetry or logs; tools allow-listed + read-only (no free-form SQL without `AI_ALLOW_TEXT_TO_SQL` + threat model); retrieved/tool text never a `SystemMessage`; bounded `error_kind` to clients; keys only in `api_key` dev mode.
10. **Bicep** (`infra/**`, rule 80) — no secret values in `*.bicepparam`/manifests/outputs; no role assignments (requests only); no platform-tier resource declared; TLS floors, Entra-only SQL auth, storage hardening and `allowInsecure: false` not loosened; developer IPs only in dev; prod params hardened (purge protection, ZRS).

## Output

A `## Security Review` report grouped CRITICAL / HIGH / MEDIUM / LOW. CRITICAL blocks merge; HIGH blocks unless a time-bounded waiver; MEDIUM → backlog; LOW → informational. For anything heavier (auth changes, multi-file), delegate to the `security-reviewer` agent.
