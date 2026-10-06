"""Alembic is wired but idle (ADR-0004 / ADR-0008): no hard-coded URL, no revisions,
and the async ``env.py`` runs in OFFLINE mode with no database and no connection
— rendering for the SQL Server dialect.
"""

from __future__ import annotations

import io
import logging
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


@pytest.fixture()
def _restore_logging():
    """env.py applies alembic.ini's CLI logging via fileConfig; undo it afterwards
    so the service's stdlib logging setup is untouched for the rest of the run."""
    root = logging.getLogger()
    saved = (root.level, list(root.handlers))
    yield
    root.setLevel(saved[0])
    root.handlers[:] = saved[1]
    for name in ("alembic", "sqlalchemy.engine"):
        logger = logging.getLogger(name)
        logger.handlers[:] = []
        logger.setLevel(logging.NOTSET)
        logger.propagate = True


def test_ini_has_no_hardcoded_database_url() -> None:
    assert "sqlalchemy.url" not in INI.read_text(encoding="utf-8")


def test_script_location_resolves_to_the_alembic_dir() -> None:
    script = ScriptDirectory.from_config(_config())
    assert Path(script.dir).resolve() == (SERVICE_ROOT / "alembic").resolve()
    assert (SERVICE_ROOT / "alembic" / "script.py.mako").is_file()


def test_versions_dir_exists_and_holds_no_revisions() -> None:
    assert VERSIONS.is_dir()
    assert [p.name for p in VERSIONS.iterdir() if p.suffix == ".py"] == []
    assert ScriptDirectory.from_config(_config()).get_heads() == []


def test_env_py_reads_url_from_settings_and_targets_base_metadata() -> None:
    source = ENV_PY.read_text(encoding="utf-8")
    compile(source, str(ENV_PY), "exec")  # syntactically valid
    assert "get_settings().database_url" in source
    assert "target_metadata = Base.metadata" in source
    assert "import app.models" in source
    assert 'config.get_main_option("sqlalchemy.url")' not in source


@pytest.mark.usefixtures("_restore_logging")
def test_offline_upgrade_runs_without_a_database(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts: list[tuple[Any, ...]] = []

    def fake_connect(*args: Any, **kwargs: Any) -> None:
        attempts.append((args, kwargs))
        raise AssertionError("offline mode must never connect")

    monkeypatch.setattr(pyodbc, "connect", fake_connect)
    monkeypatch.setenv("DATABASE_URL", TEST_URL)

    output = io.StringIO()
    command.upgrade(_config(output), "head", sql=True)  # `alembic upgrade head --sql`

    assert attempts == []
    # No revisions -> no DDL is emitted; only the transaction wrapper may appear.
    # The SQL Server dialect renders it as BEGIN TRANSACTION / COMMIT (+ GO
    # batch separators); nothing else is acceptable.
    emitted = [line.strip().rstrip(";") for line in output.getvalue().splitlines() if line.strip()]
    assert all(line in ("BEGIN TRANSACTION", "BEGIN", "COMMIT", "GO") for line in emitted), emitted
