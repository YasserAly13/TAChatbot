"""Model + embedding client factory — THE mock seam (ADR-0009).

Every model call in the service goes through a client built here, so tests replace exactly
one thing: ``monkeypatch.setattr(app.ai.client, "get_chat_model", lambda: fake)`` — or pass a
fake straight into ``build_graph(chat_model=...)``.

AUTH: ``managed_identity`` (the deployed default) hands ``langchain-openai`` a bearer-token
provider built from ``DefaultAzureCredential`` for the Cognitive Services scope; the api's
user-assigned identity is selected through ``AZURE_CLIENT_ID`` (set by the use-case Bicep).
``api_key`` is for local dev only (the key comes from Key Vault, never from a param file or a
committed file).

LAZY: nothing here talks to Azure at import or at construction — ``DefaultAzureCredential``
fetches a token on the first request, and the OpenAI client opens no connection until then.
Field names below were verified against the installed ``langchain-openai`` 1.6.6 models
(``azure_endpoint``, ``azure_deployment``, ``api_version``, ``api_key``,
``azure_ad_token_provider``, ``timeout``, ``max_retries``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel

from app.ai.config import AISettings, get_ai_settings
from app.logging_config import get_logger

# Entra ID scope for Azure OpenAI / AI Services.
COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"

_chat_model: BaseChatModel | None = None
_embeddings: Embeddings | None = None


def _token_provider() -> Callable[[], str]:
    """Bearer-token provider for the Cognitive Services scope (managed identity when deployed)."""
    from azure.identity import DefaultAzureCredential, get_bearer_token_provider

    return get_bearer_token_provider(DefaultAzureCredential(), COGNITIVE_SERVICES_SCOPE)


def _auth_kwargs(settings: AISettings) -> dict[str, Any]:
    if settings.auth_mode == "api_key":
        if not settings.api_key:
            raise ValueError("AZURE_AI_AUTH_MODE=api_key but AZURE_AI_API_KEY is empty")
        return {"api_key": settings.api_key}
    return {"azure_ad_token_provider": _token_provider()}


def build_chat_model(
    *,
    settings: AISettings | None = None,
    temperature: float = 0.0,
    streaming: bool = False,
    **overrides: Any,
) -> BaseChatModel:
    """Build a fresh ``AzureChatOpenAI`` for the configured deployment (no caching)."""
    from langchain_openai import AzureChatOpenAI

    s = settings or get_ai_settings()
    s.require_model()
    kwargs: dict[str, Any] = {
        "azure_endpoint": s.endpoint,
        "azure_deployment": s.chat_deployment,
        "api_version": s.api_version,
        "timeout": s.request_timeout_seconds,
        "max_retries": s.max_retries,
        "temperature": temperature,
        "streaming": streaming,
        # Ask Azure OpenAI to report token usage on the final streamed chunk too, so
        # telemetry sees input/output tokens for streamed answers (field verified in 1.6.6).
        "stream_usage": True,
        # Caps each answer's length and cost; sent as max_completion_tokens (verified in
        # langchain-openai 1.6.6). AI_MAX_OUTPUT_TOKENS=0 removes the cap.
        **({"max_tokens": s.max_output_tokens} if s.max_output_tokens else {}),
        **_auth_kwargs(s),
        **overrides,
    }
    model = AzureChatOpenAI(**kwargs)
    get_logger("app.ai.client").info(
        "chat model client built (lazy — no request made)",
        deployment=s.chat_deployment,
        auth_mode=s.auth_mode,
        api_version=s.api_version,
    )
    return model


def build_embeddings(*, settings: AISettings | None = None, **overrides: Any) -> Embeddings:
    """Build a fresh ``AzureOpenAIEmbeddings`` for the configured embedding deployment."""
    from langchain_openai import AzureOpenAIEmbeddings

    s = settings or get_ai_settings()
    s.require_embeddings()
    kwargs: dict[str, Any] = {
        "azure_endpoint": s.endpoint,
        "azure_deployment": s.embedding_deployment,
        "api_version": s.api_version,
        "timeout": s.request_timeout_seconds,
        "max_retries": s.max_retries,
        **_auth_kwargs(s),
        **overrides,
    }
    embeddings = AzureOpenAIEmbeddings(**kwargs)
    get_logger("app.ai.client").info(
        "embeddings client built (lazy — no request made)",
        deployment=s.embedding_deployment,
        auth_mode=s.auth_mode,
    )
    return embeddings


def get_chat_model() -> BaseChatModel:
    """Process-wide chat model (built on first use)."""
    global _chat_model
    if _chat_model is None:
        _chat_model = build_chat_model()
    return _chat_model


def get_embeddings() -> Embeddings:
    """Process-wide embeddings client (built on first use)."""
    global _embeddings
    if _embeddings is None:
        _embeddings = build_embeddings()
    return _embeddings


def _reset_for_tests() -> None:
    """TEST-ONLY: forget the cached clients."""
    global _chat_model, _embeddings
    _chat_model = None
    _embeddings = None
