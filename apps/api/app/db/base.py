"""Declarative base shared by every model (SQLAlchemy 2.0 style).

The ``MetaData`` carries an explicit constraint NAMING CONVENTION so that every
index / unique / check / foreign-key / primary-key constraint gets a
deterministic name. Alembic autogenerate and ``downgrade()`` need stable names
to drop or alter constraints; without a convention SQL Server invents names
(``PK__widgets__3213E83F…``) and migrations become environment-specific.

NOTE: the ``ck`` template uses ``%(constraint_name)s``, so every
``CheckConstraint`` MUST be given an explicit ``name=`` (SQLAlchemy raises at
DDL-compile time otherwise). Indexes, unique/foreign/primary keys are named
automatically.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Subclass this for every model (see ``app/models/__init__.py``).

    Alembic's ``env.py`` points ``target_metadata`` at ``Base.metadata``; a
    model only takes part in autogenerate once its module is imported by
    ``app.models``.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
