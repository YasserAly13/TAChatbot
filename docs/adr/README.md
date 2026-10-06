# Architecture Decision Records

Numbered, immutable records of stack- and architecture-affecting decisions for the
**AI Accelerator**. They are the team's memory — without them the same debates
recur and agents re-invent decisions on every change.

- Write one with `/write-adr` (or the `adr-writer` agent) when a tool/pattern/standard
  is adopted, removed, or changed — see [`CLAUDE.md`](../../CLAUDE.md) rule on ADRs.
- Don't write one for a bug fix, refactor, or style preference.
- Copy [`0000-template.md`](0000-template.md); number is zero-padded 4-digit, incrementing.
- Never delete an ADR — mark it `Deprecated` or `Superseded by ADR-NNNN`.

| ADR  | Title                                                                           | Status             | Date       |
| ---- | ------------------------------------------------------------------------------- | ------------------ | ---------- |
| 0000 | Template                                                                        | —                  | —          |
| 0001 | Mandatory API versioning (URI /v1)                                              | Accepted           | 2026-06-10 |
| 0002 | DB spans via pg driver instrumentation, not @prisma/instrumentation             | Superseded by 0004 | 2026-07-26 |
| 0003 | Remove the NestJS api layer; FastAPI is the sole backend                        | Accepted           | 2026-09-20 |
| 0004 | SQLAlchemy 2 async + Alembic DB layer; DB spans via asyncpg instrumentation     | Superseded by 0008 | 2026-09-20 |
| 0005 | Name services by role — the FastAPI backend is `apps/api`                       | Accepted           | 2026-09-20 |
| 0006 | Living architecture document with a template-owned baseline                     | Proposed           | 2026-09-28 |
| 0007 | Terraform for all infrastructure, pre-existing RGs, GitHub applies per env      | Superseded by 0012 | 2026-09-28 |
| 0008 | Azure SQL Database via `mssql+aioodbc`; DB spans via SQLAlchemy instrumentation | Proposed           | 2026-09-28 |
| 0009 | LangChain + LangGraph on Azure AI Foundry; Azure AI Search as the vector store  | Proposed           | 2026-09-28 |
| 0010 | UI foundation — Tailwind v4, chat components, SSE pass-through, MOCK_UPSTREAM   | Proposed           | 2026-09-28 |
| 0011 | Component tests with React Testing Library in Vitest (per-file jsdom)           | Proposed           | 2026-09-28 |
| 0012 | Bicep on a shared platform — use-case-scoped infrastructure, vendored blocks    | Proposed           | 2026-10-04 |

<!-- Append new rows above; newest last. -->
