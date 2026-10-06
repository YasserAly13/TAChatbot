"""ORM models — PLACEHOLDER ONLY (the template ships no domain model; ADR-0004).

The model set is intentionally empty: the service boots, Alembic is wired, and
``alembic/versions/`` holds no revisions. Migrations are NOT run by this project.

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

__all__: list[str] = []
