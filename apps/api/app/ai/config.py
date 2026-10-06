"""AI runtime configuration (ADR-0009) — read from environment variables.

Nothing here is a secret except ``AZURE_AI_API_KEY`` / ``AZURE_SEARCH_API_KEY``, which exist for
LOCAL DEV ONLY: deployed apps authenticate with their managed identity
(``AZURE_AI_AUTH_MODE=managed_identity``; ``DefaultAzureCredential`` picks the user-assigned
identity from ``AZURE_CLIENT_ID``, which the use-case Bicep sets on the Container App).

Like ``app.config``, this is a snapshot: call ``get_ai_settings()`` when you need it, never
cache it at import (tests monkeypatch the environment).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

AUTH_MODES = ("managed_identity", "api_key")
DEFAULT_API_VERSION = "2024-10-21"
DEFAULT_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_RETRIES = 2
# Cap on each answer's length (and cost) — ~700–800 English words. 0 = no cap.
DEFAULT_MAX_OUTPUT_TOKENS = 1024
# text-embedding-3-small / ada-002 produce 1536-dimensional vectors; large = 3072.
DEFAULT_EMBEDDING_DIMENSIONS = 1536


class AINotConfigured(RuntimeError):
    """A required AI setting is missing — the feature cannot run in this deployment."""


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _float_env(name: str, default: float) -> float:
    raw = _env(name)
    if raw is None:
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _bool_env(name: str) -> bool:
    return (_env(name) or "").lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class AISettings:
    """Immutable snapshot of the AI-related environment."""

    endpoint: str | None
    chat_deployment: str | None
    embedding_deployment: str | None
    # Vector size of the embedding deployment (index definition + query vectors).
    embedding_dimensions: int
    api_version: str
    auth_mode: str
    api_key: str | None
    search_endpoint: str | None
    search_index: str | None
    search_api_key: str | None
    request_timeout_seconds: float
    max_retries: int
    allow_text_to_sql: bool
    # Output-token cap per model call (AI_MAX_OUTPUT_TOKENS); None = no cap.
    max_output_tokens: int | None = DEFAULT_MAX_OUTPUT_TOKENS

    @property
    def has_model(self) -> bool:
        return bool(self.endpoint and self.chat_deployment)

    @property
    def has_embeddings(self) -> bool:
        return bool(self.endpoint and self.embedding_deployment)

    @property
    def has_search(self) -> bool:
        return bool(self.search_endpoint and self.search_index)

    def require_model(self) -> None:
        if not self.has_model:
            raise AINotConfigured(
                "AZURE_AI_ENDPOINT and AZURE_AI_DEPLOYMENT must be set to use the chat model"
            )

    def require_embeddings(self) -> None:
        if not self.has_embeddings:
            raise AINotConfigured(
                "AZURE_AI_ENDPOINT and AZURE_AI_EMBEDDING_DEPLOYMENT must be set to use embeddings"
            )

    def require_search(self) -> None:
        if not self.has_search:
            raise AINotConfigured(
                "AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_INDEX must be set to use retrieval"
            )


def get_ai_settings() -> AISettings:
    """Build a settings snapshot from the current environment.

    Raises ``ValueError`` for an unknown ``AZURE_AI_AUTH_MODE`` — a mistyped value must fail
    visibly, never fall back to a key or to anonymous access.
    """
    auth_mode = (_env("AZURE_AI_AUTH_MODE") or "managed_identity").lower()
    if auth_mode not in AUTH_MODES:
        raise ValueError(
            f'invalid AZURE_AI_AUTH_MODE "{auth_mode}" — expected one of {", ".join(AUTH_MODES)}'
        )
    max_retries_raw = _env("AI_MAX_RETRIES")
    try:
        max_retries = int(max_retries_raw) if max_retries_raw else DEFAULT_MAX_RETRIES
    except ValueError:
        max_retries = DEFAULT_MAX_RETRIES
    max_output_raw = _env("AI_MAX_OUTPUT_TOKENS")
    try:
        max_output = int(max_output_raw) if max_output_raw else DEFAULT_MAX_OUTPUT_TOKENS
    except ValueError:
        max_output = DEFAULT_MAX_OUTPUT_TOKENS
    if max_output < 0:
        max_output = DEFAULT_MAX_OUTPUT_TOKENS
    dims_raw = _env("AZURE_AI_EMBEDDING_DIMENSIONS")
    try:
        dims = int(dims_raw) if dims_raw else DEFAULT_EMBEDDING_DIMENSIONS
    except ValueError:
        dims = DEFAULT_EMBEDDING_DIMENSIONS
    return AISettings(
        endpoint=_env("AZURE_AI_ENDPOINT"),
        chat_deployment=_env("AZURE_AI_DEPLOYMENT"),
        embedding_deployment=_env("AZURE_AI_EMBEDDING_DEPLOYMENT"),
        embedding_dimensions=dims if dims > 0 else DEFAULT_EMBEDDING_DIMENSIONS,
        api_version=_env("AZURE_AI_API_VERSION") or DEFAULT_API_VERSION,
        auth_mode=auth_mode,
        api_key=_env("AZURE_AI_API_KEY"),
        search_endpoint=_env("AZURE_SEARCH_ENDPOINT"),
        search_index=_env("AZURE_SEARCH_INDEX"),
        search_api_key=_env("AZURE_SEARCH_API_KEY"),
        request_timeout_seconds=_float_env("AI_REQUEST_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS),
        max_retries=max(0, max_retries),
        allow_text_to_sql=_bool_env("AI_ALLOW_TEXT_TO_SQL"),
        max_output_tokens=max_output or None,
    )
