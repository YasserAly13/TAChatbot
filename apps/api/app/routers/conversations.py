"""``/v1/conversations`` — create, list (roadmap api 2.1) and read one with its messages
(api 2.2) — F2.

Conversations are shared — there is no owner until auth lands (ADR-0014). Titles, ids and
message content are user-linked data: they never go into this code's logs, span attributes or
metric attributes (the request metric uses the route *template*,
``/v1/conversations/{conversation_id}``). The framework's own request span and uvicorn's local
access log carry the raw URL, id included.

Timestamps are stored as naive UTC (``DATETIME2(3)``); responses attach UTC so they serialise
with an explicit offset and browsers do not read them as local time.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import ErrorBody, NotFound
from app.logging_config import get_logger
from app.models.conversation import TITLE_MAX_LENGTH, Conversation, Message
from app.repositories import conversations as repo

_log = get_logger("app.routers.conversations")

# A module-level alias, not an inline annotation: with postponed annotations, ruff's
# quoted-annotation fix would strip the quotes from an inline Literal["user", ...].
MessageRole = Literal["user", "assistant"]

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


class Citation(BaseModel):
    title: str
    path: str


class MessageOut(BaseModel):
    id: UUID
    role: MessageRole
    content: str
    citations: list[Citation] | None = Field(
        description="The documents an assistant answer cites; null for user messages."
    )
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _attach_utc(cls, value: datetime) -> datetime:
        return _utc(value)

    @classmethod
    def of(cls, message: Message) -> MessageOut:
        return cls(
            id=message.id,
            role=message.role,  # type: ignore[arg-type]  # the CHECK constraint guarantees it
            content=message.content,
            citations=_parse_citations(message.citations),
            created_at=message.created_at,
        )


class ConversationDetail(ConversationOut):
    messages: list[MessageOut] = Field(description="Oldest first.")


_citation_list = TypeAdapter(list[Citation])


def _parse_citations(raw: str | None) -> list[Citation] | None:
    """Stored JSON ``[{title, path}]`` → citations. The column only guarantees *valid JSON*
    (``ISJSON``); a row with another shape degrades to ``null`` instead of failing the read.
    Only the failure kind is logged — never the stored text."""
    if raw is None:
        return None
    try:
        return _citation_list.validate_json(raw)
    except ValidationError as exc:
        _log.warning(
            "unreadable citations", reason="not_a_title_path_list", errors=exc.error_count()
        )
        return None


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


@router.get(
    "/{conversation_id}",
    responses={404: {"model": ErrorBody, "description": "No such conversation (`not_found`)"}},
)
async def read_conversation(conversation_id: UUID, session: DbSession) -> ConversationDetail:
    """One conversation with its messages, oldest first. A malformed id is a 422."""
    conversation = await repo.get_conversation_with_messages(session, conversation_id)
    if conversation is None:
        raise NotFound()
    return ConversationDetail(
        **ConversationOut.of(conversation).model_dump(),
        messages=[MessageOut.of(m) for m in conversation.messages],
    )
