"""The AI runtime slot of the baseline (ADR-0009) — LangChain + LangGraph on Azure AI
Foundry, Azure AI Search for retrieval, a read-only external-database tool.

- ``config.py``     — ``get_ai_settings()``: the ``AZURE_AI_*`` / ``AZURE_SEARCH_*`` / ``AI_*``
                      environment.
- ``client.py``     — ``get_chat_model()`` / ``get_embeddings()``: THE mock seam; managed
                      identity when deployed, API key only in dev.
- ``telemetry.py``  — ``model_call_span()`` + token/latency/failure metrics; never content.
- ``prompts/``      — versioned prompt files + ``load_prompt(name)``.
- ``graph.py``      — ``build_graph()``: the ``retrieve → answer`` LangGraph skeleton
                      (optional tool loop).
- ``tools/``        — ``retrieve.py`` (Azure AI Search), ``query_external_db.py``
                      (allow-listed, parameterised, read-only), the tool registry.
- ``streaming.py``  — Server-Sent Events helpers for streamed answers under ``/v1``.
- ``ingest.py``     — RAG ingestion job: chunk → embed → upload; owns the index definition.

Rules: ``.claude/rules/70-ai.md``. Nothing here connects at import; every client is lazy.
"""

from __future__ import annotations

from app.ai.config import AINotConfigured, AISettings, get_ai_settings

__all__ = ["AINotConfigured", "AISettings", "get_ai_settings"]
