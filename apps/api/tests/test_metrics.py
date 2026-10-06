"""Custom-metric helper tests (Phase 3, offline):
- namespaced meters ("ai-accelerator.<scope>") from the global provider
- bounded status classes / outbound-target labels
- starter instruments record with bounded attributes only
- recording is best-effort: a throwing meter never breaks the caller
"""

from __future__ import annotations

import math
from typing import Any

import pytest

import app.metrics as metrics_mod


class _FakeHistogram:
    def __init__(self, name: str, sink: list[dict[str, Any]], throw: bool) -> None:
        self._name = name
        self._sink = sink
        self._throw = throw

    def record(self, value: float, attributes: dict[str, Any]) -> None:
        if self._throw:
            raise RuntimeError("meter boom")
        self._sink.append({"instrument": self._name, "value": value, "attributes": attributes})


class _FakeMeter:
    def __init__(self, sink: list[dict[str, Any]], throw: bool) -> None:
        self._sink = sink
        self._throw = throw

    def create_histogram(self, name: str, **_kwargs: Any) -> _FakeHistogram:
        return _FakeHistogram(name, self._sink, self._throw)


class _FakeMetricsModule:
    def __init__(self, throw: bool = False) -> None:
        self.recorded: list[dict[str, Any]] = []
        self.meter_names: list[str] = []
        self._throw = throw

    def get_meter(self, name: str) -> _FakeMeter:
        self.meter_names.append(name)
        return _FakeMeter(self.recorded, self._throw)


@pytest.fixture()
def fake_metrics(monkeypatch: pytest.MonkeyPatch) -> _FakeMetricsModule:
    fake = _FakeMetricsModule()
    monkeypatch.setattr(metrics_mod, "_otel_metrics", fake)
    metrics_mod._reset_for_tests()
    yield fake
    metrics_mod._reset_for_tests()


class TestGetMeter:
    def test_namespaces_meters(self, fake_metrics: _FakeMetricsModule) -> None:
        metrics_mod.get_meter("billing")
        assert "ai-accelerator.billing" in fake_metrics.meter_names


class TestStatusClass:
    @pytest.mark.parametrize(
        ("status", "expected"),
        [(200, "2xx"), (204, "2xx"), (301, "3xx"), (404, "4xx"), (502, "5xx")],
    )
    def test_maps_codes(self, status: int, expected: str) -> None:
        assert metrics_mod.status_class(status) == expected

    @pytest.mark.parametrize("status", [0, 99, 600, True, math.nan])
    def test_collapses_out_of_range_to_unknown(self, status: Any) -> None:
        assert metrics_mod.status_class(status) == "unknown"


class TestResolveTarget:
    def test_labels_api_upstream(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_BASE_URL", "http://localhost:8000")
        assert metrics_mod.resolve_target("http://localhost:8000/ping") == "api"

    def test_collapses_unknown_hosts_to_other(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("API_BASE_URL", raising=False)
        assert metrics_mod.resolve_target("https://example.com/x") == "other"

    def test_collapses_invalid_urls_to_other(self) -> None:
        assert metrics_mod.resolve_target("not a url") == "other"


class TestRecordServerDuration:
    def test_records_bounded_attributes(self, fake_metrics: _FakeMetricsModule) -> None:
        metrics_mod.record_server_duration("/v1/things/{id}", "GET", 200, 12.5)
        assert fake_metrics.recorded == [
            {
                "instrument": "ai-accelerator.http.server.duration",
                "value": 12.5,
                "attributes": {
                    "route_class": "/v1/things/{id}",
                    "method": "GET",
                    "status_class": "2xx",
                },
            }
        ]

    def test_never_raises_when_meter_throws(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeMetricsModule(throw=True)
        monkeypatch.setattr(metrics_mod, "_otel_metrics", fake)
        metrics_mod._reset_for_tests()
        metrics_mod.record_server_duration("/x", "GET", 200, 1.0)  # must not raise
        metrics_mod._reset_for_tests()


class TestRecordHopDuration:
    def test_records_target_and_outcome(self, fake_metrics: _FakeMetricsModule) -> None:
        metrics_mod.record_hop_duration("api", "2xx", 5.0)
        assert fake_metrics.recorded == [
            {
                "instrument": "ai-accelerator.http.client.hop.duration",
                "value": 5.0,
                "attributes": {"target": "api", "outcome": "2xx"},
            }
        ]

    def test_never_raises_when_meter_throws(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake = _FakeMetricsModule(throw=True)
        monkeypatch.setattr(metrics_mod, "_otel_metrics", fake)
        metrics_mod._reset_for_tests()
        metrics_mod.record_hop_duration("api", "error", 1.0)  # must not raise
        metrics_mod._reset_for_tests()
