"""Phase 0 observability config tests (offline — azure SDK monkeypatched).

Covers:
  - explicitly pinned fixed-percentage sampling (TRACE_SAMPLING_RATIO,
    OTEL_TRACES_SAMPLER precedence, invalid-value fallback)
  - cloud role identity env defaults (never override operator values)
  - idempotent init (process-wide guard around configure_azure_monitor)
  - fail-safe on configuration errors
"""

from __future__ import annotations

import socket
from typing import Any

import pytest
from fastapi import FastAPI

import app.observability as obs

FAKE_CONNECTION_STRING = (
    "InstrumentationKey=00000000-0000-0000-0000-000000000000;"
    "IngestionEndpoint=https://example.invalid/"
)

_ENV_KEYS = [
    "APPLICATIONINSIGHTS_CONNECTION_STRING",
    "OTEL_SERVICE_NAME",
    "OTEL_RESOURCE_ATTRIBUTES",
    "OTEL_TRACES_SAMPLER",
    "TRACE_SAMPLING_RATIO",
    "CONTAINER_APP_REPLICA_NAME",
    "HOSTNAME",
    "TELEMETRY_AUTH_MODE",
    "TELEMETRY_MANAGED_IDENTITY_CLIENT_ID",
]


@pytest.fixture(autouse=True)
def _clean_observability(monkeypatch: pytest.MonkeyPatch):
    """Isolate env + reset the process-wide guard/state around every test."""
    import os

    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    obs._reset_for_tests()
    yield
    # The code under test writes os.environ directly (apply_resource_defaults);
    # pop those leaks before monkeypatch restores any pre-existing values.
    for key in _ENV_KEYS:
        os.environ.pop(key, None)
    obs._reset_for_tests()


class TestResolveSamplingRatio:
    def test_defaults_to_full_sampling(self) -> None:
        assert obs.resolve_sampling_ratio() == 1.0

    def test_honors_trace_sampling_ratio(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRACE_SAMPLING_RATIO", "0.25")
        assert obs.resolve_sampling_ratio() == 0.25

    def test_accepts_boundaries(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRACE_SAMPLING_RATIO", "0")
        assert obs.resolve_sampling_ratio() == 0.0
        monkeypatch.setenv("TRACE_SAMPLING_RATIO", "1")
        assert obs.resolve_sampling_ratio() == 1.0

    @pytest.mark.parametrize("raw", ["not-a-number", "-0.5", "1.5", "nan"])
    def test_invalid_values_fall_back_to_full_sampling(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        monkeypatch.setenv("TRACE_SAMPLING_RATIO", raw)
        assert obs.resolve_sampling_ratio() == 1.0

    def test_empty_value_falls_back_without_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TRACE_SAMPLING_RATIO", "  ")
        assert obs.resolve_sampling_ratio() == 1.0

    def test_defers_to_standard_otel_sampler_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OTEL_TRACES_SAMPLER", "microsoft.rate_limited")
        monkeypatch.setenv("TRACE_SAMPLING_RATIO", "0.5")
        assert obs.resolve_sampling_ratio() is None


class TestApplyResourceDefaults:
    def test_defaults_otel_service_name(self) -> None:
        import os

        obs.apply_resource_defaults()
        assert os.environ["OTEL_SERVICE_NAME"] == "team-assistant-api"

    def test_never_overrides_operator_service_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setenv("OTEL_SERVICE_NAME", "my-renamed-api")
        obs.apply_resource_defaults()
        assert os.environ["OTEL_SERVICE_NAME"] == "my-renamed-api"

    def test_skips_service_name_when_present_in_resource_attributes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setenv(
            "OTEL_RESOURCE_ATTRIBUTES",
            "service.name=operator-api,service.instance.id=replica-1",
        )
        obs.apply_resource_defaults()
        assert "OTEL_SERVICE_NAME" not in os.environ
        # Operator attributes are untouched.
        assert (
            os.environ["OTEL_RESOURCE_ATTRIBUTES"]
            == "service.name=operator-api,service.instance.id=replica-1"
        )

    def test_appends_instance_id_preferring_replica_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setenv("CONTAINER_APP_REPLICA_NAME", "replica-abc")
        obs.apply_resource_defaults()
        assert os.environ["OTEL_RESOURCE_ATTRIBUTES"] == "service.instance.id=replica-abc"

    def test_falls_back_to_hostname_env_then_gethostname(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setenv("HOSTNAME", "pod-42")
        obs.apply_resource_defaults()
        assert os.environ["OTEL_RESOURCE_ATTRIBUTES"] == "service.instance.id=pod-42"

        monkeypatch.delenv("HOSTNAME")
        monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES")
        obs.apply_resource_defaults()
        assert (
            os.environ["OTEL_RESOURCE_ATTRIBUTES"] == f"service.instance.id={socket.gethostname()}"
        )

    def test_appends_to_operator_attributes_without_touching_them(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import os

        monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "cloud.region=westeurope")
        monkeypatch.setenv("HOSTNAME", "pod-42")
        obs.apply_resource_defaults()
        assert (
            os.environ["OTEL_RESOURCE_ATTRIBUTES"]
            == "cloud.region=westeurope,service.instance.id=pod-42"
        )

    def test_respects_operator_instance_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import os

        monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "service.instance.id=operator-instance")
        obs.apply_resource_defaults()
        assert os.environ["OTEL_RESOURCE_ATTRIBUTES"] == "service.instance.id=operator-instance"


class TestInitObservability:
    def _fake_azure(self, monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
        """Replace configure_azure_monitor with a recording fake."""
        calls: list[dict[str, Any]] = []

        def fake_configure(**kwargs: Any) -> None:
            calls.append(kwargs)

        monkeypatch.setattr("azure.monitor.opentelemetry.configure_azure_monitor", fake_configure)
        return calls

    def test_degraded_without_connection_string(self) -> None:
        state = obs.init_observability(FastAPI())
        assert state["enabled"] is False
        assert "connection string" in state["reason"].lower()

    def test_configures_once_and_pins_sampling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls = self._fake_azure(monkeypatch)
        monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", FAKE_CONNECTION_STRING)
        monkeypatch.setenv("TRACE_SAMPLING_RATIO", "0.25")

        state = obs.init_observability(FastAPI())
        assert state["enabled"] is True
        assert len(calls) == 1
        assert calls[0]["sampling_ratio"] == 0.25
        assert calls[0]["connection_string"] == FAKE_CONNECTION_STRING

        # Second init (e.g. a second create_app in the same process) must not
        # re-register the SDK.
        state = obs.init_observability(FastAPI())
        assert state["enabled"] is True
        assert len(calls) == 1

    def test_skips_sampling_kwarg_when_otel_sampler_env_set(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls = self._fake_azure(monkeypatch)
        monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", FAKE_CONNECTION_STRING)
        monkeypatch.setenv("OTEL_TRACES_SAMPLER", "microsoft.fixed_percentage")
        monkeypatch.setenv("OTEL_TRACES_SAMPLER_ARG", "0.1")

        obs.init_observability(FastAPI())
        assert len(calls) == 1
        assert "sampling_ratio" not in calls[0]

    def test_configuration_failure_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(**kwargs: Any) -> None:
            raise RuntimeError("boom")

        monkeypatch.setattr("azure.monitor.opentelemetry.configure_azure_monitor", boom)
        monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", FAKE_CONNECTION_STRING)

        state = obs.init_observability(FastAPI())
        assert state["enabled"] is False
        assert "boom" in state["reason"]

    def test_registers_system_metrics_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._fake_azure(monkeypatch)
        monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", FAKE_CONNECTION_STRING)
        seen: list[bool] = []
        monkeypatch.setattr(obs, "_instrument_system_metrics", lambda log: seen.append(True))

        state = obs.init_observability(FastAPI())
        assert state["enabled"] is True
        assert seen == [True]


class _RecordingCredential:
    def __init__(self, client_id: str | None = None) -> None:
        self.client_id = client_id


class TestAuthMode:
    def test_defaults_to_connection_string(self) -> None:
        assert obs.resolve_auth_mode() == {"mode": "connection_string", "client_id": None}

    def test_accepts_explicit_connection_string(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEMETRY_AUTH_MODE", "connection_string")
        assert obs.resolve_auth_mode()["mode"] == "connection_string"

    def test_managed_identity_with_optional_client_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("TELEMETRY_AUTH_MODE", "managed_identity")
        assert obs.resolve_auth_mode() == {"mode": "managed_identity", "client_id": None}
        monkeypatch.setenv("TELEMETRY_MANAGED_IDENTITY_CLIENT_ID", "client-123")
        assert obs.resolve_auth_mode()["client_id"] == "client-123"

    def test_mistyped_value_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("TELEMETRY_AUTH_MODE", "managed-identity")  # dash typo
        with pytest.raises(ValueError, match="TELEMETRY_AUTH_MODE"):
            obs.resolve_auth_mode()

    def test_init_disables_visibly_on_mistyped_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[dict[str, Any]] = []

        def fake_configure(**kwargs: Any) -> None:
            calls.append(kwargs)

        monkeypatch.setattr("azure.monitor.opentelemetry.configure_azure_monitor", fake_configure)
        monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", FAKE_CONNECTION_STRING)
        monkeypatch.setenv("TELEMETRY_AUTH_MODE", "aad")

        state = obs.init_observability(FastAPI())
        assert state["enabled"] is False
        assert "TELEMETRY_AUTH_MODE" in state["reason"]
        # No silent fallback to unauthenticated ingestion.
        assert calls == []

    def test_init_passes_managed_identity_credential(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[dict[str, Any]] = []

        def fake_configure(**kwargs: Any) -> None:
            calls.append(kwargs)

        monkeypatch.setattr("azure.monitor.opentelemetry.configure_azure_monitor", fake_configure)
        monkeypatch.setattr("azure.identity.ManagedIdentityCredential", _RecordingCredential)
        monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", FAKE_CONNECTION_STRING)
        monkeypatch.setenv("TELEMETRY_AUTH_MODE", "managed_identity")
        monkeypatch.setenv("TELEMETRY_MANAGED_IDENTITY_CLIENT_ID", "client-123")

        state = obs.init_observability(FastAPI())
        assert state["enabled"] is True
        assert len(calls) == 1
        credential = calls[0]["credential"]
        assert isinstance(credential, _RecordingCredential)
        assert credential.client_id == "client-123"

    def test_init_uses_system_assigned_identity_without_client_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[dict[str, Any]] = []

        def fake_configure(**kwargs: Any) -> None:
            calls.append(kwargs)

        monkeypatch.setattr("azure.monitor.opentelemetry.configure_azure_monitor", fake_configure)
        monkeypatch.setattr("azure.identity.ManagedIdentityCredential", _RecordingCredential)
        monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", FAKE_CONNECTION_STRING)
        monkeypatch.setenv("TELEMETRY_AUTH_MODE", "managed_identity")

        obs.init_observability(FastAPI())
        assert calls[0]["credential"].client_id is None

    def test_default_mode_sends_no_credential(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[dict[str, Any]] = []

        def fake_configure(**kwargs: Any) -> None:
            calls.append(kwargs)

        monkeypatch.setattr("azure.monitor.opentelemetry.configure_azure_monitor", fake_configure)
        monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", FAKE_CONNECTION_STRING)

        obs.init_observability(FastAPI())
        assert "credential" not in calls[0]


class TestInstrumentSystemMetrics:
    class _FakeLog:
        def __init__(self) -> None:
            self.warnings: list[str] = []

        def warning(self, message: str, **_kwargs: Any) -> None:
            self.warnings.append(message)

    def test_selects_runtime_only_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: list[dict[str, Any]] = []

        class FakeInstrumentor:
            def __init__(self, config: dict[str, Any]) -> None:
                captured.append(config)

            def instrument(self) -> None:
                pass

        monkeypatch.setattr(
            "opentelemetry.instrumentation.system_metrics.SystemMetricsInstrumentor",
            FakeInstrumentor,
        )
        log = self._FakeLog()
        obs._instrument_system_metrics(log)

        assert log.warnings == []
        assert len(captured) == 1
        assert captured[0], "runtime config must not be empty"
        assert all(key.startswith(("process.", "cpython.")) for key in captured[0])

    def test_swallows_instrumentor_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class BoomInstrumentor:
            def __init__(self, config: dict[str, Any]) -> None:
                raise RuntimeError("sysm boom")

        monkeypatch.setattr(
            "opentelemetry.instrumentation.system_metrics.SystemMetricsInstrumentor",
            BoomInstrumentor,
        )
        log = self._FakeLog()
        obs._instrument_system_metrics(log)  # must not raise
        assert log.warnings == ["system-metrics instrumentation failed"]


class _WarningLog:
    def __init__(self) -> None:
        self.warnings: list[str] = []

    def warning(self, message: str, **_kwargs: Any) -> None:
        self.warnings.append(message)


class TestInstrumentSqlalchemy:
    """DB dependency spans (ADR-0008): explicit, fail-safe SQLAlchemy engine instrumentation,
    registered WITHOUT an engine so every lazily created engine is covered."""

    def test_registers_instrumentor_without_an_engine(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[dict[str, Any]] = []

        class FakeInstrumentor:
            def instrument(self, **kwargs: Any) -> None:
                calls.append(kwargs)

        monkeypatch.setattr(
            "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor", FakeInstrumentor
        )
        log = _WarningLog()
        obs._instrument_sqlalchemy(log)
        assert calls == [{}]  # no engine= kwarg: wraps create_async_engine globally
        assert log.warnings == []

    def test_swallows_instrumentor_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class BoomInstrumentor:
            def instrument(self, **_kwargs: Any) -> None:
                raise RuntimeError("sqlalchemy boom")

        monkeypatch.setattr(
            "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor", BoomInstrumentor
        )
        log = _WarningLog()
        obs._instrument_sqlalchemy(log)  # must not raise
        assert log.warnings == ["sqlalchemy instrumentation failed"]

    def test_init_registers_sqlalchemy_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "azure.monitor.opentelemetry.configure_azure_monitor", lambda **kwargs: None
        )
        monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", FAKE_CONNECTION_STRING)
        seen: list[bool] = []
        monkeypatch.setattr(obs, "_instrument_sqlalchemy", lambda log: seen.append(True))

        state = obs.init_observability(FastAPI())
        assert state["enabled"] is True
        assert seen == [True]

    def test_init_skips_sqlalchemy_when_degraded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[bool] = []
        monkeypatch.setattr(obs, "_instrument_sqlalchemy", lambda log: seen.append(True))

        state = obs.init_observability(FastAPI())  # no connection string -> degraded
        assert state["enabled"] is False
        assert seen == []
