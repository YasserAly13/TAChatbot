# Data layer

`apps/api` owns the database. It uses **SQLAlchemy 2.0 (asyncio)** on the **`mssql+aioodbc`**
driver (aioodbc → pyodbc → Microsoft ODBC Driver 18 for SQL Server), with **Alembic** for
migrations, against **Azure SQL Database** — and today it ships an **empty model set with no
migrations run**, on purpose. A second, **read-only** engine can reach an external database the
project does not own.

Two facts shape everything below. **There is no local database, ever** (team decision D2): the
project's database is created on Azure by the use-case Bicep deployment first, and developers work against the
**dev** database. And the template has to boot, build, test and containerize on a machine that
has no database at all, while still being one `DATABASE_URL` away from a real one.

The enforced conventions are [`.claude/rules/25-sqlalchemy.md`](../../.claude/rules/25-sqlalchemy.md);
the operator-facing summary is the root [`README.md`](../../README.md) → _Database (SQLAlchemy 2
async + Alembic)_. The decisions are [ADR-0008](../adr/0008-azure-sql-data-layer.md) (Azure SQL,
the driver, the instrumentation — superseding the Postgres choices of
[ADR-0004](../adr/0004-sqlalchemy-async-alembic-db-layer.md), whose layer design still stands) and
[ADR-0012](../adr/0012-bicep-shared-platform.md) (the use-case Bicep provisions the server and
database and writes the URL to Key Vault).

---

## Shape

```mermaid
flowchart LR
    route["/v1 route handler<br/>session: Annotated[AsyncSession, Depends(get_session)]"]
    sess["app/db/session.py<br/>get_session() → one AsyncSession per request"]
    eng["app/db/engine.py<br/>get_engine() — lazy singleton AsyncEngine"]
    drv["aioodbc → pyodbc → ODBC Driver 18<br/>spans: opentelemetry-instrumentation-sqlalchemy"]
    db[("Azure SQL Database<br/>project database (infra/main.bicep)")]

    xroute["/v1 route or AI tool<br/>Depends(get_external_session)"]
    xeng["app/db/external.py<br/>get_external_engine() — lazy, READ-ONLY"]
    xdb[("External Azure SQL<br/>SELECT-only login")]

    base["app/db/base.py<br/>Base(DeclarativeBase) + naming convention"]
    models["app/models/<br/>2.0-style Mapped[] models (none yet)"]
    cli["alembic CLI<br/>revision · upgrade --sql · heads · check"]
    env["alembic/env.py<br/>async template — URL from DATABASE_URL via app.config"]
    versions["alembic/versions/<br/>(empty)"]

    route --> sess --> eng --> drv -.->|"DATABASE_URL"| db
    xroute --> xeng --> drv -.->|"EXTERNAL_DATABASE_URL"| xdb
    models --> base
    cli --> env
    env -->|"target_metadata = Base.metadata"| base
    env --> versions
    env -.->|"online mode only"| db
```

Two paths reach the project database configuration, and they share **one source of truth**:
both the **runtime** engine and the **Alembic** environment read `DATABASE_URL` through
`app.config.get_settings()`. The URL is never in `alembic.ini`. The external engine has **no
Alembic path at all**.

---

## SQLAlchemy 2 async — the layer in `app/db/`

Four small modules, each with one job
([`apps/api/app/db/`](../../apps/api/app/db/__init__.py)):

**`base.py` — the declarative base.** `class Base(DeclarativeBase)` whose `MetaData` carries an
explicit **naming convention** (`ix_` / `uq_` / `ck_` / `fk_` / `pk_`). Every model subclasses
it; there is never a second `MetaData`. The convention exists for Alembic: `downgrade()` and
autogenerate need deterministic constraint names, and without one SQL Server invents them
(`PK__widgets__3213E83F…`) and migrations become environment-specific.

**`engine.py` — the lazy engine.** `get_engine()` is a process-wide singleton built with
`sa_asyncio.create_async_engine(settings.database_url, pool_pre_ping=True)`. Building the engine
**does not open a connection** — see below. `dispose_engine()` closes the pool and is awaited
from the FastAPI `lifespan` shutdown; it is idempotent. The URL is never logged (it carries
credentials); the startup line records `engine.url.host` at most. `create_async_engine` is
resolved **through the module attribute at call time** — the OpenTelemetry instrumentor wraps
that attribute after `app.db` has been imported, and a name bound at import would miss it.

**`session.py` — one session per request.** An `async_sessionmaker(expire_on_commit=False)`
bound to the lazy engine, plus the FastAPI dependency `get_session()` that yields one
`AsyncSession` per request and closes it afterwards. **Routes get a DB handle only through the
dependency:**

```python
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session

router = APIRouter(prefix="/widgets", tags=["widgets"])


@router.get("")
async def list_widgets(session: Annotated[AsyncSession, Depends(get_session)]) -> list[dict]:
    result = await session.execute(select(Widget))
    ...
```

**`external.py` — the read-only second engine.** `get_external_engine()` builds a separate lazy
engine from `EXTERNAL_DATABASE_URL`; `get_external_session()` is the dependency. There is
deliberately **no placeholder**: when the variable is unset the engine refuses to build
(`ExternalDatabaseNotConfigured`) — a project with no external source never touches it. The
real control is the **SELECT-only login** the source's owner provides; as defence in depth a
`before_cursor_execute` listener refuses any statement that does not start with `SELECT` or
`WITH` (`ReadOnlyViolation`) before it reaches the driver. AI tools that query external data
(`app/ai/tools/query_external_db.py`, roadmap Phase 4) go through this engine with allow-listed,
parameterised queries.

No module-level sessions, no sessions shared across requests or tasks, and **no sync
`create_engine` / `Session` anywhere** in the service — a sync call blocks the event loop.
aioodbc is asynchronous at the API but runs pyodbc in a thread pool underneath, so the pool
size (`pool_size`/`max_overflow`) bounds concurrency more tightly than a native async driver
would — tune it per project once real load exists.

---

## Azure SQL — and no local database

`DATABASE_URL` points at the **Azure SQL Database** the use-case Bicep created for the environment
([`infra/modules/sql-database.bicep`](../../infra/modules/sql-database.bicep), called from `infra/main.bicep`).
There is **no database service in `docker-compose.yml`**, and there will not be one: the team
decided every database lives on Azure. Fidelity is the bonus — TLS, firewall reachability,
managed-identity auth and Key Vault-sourced URLs are exercised from day one instead of being
hidden by a container that behaves nothing like the deployed database.

The compose file and every `.env.example` supply a **placeholder** default so the stack starts
anyway:

```
mssql+aioodbc://USER:PASSWORD@your-server.database.windows.net:1433/your-database?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no
```

What is load-bearing in that URL:

- **The scheme is `mssql+aioodbc://`** — SQLAlchemy's async SQL Server dialect over aioodbc.
- **The query string is the ODBC connection string.** `driver=ODBC+Driver+18+for+SQL+Server`
  is mandatory (spaces URL-encoded as `+`); `Encrypt=yes` and `TrustServerCertificate=no`
  enforce validated TLS and stay on in every committed example and every deployed URL.
- **Authentication is a keyword, not a password, when deployed.** `infra/main.bicep` writes
  `mssql+aioodbc://<identity-client-id>@<server>:1433/<db>?…&Authentication=ActiveDirectoryMsi`
  to Key Vault — the api authenticates as its user-assigned managed identity (username = the
  identity's client id, per the ODBC driver's rule for user-assigned identities). Pipelines use
  `Authentication=ActiveDirectoryServicePrincipal` (username = SP client id, password = secret).
  SQL logins exist only if infrastructure enabled them; passwords with reserved characters are
  URL-encoded.

That placeholder never connects to anything, which is fine — see the next section.

### Lazy connect: why a placeholder URL still boots

`create_async_engine` builds the engine and pool objects; it **does not open a connection**. The
first connection happens on the first query. The baseline issues **no queries** — there are no
models to query — so `apps/api` boots, passes its `/health` check, and serves `/ping` and
`/info` with a `DATABASE_URL` that points nowhere. pyodbc imports without the ODBC driver being
installed, so tests and the baseline need nothing on the machine.

This is why the rules say: **never connect at import or startup** — no `await conn.execute(...)`
in `lifespan`, no `engine.begin()` in module scope. Doing so converts "no database configured"
from a non-event into a boot failure, and takes the whole template's offline-first property with
it. The unit tests pin this down: `tests/test_db_engine.py`, `tests/test_db_session.py` and
`tests/test_db_external.py` monkeypatch `pyodbc.connect` (the call aioodbc runs in its thread
pool) to raise, then exercise the engines, the session dependencies, and the lifespan to prove
nothing on the baseline path ever calls it.

---

## The database lifecycle (project database)

Every step in order; the ones marked **human** are never taken by an agent.

1. **Infrastructure creates the database** — the use-case Bicep (`modules/sql-database.bicep`) provisions the
   logical server, the database, the firewall rules (Azure services + developer IPs) and writes
   `DATABASE-URL` to Key Vault. Applied by the pipeline or, for `dev`, a developer (**human**).
2. **A human creates the api identity's contained user** on the database:
   `CREATE USER [id-<slug>-<env>-api] FROM EXTERNAL PROVIDER;` plus `db_datareader`,
   `db_datawriter` (and `db_ddladmin` for the identity the migration pipeline uses — the
   environment's SP). Bicep cannot run T-SQL; this is deliberate.
3. **Developers get the dev URL** from Key Vault into `apps/api/.env` (never committed) and
   their public IP into `developer_ip_allowlist`.
4. **Models → revision**, against **dev**: `uv run --directory apps/api alembic revision
--autogenerate -m "…"` (the `write-migration` skill / `migration-author` agent).
5. **Offline review** — `uv run --directory apps/api alembic upgrade head --sql` renders the
   T-SQL with no connection; this is what gets pasted into the PR.
6. **Apply** — the Environment-gated [`migrate.yml`](../../.github/workflows/migrate.yml)
   workflow (prints `alembic current` before/after and the offline SQL for the approver) or a
   named **human**. Never an agent, never automatically on deploy.

---

## The placeholder model set, and how to extend it

[`apps/api/app/models/__init__.py`](../../apps/api/app/models/__init__.py) is **empty on
purpose** — `__all__ = []` and one commented example model. `alembic/versions/` holds no
revisions. The service boots, Alembic is wired, and nothing has been migrated.

Growing it into a real data layer:

1. **Add a model module** under `app/models/` (e.g. `widget.py`), 2.0-style only:
   `class Widget(Base)`, an explicit snake_case plural `__tablename__`, `Mapped[...]`
   annotations with `mapped_column(...)`, a UUID primary key (`UNIQUEIDENTIFIER`), timestamps
   with `server_default=func.now()`, and a **length on every `String`** (SQL Server turns an
   unbounded `String` into `VARCHAR(max)`).
2. **Import it in `app/models/__init__.py`.** Alembic autogenerate only sees models that are
   imported when `env.py` runs (`env.py` does `import app.models`).
3. **Use it from a `/v1` router** through `Depends(get_session)` — see the snippet above. Query
   with ORM constructs (`select(...)`, `insert(...)`) or `text()` **with bound parameters**;
   never interpolate user input into SQL
   ([`.claude/rules/50-security.md`](../../.claude/rules/50-security.md)).
4. **Generate a revision — against the dev database** (lifecycle step 4). Review the generated
   `upgrade()` **and** `downgrade()`; every revision ships both. The post-write hooks in
   `alembic.ini` run `ruff format` / `ruff check --fix` on the new file.
5. **Review the SQL offline — no database needed** (step 5). Today this prints only the
   transaction wrapper (`BEGIN TRANSACTION;` … `COMMIT;`), because there are no revisions;
   `alembic heads` prints nothing.
6. **Apply it** — step 6.

Steps 1–3 and 5 need no database. Step 4, step 6 and
`uv run --directory apps/api alembic check` (model/migration drift) need the dev database.

### SQL Server safety patterns for populated tables

SQL Server has no `CREATE INDEX CONCURRENTLY` and no `NOT VALID`. The `write-migration` skill
and `migration-author` agent use these instead:

- new index → `op.execute("CREATE INDEX … WITH (ONLINE = ON)")` where the tier supports online
  builds (Business Critical / Premium); on General Purpose a brief schema lock is expected —
  schedule it;
- new foreign key → `ALTER TABLE … WITH NOCHECK ADD CONSTRAINT …`, then a separate
  `ALTER TABLE … WITH CHECK CHECK CONSTRAINT …`;
- `NOT NULL` on an existing column → add nullable → backfill in batches → `ALTER COLUMN … NOT NULL`;
- type changes on large tables → new column → backfill → swap;
- renames → `op.rename_table` / `op.alter_column(new_column_name=…)` by hand (autogenerate emits
  drop + add).

Destructive DDL — drop table/column, type narrowing — needs explicit confirmation (rule 6).
Before authoring, the **`db-introspector` skill** performs a read-only inspection of the live
schema (SQLAlchemy `inspect()`, `INFORMATION_SCHEMA`, `sys.*`, `alembic_version`, the service
tier), so you are diffing against what the database actually contains rather than what the
models claim.

---

## Alembic environment

[`apps/api/alembic/env.py`](../../apps/api/alembic/env.py) is the **async template**
(`alembic init -t async`, Alembic 1.20), adapted in three ways worth knowing:

- **The URL comes from `app.config.get_settings().database_url`** — the same `DATABASE_URL` the
  service uses — never from `alembic.ini`. A URL committed to the ini is a review-blocking
  violation, and `tests/test_alembic.py` asserts the ini has none.
- **`target_metadata = Base.metadata`** with `compare_type=True`, so autogenerate diffs the
  imported models against the database, including column type changes.
- **Offline mode connects to nothing.** `upgrade --sql` renders literal T-SQL to stdout with no
  DBAPI connection, which is what makes lifecycle step 5 safe on any machine. **Online mode**
  builds a throw-away `AsyncEngine` with `NullPool` and runs the migration inside `run_sync`.

`alembic.ini` holds only `script_location`, the revision `file_template`
(`YYYYMMDD_HHMM-<rev>_<slug>`), the ruff post-write hooks, and plain-text stderr logging for the
CLI — the service's structlog pipeline is not involved, because `env.py` only ever runs inside
the `alembic` command.

---

## Database observability

DB calls appear as client-kind dependency spans in `AppDependencies`, produced by
**`opentelemetry-instrumentation-sqlalchemy`** (`0.61b0`, the distro's instrumentation line)
wrapping SQLAlchemy's engines. This is [ADR-0008](../adr/0008-azure-sql-data-layer.md).

Why engine-level, and how it is registered:

- **The Azure Python distro covers neither aioodbc nor pyodbc.** Its default instrumentation set
  is azure_sdk / django / fastapi / flask / psycopg2 / requests / urllib / urllib3, so
  `_instrument_sqlalchemy` in [`app/observability.py`](../../apps/api/app/observability.py)
  registers `SQLAlchemyInstrumentor().instrument()` explicitly at init.
- **Registered without an engine, on purpose.** Called that way the instrumentor wraps
  `sqlalchemy.ext.asyncio.create_async_engine` (verified in the 0.61b0 source), so every engine
  created afterwards is traced — the lazy project engine and the lazy external engine, whichever
  is built first. Passing `engine=` per engine would not work: the instrumentor's singleton guard
  silently skips a second call. This is also why the engine factories resolve
  `create_async_engine` through the module attribute at call time.
- **Same pinned line as everything else.** The package is taken from the distro's `0.61b0`
  line and never bumped independently — a mismatched instrumentation package throwing inside the
  query path is a documented failure mode.

The trade-off, stated plainly: spans are engine-level SQL, not ORM-level semantics (`select(Widget)`
with model attributes). Revisit only if model-level span semantics become a real debugging need.

Runtime proof is still pending — the model set is a placeholder and the dev database is not yet
applied, so "a query lands in `AppDependencies`" is verified during the post-deploy smoke
([`OBSERVABILITY-ROADMAP.md`](../../OBSERVABILITY-ROADMAP.md),
[post-deploy smoke runbook](../operations/runbooks/post-deploy-smoke.md)).

---

## Forbidden regressions

From [`.claude/rules/25-sqlalchemy.md`](../../.claude/rules/25-sqlalchemy.md) — each of these
breaks a property the layer depends on:

| Don't                                                                               | Because                                                                                             |
| ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Use a sync `create_engine` / `Session` anywhere in the service                      | Blocks the event loop; the whole service is async                                                   |
| Create module-level `AsyncSession` objects or share one across requests/tasks       | A session is request-scoped state; sharing it corrupts transactions                                 |
| Connect at import or startup (`engine.begin()`, `await conn.execute` in `lifespan`) | Breaks the baseline's ability to boot with a placeholder `DATABASE_URL`                             |
| Bind `create_async_engine` by name at import                                        | The OTel wrapper is applied to the module attribute later; a bound name misses it — no DB spans     |
| Ship `TrustServerCertificate=yes` or `Encrypt=no`                                   | Disables certificate validation / encryption to Azure SQL                                           |
| Put a URL in `alembic.ini`                                                          | Credentials in a committed file; `env.py` reads `DATABASE_URL` through `app.config`                 |
| Run `alembic upgrade` from an agent                                                 | Migrations are the gated pipeline's or a named human's step                                         |
| Write through the external engine, or remove its read-only listener                 | The external database is someone else's; the listener is the last line behind the SELECT-only login |
| Add a database container to `docker-compose.yml`                                    | Every database is Azure SQL by team decision; a container hides the connection realities            |

---

## Related

- [overview.md](overview.md) — where `apps/api` sits in the system.
- [observability.md](observability.md) — how DB spans join the rest of the telemetry.
- [ADR-0008](../adr/0008-azure-sql-data-layer.md) — the Azure SQL decision in full, including
  the alternatives that were rejected; [ADR-0004](../adr/0004-sqlalchemy-async-alembic-db-layer.md)
  for the layer design it keeps; [ADR-0012](../adr/0012-bicep-shared-platform.md) for how the
  database gets created.
- [`apps/api/CLAUDE.md`](../../apps/api/CLAUDE.md) — the service's own layout, commands,
  and gotchas.
