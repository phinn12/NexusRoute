from pathlib import Path

from kargo_backend.config import load_settings
from kargo_backend.copilot import OperationsCopilot
from kargo_backend.providers.base import ProviderError
from kargo_backend.schemas import ArtifactPaths, JobRequest, RoutePlan, Stop, VehicleConfig, VehicleRoute
from kargo_backend.service import RoutingOrchestrator


class FailingGoogleProvider:
    def optimize(self, *args, **kwargs):
        raise ProviderError("google unavailable")


class FakeLocalProvider:
    def optimize(self, stops, vehicle_config, preserve_centers, job_dir, runtime_google_api_key=None):
        return RoutePlan(
            provider_used="local",
            total_distance_km=1.2,
            total_duration_seconds=120,
            vehicle_count=1,
            stop_count=len(stops),
            routes=[
                VehicleRoute(
                    vehicle_id="Merter Merkez-Arac-1",
                    center_name="Merter Merkez",
                    center_lat=41.04,
                    center_lng=28.85,
                    stop_count=len(stops),
                    total_distance_km=1.2,
                    total_duration_seconds=120,
                )
            ],
        )


def test_auto_provider_falls_back_to_local(monkeypatch, tmp_path):
    settings = load_settings(tmp_path)
    orchestrator = RoutingOrchestrator(settings)
    orchestrator.google_provider = FailingGoogleProvider()
    orchestrator.local_provider = FakeLocalProvider()
    monkeypatch.setattr("kargo_backend.service.render_route_plan", lambda plan, artifacts: artifacts)

    summary, plan = orchestrator.run_job_sync(
        JobRequest(
            stops=[Stop(id="1", merkez="Merter Merkez", mahalle="A", formatted_address="A", lat=41.05, lng=28.86)],
            vehicle_config={"Merter Merkez": VehicleConfig(arac_sayisi=1, kapasite=10, kisi_sayisi=1)},
            provider="auto",
            preserve_centers=True,
        ),
        job_dir=tmp_path / "job_auto",
    )

    assert summary.provider_used == "local"
    assert any("fallback" in warning for warning in plan.warnings)


def test_copilot_returns_unavailable_without_api_key(tmp_path):
    settings = load_settings(tmp_path)
    copilot = OperationsCopilot(settings)
    result = copilot.extract_constraints("Merter durakları kalsın", ["Merter Merkez"])
    assert result.available is False
    assert result.constraints is None
    assert "Gemini API key" in result.warnings[0]


def test_copilot_extracts_constraints_with_runtime_gemini_key(monkeypatch, tmp_path):
    settings = load_settings(tmp_path)
    copilot = OperationsCopilot(settings)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": '{"preferred_center":"Merter Merkez","preserve_centers":true,"max_stops_per_vehicle":80,"max_vehicle_capacity":null,"delivery_notes":["merkezleri koru"],"risk_flags":[]}'
                                }
                            ]
                        }
                    }
                ]
            }

    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("kargo_backend.copilot.httpx.post", fake_post)

    result = copilot.extract_constraints(
        "Merter durakları merkezlerinde kalsın, araç başına en fazla 80 teslimat olsun.",
        ["Merter Merkez"],
        gemini_api_key="gem-runtime-key",
    )

    assert result.available is True
    assert result.model == settings.gemini_model
    assert result.constraints.preferred_center == "Merter Merkez"
    assert captured["headers"]["x-goog-api-key"] == "gem-runtime-key"
