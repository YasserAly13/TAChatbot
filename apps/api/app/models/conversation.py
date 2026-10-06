"""Conversations and their messages (F2 — ``docs/design/db-design.md``).

Two tables on the project's Azure SQL database:

- ``conversations`` — one chat; ``title`` defaults to "New conversation" until the first
  question renames it; ``updated_at`` orders the list (newest first).
- ``messages`` — the user's questions and the assistant's answers, oldest first per
  conversation; ``citations`` is the JSON ``[{title, path}]`` of an answer.

Conversations have no owner until auth lands (ADR-0014). Message content may contain personal
data — it is stored here and must never reach logs, spans, metrics or events (rules 60/70).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, ForeignKey, Index, Unicode, Uuid, text
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

DEFAULT_TITLE = "New conversation"
TITLE_MAX_LENGTH = 200
ROLES = ("user", "assistant")


def _sql_literal(value: str) -> str:
    """An N'…' T-SQL literal for a module constant — quotes doubled, never user input."""
    return "N'" + value.replace("'", "''") + "'"


# Timestamps follow the design (datetime2(3)), not rule 25's DateTime(timezone=True) default:
# SYSUTCDATETIME() matches DATETIME2's precision and is UTC; GETDATE() (func.now()) is
# DATETIME-precise and server-local. Values come back naive — they are UTC.
_UTC_NOW = text("SYSUTCDATETIME()")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(
        Unicode(TITLE_MAX_LENGTH),
        default=DEFAULT_TITLE,
        server_default=text(_sql_literal(DEFAULT_TITLE)),
    )
    created_at: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=_UTC_NOW)
    updated_at: Mapped[datetime] = mapped_column(
        DATETIME2(precision=3), server_default=_UTC_NOW, index=True
    )

    # lazy="raise": an implicit lazy load on an AsyncSession is a MissingGreenlet 500 — load
    # messages explicitly (selectinload) so a forgotten load fails loudly in tests instead.
    # Oldest first. created_at is strictly increasing per conversation (the repository's
    # add_message guarantees it); id only makes any legacy tie deterministic.
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        order_by="(Message.created_at, Message.id)",
        lazy="raise",
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(f"role IN ({', '.join(f"'{r}'" for r in ROLES)})", name="role"),
        CheckConstraint("citations IS NULL OR ISJSON(citations) = 1", name="citations_json"),
        # The convention would name it after conversation_id alone; this one spans two columns.
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    # ON DELETE NO ACTION (SQL Server's default): there is no delete feature (B8 #6).
    conversation_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("conversations.id"))
    role: Mapped[str] = mapped_column(Unicode(20))
    # Unicode() without a length is NVARCHAR(max) on SQL Server in every mode. UnicodeText is
    # NTEXT until the dialect has seen the server version (offline SQL), and ISJSON() rejects NTEXT.
    content: Mapped[str] = mapped_column(Unicode())
    citations: Mapped[str | None] = mapped_column(Unicode())
    token_count: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(DATETIME2(precision=3), server_default=_UTC_NOW)

    conversation: Mapped[Conversation] = relationship(back_populates="messages", lazy="raise")
