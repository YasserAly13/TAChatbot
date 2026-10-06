"""``POST /v1/conversations/{conversation_id}/ask`` (roadmap api 4.1).

No database, model or index: a fake ``AsyncSession`` (from ``test_conversations``) and the
``retrieve → answer`` graph built with the fake chat model and retriever (rule 70).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
import structlog.testing
from fastapi.testclient import TestClient

import app.routers.conversations as module
from app.ai.graph import Answer, build_graph
from app.db import get_session
from app.main import app
from app.models.conversation import DEFAULT_TITLE, Conversation, Message
from app.repositories import conversations as repo
from app.routers.conversations import get_answer_graph
from tests.ai.fakes import FakeRetriever, fake_chat_model
from tests.fakes import INBOUND_TRACE, FakeSession
from tests.fakes import make_conversation as _conversation

CHUNKS = [
    {
        "id": "1",
        "content": "The BFF mints the trace id.",
        "source": "docs/tracing.md",
        "title": "Tracing",
        "score": 1.0,
    },
    {"id": "2", "content": "More on tracing.", "source": "docs/tracing.md", "score": 0.9},
    {"id": "3", "content": "Observability.", "source": "README.md", "score": 0.8},
]
ANSWER = "Trace ids are minted by the BFF [1]."


class FailingGraph:
    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        raise TimeoutError("model did not answer: <prompt text that must not be logged>")


@pytest.fixture()
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture()
def retriever() -> FakeRetriever:
    return FakeRetriever(CHUNKS)  # type: ignore[arg-type]


def _client(session: FakeSession, graph: Any) -> TestClient:
    async def fake_get_session():
        yield session

    app.dependency_overrides[get_session] = fake_get_session
    app.dependency_overrides[get_answer_graph] = lambda: graph
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def client(session: FakeSession, retriever: FakeRetriever):
    graph = build_graph(
        chat_model=fake_chat_model(ANSWER), retriever=retriever, deployment_label="test"
    )
    yield _client(session, graph)
    app.dependency_overrides.pop(get_session, None)
    app.dependency_overrides.pop(get_answer_graph, None)


def _new_conversation(session: FakeSession, title: str = DEFAULT_TITLE) -> Conversation:
    conversation = _conversation(title, datetime(2026, 10, 6, 9, 0))
    conversation.messages = []
    session.rows = [conversation]
    return conversation


def _ask(client: TestClient, conversation: Conversation, payload: Any, **kwargs: Any):
    return client.post(f"/v1/conversations/{conversation.id}/ask", json=payload, **kwargs)


def test_ask_answers_with_citations_and_stores_both_messages(
    client: TestClient, session: FakeSession, retriever: FakeRetriever
) -> None:
    conversation = _new_conversation(session)

    res = _ask(
        client,
        conversation,
        {"question": "  How are trace ids made?  "},
        headers={"x-trace-id": INBOUND_TRACE},
    )

    assert res.status_code == 200
    assert res.headers["x-trace-id"] == INBOUND_TRACE
    body = res.json()
    assert body["answer"] == ANSWER
    assert body["citations"] == [
        {"title": "Tracing", "path": "docs/tracing.md"},
        {"title": "README.md", "path": "README.md"},
    ]
    assert retriever.calls[0][0] == "How are trace ids made?"  # trimmed
    user, assistant = session.added
    assert (user.role, user.content) == ("user", "How are trace ids made?")
    assert (assistant.role, str(assistant.id)) == ("assistant", body["message_id"])
    assert json.loads(assistant.citations) == body["citations"]
    assert assistant.token_count == 5
    assert user.created_at < assistant.created_at
    assert session.commits == 2  # the question is committed before the model is called


def test_the_first_question_becomes_the_title(client: TestClient, session: FakeSession) -> None:
    conversation = _new_conversation(session)

    _ask(client, conversation, {"question": "Why  UTC?"})

    assert conversation.title == "Why UTC?"


def test_a_given_title_is_kept(client: TestClient, session: FakeSession) -> None:
    conversation = _new_conversation(session, title="My chat")

    _ask(client, conversation, {"question": "Why UTC?"})

    assert conversation.title == "My chat"


def test_the_last_10_messages_are_sent_as_history(
    client: TestClient, session: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = _new_conversation(session, title="Long")
    conversation.messages = [
        Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"m{i}",
            created_at=datetime(2026, 10, 6, 9, 0, i),
        )
        for i in range(14)
    ]
    seen: dict[str, Any] = {}

    async def fake_ask(graph: Any, question: str, *, history: Any = None) -> Answer:
        seen["history"] = history
        return Answer(text="ok")

    monkeypatch.setattr(module, "ask", fake_ask)

    res = _ask(client, conversation, {"question": "next"})

    assert res.status_code == 200 and res.json()["citations"] == []
    assert [m.content for m in seen["history"]] == [f"m{i}" for i in range(4, 14)]
    assert [type(m).__name__ for m in seen["history"][:2]] == ["HumanMessage", "AIMessage"]


def test_ask_an_unknown_conversation_is_a_404(client: TestClient, session: FakeSession) -> None:
    res = client.post(f"/v1/conversations/{uuid4()}/ask", json={"question": "hello"})

    assert res.status_code == 404 and res.json()["error"] == "not_found"
    assert session.added == []


@pytest.mark.parametrize(
    "payload",
    [{}, {"question": ""}, {"question": "   "}, {"question": "q" * 4001}, {"question": 7}],
)
def test_ask_rejects_a_missing_empty_or_too_long_question(
    client: TestClient, session: FakeSession, payload: dict[str, Any]
) -> None:
    conversation = _new_conversation(session)

    res = _ask(client, conversation, payload)

    assert res.status_code == 422 and res.json()["error"] == "validation_error"
    assert session.added == []


def test_a_4000_character_question_is_accepted(client: TestClient, session: FakeSession) -> None:
    conversation = _new_conversation(session)

    assert _ask(client, conversation, {"question": "q" * 4000}).status_code == 200


def test_a_model_failure_is_a_503_and_keeps_the_question(session: FakeSession) -> None:
    conversation = _new_conversation(session)
    client = _client(session, FailingGraph())
    try:
        with structlog.testing.capture_logs() as logs:
            res = _ask(
                client,
                conversation,
                {"question": "secret question"},
                headers={"x-trace-id": INBOUND_TRACE},
            )
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_answer_graph, None)

    assert res.status_code == 503
    assert res.json() == {"error": "ai_unavailable", "trace_id": INBOUND_TRACE}
    [user] = session.added  # the question was stored and committed; no answer
    assert (user.role, user.content) == ("user", "secret question")
    assert session.commits == 1
    [failure] = [e for e in logs if e["event"] == "ask failed"]
    assert failure["error_kind"] == "timeout"
    assert "secret question" not in str(logs) and "prompt text" not in str(logs)


def test_the_answer_graph_is_built_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module, "_graph", None)

    first = asyncio.run(module.get_answer_graph())

    assert asyncio.run(module.get_answer_graph()) is first


def test_touch_never_moves_updated_at_backwards() -> None:
    ahead = datetime(2099, 1, 1)
    conversation = _conversation("x", ahead)

    repo.rename(conversation, "renamed")
    assert conversation.updated_at == ahead
    repo.touch(conversation, datetime(2000, 1, 1))
    assert conversation.updated_at == ahead


# --- review fixes: history, failure classes, deadline -----------------------------------------


class _RaisingGraph:
    def __init__(self, exc: BaseException) -> None:
        self.exc = exc

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        raise self.exc


class _SlowGraph:
    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        await asyncio.sleep(5)


def _ask_with(session: FakeSession, graph: Any, question: str = "q"):
    conversation = _new_conversation(session, title="Chat")
    client = _client(session, graph)
    try:
        return _ask(client, conversation, {"question": question})
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_answer_graph, None)


def test_a_second_question_sees_the_first_turn_as_history(
    client: TestClient, session: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = _new_conversation(session)
    _ask(client, conversation, {"question": "first?"})
    conversation.messages = list(session.added)  # what a real session would reload
    seen: dict[str, Any] = {}

    async def fake_ask(graph: Any, question: str, *, history: Any = None) -> Answer:
        seen["history"] = history
        return Answer(text="second answer")

    monkeypatch.setattr(module, "ask", fake_ask)
    _ask(client, conversation, {"question": "second?"})

    assert [(type(m).__name__, m.content) for m in seen["history"]] == [
        ("HumanMessage", "first?"),
        ("AIMessage", ANSWER),
    ]


def test_an_unanswered_question_is_left_out_of_the_history(
    client: TestClient, session: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    conversation = _new_conversation(session, title="Retry")
    times = [datetime(2026, 10, 6, 9, 0, s) for s in range(3)]
    conversation.messages = [
        Message(id=uuid4(), conversation_id=conversation.id, role=r, content=c, created_at=t)
        for (r, c), t in zip(
            [("user", "q1"), ("assistant", "a1"), ("user", "q2 failed")], times, strict=True
        )
    ]
    seen: dict[str, Any] = {}

    async def fake_ask(graph: Any, question: str, *, history: Any = None) -> Answer:
        seen["history"] = history
        return Answer(text="ok")

    monkeypatch.setattr(module, "ask", fake_ask)
    _ask(client, conversation, {"question": "q2 failed"})

    assert [m.content for m in seen["history"]] == ["q1", "a1"]


def test_a_missing_ai_configuration_is_a_503_from_its_own_handler(session: FakeSession) -> None:
    from app.ai.config import AINotConfigured

    with structlog.testing.capture_logs() as logs:
        res = _ask_with(session, _RaisingGraph(AINotConfigured("AZURE_AI_ENDPOINT is not set")))

    assert res.status_code == 503 and res.json()["error"] == "ai_unavailable"
    assert not [e for e in logs if e["event"] == "ask failed"]  # not swallowed by the route


def test_a_bug_is_a_500_not_a_503(session: FakeSession) -> None:
    res = _ask_with(session, _RaisingGraph(KeyError("context")))

    assert res.status_code == 500 and res.json()["error"] == "internal_error"
    [user] = session.added  # the question is still kept
    assert user.role == "user"


def test_an_empty_answer_is_a_503(session: FakeSession) -> None:
    graph = build_graph(
        chat_model=fake_chat_model("   "), retriever=FakeRetriever(), deployment_label="t"
    )

    res = _ask_with(session, graph)

    assert res.status_code == 503 and res.json()["error"] == "ai_unavailable"
    assert [m.role for m in session.added] == ["user"]


def test_the_whole_ask_has_a_deadline(
    session: FakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(module, "_ask_deadline_seconds", lambda: 0.05)

    with structlog.testing.capture_logs() as logs:
        res = _ask_with(session, _SlowGraph())

    assert res.status_code == 503
    [failure] = [e for e in logs if e["event"] == "ask failed"]
    assert failure["error_kind"] == "timeout"


def test_the_deadline_is_twice_the_per_call_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_REQUEST_TIMEOUT_SECONDS", "30")
    assert module._ask_deadline_seconds() == 60


def test_if_storing_the_answer_fails_the_question_stays_and_it_is_a_500() -> None:
    session = FakeSession(fail_commit_after=1)

    res = _ask_with(
        session, build_graph(chat_model=fake_chat_model(ANSWER), retriever=FakeRetriever())
    )

    assert res.status_code == 500
    assert session.commits == 1  # the question was committed; the answer's commit failed


def test_title_from_question_collapses_whitespace_and_fits_the_column() -> None:
    assert repo.title_from_question("  how\n  does   it work? ") == "how does it work?"
    assert len(repo.title_from_question("x" * 500)) == 200
