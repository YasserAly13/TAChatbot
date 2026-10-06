"""Settings snapshot — DATABASE_URL default, override and empty-value fallback;
EXTERNAL_DATABASE_URL optional (ADR-0008)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app import config


def test_database_url_defaults_to_azure_sql_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = config.get_settings()
    assert settings.database_url == config.DEFAULT_DATABASE_URL
    # aioodbc dialect on ODBC Driver 18 with validated TLS.
    assert settings.database_url.startswith("mssql+aioodbc://")
    assert "driver=ODBC+Driver+18+for+SQL+Server" in settings.database_url
    assert "Encrypt=yes" in settings.database_url
    assert "TrustServerCertificate=no" in settings.database_url


def test_database_url_honors_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    url = (
        "mssql+aioodbc://u:p@db.example.invalid:1433/app"
        "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes"
    )
    monkeypatch.setenv("DATABASE_URL", url)
    assert config.get_settings().database_url == url


def test_empty_database_url_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    assert config.get_settings().database_url == config.DEFAULT_DATABASE_URL


def test_external_database_url_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EXTERNAL_DATABASE_URL", raising=False)
    settings = config.get_settings()
    assert settings.external_database_url is None
    assert settings.has_external_database is False

    monkeypatch.setenv("EXTERNAL_DATABASE_URL", "  ")  # blank = not configured
    assert config.get_settings().external_database_url is None

    url = "mssql+aioodbc://r:p@dw.invalid:1433/dw?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes"
    monkeypatch.setenv("EXTERNAL_DATABASE_URL", url)
    settings = config.get_settings()
    assert settings.external_database_url == url
    assert settings.has_external_database is True


def test_other_settings_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    settings = config.get_settings()
    assert settings.app_env == "local"
    assert settings.port == config.DEFAULT_PORT


class TestLoadLocalEnv:
    """apps/api/.env is OPTIONAL: missing -> no-op; present -> loaded without overriding."""

    def test_missing_file_is_a_noop(self, tmp_path: Path) -> None:
        assert config.load_local_env(tmp_path / "does-not-exist.env") is False

    def test_loads_values_without_overriding_ambient_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("WT_TEST_FROM_FILE=file\nWT_TEST_AMBIENT=file\n", encoding="utf-8")
        monkeypatch.delenv("WT_TEST_FROM_FILE", raising=False)
        monkeypatch.setenv("WT_TEST_AMBIENT", "shell")

        assert config.load_local_env(env_file) is True
        assert os.environ["WT_TEST_FROM_FILE"] == "file"
        assert os.environ["WT_TEST_AMBIENT"] == "shell"  # ambient wins
        monkeypatch.delenv("WT_TEST_FROM_FILE", raising=False)

    def test_default_target_is_the_service_env_file(self) -> None:
        assert config.LOCAL_ENV_FILE.name == ".env"
        assert config.LOCAL_ENV_FILE.parent.name == "api"
        assert (config.LOCAL_ENV_FILE.parent / ".env.example").is_file()


def test_settings_repr_never_shows_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    secret_url = "mssql+aioodbc://u:p4ss-must-not-show@db.invalid:1433/app?driver=x"
    monkeypatch.setenv("DATABASE_URL", secret_url)
    monkeypatch.setenv("EXTERNAL_DATABASE_URL", secret_url)
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "InstrumentationKey=must-not-show")

    settings = get_settings()

    assert "must-not-show" not in repr(settings)
    assert settings.database_url == secret_url  # still readable in code
