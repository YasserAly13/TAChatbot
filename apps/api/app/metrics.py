"""Custom-metric helpers (Phase 3 — see .claude/rules/60-observability.md).

``get_meter()`` returns namespaced meters ("team-assistant.<scope>") from the
GLOBAL MeterProvider. In degraded mode no provider is registered, so the OTel
API hands back its no-op proxy meter — feature code records metrics
unconditionally and never null-checks telemetry.

CARDINALITY DISCIPLINE (required): metric attributes use BOUNDED value sets
only — route classes, methods, status classes, outcomes, targets — never ids,
names, emails, or paths with parameters. App Insights bills every attribute
combination as its own series (cap: 5,000 series/metric/day).
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

from opentelemetry import metrics as _otel_metrics
from opentelemetry.metrics import Histogram, Meter

_METER_PREFIX = "team-assistant"

_SERVER_DURATION_NAME = "team-assistant.http.server.duration"
_HOP_DURATION_NAME = "team-assistant.http.client.hop.duration"

_server_duration: Histogram | None = None
_hop_duration: Histogram | None = None


def get_meter(scope: str) -> Meter:
    """Namespaced meter accessor: get_meter("http") → meter "team-assistant.http"."""
    return _otel_metrics.get_meter(f"{_METER_PREFIX}.{scope}")


def status_class(status: int) -> str:
    """Map an HTTP status code onto its bounded class ("2xx".."5xx", "unknown")."""
    if not isinstance(status, int) or isinstance(status, bool) or not 100 <= status <= 599:
        return "unknown"
    return f"{status // 100}xx"


def resolve_target(url: str) -> str:
    """Bounded outbound-target label from a URL's origin.

    Matched against the configured upstream base URL (API_BASE_URL — not
    set in this service's baseline, which has no downstream service, so
    everything collapses to "other"). Unknown/invalid URLs collapse to "other"
    so the attribute can never explode in cardinality. Label set:
    "api" | "other" — mirrors the BFF's label set so both services report
    the same target vocabulary; when this service gains a real downstream
    target, add its bounded label here (and in the rule 60 label list).
    """
    try:
        origin = _origin(url)
        if not origin:
            return "other"
        python_base = os.environ.get("API_BASE_URL", "")
        if python_base and _origin(python_base) == origin:
            return "api"
        return "other"
    except Exception:  # noqa: BLE001 - a label helper must never raise
        return "other"


def _origin(url: str) -> str | None:
    parts = urlsplit(url)
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def _server_duration_histogram() -> Histogram:
    global _server_duration
    if _server_duration is None:
        _server_duration = get_meter("http").create_histogram(
            _SERVER_DURATION_NAME,
            unit="ms",
            description="Inbound HTTP request duration by route class and status class",
        )
    return _server_duration


def _hop_duration_histogram() -> Histogram:
    global _hop_duration
    if _hop_duration is None:
        _hop_duration = get_meter("http").create_histogram(
            _HOP_DURATION_NAME,
            unit="ms",
            description="Outbound service-to-service hop duration by target and outcome",
        )
    return _hop_duration


def record_server_duration(
    route_class: str, method: str, status_code: int, duration_ms: float
) -> None:
    """Record one inbound request duration sample. Best-effort — never raises."""
    try:
        _server_duration_histogram().record(
            duration_ms,
            {
                "route_class": route_class,
                "method": method,
                "status_class": status_class(status_code),
            },
        )
    except Exception:  # noqa: BLE001 - metrics must never break the request path
        pass


def record_hop_duration(target: str, outcome: str, duration_ms: float) -> None:
    """Record one outbound chain-hop duration sample. Best-effort — never raises."""
    try:
        _hop_duration_histogram().record(duration_ms, {"target": target, "outcome": outcome})
    except Exception:  # noqa: BLE001 - metrics must never break the request path
        pass


def _reset_for_tests() -> None:
    """TEST-ONLY: drop cached instruments so a swapped provider takes effect."""
    global _server_duration, _hop_duration
    _server_duration = None
    _hop_duration = None
