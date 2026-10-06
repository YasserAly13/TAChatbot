---
name: docs-lookup
description: Fetch live, version-aware library documentation instead of guessing an API from training memory. HARD PREFERENCE for any third-party library question (Next.js, FastAPI, SQLAlchemy, Alembic, aioodbc/pyodbc, ODBC Driver 18, Azure Monitor OpenTelemetry, LangChain/LangGraph, Bicep + the ARM resource reference, pino, structlog, uv, anything in package.json / pyproject.toml). Verify against official docs before writing code that calls an API you're not certain of.
---

# Look up library docs (don't guess APIs)

> **Scope gate:** Consulting official documentation needs no confirmation (the doc domains are allow-listed in `.claude/settings.json`); just say which library/version/URL you are reading. Anything outside that allow-list is a web fetch that leaves the machine — name it and wait for a "yes".

Whenever you need an API signature, config option, or feature of a third-party library, **verify against the live docs** rather than recalling from training. This stack moves fast (SQLAlchemy 2.0 replaced the legacy declarative/Query style; the `mssql+aioodbc` dialect forwards URL query keywords to the ODBC connection string; Next 16 changed instrumentation; the Azure OTel distro hard-pins versions) — a guessed call costs a debugging cycle. PyPI wheel availability (e.g. pyodbc for CPython 3.14) is checked against the release's **file list**, not a page summary.

## Protocol

1. **Find the installed version first** — `package.json` (web) or `pyproject.toml` / `uv.lock` (api). Docs must match the installed major.
2. **Fetch the official docs for that version** with `WebFetch` (preferred) or `WebSearch`:
   - SQLAlchemy → `https://docs.sqlalchemy.org/en/20/...` (asyncio extension + the SQL Server dialect page, aioodbc section). Alembic → `https://alembic.sqlalchemy.org/en/latest/...`.
   - Next.js → `https://nextjs.org/docs/...`.
   - FastAPI → `https://fastapi.tiangolo.com/...`. uv → `https://docs.astral.sh/uv/...`.
   - Azure Monitor OpenTelemetry → `https://learn.microsoft.com/azure/azure-monitor/app/opentelemetry-...`.
   - pino → `https://getpino.io`. structlog → `https://www.structlog.org`.
   - Azure SQL / ODBC (target DB engine) → `https://learn.microsoft.com/sql/connect/python/pyodbc/...`, `https://learn.microsoft.com/azure/azure-sql/...`; SQLAlchemy MSSQL dialect → `https://docs.sqlalchemy.org/en/20/dialects/mssql.html`.
   - LangChain → `https://python.langchain.com/docs/...`; LangGraph → `https://langchain-ai.github.io/langgraph/...`; Azure AI Foundry / Azure OpenAI → `https://learn.microsoft.com/azure/ai-foundry/...`, `https://learn.microsoft.com/azure/ai-services/openai/...`; Azure AI Search → `https://learn.microsoft.com/azure/search/...`.
   - Bicep language/CLI → `https://learn.microsoft.com/azure/azure-resource-manager/bicep/...`; ARM resource reference (properties + API versions) → `https://learn.microsoft.com/azure/templates/<provider>/<type>` (e.g. `microsoft.app/containerapps`, `microsoft.sql/servers/databases`); Container Apps → `https://learn.microsoft.com/azure/container-apps/...`.
     These domains are allow-listed in `.claude/settings.json`, so fetching them needs no confirmation.
3. **Ask a specific question** in the WebFetch prompt — "what does `async_sessionmaker(expire_on_commit=False)` change for objects after commit", not "sqlalchemy docs".
4. **Quote the exact signature/snippet** in your reply with the source URL. Don't paraphrase APIs.

## Why mandatory

Training cutoff drifts; these libraries change monthly. Fetching is cheap and version-accurate. This project was built by checking docs this way (Next 16, Azure OTel, SQLAlchemy 2 async + aioodbc, the azurerm provider) — keep doing it.

## When you don't need it

A truly universal built-in (`JSON.parse`, `Array.map`) — you're certain. Anything project-specific — read the file directly. When in doubt, look it up; the cost is tiny.

## If a Context7 MCP is later connected

If `mcp__context7__*` tools appear in a session, prefer them (resolve-library-id → query-docs with the installed version) — they're more token-efficient than fetching a full page. Until then, WebFetch/WebSearch is the path.
