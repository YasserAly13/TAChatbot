"""The retrieve → answer graph and its SSE streaming — with a fake model and retriever."""

from __future__ import annotations

import asyncio
import json

import pytest
from langchain_core.messages import HumanMessage

import app.ai.tools.retrieve as retrieve_mod
from app.ai.graph import ask, build_graph, format_context, last_user_text
from app.ai.streaming import sse, sse_response, stream_answer
from app.ai.tools.retrieve import NullRetriever
from tests.ai.fakes import FakeRetriever, fake_chat_model

CHUNKS = [
    {"id": "1", "content": "The api listens on port 8000.", "source": "docs/api.md", "score": 0.9},
    {"id": "2", "content": "The web app listens on 3000.", "source": "docs/web.md", "score": 0.8},
    {"id": "3", "content": "Duplicate source chunk.", "source": "docs/api.md", "score": 0.7},
]


@pytest.fixture(autouse=True)
def _reset():
    retrieve_mod._reset_for_tests()
    yield
    retrieve_mod._reset_for_tests()


def test_format_context_numbers_chunks_and_handles_empty() -> None:
    assert format_context([]) == "(no context available)"
    text = format_context(CHUNKS[:2])
    assert text.startswith("[1] (docs/api.md)")
    assert "[2] (docs/web.md)" in text


def test_last_user_text_picks_the_latest_human_turn() -> None:
    assert last_user_text([]) == ""
    assert last_user_text([HumanMessage(content="a"), HumanMessage(content="b")]) == "b"


def test_ask_runs_retrieval_then_model_and_collects_sources() -> None:
    retriever = FakeRetriever(CHUNKS)
    graph = build_graph(
        chat_model=fake_chat_model("Port 8000 [1]."),
        retriever=retriever,
        top_k=2,
        deployment_label="test",
    )
    answer = asyncio.run(ask(graph, "which port?"))
    assert answer.text == "Port 8000 [1]."
    assert retriever.calls == [("which port?", 2)]
    assert answer.sources == ["docs/api.md", "docs/web.md"]
    assert answer.input_tokens == 10 and answer.output_tokens == 5


def test_graph_without_retriever_falls_back_to_null_retriever(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AZURE_SEARCH_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_SEARCH_INDEX", raising=False)
    assert isinstance(retrieve_mod.get_default_retriever(), NullRetriever)
    graph = build_graph(chat_model=fake_chat_model("I do not know."), deployment_label="test")
    answer = asyncio.run(ask(graph, "anything"))
    assert answer.text == "I do not know."
    assert answer.sources == [] and answer.context == []


def test_history_is_passed_through() -> None:
    model = fake_chat_model("second answer")
    graph = build_graph(chat_model=model, retriever=FakeRetriever(), deployment_label="test")
    answer = asyncio.run(ask(graph, "follow-up", history=[HumanMessage(content="first")]))
    assert answer.text == "second answer"


def test_graph_with_tools_compiles_a_tool_loop() -> None:
    from langchain_core.tools import tool

    @tool
    def echo(text: str) -> str:
        """Echo."""
        return text

    graph = build_graph(chat_model=fake_chat_model("x"), retriever=FakeRetriever(), tools=[echo])
    assert "tools" in graph.get_graph().nodes


def test_sse_frame_format() -> None:
    frame = sse("token", {"text": "héllo"})
    assert frame == 'event: token\ndata: {"text": "héllo"}\n\n'


def _collect(frames) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    for frame in frames:
        event = frame.split("\n")[0].removeprefix("event: ")
        data = json.loads(frame.split("\n")[1].removeprefix("data: "))
        out.append((event, data))
    return out


def test_stream_answer_yields_sources_tokens_done() -> None:
    graph = build_graph(
        chat_model=fake_chat_model("alpha beta"),
        retriever=FakeRetriever(CHUNKS[:1]),
        deployment_label="test",
    )

    async def run() -> list[str]:
        return [f async for f in stream_answer(graph, "q")]

    events = _collect(asyncio.run(run()))
    kinds = [e for e, _ in events]
    assert kinds[0] == "sources"
    assert events[0][1] == {"sources": ["docs/api.md"], "count": 1}
    assert kinds[-1] == "done"
    tokens = "".join(d["text"] for e, d in events if e == "token")
    assert tokens == "alpha beta"
    assert events[-1][1]["sources"] == ["docs/api.md"]
    # Usage is provider-reported; a streaming fake aggregates chunks without it, so the
    # contract is "the keys are present, values may be None".
    assert set(events[-1][1]) == {"sources", "input_tokens", "output_tokens"}


def test_stream_answer_emits_bounded_error_frame() -> None:
    class Boom:
        async def retrieve(self, query: str, top_k: int = 5):
            raise TimeoutError("secret details must not leak")

    graph = build_graph(chat_model=fake_chat_model("x"), retriever=Boom(), deployment_label="test")

    async def run() -> list[str]:
        return [f async for f in stream_answer(graph, "q")]

    events = _collect(asyncio.run(run()))
    assert events[-1] == ("error", {"error_kind": "timeout"})
    assert "secret" not in json.dumps(events)


def test_sse_response_headers() -> None:
    async def frames():
        yield sse("done", {})

    response = sse_response(frames())
    assert response.media_type == "text/event-stream"
    assert response.headers["cache-control"] == "no-cache"
