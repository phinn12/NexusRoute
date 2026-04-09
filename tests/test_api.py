from fastapi.testclient import TestClient

from kargo_backend.api import app
from kargo_backend.schemas import (
    ArtifactPaths,
    ExtractConstraintsResponse,
    FailureSummary,
    JobSummary,
    SummarizeFailuresResponse,
)


class FakeCopilot:
    def __init__(self):
        self.last_gemini_api_key = None

    def extract_constraints(self, text, known_centers, gemini_api_key=None):
        self.last_gemini_api_key = gemini_api_key
        return ExtractConstraintsResponse(available=False, warnings=["disabled"])

    def summarize_failures(self, warnings, failed_deliveries, metrics, gemini_api_key=None):
        self.last_gemini_api_key = gemini_api_key
        return SummarizeFailuresResponse(available=True, summary=FailureSummary(summary="ok"))


class FakeOrchestrator:
    def __init__(self):
        artifacts = ArtifactPaths(job_dir="/tmp/job_1")
        self.last_create_request = None
        self.summary = JobSummary(
            job_id="job_1",
            status="completed",
            provider_requested="local",
            provider_used="local",
            total_distance_km=1.0,
            vehicle_count=1,
            stop_count=1,
            artifact_paths=artifacts,
        )
        self.copilot = FakeCopilot()

    def create_job(self, request):
        self.last_create_request = request
        return JobSummary(
            job_id="job_1",
            status="pending",
            provider_requested=request.provider,
            artifact_paths=self.summary.artifact_paths,
        )

    def process_job(self, job_id, request):
        return None

    def get_job(self, job_id):
        return self.summary

    def get_artifacts(self, job_id):
        return self.summary.artifact_paths


def test_api_endpoints():
    original_orchestrator = app.state.orchestrator
    app.state.orchestrator = FakeOrchestrator()
    client = TestClient(app)

    create_response = client.post(
        "/api/jobs",
        json={
            "stops": [{"id": "1", "merkez": "Merter Merkez", "formatted_address": "A", "lat": 41.0, "lng": 28.8}],
            "vehicle_config": {"Merter Merkez": {"arac_sayisi": 1, "kapasite": 10, "kisi_sayisi": 1}},
            "provider": "local",
            "preserve_centers": True,
        },
    )
    assert create_response.status_code == 200
    assert create_response.json()["status"] == "pending"

    status_response = client.get("/api/jobs/job_1")
    assert status_response.status_code == 200
    assert status_response.json()["provider_used"] == "local"

    copilot_response = client.post("/api/copilot/extract-constraints", json={"text": "abc", "known_centers": []})
    assert copilot_response.status_code == 200
    assert copilot_response.json()["available"] is False

    header_response = client.post(
        "/api/copilot/extract-constraints",
        json={"text": "abc", "known_centers": []},
        headers={"X-Gemini-API-Key": "gem-test-key"},
    )
    assert header_response.status_code == 200
    assert app.state.orchestrator.copilot.last_gemini_api_key == "gem-test-key"

    google_job_response = client.post(
        "/api/jobs",
        json={
            "stops": [{"id": "1", "merkez": "Merter Merkez", "formatted_address": "A", "lat": 41.0, "lng": 28.8}],
            "vehicle_config": {"Merter Merkez": {"arac_sayisi": 1, "kapasite": 10, "kisi_sayisi": 1}},
            "provider": "google",
            "preserve_centers": True,
        },
        headers={"X-Google-API-Key": "google-test-key"},
    )
    assert google_job_response.status_code == 200
    assert app.state.orchestrator.last_create_request.google_api_key == "google-test-key"

    app.state.orchestrator = original_orchestrator
