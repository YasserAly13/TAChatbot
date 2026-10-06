"""Read-only external-database tool (ADR-0009 / ADR-0008).

Runs an **allow-listed** query (``queries.py``) with **bound parameters** through the read-only
external engine (``app/db/external.py``). Three layers keep it safe: the allow-list (the model
never writes SQL), the engine's non-SELECT guard, and the SELECT-only login the DB owner
provides. Results are capped at the query's ``max_rows``.

Optional escape hatch — ``AI_ALLOW_TEXT_TO_SQL=true`` — lets ``run_readonly_sql`` execute a
model-written statement that starts with SELECT/WITH. It is OFF by default, must be an explicit
project decision (threat model first), and is still bounded by the engine guard and the login.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from langchain_core.tools import tool
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.config import get_ai_settings
from app.ai.tools import register_tool
from app.ai.tools.queries import READ_ONLY_PREFIXES, get_query, list_queries
from app.db.external import get_external_sessionmaker
from app.logging_config import get_logger

SessionFactory = Callable[[], async_sessionmaker[AsyncSession]]


class TextToSqlDisabled(PermissionError):
    """``AI_ALLOW_TEXT_TO_SQL`` is off (the default)."""


def _rows(result: Any, limit: int) -> list[dict[str, Any]]:
    rows = result.mappings().fetchmany(limit)
    return [dict(row) for row in rows]


async def run_allowed_query(
    name: str,
    params: dict[str, object] | None = None,
    *,
    session_factory: SessionFactory | None = None,
) -> list[dict[str, Any]]:
    """Execute allow-listed query ``name`` with validated, bound ``params``.

    ``session_factory`` defaults to the read-only external engine's sessionmaker, resolved at
    call time (so tests can swap ``get_external_sessionmaker`` on this module).
    """
    query = get_query(name)
    clean = query.validate_params(params or {})
    log = get_logger("app.ai.tools")
    started = time.perf_counter()
    factory = session_factory or get_external_sessionmaker
    async with factory()() as session:
        result = await session.execute(text(query.sql), clean)
        rows = _rows(result, query.max_rows)
    # Log the query NAME and row count — never the parameter values or the rows.
    log.info(
        "external query executed",
        query_name=name,
        rows=len(rows),
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return rows


async def run_readonly_sql(
    sql: str,
    *,
    max_rows: int = 100,
    session_factory: SessionFactory | None = None,
) -> list[dict[str, Any]]:
    """Execute a model-written SELECT — only when ``AI_ALLOW_TEXT_TO_SQL`` is on."""
    if not get_ai_settings().allow_text_to_sql:
        raise TextToSqlDisabled("free-form SQL is disabled (AI_ALLOW_TEXT_TO_SQL is not true)")
    first = sql.lstrip().split(None, 1)[0].upper() if sql.strip() else ""
    if first not in READ_ONLY_PREFIXES:
        raise PermissionError(f"only SELECT/WITH statements are allowed (got {first!r})")
    factory = session_factory or get_external_sessionmaker
    async with factory()() as session:
        result = await session.execute(text(sql))
        rows = _rows(result, max_rows)
    get_logger("app.ai.tools").info("free-form read-only sql executed", rows=len(rows))
    return rows


def describe_queries() -> str:
    """Human/model-readable list of the allow-listed queries (name, params, description)."""
    lines = [
        f"- {q.name}({', '.join(f'{k}: {t}' for k, t in q.params.items())}): {q.description}"
        for q in list_queries()
    ]
    return "\n".join(lines) if lines else "(no queries registered)"


@tool("query_external_db")
async def query_external_db(query_name: str, params: str = "{}") -> str:
    """Run one of the allow-listed read-only queries against the external database.

    ``query_name`` must be a registered name; ``params`` is a JSON object with exactly the
    parameters that query declares. Returns a JSON array of rows (capped).
    """
    try:
        parsed = json.loads(params or "{}")
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"params must be a JSON object: {exc.msg}"})
    if not isinstance(parsed, dict):
        return json.dumps({"error": "params must be a JSON object"})
    try:
        rows = await run_allowed_query(query_name, parsed)
    except (PermissionError, ValueError) as exc:
        # Safe to return to the model: our own validation messages, no data.
        return json.dumps({"error": str(exc), "available": describe_queries()})
    return json.dumps(rows, default=str)


register_tool(query_external_db)
