"""``/v1/conversations`` create + list and the conversation repository (roadmap api 2.1).

No database: routes run against a fake ``AsyncSession`` through
``app.dependency_overrides[get_session]``; repository queries are checked by compiling them
for SQL Server.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any, get_args
from uuid import UUID, uuid4

import pytest
import structlog.testing
from fastapi.testclient import TestClient
from sqlalchemy.dialects import mssql

from app.db import get_session
from app.main import app
from app.models.conversation import DEFAULT_TITLE, ROLES, Conversation, Message
from app.repositories import conversations as repo
from app.routers.conversations import MessageRole

INBOUND_TRACE = "0eb01" + "a" * 27
EMOJI = "\U0001f600"  # one character, two UTF-16 units


class FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> FakeResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None


class FakeSession:
    """Just enough of ``AsyncSession`` for the repository: add/flush/commit/execute/get."""

    def __init__(self, rows: list[Any] | None = None, *, fail_commit: bool = False) -> None:
        self.rows = rows or []
        self.added: list[Any] = []
        self.statements: list[Any] = []
        self.flushes = 0
        self.commits = 0
        self.fail_commit = fail_commit

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("database unavailable")
        self.commits += 1

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.rows)

    async def get(self, model: Any, key: Any) -> Any:
        return next((r for r in self.rows if isinstance(r, model) and r.id == key), None)


def _conversation(title: str, updated: datetime) -> Conversation:
    return Conversation(id=uuid4(), title=title, created_at=updated, updated_at=updated)


@pytest.fixture()
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture()
def client(session: FakeSession):
    async def fake_get_session():
        yield session

    app.dependency_overrides[get_session] = fake_get_session
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(get_session, None)


# --- POST /v1/conversations ------------------------------------------------------------


def test_create_with_a_title_returns_201_and_commits(
    client: TestClient, session: FakeSession
) -> None:
    res = client.post("/v1/conversations", json={"title": "Trace ids"})

    assert res.status_code == 201
    body = res.json()
    assert body["title"] == "Trace ids"
    assert UUID(body["id"])
    assert body["created_at"] == body["updated_at"]
    assert body["created_at"].endswith("Z")
    assert session.commits == 1
    [stored] = session.added
    assert isinstance(stored, Conversation) and str(stored.id) == body["id"]


@pytest.mark.parametrize("payload", [None, {}, {"title": None}, {"title": "   "}])
def test_create_without_a_title_uses_the_default(
    client: TestClient, payload: dict[str, Any] | None
) -> None:
    res = (
        client.post("/v1/conversations", json=payload)
        if payload is not None
        else (client.post("/v1/conversations"))
    )

    assert res.status_code == 201
    assert res.json()["title"] == DEFAULT_TITLE


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "x" * 201},
        {"title": EMOJI * 101},  # 202 UTF-16 units: would overflow NVARCHAR(200) as a 500
        {"title": "line\nbreak"},
        {"title": "nul\x00byte"},
        {"title": 42},
        [1, 2],
    ],
)
def test_create_rejects_bad_input_with_the_error_contract(
    client: TestClient, session: FakeSession, payload: Any
) -> None:
    res = client.post("/v1/conversations", json=payload, headers={"x-trace-id": INBOUND_TRACE})

    assert res.status_code == 422
    assert res.json() == {"error": "validation_error", "trace_id": INBOUND_TRACE}
    assert session.added == [] and session.commits == 0


@pytest.mark.parametrize(
    ("title", "stored"),
    [
        (EMOJI * 100, EMOJI * 100),  # exactly 200 UTF-16 units fits
        ("  " + "x" * 200 + "  ", "x" * 200),  # trimmed before the length check
    ],
)
def test_create_accepts_titles_that_fit_the_column(
    client: TestClient, title: str, stored: str
) -> None:
    res = client.post("/v1/conversations", json={"title": title})

    assert res.status_code == 201
    assert res.json()["title"] == stored


def test_create_echoes_the_inbound_trace_id(client: TestClient) -> None:
    res = client.post("/v1/conversations", headers={"x-trace-id": INBOUND_TRACE})

    assert res.headers["x-trace-id"] == INBOUND_TRACE


def test_a_database_failure_is_a_500_without_detail(
    client: TestClient, session: FakeSession
) -> None:
    session.fail_commit = True

    res = client.post("/v1/conversations", json={"title": "secret project"})

    assert res.status_code == 500
    body = res.json()
    assert body["error"] == "internal_error"
    assert "secret project" not in res.text and "database unavailable" not in res.text


# --- GET /v1/conversations -------------------------------------------------------------


def test_list_returns_items_and_count(client: TestClient, session: FakeSession) -> None:
    newer = _conversation("Error contract", datetime(2026, 10, 6, 10, 12, 0, 123000))
    older = _conversation("Onboarding", datetime(2026, 10, 5, 9, 0, 0))
    session.rows = [newer, older]

    res = client.get("/v1/conversations")

    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 2
    assert [i["title"] for i in body["items"]] == ["Error contract", "Onboarding"]
    assert set(body["items"][0]) == {"id", "title", "updated_at"}
    assert body["items"][0]["updated_at"].startswith("2026-10-06T10:12:00.123")
    assert body["items"][0]["updated_at"].endswith("Z")


def test_list_is_empty_when_there_are_no_conversations(client: TestClient) -> None:
    res = client.get("/v1/conversations")

    assert res.status_code == 200
    assert res.json() == {"items": [], "count": 0}


@pytest.mark.parametrize("limit", ["0", "101", "-1", "ten"])
def test_list_rejects_a_limit_outside_1_to_100(client: TestClient, limit: str) -> None:
    res = client.get(f"/v1/conversations?limit={limit}")

    assert res.status_code == 422
    assert res.json()["error"] == "validation_error"


def test_list_passes_the_limit_to_the_query(client: TestClient, session: FakeSession) -> None:
    client.get("/v1/conversations?limit=7")

    [statement] = session.statements
    assert "SELECT TOP 7 " in _sql(statement, literal=True)


def test_list_echoes_the_inbound_trace_id(client: TestClient) -> None:
    res = client.get("/v1/conversations", headers={"x-trace-id": INBOUND_TRACE})

    assert res.headers["x-trace-id"] == INBOUND_TRACE


# --- repository -------------------------------------------------------------------------


def _sql(statement: Any, *, literal: bool = False) -> str:
    return str(
        statement.compile(dialect=mssql.dialect(), compile_kwargs={"literal_binds": literal})
    )


def test_list_orders_newest_first_with_a_stable_tiebreak() -> None:
    session = FakeSession()

    asyncio.run(repo.list_conversations(session, limit=50))  # type: ignore[arg-type]

    sql = _sql(session.statements[0])
    assert re.search(r"ORDER BY conversations\.updated_at DESC, conversations\.id DESC", sql)


def test_create_sets_id_and_millisecond_utc_timestamps() -> None:
    session = FakeSession()

    conversation = asyncio.run(repo.create_conversation(session, "  Spaced  "))  # type: ignore[arg-type]

    assert conversation.title == "Spaced"
    assert isinstance(conversation.id, UUID)
    assert conversation.created_at == conversation.updated_at
    assert conversation.created_at.tzinfo is None
    assert conversation.created_at.microsecond % 1000 == 0
    assert session.flushes == 1 and session.commits == 0  # the caller commits


def test_add_message_bumps_updated_at() -> None:
    session = FakeSession()
    conversation = _conversation("Old", datetime(2020, 1, 1))

    message = asyncio.run(
        repo.add_message(  # type: ignore[arg-type]
            session, conversation, role="user", content="How does tracing work?"
        )
    )

    assert isinstance(message, Message)
    assert message.conversation_id == conversation.id
    assert conversation.updated_at == message.created_at > datetime(2020, 1, 1)
    assert session.added == [message]


def test_rename_cuts_the_title_and_bumps_updated_at() -> None:
    conversation = _conversation("New conversation", datetime(2020, 1, 1))

    repo.rename(conversation, "q" * 250)

    assert conversation.title == "q" * 200
    assert conversation.updated_at > datetime(2020, 1, 1)


def test_fit_title_counts_utf16_units_and_never_splits_an_emoji() -> None:
    assert repo.utf16_length(EMOJI) == 2
    assert repo.fit_title(EMOJI * 150) == EMOJI * 100  # 200 units, whole characters only
    assert repo.fit_title("a" + EMOJI * 100) == "a" + EMOJI * 99  # 199 units; no half emoji
    assert repo.fit_title("   ") == DEFAULT_TITLE


def test_add_message_rejects_an_unknown_role() -> None:
    session = FakeSession()
    conversation = _conversation("Old", datetime(2020, 1, 1))

    with pytest.raises(ValueError):
        asyncio.run(
            repo.add_message(session, conversation, role="system", content="x")  # type: ignore[arg-type]
        )
    assert session.added == [] and conversation.updated_at == datetime(2020, 1, 1)


def test_get_returns_none_for_an_unknown_id() -> None:
    known = _conversation("Known", datetime(2026, 1, 1))
    session = FakeSession(rows=[known])

    assert asyncio.run(repo.get_conversation(session, uuid4())) is None  # type: ignore[arg-type]
    assert asyncio.run(repo.get_conversation(session, known.id)) is known  # type: ignore[arg-type]


# --- GET /v1/conversations/{conversation_id} (roadmap api 2.2) -------------------------------


def _thread() -> Conversation:
    conversation = _conversation("Trace ids", datetime(2026, 10, 6, 10, 12))
    conversation.messages = [
        Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role="user",
            content="How does trace_id propagation work?",
            citations=None,
            created_at=datetime(2026, 10, 6, 10, 11, 0, 500000),
        ),
        Message(
            id=uuid4(),
            conversation_id=conversation.id,
            role="assistant",
            content="The BFF mints it and forwards it.",
            citations='[{"title": "trace_id — the invariant", "path": "README.md"}]',
            token_count=42,
            created_at=datetime(2026, 10, 6, 10, 12),
        ),
    ]
    return conversation


def test_read_returns_the_conversation_with_messages_oldest_first(
    client: TestClient, session: FakeSession
) -> None:
    conversation = _thread()
    session.rows = [conversation]

    res = client.get(f"/v1/conversations/{conversation.id}")

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == str(conversation.id)
    assert body["title"] == "Trace ids"
    assert body["updated_at"].endswith("Z")
    user, assistant = body["messages"]
    assert set(user) == {"id", "role", "content", "citations", "created_at"}
    assert (user["role"], user["citations"]) == ("user", None)
    assert user["created_at"] == "2026-10-06T10:11:00.500000Z"
    assert assistant["role"] == "assistant"
    assert assistant["citations"] == [{"title": "trace_id — the invariant", "path": "README.md"}]


def test_read_a_conversation_without_messages(client: TestClient, session: FakeSession) -> None:
    conversation = _conversation("Empty", datetime(2026, 10, 6))
    conversation.messages = []
    session.rows = [conversation]

    res = client.get(f"/v1/conversations/{conversation.id}")

    assert res.status_code == 200
    assert res.json()["messages"] == []


def test_read_an_unknown_id_is_a_404_with_the_error_contract(client: TestClient) -> None:
    res = client.get(f"/v1/conversations/{uuid4()}", headers={"x-trace-id": INBOUND_TRACE})

    assert res.status_code == 404
    assert res.json() == {"error": "not_found", "trace_id": INBOUND_TRACE}
    assert res.headers["x-trace-id"] == INBOUND_TRACE


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "123", "00000000-0000-0000-0000"])
def test_read_a_malformed_id_is_a_422(
    client: TestClient, session: FakeSession, bad_id: str
) -> None:
    res = client.get(f"/v1/conversations/{bad_id}")

    assert res.status_code == 422
    assert res.json()["error"] == "validation_error"
    assert session.statements == []  # rejected before any query


@pytest.mark.parametrize("stored", ['{"title": "not a list"}', '[{"path": "x.md"}]', "[1, 2]"])
def test_unreadable_citations_become_null_and_log_no_content(
    client: TestClient, session: FakeSession, stored: str
) -> None:
    conversation = _thread()
    conversation.messages[1].citations = stored
    session.rows = [conversation]

    with structlog.testing.capture_logs() as logs:
        res = client.get(f"/v1/conversations/{conversation.id}")

    assert res.status_code == 200
    assert res.json()["messages"][1]["citations"] is None
    [warning] = [e for e in logs if e["event"] == "unreadable citations"]
    assert stored not in str(warning) and str(conversation.id) not in str(warning)


def test_read_loads_messages_explicitly_for_one_id() -> None:
    session = FakeSession()
    wanted = uuid4()

    asyncio.run(repo.get_conversation_with_messages(session, wanted))  # type: ignore[arg-type]

    [statement] = session.statements
    assert "WHERE conversations.id = " in _sql(statement)
    # messages is lazy="raise" — the read must eager-load it (selectinload), never lazily
    assert any("messages" in str(option.path) for option in statement._with_options)


def test_messages_stored_in_the_same_millisecond_still_read_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frozen = datetime(2026, 10, 6, 12, 0, 0, 123000)
    monkeypatch.setattr(repo, "utc_now", lambda: frozen)
    session = FakeSession()
    conversation = _conversation("Same ms", frozen)

    question = asyncio.run(
        repo.add_message(session, conversation, role="user", content="q")  # type: ignore[arg-type]
    )
    answer = asyncio.run(
        repo.add_message(session, conversation, role="assistant", content="a")  # type: ignore[arg-type]
    )

    assert frozen < question.created_at < answer.created_at == conversation.updated_at


def test_the_response_role_type_matches_the_database_check() -> None:
    assert get_args(MessageRole) == ROLES
