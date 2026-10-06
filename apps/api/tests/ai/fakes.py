"""Offline doubles shared by the AI tests (rule 70 → Testing)."""

from __future__ import annotations

from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app.ai.tools.retrieve import RetrievedChunk


def fake_chat_model(*answers: str, usage: bool = True) -> GenericFakeChatModel:
    """A LangChain fake that returns the given answers in order (streams word by word)."""
    messages = [
        AIMessage(
            content=text,
            usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}
            if usage
            else None,
        )
        for text in answers
    ]
    return GenericFakeChatModel(messages=iter(messages))


class FakeEmbeddings(Embeddings):
    """Deterministic vectors: length = dimensions, first value = text length."""

    def __init__(self, dimensions: int = 4) -> None:
        self.dimensions = dimensions
        self.queries: list[str] = []
        self.documents: list[list[str]] = []

    def _vec(self, text: str) -> list[float]:
        return [float(len(text))] + [0.0] * (self.dimensions - 1)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.documents.append(list(texts))
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        self.queries.append(text)
        return self._vec(text)


class FakeRetriever:
    def __init__(self, chunks: list[RetrievedChunk] | None = None) -> None:
        self.chunks = chunks or []
        self.calls: list[tuple[str, int]] = []

    async def retrieve(self, query: str, top_k: int = 5) -> list[RetrievedChunk]:
        self.calls.append((query, top_k))
        return self.chunks[:top_k]


class FakeSearchClient:
    """Records ``search``/``upload_documents`` calls; returns canned rows."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.search_calls: list[dict[str, Any]] = []
        self.uploaded: list[list[dict[str, Any]]] = []

    def search(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.search_calls.append(kwargs)
        return list(self.rows)

    def upload_documents(self, documents: list[dict[str, Any]]) -> list[Any]:
        self.uploaded.append(list(documents))

        class _Result:
            succeeded = True

        return [_Result() for _ in documents]


class FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> FakeResult:
        return self

    def fetchmany(self, limit: int) -> list[dict[str, Any]]:
        return self._rows[:limit]


class FakeSession:
    """Async-context session that records the statement + params it executes."""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []
        self.executed: list[tuple[str, Any]] = []

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def execute(self, statement: Any, params: Any = None) -> FakeResult:
        self.executed.append((str(statement), params))
        return FakeResult(self.rows)


def fake_session_factory(session: FakeSession) -> Any:
    """Mimics ``get_external_sessionmaker``: returns a factory whose call yields the session."""

    def factory() -> Any:
        return lambda: session

    return factory
