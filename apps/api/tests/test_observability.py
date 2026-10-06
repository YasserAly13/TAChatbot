"""Observability is fail-safe: with no connection string it reports disabled."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

import app.observability as obs


def test_observability_disabled_without_connection_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    obs._reset_for_tests()
    try:
        state = obs.init_observability(FastAPI())
        assert state["enabled"] is False
        assert "connection string" in state["reason"].lower()
    finally:
        obs._reset_for_tests()
