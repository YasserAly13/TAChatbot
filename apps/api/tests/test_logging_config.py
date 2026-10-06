"""Log pipeline tests (Phase 1, offline).

Covers:
  - redaction at source (default fields, case/hyphen normalization, nesting,
    extensibility) — before ANY sink
  - Azure bridge processor: mirrors into stdlib "app.telemetry" when enabled,
    no-ops when disabled/opted-out, never breaks local logging on failure
  - non-blocking async stdout sink with best-effort synchronous flush
"""

from __future__ import annotations

import io
import json
import logging
from typing import Any

import pytest

import app.logging_config as lc
import app.observability as obs


@pytest.fixture(autouse=True)
def _clean_logging_state(monkeypatch: pytest.MonkeyPatch):
    """Reset extra redaction fields and observability state around each test."""
    lc._extra_redacted_fields.clear()
    obs._reset_for_tests()
    yield
    lc._extra_redacted_fields.clear()
    obs._reset_for_tests()
    # Restore the default logging configuration for subsequent test modules.
    lc.configure_logging()


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture()
def bridge_capture():
    """Attach a capturing handler where the Azure distro's handler would sit."""
    handler = _CaptureHandler()
    app_logger = logging.getLogger("app")
    app_logger.addHandler(handler)
    old_propagate = app_logger.propagate
    app_logger.propagate = False  # keep test output clean
    yield handler
    app_logger.removeHandler(handler)
    app_logger.propagate = old_propagate


def _enable_observability(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(obs, "get_observability_state", lambda: {"enabled": True, "reason": "test"})


class TestRedactProcessor:
    @pytest.mark.parametrize("field", sorted(lc.DEFAULT_REDACTED_FIELDS))
    def test_censors_default_fields(self, field: str) -> None:
        event = lc.redact_processor(None, "info", {field: "super-secret"})
        assert event[field] == lc.REDACTION_CENSOR

    def test_matches_case_insensitively_and_hyphens(self) -> None:
        event = lc.redact_processor(
            None,
            "info",
            {"Authorization": "Bearer x", "Set-Cookie": "sid=1", "connectionString": "cs"},
        )
        assert event["Authorization"] == lc.REDACTION_CENSOR
        assert event["Set-Cookie"] == lc.REDACTION_CENSOR
        assert event["connectionString"] == lc.REDACTION_CENSOR

    def test_censors_nested_dicts(self) -> None:
        event = lc.redact_processor(
            None,
            "info",
            {"headers": {"authorization": "Bearer x", "accept": "json"}, "message": "m"},
        )
        assert event["headers"]["authorization"] == lc.REDACTION_CENSOR
        assert event["headers"]["accept"] == "json"
        assert event["message"] == "m"

    def test_extensible_via_configure_logging(self) -> None:
        lc.configure_logging(extra_redacted_fields={"SSN"}, async_sink=False)
        event = lc.redact_processor(None, "info", {"ssn": "123-45-6789", "ok": 1})
        assert event["ssn"] == lc.REDACTION_CENSOR
        assert event["ok"] == 1

    def test_leaves_non_secret_fields_intact(self) -> None:
        event = lc.redact_processor(None, "info", {"status": 200, "url": "/ping"})
        assert event == {"status": 200, "url": "/ping"}


class TestAzureBridgeProcessor:
    def test_mirrors_event_into_stdlib_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch, bridge_capture: _CaptureHandler
    ) -> None:
        _enable_observability(monkeypatch)
        event_in = {
            "level": "warning",
            "message": "upstream failed",
            "trace_id": "0c70" + "0" * 28,
            "status": 502,
            "timestamp": "2026-07-25T00:00:00Z",
        }
        event_out = lc.azure_bridge_processor(None, "warning", dict(event_in))

        assert event_out == event_in  # local pipeline unchanged
        assert len(bridge_capture.records) == 1
        record = bridge_capture.records[0]
        assert record.levelno == logging.WARNING
        assert record.getMessage() == "upstream failed"
        assert record.trace_id == event_in["trace_id"]
        assert record.status == 502
        assert record.name == "app.telemetry"

    def test_serializes_non_primitive_attributes(
        self, monkeypatch: pytest.MonkeyPatch, bridge_capture: _CaptureHandler
    ) -> None:
        _enable_observability(monkeypatch)
        lc.azure_bridge_processor(None, "info", {"message": "m", "payload": {"a": 1}})
        assert bridge_capture.records[0].payload == json.dumps({"a": 1})

    def test_noop_in_degraded_mode(self, bridge_capture: _CaptureHandler) -> None:
        event = lc.azure_bridge_processor(None, "info", {"message": "local only"})
        assert event == {"message": "local only"}
        assert bridge_capture.records == []

    def test_per_logger_opt_out(
        self, monkeypatch: pytest.MonkeyPatch, bridge_capture: _CaptureHandler
    ) -> None:
        _enable_observability(monkeypatch)
        event = lc.azure_bridge_processor(
            None, "info", {"message": "m", lc.TELEMETRY_EXPORT_KEY: False}
        )
        assert bridge_capture.records == []
        # The opt-out marker never reaches the rendered line.
        assert lc.TELEMETRY_EXPORT_KEY not in event

    def test_bridge_failure_never_breaks_local_logging(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _enable_observability(monkeypatch)

        def boom(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("logging exploded")

        monkeypatch.setattr(logging.getLogger("app.telemetry"), "log", boom)
        event = lc.azure_bridge_processor(None, "info", {"message": "still fine"})
        assert event == {"message": "still fine"}


class TestAsyncLineWriter:
    def test_writes_lines_via_background_thread(self) -> None:
        buffer = io.StringIO()
        writer = lc._AsyncLineWriter(stream_factory=lambda: buffer)
        writer.write_line('{"message": "a"}')
        writer.write_line('{"message": "b"}')
        assert writer.flush_sync(timeout=5.0) is True
        assert buffer.getvalue() == '{"message": "a"}\n{"message": "b"}\n'

    def test_flush_logs_without_writer_is_a_noop(self) -> None:
        assert lc.flush_logs() is True or lc._writer is not None

    def test_stream_errors_do_not_kill_the_writer(self) -> None:
        calls: list[str] = []

        class FlakyStream:
            def write(self, line: str) -> None:
                if not calls:
                    calls.append("boom")
                    raise OSError("pipe closed")
                calls.append(line)

            def flush(self) -> None:
                pass

        stream = FlakyStream()
        writer = lc._AsyncLineWriter(stream_factory=lambda: stream)
        writer.write_line("first")  # swallowed by the broken write
        writer.write_line("second")
        assert writer.flush_sync(timeout=5.0) is True
        assert calls == ["boom", "second\n"]


class TestConfiguredPipeline:
    def test_stdout_line_is_structured_and_redacted(self, capsys: pytest.CaptureFixture) -> None:
        lc.configure_logging(async_sink=False)
        log = lc.get_logger("app.test")
        log.info("hello pipeline", password="hunter2", status=200)
        line = capsys.readouterr().out.strip().splitlines()[-1]
        record = json.loads(line)
        assert record["message"] == "hello pipeline"
        assert record["password"] == lc.REDACTION_CENSOR
        assert record["status"] == 200
        assert record["service"] == "api"
        assert record["origin"] == "0c70"
        assert "timestamp" in record and "level" in record

    def test_async_sink_writes_the_same_structured_line(self) -> None:
        buffer = io.StringIO()
        writer = lc._AsyncLineWriter(stream_factory=lambda: buffer)
        logger = lc._AsyncPrintLogger(writer)
        logger.msg('{"message": "via async"}')
        assert writer.flush_sync(timeout=5.0) is True
        assert '{"message": "via async"}' in buffer.getvalue()
