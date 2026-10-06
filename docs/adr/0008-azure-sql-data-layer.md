# ADR-0008: Azure SQL Database via SQLAlchemy 2 async (`mssql+aioodbc`) + Alembic; DB spans via SQLAlchemy instrumentation

|        |            |
| ------ | ---------- |
| Status | Proposed   |
| Date   | 2026-09-28 |

## Context

ADR-0004 put the database layer on **SQLAlchemy 2 async + Alembic** in `apps/api`, with
**asyncpg** against an external **Azure Postgres** and DB dependency spans from the asyncpg
driver instrumentation. The team that owns the projects built on this template has since
decided (2026-09-28, decision D6 in `docs/template-roadmap.md`) that **every database is Azure
SQL Database** — the project's own database and the external read-only sources — created by
Terraform first (ADR-0007), reachable over a public endpoint with firewall rules for now, and
**never local**. asyncpg cannot speak to SQL Server; the TLS/auth syntax (`?ssl=require`), the
Postgres-specific migration-safety guidance (`CONCURRENTLY`, `NOT VALID`), the placeholder URL,
the offline test doubles and the OTel driver instrumentation all assume Postgres. The parts of
ADR-0004 that are engine-agnostic — lazy engine, one `AsyncSession` per request, Alembic with
the URL from `DATABASE_URL`, offline tests, no migrations run by the service — remain correct.

## Decision

We keep the SQLAlchemy 2 async + Alembic layer and change the engine: the api talks to **Azure
SQL Database** through **`mssql+aioodbc`** (aioodbc on pyodbc on **Microsoft ODBC Driver 18 for
SQL Server**, installed in the runtime image), with `Encrypt=yes` and certificate validation on
every URL. **Deployed apps authenticate with their managed identity**
(`Authentication=ActiveDirectoryMsi`, `UID` = the user-assigned identity's client id — the
`DATABASE_URL` Terraform writes to Key Vault); developers use Entra service-principal or SQL
auth against the **dev** database only. External databases are reached through a **second,
read-only engine** (`EXTERNAL_DATABASE_URL`, `ApplicationIntent=ReadOnly`, no Alembic). **DB
dependency spans come from `opentelemetry-instrumentation-sqlalchemy`** (the distro-pinned
`0.61b0` line) registered on the engine's `sync_engine` at first creation, replacing the
asyncpg instrumentor. Migration guidance becomes SQL-Server-specific (`WITH (ONLINE = ON)`,
`WITH NOCHECK` + `CHECK CONSTRAINT`, add-nullable → backfill → `ALTER COLUMN … NOT NULL`).
This ADR **supersedes ADR-0004** for the driver, TLS/auth syntax, instrumentation and DDL
guidance; ADR-0004's layer design otherwise stands.

## Consequences

- Good: one database engine across the project's own data and the external sources the AI
  layer queries; Terraform provisions it (ADR-0007) and the identity model is keyless in
  every deployed environment.
- Good: the layer's shape is unchanged — routes, tests and skills keep the `get_session()`
  dependency-override pattern; only the driver, URL and instrumentation change.
- Bad: the runtime image needs the Microsoft ODBC driver (an apt repository + EULA
  acceptance), and `pyodbc` is a compiled extension — the wheel-only Docker build now depends
  on pyodbc publishing CPython 3.14 wheels (verified at adoption; re-verify on every bump).
- Bad: aioodbc runs pyodbc calls in a thread pool — it is async at the API, not at the socket,
  so pool sizing matters more than with asyncpg.
- Bad: autogenerate and `alembic check` need the **dev Azure SQL** database reachable (firewall
  allowlist); there is no local fallback by team decision.
- Bad: Azure SQL has no `CONCURRENTLY`; online index builds depend on the service tier, so the
  migration skills must state the tier assumption.

## Alternatives considered

- **Keep Postgres** — rejected: the team's databases are Azure SQL; the template must match
  what projects actually connect to.
- **`mssql+pyodbc` (sync) with `run_in_threadpool`** — rejected: loses the async session
  contract every route and skill is written against; aioodbc gives the same DBAPI behind the
  async API.
- **`pymssql` / FreeTDS** — rejected: no Microsoft Entra managed-identity authentication path
  comparable to ODBC Driver 18's `ActiveDirectoryMsi`, which is the deployed auth model.
- **A SQLAlchemy-level `mssql+aiodbc`-style third-party dialect** — rejected: `mssql+aioodbc`
  is the dialect SQLAlchemy 2 ships and documents.
- **Keep driver-level instrumentation (a pyodbc/DBAPI instrumentor)** — rejected: the
  SQLAlchemy instrumentor is the documented, distro-pinned option that works with async engines
  (`engine.sync_engine`) regardless of the DBAPI underneath.

## References

- Supersedes: ADR-0004 (driver, TLS/auth syntax, instrumentation, DDL guidance)
- Related: ADR-0007 (Terraform provisions the server/database and writes `DATABASE_URL`)
- Docs: `docs/template-roadmap.md` (D6, Phase 3), `docs/architecture/data.md`,
  `.claude/rules/25-sqlalchemy.md`, `infra/terraform/modules/sql-database/`
- External: SQLAlchemy SQL Server dialect (`https://docs.sqlalchemy.org/en/20/dialects/mssql.html`);
  ODBC Driver 18 Entra ID keywords (`https://learn.microsoft.com/sql/connect/odbc/using-azure-active-directory`);
  ODBC Driver 18 Linux install (`https://learn.microsoft.com/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server`);
  `opentelemetry-instrumentation-sqlalchemy` (`https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/sqlalchemy/sqlalchemy.html`)
