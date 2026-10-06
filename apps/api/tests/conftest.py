"""Shared pytest fixtures for the api tests."""

from __future__ import annotations

import logging

import pytest


@pytest.fixture()
def _restore_logging():
    """Alembic's env.py applies alembic.ini's CLI logging via fileConfig; undo it afterwards
    so the service's stdlib logging setup is untouched for the rest of the run."""
    root = logging.getLogger()
    saved = (root.level, list(root.handlers))
    yield
    root.setLevel(saved[0])
    root.handlers[:] = saved[1]
    for name in ("alembic", "sqlalchemy.engine"):
        logger = logging.getLogger(name)
        logger.handlers[:] = []
        logger.setLevel(logging.NOTSET)
        logger.propagate = True
