"""Structured logging via structlog.

Always renders JSON to stdout. Every log line carries the shared fields:
    timestamp, level, service="api", origin="0c70", env=<APP_ENV|local>,
    trace_id (from the request-scoped contextvar) and message (structlog's
    "event" renamed to "message").

PHASE 1 — log pipeline (see .claude/rules/60-observability.md):

- REDACTION AT SOURCE: ``redact_processor`` censors the default secret-bearing
  fields (DEFAULT_REDACTED_FIELDS, matched case-insensitively with ``-``/``_``
  normalized, recursively into nested dicts) to "[redacted]" BEFORE any sink —
  stdout or Azure — sees the event. Extensible via
  ``configure_logging(extra_redacted_fields={...})``.
- AZURE BRIDGE: structlog renders straight to stdout and BYPASSES stdlib
  ``logging`` — so the Azure distro (whose ``LoggingHandler`` sits on the
  stdlib "app" logger via ``configure_azure_monitor(logger_name="app")``)
  would never see these logs. ``azure_bridge_processor`` mirrors every event
  into the stdlib logger "app.telemetry" (which propagates to "app"), so the
  distro exports it with mapped severity and the ACTIVE SPAN CONTEXT (=>
  AppTraces.operation_Id matches AppRequests). The bridge is a no-op in
  degraded mode, never raises (fail-safe), and a logger can opt out by binding
  ``telemetry_export=False``.
- NON-BLOCKING SINK: rendered lines are handed to a queue backed by a single
  daemon writer thread (never blocking the request path on a slow stdout
  pipe), with a best-effort synchronous drain registered via ``atexit`` so
  shutdown lines aren't lost. Falls back to direct writes if the writer thread
  is unavailable — logs are never dropped silently.
"""

from __future__ import annotations

import atexit
import json
import logging
import queue
import sys
import threading
from typing import Any, TextIO

import structlog

from app.config import SERVICE_NAME, get_settings
from app.tracing import ORIGIN, get_trace_id

REDACTION_CENSOR = "[redacted]"

# Default secret-bearing log fields, censored before ANY sink sees the event.
# Keys are matched case-insensitively with "-" normalized to "_"
# (so Authorization, set-cookie, connectionString, api-key etc. all match).
DEFAULT_REDACTED_FIELDS: frozenset[str] = frozenset(
    {
        "authorization",
        "cookie",
        "set_cookie",
        "x_api_key",
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "password",
        "secret",
        "client_secret",
        "api_key",
        "apikey",
        "connection_string",
        "connectionstring",
    }
)

# Extra fields registered via configure_logging(extra_redacted_fields=...).
_extra_redacted_fields: set[str] = set()

# structlog bound-context key for the per-logger bridge opt-out.
TELEMETRY_EXPORT_KEY = "telemetry_export"

# Bridge target: child of "app", where the Azure distro attaches its handler.
_BRIDGE_LOGGER_NAME = "app.telemetry"

_LEVEL_TO_STDLIB: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "exception": logging.ERROR,
    "fatal": logging.CRITICAL,
    "critical": logging.CRITICAL,
}

# stdlib LogRecord attribute names that must not be passed via `extra`.
_RESERVED_RECORD_KEYS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)

_MAX_REDACTION_DEPTH = 4


def _normalize_key(key: str) -> str:
    return key.lower().replace("-", "_")


def _redacted_fields() -> frozenset[str]:
    return DEFAULT_REDACTED_FIELDS | frozenset(_extra_redacted_fields)


def _redact_mapping(value: Any, fields: frozenset[str], depth: int = 0) -> Any:
    if depth >= _MAX_REDACTION_DEPTH or not isinstance(value, dict):
        return value
    return {
        key: (
            REDACTION_CENSOR
            if isinstance(key, str) and _normalize_key(key) in fields
            else _redact_mapping(val, fields, depth + 1)
        )
        for key, val in value.items()
    }


def redact_processor(
    _logger: Any, _method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Censor secret-bearing fields (recursively) before any sink renders them."""
    fields = _redacted_fields()
    # Only existing keys are reassigned (no adds/removes), so direct iteration is safe.
    for key in event_dict:
        if isinstance(key, str) and _normalize_key(key) in fields:
            event_dict[key] = REDACTION_CENSOR
        else:
            event_dict[key] = _redact_mapping(event_dict[key], fields, depth=1)
    return event_dict


def _bridge_attribute(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return json.dumps(value, default=str)
    except Exception:  # noqa: BLE001 - attributes are best-effort
        return str(value)


def azure_bridge_processor(
    _logger: Any, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Mirror the (already-redacted) event into stdlib logging for Azure export.

    Runs AFTER redact_processor and BEFORE the JSON renderer. Fail-safe: any
    error here is swallowed — the local stdout line is never affected.
    """
    export = event_dict.pop(TELEMETRY_EXPORT_KEY, True)
    if not export:
        return event_dict
    try:
        from app.observability import get_observability_state

        if not get_observability_state()["enabled"]:
            return event_dict
        level = _LEVEL_TO_STDLIB.get(str(event_dict.get("level", method_name)), logging.INFO)
        message = str(event_dict.get("message", ""))
        extra = {
            key: _bridge_attribute(value)
            for key, value in event_dict.items()
            if key not in ("message", "level", "timestamp") and key not in _RESERVED_RECORD_KEYS
        }
        logging.getLogger(_BRIDGE_LOGGER_NAME).log(level, message, extra=extra)
    except Exception:  # noqa: BLE001 - the bridge must never break local logging
        pass
    return event_dict


class _AsyncLineWriter:
    """Queue-backed line writer: a single daemon thread writes to the stream.

    Log calls only enqueue (never block on stdout); ``flush_sync`` drains the
    queue best-effort (used at process exit). If the writer thread is not
    available, lines are written directly — never dropped.
    """

    def __init__(self, stream_factory: Any = None) -> None:
        # Resolve the stream at WRITE time so redirected stdout (tests,
        # supervisors) is honored.
        self._stream_factory = stream_factory or (lambda: sys.stdout)
        self._queue: queue.SimpleQueue[str | threading.Event] = queue.SimpleQueue()
        self._thread = threading.Thread(target=self._run, name="log-writer", daemon=True)
        self._thread.start()

    def write_line(self, line: str) -> None:
        if self._thread.is_alive():
            self._queue.put(line)
        else:
            self._write_direct(line)

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if isinstance(item, threading.Event):
                item.set()
                continue
            self._write_direct(item)

    def _write_direct(self, line: str) -> None:
        try:
            stream: TextIO = self._stream_factory()
            stream.write(line + "\n")
            stream.flush()
        except Exception:  # noqa: BLE001 - a broken stream must not kill the writer
            pass

    def flush_sync(self, timeout: float = 2.0) -> bool:
        """Best-effort synchronous drain: wait until queued lines are written."""
        if not self._thread.is_alive():
            return True
        marker = threading.Event()
        self._queue.put(marker)
        return marker.wait(timeout)


_writer: _AsyncLineWriter | None = None
_atexit_registered = False


def _get_writer() -> _AsyncLineWriter:
    global _writer
    if _writer is None:
        _writer = _AsyncLineWriter()
    return _writer


def flush_logs(timeout: float = 2.0) -> bool:
    """Best-effort synchronous flush of the async log sink (used at exit)."""
    if _writer is None:
        return True
    return _writer.flush_sync(timeout)


class _AsyncPrintLogger:
    """structlog logger that enqueues rendered lines onto the async writer."""

    def __init__(self, writer: _AsyncLineWriter) -> None:
        self._writer = writer

    def msg(self, message: str) -> None:
        self._writer.write_line(message)

    log = debug = info = warn = warning = msg
    fatal = failure = err = error = critical = exception = msg


class _AsyncPrintLoggerFactory:
    def __init__(self, writer: _AsyncLineWriter) -> None:
        self._writer = writer

    def __call__(self, *args: Any) -> _AsyncPrintLogger:
        return _AsyncPrintLogger(self._writer)


def _inject_context(
    _logger: Any, _method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Inject shared service/origin/env/trace_id fields onto every event."""
    event_dict["service"] = SERVICE_NAME
    event_dict["origin"] = ORIGIN
    event_dict["env"] = get_settings().app_env
    trace_id = get_trace_id()
    if trace_id is not None:
        event_dict["trace_id"] = trace_id
    return event_dict


def _rename_event_to_message(
    _logger: Any, _method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """Rename structlog's 'event' key to 'message'."""
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    return event_dict


def configure_logging(
    extra_redacted_fields: set[str] | None = None,
    async_sink: bool = True,
) -> None:
    """Configure structlog + stdlib logging to emit JSON on stdout.

    Idempotent: safe to call more than once.

    - ``extra_redacted_fields``: additional field names to censor (merged into
      the default list; matched case-insensitively, "-" normalized to "_").
    - ``async_sink``: hand rendered lines to the queue-backed writer thread
      (default). ``False`` writes synchronously to stdout (tests/debugging).
    """
    global _atexit_registered

    if extra_redacted_fields:
        _extra_redacted_fields.update(_normalize_key(f) for f in extra_redacted_fields)

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        _inject_context,
        structlog.processors.TimeStamper(fmt="iso", key="timestamp", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _rename_event_to_message,
        # Redact BEFORE any sink: both the stdout JSON line and the Azure
        # bridge below only ever see censored values.
        redact_processor,
        azure_bridge_processor,
        structlog.processors.JSONRenderer(),
    ]

    if async_sink:
        logger_factory: Any = _AsyncPrintLoggerFactory(_get_writer())
        if not _atexit_registered:
            _atexit_registered = True
            atexit.register(flush_logs)
    else:
        # No explicit file: PrintLogger then resolves sys.stdout at PRINT time,
        # so redirected stdout (tests, supervisors) is always honored and a
        # stale stream object can never be captured in the config.
        logger_factory = structlog.PrintLoggerFactory()

    structlog.configure(
        processors=processors,
        logger_factory=logger_factory,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )

    # Route stdlib logging (uvicorn, azure, otel) through stdout at INFO too,
    # so we never lose the degraded-mode warnings even before structlog wiring.
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        handler = logging.StreamHandler(stream=sys.stdout)
        root.addHandler(handler)
    root.setLevel(logging.INFO)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a configured structlog logger."""
    return structlog.get_logger(name)
