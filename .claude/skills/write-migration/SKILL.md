---
name: write-migration
description: Produce an Alembic revision (upgrade + mandatory downgrade + safety checks) for apps/api's SQLAlchemy 2 async models on Azure SQL Database. Lightweight version of the migration-author agent — use for additive, non-destructive changes; delegate to the agent for anything destructive or table-rewriting. Offline SQL review needs no DB; autogenerate needs the dev Azure SQL database reachable (there is no local database).
---

# Write an Alembic migration

> **Scope gate:** If this run is part of an approved plan or roadmap item, say in 1–2 lines what you'll touch (files, commands) and proceed. If invoked ad hoc, state that first and wait for a "yes". Hard stops always apply (root `CLAUDE.md` → _Graded autonomy_): never apply infra or migrations, push, read/write secrets, or delete without explicit confirmation.

Read `.claude/rules/25-sqlalchemy.md` first. **The project runs no migrations yet** (`alembic/versions/` is empty, the model set is a placeholder). `alembic.ini` holds **no URL** — `alembic/env.py` reads `DATABASE_URL` via `app.config.get_settings()`. **There is no local database, ever** (team decision D2): `revision --autogenerate` and `check` need the **dev Azure SQL database** reachable — the database the use-case Bicep deployment created, the URL from Key Vault in the developer's `apps/api/.env`, and the developer's IP on the SQL firewall allowlist. If it isn't reachable, hand-write the revision and review it with **offline SQL** — say which path you took.

## Prereqs

- Models: `apps/api/app/models/` (2.0-style `Mapped[]`, subclass `app.db.Base`; import the module in `app/models/__init__.py` or autogenerate won't see it).
- Alembic: `apps/api/alembic.ini`, `apps/api/alembic/env.py` (async), revisions in `apps/api/alembic/versions/`.
- All commands run from `apps/api` (or `uv run --directory apps/api …`).
- Optional first step: the `db-introspector` skill to see what the dev database actually contains.

## Workflow (additive / non-destructive only)

1. Edit/add the model to express the new desired state (new table, nullable column, index). Give every `String` a length (SQL Server turns an unbounded `String` into `VARCHAR(max)`).
2. Generate the revision against the **dev** database (or write it by hand from `alembic/script.py.mako`):
   ```
   uv run alembic revision --autogenerate -m "<snake_case_name>"
   ```
3. Read the generated file. Autogenerate misses renames/server defaults — fix by hand. **`downgrade()` must mirror `upgrade()`** (never `pass`). Apply the SQL Server safety patterns for populated tables (no `CONCURRENTLY`, no `NOT VALID` here):
   - new index → `op.execute("CREATE INDEX ix_… ON … (…) WITH (ONLINE = ON)")` and state the tier assumption (online builds need Business Critical / Premium; on General Purpose the build takes a short lock — schedule it).
   - `add_column(nullable=False, server_default=…)` on an existing table → split (nullable add → backfill in batches → `alter_column(nullable=False)` → optional default); document why in a comment.
   - Adding a FK to a populated table → `op.execute("ALTER TABLE … WITH NOCHECK ADD CONSTRAINT fk_… FOREIGN KEY …")` then a separate `ALTER TABLE … WITH CHECK CHECK CONSTRAINT fk_…` step.
4. Review the SQL **offline** (no DB needed — renders T-SQL) and paste the relevant DDL in your report:
   ```
   uv run alembic upgrade head --sql
   uv run alembic downgrade <previous_rev> --sql
   ```
5. `uv run ruff format alembic && uv run ruff check alembic`; commit model + revision together.
6. Hand over: **applying is not yours.** State the human step — run `.github/workflows/migrate.yml` for `dev` (Environment-gated, prints `alembic current` before/after), then `uv run alembic check` against dev to confirm no drift.

## Not covered here — delegate to `migration-author`

- Any `drop_table` / `drop_column` / narrowing `alter_column` / `TRUNCATE` (destructive — needs explicit confirmation).
- Large backfills (separate batched script).
- **Never** run `alembic upgrade` against any database (root `CLAUDE.md` → _What you cannot do_); applying is the migration pipeline or a named human.
