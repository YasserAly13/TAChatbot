"""Fail-safe Azure Monitor / OpenTelemetry observability wiring.

Uses azure-monitor-opentelemetry's ``configure_azure_monitor()`` plus explicit
FastAPI, httpx and SQLAlchemy (DB dependency spans, ADR-0008) instrumentation.
Everything is wrapped so that a missing
connection string or any configuration failure degrades gracefully to local
stdout logging instead of crashing the service.

INIT-ORDER DISCIPLINE: unlike the Node services (which rely on import-time
patching), this service instruments explicitly — ``configure_azure_monitor()``
registers the providers, then ``FastAPIInstrumentor.instrument_app(app)`` and
``HTTPXClientInstrumentor().instrument()`` patch the frameworks directly, so
init just needs to run inside ``create_app()`` before requests are served.

IDEMPOTENT: the process-wide pieces (``configure_azure_monitor``, httpx
patching) run at most once per process, guarded by a module flag; the per-app
FastAPI instrumentation is guarded by the instrumentor's own per-app flag.

SAMPLING IS PINNED EXPLICITLY: azure-monitor-opentelemetry >= 1.8.6 defaults
to RATE-LIMITED sampling (~5 traces/sec) — a silent telemetry cap. We pass
``sampling_ratio`` (fixed percentage, default 1.0 = 100%, tunable via
TRACE_SAMPLING_RATIO). The kwarg is SKIPPED when the standard
OTEL_TRACES_SAMPLER env var is set, so the standard OTel env config takes
precedence (verified against the distro: a ``sampling_ratio`` kwarg would
otherwise shadow an env-selected ``microsoft.rate_limited`` sampler).

CLOUD ROLE IDENTITY: service.name (→ App Insights cloud role name) and
service.instance.id (→ cloud role instance) are defaulted via the standard
OTEL_SERVICE_NAME / OTEL_RESOURCE_ATTRIBUTES env vars (read by the distro's
``Resource.create()``). Defaults are append-only: operator-provided values are
NEVER overridden. service.namespace is deliberately not set.

API references (azure-monitor-opentelemetry 1.8.8 / OTEL 0.61b0 line):
    configure_azure_monitor(connection_string=..., logger_name=..., sampling_ratio=...)
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument()   # opentelemetry-instrumentation-sqlalchemy 0.61b0
The Azure distro exports telemetry via batch processors (non-blocking) by
default, so request handling is never blocked on export.

DB SPANS (ADR-0008): the distro's default instrumentation set (azure_sdk, django,
fastapi, flask, psycopg2, requests, urllib, urllib3 — verified in its
``_constants.py``) does NOT cover the ``mssql+aioodbc`` engines, so the
SQLAlchemy instrumentor is registered explicitly here — WITHOUT an engine, which
makes it wrap ``sqlalchemy.ext.asyncio.create_async_engine`` (verified in the
0.61b0 source) so every engine created afterwards is traced: the lazy project
engine (``app/db/engine.py``) and the lazy read-only external engine
(``app/db/external.py``), whichever is built first. Both resolve
``create_async_engine`` at call time for exactly this reason. Fail-safe like
everything else in this module.
"""

from __future__ import annotations

import logging
import os
import socket
from typing import Any

from app.config import DEFAULT_OTEL_SERVICE_NAME, get_settings
from app.logging_config import get_logger

_DISABLED_WARNING = (
    "Observability disabled: no Azure connection string — running with local stdout logging only"
)

TRACE_SAMPLING_RATIO_ENV = "TRACE_SAMPLING_RATIO"

TELEMETRY_AUTH_MODE_ENV = "TELEMETRY_AUTH_MODE"
TELEMETRY_MANAGED_IDENTITY_CLIENT_ID_ENV = "TELEMETRY_MANAGED_IDENTITY_CLIENT_ID"

# Module-level observability state; updated by init_observability().
_state: dict[str, Any] = {"enabled": False, "reason": "not initialized"}

# Process-wide guard: configure_azure_monitor()/httpx patching must run once.
_configured = False


def get_observability_state() -> dict[str, Any]:
    """Return the current observability state: {"enabled", "reason"}."""
    return {"enabled": _state["enabled"], "reason": _state["reason"]}


def resolve_sampling_ratio() -> float | None:
    """Resolve the fixed-percentage sampling ratio to pass to the distro.

    - OTEL_TRACES_SAMPLER set  -> ``None``: skip the kwarg so the standard OTel
      env config drives sampling (kwarg would otherwise shadow it).
    - TRACE_SAMPLING_RATIO set -> parsed float in [0, 1]; invalid values warn
      and fall back to 1.0 (never crash, never silently under-sample).
    - otherwise                -> 1.0 (100%).
    """
    if os.environ.get("OTEL_TRACES_SAMPLER", "").strip():
        return None
    raw = os.environ.get(TRACE_SAMPLING_RATIO_ENV, "").strip()
    if not raw:
        return 1.0
    log = get_logger("app.observability")
    try:
        value = float(raw)
    except ValueError:
        log.warning(
            "Invalid TRACE_SAMPLING_RATIO — expected a number in [0, 1]; using 1.0",
            raw_value=raw,
        )
        return 1.0
    if not 0.0 <= value <= 1.0:
        log.warning(
            "Invalid TRACE_SAMPLING_RATIO — expected a number in [0, 1]; using 1.0",
            raw_value=raw,
        )
        return 1.0
    return value


def resolve_auth_mode() -> dict[str, Any]:
    """Resolve the telemetry ingestion auth mode (Phase 4 ingestion hardening).

    - unset/"" or "connection_string" -> connection-string ingestion (default).
    - "managed_identity" -> Entra ID ingestion via ManagedIdentityCredential
      (system-assigned, or user-assigned when
      TELEMETRY_MANAGED_IDENTITY_CLIENT_ID is set). Requires the identity to
      hold "Monitoring Metrics Publisher" on the App Insights component.
    - anything else -> raises ValueError. A mistyped value must degrade
      VISIBLY (observability disabled, reason on /health) — never silently
      fall back to unauthenticated ingestion.
    """
    raw = os.environ.get(TELEMETRY_AUTH_MODE_ENV, "").strip()
    if raw in ("", "connection_string"):
        return {"mode": "connection_string", "client_id": None}
    if raw == "managed_identity":
        client_id = os.environ.get(TELEMETRY_MANAGED_IDENTITY_CLIENT_ID_ENV, "").strip() or None
        return {"mode": "managed_identity", "client_id": client_id}
    raise ValueError(
        f'invalid TELEMETRY_AUTH_MODE "{raw}" — expected "connection_string" or "managed_identity"'
    )


def _has_resource_attribute(attrs: str, key: str) -> bool:
    """True when OTEL_RESOURCE_ATTRIBUTES already carries the given key."""
    return any(pair.strip().startswith(f"{key}=") for pair in attrs.split(","))


def apply_resource_defaults() -> None:
    """Default the OTel resource identity via env vars (append-only).

    Read by the distro's ``Resource.create()``; operator-provided
    OTEL_SERVICE_NAME / OTEL_RESOURCE_ATTRIBUTES values are never overridden.

    - service.name        -> cloud role name (default: team-assistant-api)
    - service.instance.id -> cloud role instance (container replica name,
      then HOSTNAME, then socket.gethostname() fallback)
    """
    attrs = os.environ.get("OTEL_RESOURCE_ATTRIBUTES", "")
    if not os.environ.get("OTEL_SERVICE_NAME") and not _has_resource_attribute(
        attrs, "service.name"
    ):
        os.environ["OTEL_SERVICE_NAME"] = DEFAULT_OTEL_SERVICE_NAME
    if not _has_resource_attribute(attrs, "service.instance.id"):
        instance_id = (
            os.environ.get("CONTAINER_APP_REPLICA_NAME")
            or os.environ.get("HOSTNAME")
            or socket.gethostname()
        )
        os.environ["OTEL_RESOURCE_ATTRIBUTES"] = (
            f"{attrs},service.instance.id={instance_id}"
            if attrs
            else f"service.instance.id={instance_id}"
        )


def _instrument_fastapi(app: Any, log: Any) -> None:
    """Explicitly instrument the FastAPI app (best-effort, per-app guard)."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:  # noqa: BLE001
        log.warning("fastapi instrumentation failed", error=str(exc))


def _instrument_httpx(log: Any) -> None:
    """Explicitly instrument the httpx client (best-effort)."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception as exc:  # noqa: BLE001
        log.warning("httpx instrumentation failed", error=str(exc))


def _instrument_sqlalchemy(log: Any) -> None:
    """DB dependency spans via SQLAlchemy engine instrumentation (ADR-0008).

    Registered WITHOUT an engine so it wraps ``create_async_engine`` and covers
    every lazy engine created later (project + external read-only). Not part of
    the Azure distro's default set, hence explicit. Best-effort: a failure here
    only costs DB spans, never the service.
    """
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument()
    except Exception as exc:  # noqa: BLE001
        log.warning("sqlalchemy instrumentation failed", error=str(exc))


def _instrument_system_metrics(log: Any) -> None:
    """Runtime-health metrics (Phase 3, best-effort): GC, memory, CPU, threads.

    Uses the system-metrics instrumentor pinned to the distro's 0.61b0 line,
    with a RUNTIME-ONLY selection (``process.*`` + ``cpython.*``): the default
    config would also emit host-wide disk/network/swap series — noise inside a
    container. ``_DEFAULT_CONFIG`` is private but version-pinned; the whole
    call is best-effort either way.
    """
    try:
        from opentelemetry.instrumentation.system_metrics import (
            _DEFAULT_CONFIG,
            SystemMetricsInstrumentor,
        )

        runtime_config = {
            key: value
            for key, value in _DEFAULT_CONFIG.items()
            if key.startswith(("process.", "cpython."))
        }
        SystemMetricsInstrumentor(config=runtime_config).instrument()
    except Exception as exc:  # noqa: BLE001
        log.warning("system-metrics instrumentation failed", error=str(exc))


def init_observability(app: Any) -> dict[str, Any]:
    """Initialize observability in a fail-safe, idempotent manner.

    - No connection string -> disabled, reason "no Azure connection string",
      and a clear WARNING is logged.
    - configure_azure_monitor() failure -> swallowed, disabled with reason.
    - Second call in the same process -> no re-registration (module guard);
      only the per-app FastAPI instrumentation runs for a new app instance.
    - Never raises.

    Returns the resulting state dict.
    """
    global _configured
    log = get_logger("app.observability")
    settings = get_settings()

    # Ingestion auth mode is validated FIRST: a mistyped value disables
    # telemetry visibly instead of silently ingesting unauthenticated.
    try:
        auth = resolve_auth_mode()
    except ValueError as exc:
        _state["enabled"] = False
        _state["reason"] = str(exc)
        log.warning(
            "Observability disabled: invalid TELEMETRY_AUTH_MODE — refusing to fall "
            "back to unauthenticated ingestion; running with local stdout logging only",
            error=str(exc),
        )
        return get_observability_state()

    if not settings.has_connection_string:
        _state["enabled"] = False
        _state["reason"] = "no Azure connection string"
        log.warning(_DISABLED_WARNING)
        return get_observability_state()

    try:
        if not _configured:
            apply_resource_defaults()
            sampling_ratio = resolve_sampling_ratio()

            from azure.monitor.opentelemetry import configure_azure_monitor

            kwargs: dict[str, Any] = {
                "connection_string": settings.applicationinsights_connection_string,
                # Capture logs from the application's logger namespace only,
                # avoiding telemetry feedback loops from the SDK itself.
                "logger_name": "app",
            }
            # Pin fixed-percentage sampling; the distro (>=1.8.6) otherwise
            # defaults to rate-limited sampling (~5 traces/sec) and silently
            # drops telemetry. None => OTEL_TRACES_SAMPLER env config wins.
            if sampling_ratio is not None:
                kwargs["sampling_ratio"] = sampling_ratio
            # Entra ID ingestion (Phase 4 hardening): the credential makes the
            # exporter send AAD-authenticated telemetry; pairs with
            # DisableLocalAuth on the component (infra/main.bicep).
            if auth["mode"] == "managed_identity":
                from azure.identity import ManagedIdentityCredential

                kwargs["credential"] = (
                    ManagedIdentityCredential(client_id=auth["client_id"])
                    if auth["client_id"]
                    else ManagedIdentityCredential()
                )

            configure_azure_monitor(**kwargs)
            _instrument_httpx(log)
            _instrument_sqlalchemy(log)
            _instrument_system_metrics(log)
            # The distro's LoggingHandler now sits on the stdlib "app" logger
            # (the structlog bridge emits through "app.telemetry" → "app").
            # Stop propagation to root so bridged records don't ALSO print a
            # bare duplicate via the root StreamHandler — structlog already
            # writes the structured stdout line itself.
            logging.getLogger("app").propagate = False
            _configured = True
            log.info(
                "observability configured",
                service_name=os.environ.get("OTEL_SERVICE_NAME", settings.otel_service_name),
                sampling_ratio=sampling_ratio if sampling_ratio is not None else "OTEL env",
                auth_mode=auth["mode"],
            )

        # Per-app instrumentation (its own per-app guard makes repeats safe).
        _instrument_fastapi(app, log)

        _state["enabled"] = True
        _state["reason"] = "azure monitor configured"
    except Exception as exc:  # noqa: BLE001
        _state["enabled"] = False
        _state["reason"] = f"configure_azure_monitor failed: {exc}"
        log.warning(
            "Observability disabled: configuration failed — running with local stdout logging only",
            error=str(exc),
        )

    return get_observability_state()


def _reset_for_tests() -> None:
    """TEST-ONLY: clear the process-wide guard + state between test cases."""
    global _configured
    _configured = False
    _state["enabled"] = False
    _state["reason"] = "not initialized"
    logging.getLogger("app").propagate = True
