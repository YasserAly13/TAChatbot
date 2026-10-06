"""Custom-event helper tests (Phase 3, offline):
- enabled → a stdlib record with the microsoft.custom_event.name marker lands
  on the "app.telemetry" logger (the distro's export path)
- degraded mode → no export record, local structured line still prints
- any internal failure is swallowed (fail-safe)
"""

from __future__ import annotations

import logging

import pytest

import app.events as events_mod
from app.events import CUSTOM_EVENT_MARKER, track_event
from app.logging_config import configure_logging


class _CapturingHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture()
def capture_telemetry_logger() -> _CapturingHandler:
    configure_logging(async_sink=False)
    handler = _CapturingHandler()
    logger = logging.getLogger("app.telemetry")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    yield handler
    logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)


class TestTrackEvent:
    def test_emits_marker_record_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch, capture_telemetry_logger: _CapturingHandler
    ) -> None:
        monkeypatch.setattr(
            events_mod, "get_observability_state", lambda: {"enabled": True, "reason": "ok"}
        )
        track_event("service.start", {"mode": "test"})

        assert len(capture_telemetry_logger.records) == 1
        record = capture_telemetry_logger.records[0]
        assert record.getMessage() == "service.start"
        assert record.__dict__[CUSTOM_EVENT_MARKER] == "service.start"
        assert record.__dict__["mode"] == "test"

    def test_degraded_mode_skips_export_but_prints_local_line(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capture_telemetry_logger: _CapturingHandler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            events_mod, "get_observability_state", lambda: {"enabled": False, "reason": "off"}
        )
        track_event("service.start")

        assert capture_telemetry_logger.records == []
        out = capsys.readouterr().out
        assert '"custom event"' in out
        assert "service.start" in out

    def test_local_line_prints_when_enabled_too(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capture_telemetry_logger: _CapturingHandler,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            events_mod, "get_observability_state", lambda: {"enabled": True, "reason": "ok"}
        )
        track_event("thing.created")
        assert len(capture_telemetry_logger.records) == 1
        assert "thing.created" in capsys.readouterr().out

    def test_never_raises_when_state_lookup_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        configure_logging(async_sink=False)

        def boom() -> dict[str, object]:
            raise RuntimeError("state boom")

        monkeypatch.setattr(events_mod, "get_observability_state", boom)
        track_event("service.start")  # must not raise
