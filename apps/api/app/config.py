"""Runtime configuration read from environment variables.

Shared monorepo contract:
    - Ports: web=3000, api=8000 (this service listens on 8000).
    - Service identity name = "api", trace origin = "0c70".
    - Env var names: APP_ENV, APPLICATIONINSIGHTS_CONNECTION_STRING,
      OTEL_SERVICE_NAME, PORT, DATABASE_URL, EXTERNAL_DATABASE_URL (optional).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# apps/api/.env — the local-dev env file (copy of .env.example). Optional.
LOCAL_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


def load_local_env(path: Path | None = None) -> bool:
    """Load ``apps/api/.env`` into the process env for LOCAL DEV, if it exists.

    - Missing file → no-op (returns False): the service, ``just dev`` and Docker
      never require a ``.env`` (Docker/Compose supply real env; tests run without one).
    - Never overrides ambient/shell env (``override=False``), matching the
      root/compose precedence rules documented in the README.
    - Must run before anything reads settings, so ``app.main`` calls it first.
    """
    target = path or LOCAL_ENV_FILE
    if not target.is_file():
        return False
    return load_dotenv(target, override=False)


# This service's fixed identity (part of the shared cross-service contract).
SERVICE_NAME = "api"
DEFAULT_OTEL_SERVICE_NAME = "team-assistant-api"
DEFAULT_PORT = 8000
# Distribution name as declared in pyproject.toml ([project].name).
DISTRIBUTION_NAME = "team-assistant-api"
# Placeholder DATABASE_URL — Azure SQL Database via the `mssql+aioodbc` dialect
# (ADR-0008). The engine is lazy, so the baseline boots with this unreachable
# placeholder — no connection is opened until the first query. Query-string
# keywords are forwarded to the ODBC connection string: `driver` selects
# Microsoft ODBC Driver 18 (spaces URL-encoded as `+`), `Encrypt=yes` +
# `TrustServerCertificate=no` enforce validated TLS. Deployed apps use the
# managed-identity form infra/main.bicep writes to Key Vault instead of USER:PASSWORD:
#   mssql+aioodbc://<identity-client-id>@<server>.database.windows.net:1433/<db>
#     ?driver=...&Encrypt=yes&TrustServerCertificate=no&Authentication=ActiveDirectoryMsi
# Passwords with reserved characters must be URL-encoded.
DEFAULT_DATABASE_URL = (
    "mssql+aioodbc://USER:PASSWORD@your-server.database.windows.net:1433/your-database"
    "?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no"
)


def get_version() -> str:
    """Installed package version, read from distribution metadata.

    Uses ``importlib.metadata`` (the project is installed into the venv by
    ``uv sync``), so it works in the Docker runtime where pyproject.toml is not
    shipped. Falls back to "unknown" rather than raising.
    """
    try:
        from importlib.metadata import PackageNotFoundError, version

        try:
            return version(DISTRIBUTION_NAME)
        except PackageNotFoundError:
            return "unknown"
    except Exception:  # noqa: BLE001 - version reporting must never crash a request
        return "unknown"


def _normalize_env(value: str | None) -> str:
    """Normalize APP_ENV; unknown/missing is treated as local."""
    if not value:
        return "local"
    return value.strip().lower()


@dataclass(frozen=True)
class Settings:
    """Immutable, process-wide settings snapshot."""

    app_env: str
    otel_service_name: str
    port: int
    applicationinsights_connection_string: str
    # SQLAlchemy async URL (mssql+aioodbc://…). Read lazily by app.db.engine;
    # never logged (carries credentials).
    database_url: str
    # Optional READ-ONLY external database (mssql+aioodbc://…), read lazily by
    # app.db.external. None = not configured (the external engine refuses to build).
    external_database_url: str | None

    @property
    def has_connection_string(self) -> bool:
        return bool(self.applicationinsights_connection_string.strip())

    @property
    def has_external_database(self) -> bool:
        return self.external_database_url is not None


def _read_port(raw: str | None) -> int:
    if not raw:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_PORT


def get_settings() -> Settings:
    """Build a Settings snapshot from the current environment."""
    return Settings(
        app_env=_normalize_env(os.getenv("APP_ENV")),
        otel_service_name=os.getenv("OTEL_SERVICE_NAME", DEFAULT_OTEL_SERVICE_NAME),
        port=_read_port(os.getenv("PORT")),
        applicationinsights_connection_string=os.getenv(
            "APPLICATIONINSIGHTS_CONNECTION_STRING", ""
        ),
        # Empty counts as unset so `DATABASE_URL=` in a .env still boots the service.
        database_url=os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL,
        # Empty/missing = no external database; there is deliberately no placeholder.
        external_database_url=(os.getenv("EXTERNAL_DATABASE_URL") or "").strip() or None,
    )
