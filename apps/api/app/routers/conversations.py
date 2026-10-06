"""``/v1/conversations`` — create and list conversations (roadmap api 2.1, F2).

Conversations are shared — there is no owner until auth lands (ADR-0014). Titles and ids are
user-linked data: they never go into logs, span attributes or metric attributes (the request
metrics already use the route *template*, ``/v1/conversations``).

Timestamps are stored as naive UTC (``DATETIME2(3)``); responses attach UTC so they serialise
with an explicit offset and browsers do not read them as local time.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.conversation import TITLE_MAX_LENGTH, Conversation
from app.repositories import conversations as repo

router = APIRouter(prefix="/conversations", tags=["conversations"])

DbSession = Annotated[AsyncSession, Depends(get_session)]


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


class ConversationCreate(BaseModel):
    title: str | None = Field(
        default=None,
        max_length=TITLE_MAX_LENGTH,
        description=(
            'Optional; missing or blank becomes "New conversation". At most 200 UTF-16 units '
            "after trimming (an emoji counts 2); no control characters."
        ),
    )

    @field_validator("title", mode="before")
    @classmethod
    def _trim(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("title")
    @classmethod
    def _fits_the_column(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if _CONTROL_CHARS.search(value):
            raise ValueError("title must not contain control characters")
        if repo.utf16_length(value) > TITLE_MAX_LENGTH:
            raise ValueError("title is longer than the column allows")
        return value


class ConversationOut(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    @field_validator("created_at", "updated_at")
    @classmethod
    def _attach_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @classmethod
    def of(cls, conversation: Conversation) -> ConversationOut:
        return cls(
            id=conversation.id,
            title=conversation.title,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class ConversationSummary(BaseModel):
    id: UUID
    title: str
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def _attach_utc(cls, value: datetime) -> datetime:
        return _utc(value)


class ConversationList(BaseModel):
    items: list[ConversationSummary]
    count: int = Field(description="Number of items in this response (at most `limit`).")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    session: DbSession, body: ConversationCreate | None = None
) -> ConversationOut:
    """Start a conversation. The body is optional."""
    conversation = await repo.create_conversation(session, body.title if body else None)
    await session.commit()
    return ConversationOut.of(conversation)


@router.get("")
async def list_conversations(
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=repo.MAX_LIST_LIMIT)] = repo.DEFAULT_LIST_LIMIT,
) -> ConversationList:
    """Conversations, most recently updated first."""
    conversations = await repo.list_conversations(session, limit)
    items = [
        ConversationSummary(id=c.id, title=c.title, updated_at=c.updated_at) for c in conversations
    ]
    return ConversationList(items=items, count=len(items))
