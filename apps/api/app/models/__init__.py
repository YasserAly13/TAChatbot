"""ORM models — every module is imported here so it registers on ``Base.metadata``.

Team Assistant's models (``docs/design/db-design.md``):

- ``conversation`` — ``Conversation`` and ``Message`` (F2), first revision
  ``alembic/versions/20261006_1200-7c1d4e2a9b30_create_conversations_and_messages.py``.

Migrations are applied by a named human from a developer machine against dev (ADR-0013) —
never by an agent.

HOW TO EXTEND:
  1. Add a module here (e.g. ``app/models/widget.py``) with a 2.0-style model
     subclassing ``app.db.Base`` and import it below so it registers on
     ``Base.metadata`` (Alembic autogenerate only sees imported models).
  2. With a reachable dev database, generate a revision (needs a human + DB):
         uv run alembic revision --autogenerate -m "add widget"
     Review the generated ``upgrade()``/``downgrade()``; offline SQL for review:
         uv run alembic upgrade head --sql
  3. Applying it (``alembic upgrade head``) is a deliberate, confirmed human step —
     never run from an agent (``.claude/rules/25-sqlalchemy.md``).

Example model (uncomment and adapt)::

    # app/models/widget.py
    from datetime import datetime
    from uuid import UUID, uuid4

    from sqlalchemy import func
    from sqlalchemy.orm import Mapped, mapped_column

    from app.db import Base


    class Widget(Base):
        __tablename__ = "widgets"

        id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
        name: Mapped[str]
        created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    # then, here:
    # from app.models.widget import Widget  # noqa: F401
"""

from __future__ import annotations

from app.models.conversation import Conversation, Message

__all__: list[str] = ["Conversation", "Message"]
