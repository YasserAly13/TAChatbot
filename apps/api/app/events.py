"""Custom-event helper (Phase 3 — see .claude/rules/60-observability.md).

``track_event(name, attrs)`` emits an App Insights ``customEvents`` row: the
Azure Monitor exporter maps any log record carrying the
``microsoft.custom_event.name`` attribute to an event envelope (verified in
azure-monitor-opentelemetry-exporter — ``_MICROSOFT_CUSTOM_EVENT_NAME``).
The record is emitted through the stdlib "app.telemetry" logger, where the
distro's LoggingHandler sits (same path as the Phase 1 log bridge), so events
are request-correlated via the active span context.

Fail-safe: degraded mode → the exported record is skipped (the local
structured line still prints); any failure is swallowed.

NO IDENTIFYING ATTRIBUTES: event attributes follow the same no-PII and
bounded-cardinality rules as metrics — kinds and outcomes, never ids/emails.
"""

from __future__ import annotations

import logging

from app.logging_config import TELEMETRY_EXPORT_KEY, get_logger
from app.observability import get_observability_state

CUSTOM_EVENT_MARKER = "microsoft.custom_event.name"

# The distro's LoggingHandler listens on "app" — same target as the log bridge.
_EVENT_STDLIB_LOGGER = "app.telemetry"

EventAttributes = dict[str, str | int | float | bool]


def track_event(name: str, attributes: EventAttributes | None = None) -> None:
    """Emit a business-milestone custom event (e.g. "service.start", "X.created")."""
    attrs = attributes or {}
    # Local visibility: a structured stdout line, with the Phase 1 bridge
    # opted OUT — the stdlib record below is the exported copy; a bridged
    # line would double-export to AppTraces.
    try:
        get_logger("app.events").bind(**{TELEMETRY_EXPORT_KEY: False}).info(
            "custom event", event_name=name, **attrs
        )
    except Exception:  # noqa: BLE001 - local logging is best-effort here
        pass
    try:
        if not get_observability_state()["enabled"]:
            return
        logging.getLogger(_EVENT_STDLIB_LOGGER).info(
            name, extra={CUSTOM_EVENT_MARKER: name, **attrs}
        )
    except Exception:  # noqa: BLE001 - an export problem must never break the caller
        pass
