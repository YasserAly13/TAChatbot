---
description: Author an Alembic revision (upgrade + mandatory downgrade + SQL-Server-safe DDL) for apps/api on Azure SQL. Offline SQL needs no DB; autogenerate needs the dev Azure SQL database (there is no local DB).
argument-hint: <model change>
---

**Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

Use the `write-migration` skill (or the `migration-author` agent for destructive / table-rewriting changes) for: `$ARGUMENTS`.

Note: this project runs **no migrations yet** (`apps/api/alembic/versions/` is empty), and `alembic.ini` holds no URL — `alembic/env.py` reads `DATABASE_URL` via `app.config`. `revision --autogenerate` and `check` need the **dev Azure SQL database** reachable (URL from Key Vault, developer IP on the firewall) — **there is no local database**; offline SQL review does not. If the dev DB isn't reachable, hand-write the revision and stop at the offline-SQL step — say so.

1. Edit/add the model under `apps/api/app/models/` (import it in `app/models/__init__.py`; give every `String` a length).
2. `uv run --directory apps/api alembic revision --autogenerate -m "<snake_case>"` (dev DB) — or write the revision by hand.
3. Write the mirroring `downgrade()`; harden the DDL for populated tables the SQL Server way (`CREATE INDEX … WITH (ONLINE = ON)` where the tier allows, multi-step `NOT NULL`, `WITH NOCHECK` FK + separate `CHECK CONSTRAINT`).
4. Review offline: `uv run --directory apps/api alembic upgrade head --sql` (and `downgrade <prev> --sql`) — renders T-SQL, no DB needed.
5. Hand over the apply step: `.github/workflows/migrate.yml` on `dev` (Environment-gated), then `alembic check` against dev.

Refuse destructive ops (`drop_table`/`drop_column`, narrowing `alter_column`, `TRUNCATE`) without explicit confirmation. **Never run `alembic upgrade` against any database.**
