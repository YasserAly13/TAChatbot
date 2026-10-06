"""Alembic (ADR-0008 / ADR-0013): no hard-coded URL, one linear history starting with the
conversations revision (roadmap api 1.1), and the async ``env.py`` renders upgrade AND
downgrade in OFFLINE mode with no database and no connection — for the SQL Server dialect.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pyodbc
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

SERVICE_ROOT = Path(__file__).resolve().parents[1]
INI = SERVICE_ROOT / "alembic.ini"
ENV_PY = SERVICE_ROOT / "alembic" / "env.py"
VERSIONS = SERVICE_ROOT / "alembic" / "versions"

TEST_URL = (
    "mssql+aioodbc://u:p@db.invalid:1433/app"
    "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
)


def _config(output: io.StringIO | None = None) -> Config:
    return Config(str(INI), output_buffer=output, stdout=io.StringIO())


def test_ini_has_no_hardcoded_database_url() -> None:
    assert "sqlalchemy.url" not in INI.read_text(encoding="utf-8")


def test_script_location_resolves_to_the_alembic_dir() -> None:
    script = ScriptDirectory.from_config(_config())
    assert Path(script.dir).resolve() == (SERVICE_ROOT / "alembic").resolve()
    assert (SERVICE_ROOT / "alembic" / "script.py.mako").is_file()


FIRST_REVISION = "7c1d4e2a9b30"


def test_history_is_linear_and_starts_with_the_conversations_revision() -> None:
    script = ScriptDirectory.from_config(_config())
    assert VERSIONS.is_dir()
    assert script.get_heads() == [FIRST_REVISION]
    assert script.get_revision(FIRST_REVISION).down_revision is None


def test_every_revision_has_a_real_downgrade() -> None:
    # A structural mirror: every table/index created in upgrade() is dropped in downgrade().
    for path in VERSIONS.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        upgrade, downgrade = source.split("def downgrade() -> None:", 1)
        for create, drop in (("create_table(", "drop_table("), ("create_index(", "drop_index(")):
            assert upgrade.count(f"op.{create}") == downgrade.count(f"op.{drop}"), (
                f"{path.name}: downgrade() must undo every op.{create} in upgrade()"
            )


def test_env_py_reads_url_from_settings_and_targets_base_metadata() -> None:
    source = ENV_PY.read_text(encoding="utf-8")
    compile(source, str(ENV_PY), "exec")  # syntactically valid
    assert "get_settings().database_url" in source
    assert "load_local_env()" in source  # apps/api/.env is honoured, like app.main
    assert "target_metadata = Base.metadata" in source
    assert "import app.models" in source
    assert 'config.get_main_option("sqlalchemy.url")' not in source


def _offline(monkeypatch: pytest.MonkeyPatch, direction: str, target: str) -> str:
    """Render ``alembic <direction> <target> --sql`` and fail if anything tries to connect."""
    attempts: list[tuple[Any, ...]] = []

    def fake_connect(*args: Any, **kwargs: Any) -> None:
        attempts.append((args, kwargs))
        raise AssertionError("offline mode must never connect")

    monkeypatch.setattr(pyodbc, "connect", fake_connect)
    monkeypatch.setenv("DATABASE_URL", TEST_URL)

    output = io.StringIO()
    getattr(command, direction)(_config(output), target, sql=True)
    assert attempts == []
    return output.getvalue()


@pytest.mark.usefixtures("_restore_logging")
def test_offline_upgrade_creates_both_tables_without_a_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _offline(monkeypatch, "upgrade", "head")  # `alembic upgrade head --sql`

    assert "CREATE TABLE conversations" in sql
    assert "CREATE TABLE messages" in sql
    assert "CONSTRAINT fk_messages_conversation_id_conversations FOREIGN KEY" in sql
    assert "CREATE INDEX ix_conversations_updated_at ON conversations (updated_at)" in sql
    assert "CREATE INDEX ix_messages_conversation_id_created_at" in sql
    assert f"VALUES ('{FIRST_REVISION}')" in sql


@pytest.mark.usefixtures("_restore_logging")
def test_offline_sql_never_uses_deprecated_large_types(monkeypatch: pytest.MonkeyPatch) -> None:
    # ISJSON() rejects NTEXT, so `citations` must be NVARCHAR(max) even when rendered offline.
    sql = _offline(monkeypatch, "upgrade", "head")

    assert "NTEXT" not in sql
    assert "citations NVARCHAR(max) NULL" in sql
    assert "content NVARCHAR(max) NOT NULL" in sql


@pytest.mark.usefixtures("_restore_logging")
def test_offline_downgrade_drops_everything_the_upgrade_created(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sql = _offline(monkeypatch, "downgrade", f"{FIRST_REVISION}:base")

    for statement in (
        "DROP INDEX ix_messages_conversation_id_created_at ON messages",
        "DROP TABLE messages",
        "DROP INDEX ix_conversations_updated_at ON conversations",
        "DROP TABLE conversations",
    ):
        assert statement in sql
    # messages (the FK side) goes before conversations
    assert sql.index("DROP TABLE messages") < sql.index("DROP TABLE conversations")
