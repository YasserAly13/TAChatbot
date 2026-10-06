"""AI settings snapshot + the client factory (the mock seam) — offline, no Azure calls."""

from __future__ import annotations

import pytest

import app.ai.client as client_mod
from app.ai.config import AINotConfigured, get_ai_settings

ENDPOINT = "https://ais-example.cognitiveservices.azure.com/"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "AZURE_AI_ENDPOINT",
        "AZURE_AI_DEPLOYMENT",
        "AZURE_AI_EMBEDDING_DEPLOYMENT",
        "AZURE_AI_EMBEDDING_DIMENSIONS",
        "AZURE_AI_API_VERSION",
        "AZURE_AI_AUTH_MODE",
        "AZURE_AI_API_KEY",
        "AZURE_SEARCH_ENDPOINT",
        "AZURE_SEARCH_INDEX",
        "AZURE_SEARCH_API_KEY",
        "AI_REQUEST_TIMEOUT_SECONDS",
        "AI_MAX_RETRIES",
        "AI_ALLOW_TEXT_TO_SQL",
    ):
        monkeypatch.delenv(name, raising=False)
    client_mod._reset_for_tests()
    yield
    client_mod._reset_for_tests()


class TestSettings:
    def test_defaults_are_safe(self) -> None:
        s = get_ai_settings()
        assert s.auth_mode == "managed_identity"
        assert s.has_model is False and s.has_embeddings is False and s.has_search is False
        assert s.request_timeout_seconds == 60.0
        assert s.max_retries == 2
        assert s.embedding_dimensions == 1536
        assert s.allow_text_to_sql is False

    def test_require_raises_clear_errors(self) -> None:
        s = get_ai_settings()
        with pytest.raises(AINotConfigured):
            s.require_model()
        with pytest.raises(AINotConfigured):
            s.require_embeddings()
        with pytest.raises(AINotConfigured):
            s.require_search()

    def test_invalid_auth_mode_fails_visibly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AZURE_AI_AUTH_MODE", "keys")
        with pytest.raises(ValueError, match="AZURE_AI_AUTH_MODE"):
            get_ai_settings()

    def test_values_are_read(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AZURE_AI_ENDPOINT", ENDPOINT)
        monkeypatch.setenv("AZURE_AI_DEPLOYMENT", "gpt-4o-mini")
        monkeypatch.setenv("AZURE_AI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
        monkeypatch.setenv("AZURE_AI_EMBEDDING_DIMENSIONS", "3072")
        monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://srch.search.windows.net")
        monkeypatch.setenv("AZURE_SEARCH_INDEX", "docs")
        monkeypatch.setenv("AI_REQUEST_TIMEOUT_SECONDS", "12.5")
        monkeypatch.setenv("AI_MAX_RETRIES", "0")
        monkeypatch.setenv("AI_ALLOW_TEXT_TO_SQL", "true")
        s = get_ai_settings()
        assert s.has_model and s.has_embeddings and s.has_search
        assert s.embedding_dimensions == 3072
        assert s.request_timeout_seconds == 12.5
        assert s.max_retries == 0
        assert s.allow_text_to_sql is True

    def test_bad_numbers_fall_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AI_REQUEST_TIMEOUT_SECONDS", "-3")
        monkeypatch.setenv("AI_MAX_RETRIES", "many")
        monkeypatch.setenv("AZURE_AI_EMBEDDING_DIMENSIONS", "0")
        s = get_ai_settings()
        assert s.request_timeout_seconds == 60.0
        assert s.max_retries == 2
        assert s.embedding_dimensions == 1536


class TestClientFactory:
    def test_api_key_mode_builds_without_credential(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AZURE_AI_ENDPOINT", ENDPOINT)
        monkeypatch.setenv("AZURE_AI_DEPLOYMENT", "gpt-4o-mini")
        monkeypatch.setenv("AZURE_AI_AUTH_MODE", "api_key")
        monkeypatch.setenv("AZURE_AI_API_KEY", "dev-key")
        called: list[bool] = []
        monkeypatch.setattr(client_mod, "_token_provider", lambda: called.append(True))

        model = client_mod.build_chat_model(temperature=0.2)
        assert model.deployment_name == "gpt-4o-mini"
        assert model.azure_endpoint == ENDPOINT
        assert model.temperature == 0.2
        assert model.max_retries == 2
        assert model.azure_ad_token_provider is None
        assert called == []  # no identity credential in api_key mode

    def test_api_key_mode_requires_a_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AZURE_AI_ENDPOINT", ENDPOINT)
        monkeypatch.setenv("AZURE_AI_DEPLOYMENT", "gpt-4o-mini")
        monkeypatch.setenv("AZURE_AI_AUTH_MODE", "api_key")
        with pytest.raises(ValueError, match="AZURE_AI_API_KEY"):
            client_mod.build_chat_model()

    def test_managed_identity_mode_uses_a_token_provider(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("AZURE_AI_ENDPOINT", ENDPOINT)
        monkeypatch.setenv("AZURE_AI_DEPLOYMENT", "gpt-4o-mini")
        monkeypatch.setenv("AZURE_AI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
        provider = lambda: "token"  # noqa: E731
        monkeypatch.setattr(client_mod, "_token_provider", lambda: provider)

        model = client_mod.build_chat_model()
        embeddings = client_mod.build_embeddings()
        assert model.azure_ad_token_provider is provider
        assert model.openai_api_key is None
        assert embeddings.azure_ad_token_provider is provider
        assert embeddings.deployment == "text-embedding-3-small"

    def test_missing_configuration_raises(self) -> None:
        with pytest.raises(AINotConfigured):
            client_mod.build_chat_model()
        with pytest.raises(AINotConfigured):
            client_mod.build_embeddings()

    def test_singletons_are_cached_and_resettable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AZURE_AI_ENDPOINT", ENDPOINT)
        monkeypatch.setenv("AZURE_AI_DEPLOYMENT", "gpt-4o-mini")
        monkeypatch.setenv("AZURE_AI_AUTH_MODE", "api_key")
        monkeypatch.setenv("AZURE_AI_API_KEY", "dev-key")
        first = client_mod.get_chat_model()
        assert client_mod.get_chat_model() is first
        client_mod._reset_for_tests()
        assert client_mod.get_chat_model() is not first
