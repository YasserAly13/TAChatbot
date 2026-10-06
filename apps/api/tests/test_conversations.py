"""``/v1/conversations`` create + list and the conversation repository (roadmap api 2.1).

No database: routes run against a fake ``AsyncSession`` through
``app.dependency_overrides[get_session]``; repository queries are checked by compiling them
for SQL Server.
"""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects import mssql

from app.db import get_session
from app.main import app
from app.models.conversation import DEFAULT_TITLE, Conversation, Message
from app.repositories import conversations as repo

INBOUND_TRACE = "0eb01" + "a" * 27
EMOJI = "\U0001f600"  # one character, two UTF-16 units


class FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> FakeResult:
        return self

    def all(self) -> list[Any]:
        return list(self._rows)


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
