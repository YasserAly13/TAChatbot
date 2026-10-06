"""Conversation repository (roadmap api 2.1) — every read and write of ``conversations`` and
``messages`` goes through here, on the request's ``AsyncSession`` (``Depends(get_session)``).

The repository adds and flushes; the caller commits, so one request is one transaction.

Ids and timestamps are set here, not left to the server defaults: the returned object then
carries exactly what was stored without a refresh round trip. Timestamps are naive UTC truncated
to milliseconds, matching ``DATETIME2(3)``, from the api's clock (one process locally — ADR-0013;
with several replicas, clock skew could reorder near-simultaneous updates slightly).

Titles are measured the way ``NVARCHAR(200)`` measures them — UTF-16 code units, so an emoji
counts 2 — never Python code points, or a long emoji title would overflow the column (a 500).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import DEFAULT_TITLE, ROLES, TITLE_MAX_LENGTH, Conversation, Message

DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 100
_ONE_MS = timedelta(milliseconds=1)


def utf16_length(text: str) -> int:
    """Length as SQL Server's NVARCHAR counts it (UTF-16 code units)."""
    return len(text.encode("utf-16-le")) // 2


def fit_title(text: str) -> str:
    """Trim whitespace and cut to ``TITLE_MAX_LENGTH`` UTF-16 units without splitting a character;
    blank → the default title."""
    title = text.strip()
    while utf16_length(title) > TITLE_MAX_LENGTH:
        title = title[:-1]
    return title.rstrip() or DEFAULT_TITLE


def utc_now() -> datetime:
    """Naive UTC now at DATETIME2(3) precision (what the column stores)."""
    now = datetime.now(UTC).replace(tzinfo=None)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


async def create_conversation(session: AsyncSession, title: str | None = None) -> Conversation:
    """Add a conversation; a missing or blank title becomes "New conversation"."""
    now = utc_now()
    conversation = Conversation(
        id=uuid4(),
        title=fit_title(title or ""),
        created_at=now,
        updated_at=now,
    )
    session.add(conversation)
    await session.flush()
    return conversation


async def list_conversations(
    session: AsyncSession, limit: int = DEFAULT_LIST_LIMIT
) -> list[Conversation]:
    """The most recently updated conversations first (id breaks ties so paging is stable)."""
    statement = (
        select(Conversation)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        .limit(limit)
    )
    result = await session.execute(statement)
    return list(result.scalars().all())


async def get_conversation(session: AsyncSession, conversation_id: UUID) -> Conversation | None:
    return await session.get(Conversation, conversation_id)


async def get_conversation_with_messages(
    session: AsyncSession, conversation_id: UUID
) -> Conversation | None:
    """The conversation with its messages loaded oldest first, in one extra SELECT.

    ``messages`` is ``lazy="raise"``, so it must be loaded here explicitly (``selectinload``);
    touching it later on the async session would fail instead of silently querying.
    """
    statement = (
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .options(selectinload(Conversation.messages))
    )
    result = await session.execute(statement)
    return result.scalars().first()


async def add_message(
    session: AsyncSession,
    conversation: Conversation,
    *,
    role: str,
    content: str,
    citations: str | None = None,
    token_count: int | None = None,
) -> Message:
    """Add a message and bump the conversation's ``updated_at`` so the list reorders.

    Nothing in the database bumps ``updated_at`` — this is the one place that does.
    """
    if role not in ROLES:  # the CHECK constraint would reject it later, as a 500
        raise ValueError(f"role must be one of {ROLES}")
    # Strictly later than anything already in this conversation (updated_at moves with every
    # message), so a question and its answer stored in the same millisecond still read in order.
    now = max(utc_now(), conversation.updated_at + _ONE_MS)
    message = Message(
        id=uuid4(),
        conversation_id=conversation.id,
        role=role,
        content=content,
        citations=citations,
        token_count=token_count,
        created_at=now,
    )
    session.add(message)
    touch(conversation, now)
    await session.flush()
    return message


def rename(conversation: Conversation, title: str) -> None:
    """Set the title (cut to the column's UTF-16 length) and bump ``updated_at``."""
    conversation.title = fit_title(title)
    touch(conversation)


def touch(conversation: Conversation, when: datetime | None = None) -> None:
    conversation.updated_at = when or utc_now()
