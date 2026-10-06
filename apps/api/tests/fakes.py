"""Shared fakes for the conversation route and repository tests — no database (rule 40).

``FakeSession`` is just enough of ``AsyncSession`` for ``app/repositories/conversations.py``;
routes get it through ``app.dependency_overrides[get_session]``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from app.models.conversation import Conversation

INBOUND_TRACE = "0eb01" + "a" * 27


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
    """Just enough of ``AsyncSession`` for the repository: add/flush/commit/execute/get.

    ``fail_commit=True`` fails every commit; ``fail_commit_after=n`` lets ``n`` commits succeed
    and fails the next ones.
    """

    def __init__(
        self,
        rows: list[Any] | None = None,
        *,
        fail_commit: bool = False,
        fail_commit_after: int | None = None,
    ) -> None:
        self.rows = rows or []
        self.added: list[Any] = []
        self.statements: list[Any] = []
        self.flushes = 0
        self.commits = 0
        self.fail_commit = fail_commit
        self.fail_commit_after = fail_commit_after

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushes += 1

    async def commit(self) -> None:
        if self.fail_commit or (
            self.fail_commit_after is not None and self.commits >= self.fail_commit_after
        ):
            raise RuntimeError("database unavailable")
        self.commits += 1

    async def execute(self, statement: Any) -> FakeResult:
        self.statements.append(statement)
        return FakeResult(self.rows)

    async def get(self, model: Any, key: Any) -> Any:
        return next((r for r in self.rows if isinstance(r, model) and r.id == key), None)


def make_conversation(title: str, updated: datetime) -> Conversation:
    return Conversation(id=uuid4(), title=title, created_at=updated, updated_at=updated)
