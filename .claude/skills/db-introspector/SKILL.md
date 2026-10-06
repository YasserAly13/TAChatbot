---
name: db-introspector
description: Read-only inspection of a live Azure SQL schema BEFORE authoring or applying an Alembic migration — verify what actually exists (tables, columns, nullability, indexes, FKs, row counts, alembic_version) vs. what the SQLAlchemy models and alembic/versions claim; or dump an EXTERNAL read-only database's schema into docs/design/external-schema.md for the AI query tool. Use before the write-migration skill / migration-author agent. Requires a reachable DATABASE_URL (or EXTERNAL_DATABASE_URL) — the dev Azure SQL database, since there is no local database.
---

# Database introspector (read-only)

> **Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

Migrations break in prod when the developer's mental model of the live schema is stale. Verify reality first. Every database is **Azure SQL Database** (ADR-0008) and **there is no local database**: the target is the **dev** database the use-case Bicep deployment created (URL from Key Vault → `apps/api/.env`, developer IP on the SQL firewall). If a read-only SQL MCP is wired in `.mcp.json`, prefer it; otherwise use SQLAlchemy's `inspect()` through the service's own async engines and Alembic's commands.

## Targets

| `--target`          | Engine                                     | Env var                 | Purpose                                                                                                                                                                     |
| ------------------- | ------------------------------------------ | ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `project` (default) | `app.db.get_engine()`                      | `DATABASE_URL`          | Drift between models / `alembic/versions/` and the real dev schema before a migration                                                                                       |
| `external`          | `app.db.get_external_engine()` (read-only) | `EXTERNAL_DATABASE_URL` | Dump the schema of an external source into `docs/design/external-schema.md` so `docs/design/external-systems.md` and the AI query tool's allow-list are grounded in reality |

## Caveats

- The baseline model set is an **empty placeholder** and the dev database may be unreachable from this machine (firewall). If the URL is unset/unreachable, say so and fall back to reading `apps/api/app/models/` + `alembic/versions/` — but note that models describe _intent_, the database describes _reality_.
- **Read-only only.** Never mutate. If you want to change the schema, that's a migration (`write-migration`), not a query. The external engine refuses non-SELECT statements by construction.
- Don't paste rows containing PII into output — `TOP`/`OFFSET … FETCH` and redact. Never print either URL.

## Where the tooling stands vs. the DB (no SQL)

```
uv run --directory apps/api alembic heads      # revisions the repo knows about
uv run --directory apps/api alembic current    # revision the DB is at (needs the dev DB)
uv run --directory apps/api alembic check      # models vs migrations drift (needs the dev DB)
```

## Introspect the real schema (read-only, via the async engine)

Run from `apps/api` with the relevant URL set. Swap `get_engine`/`dispose_engine` for `get_external_engine`/`dispose_external_engine` for `--target external`; SQL Server's default schema is `dbo`.

```
uv run python - <<'EOF'
import asyncio
from sqlalchemy import inspect
from app.db import get_engine, dispose_engine

async def main():
    engine = get_engine()
    async with engine.connect() as conn:
        def dump(sync_conn):
            insp = inspect(sync_conn)
            for table in insp.get_table_names(schema="dbo"):
                print(f"\n== {table}")
                for col in insp.get_columns(table, schema="dbo"):
                    print(f"  {col['name']}: {col['type']} nullable={col['nullable']} default={col['default']}")
                for idx in insp.get_indexes(table, schema="dbo"):
                    print(f"  index {idx['name']} {idx['column_names']} unique={idx['unique']}")
                for fk in insp.get_foreign_keys(table, schema="dbo"):
                    print(f"  fk {fk['name']} {fk['constrained_columns']} -> {fk['referred_table']}{fk['referred_columns']}")
        await conn.run_sync(dump)
    await dispose_engine()

asyncio.run(main())
EOF
```

For `--target external`, write the same dump (tables, columns, types, nullability, FKs — no rows) to `docs/design/external-schema.md` with a header naming the source, the date and the login used, and mark the tables the app may use (the allow-list for `app/ai/tools/query_external_db.py`).

Compare against `Base.metadata` (the imported models) to see drift: columns that exist but aren't modelled, nullability differences, indexes the naming convention would name differently.

## Targeted T-SQL checks (read-only, via `sqlcmd` or the engine)

All read-only `SELECT`s. Substitute `$TABLE` / `$SCHEMA` (default `dbo`).

```sql
-- current alembic revision
SELECT version_num FROM alembic_version;

-- columns + nullability + defaults
SELECT c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH, c.IS_NULLABLE, c.COLUMN_DEFAULT
FROM INFORMATION_SCHEMA.COLUMNS c
WHERE c.TABLE_SCHEMA = '$SCHEMA' AND c.TABLE_NAME = '$TABLE' ORDER BY c.ORDINAL_POSITION;

-- approx row count + size (cheap; no table scan)
SELECT SUM(p.rows) AS approx_rows,
       SUM(a.total_pages) * 8 / 1024 AS total_mb
FROM sys.partitions p
JOIN sys.allocation_units a ON a.container_id = p.hobt_id
WHERE p.object_id = OBJECT_ID('$SCHEMA.$TABLE') AND p.index_id IN (0, 1);

-- indexes
SELECT i.name, i.type_desc, i.is_unique, STRING_AGG(c.name, ', ') WITHIN GROUP (ORDER BY ic.key_ordinal) AS columns
FROM sys.indexes i
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE i.object_id = OBJECT_ID('$SCHEMA.$TABLE') AND i.name IS NOT NULL
GROUP BY i.name, i.type_desc, i.is_unique;

-- foreign keys
SELECT fk.name, OBJECT_NAME(fk.referenced_object_id) AS referenced_table, fk.is_not_trusted
FROM sys.foreign_keys fk WHERE fk.parent_object_id = OBJECT_ID('$SCHEMA.$TABLE');

-- service tier (decides whether ONLINE index builds are available)
SELECT DATABASEPROPERTYEX(DB_NAME(), 'Edition') AS edition, DATABASEPROPERTYEX(DB_NAME(), 'ServiceObjective') AS objective;
```

Anything over ~1M rows triggers the SQL-Server-safe DDL patterns in the `migration-author` agent (`ONLINE = ON` where the tier allows, `WITH NOCHECK` + `CHECK CONSTRAINT`, multi-step NOT NULL).

## Workflow when paired with write-migration

1. **Inspect** (above) — note the current revision, nullability, row counts, existing indexes/FKs, and the service tier.
2. **Decide** whether the planned DDL needs the safe multi-step pattern.
3. **Author** the revision. 4. **Verify** by introspecting again (and `alembic check`) after the migration pipeline applies it to dev.

## Optional upgrade

If the team wants agent-native introspection, wire a read-only SQL Server MCP in `.mcp.json` (login with `SELECT`-only grants, see `.mcp.example.json`) and prefer it — record the choice as an ADR.
