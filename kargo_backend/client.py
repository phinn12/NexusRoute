from __future__ import annotations

import httpx

from .config import Settings, load_settings
from .schemas import (
    ExtractConstraintsRequest,
    ExtractConstraintsResponse,
    JobArtifactsResponse,
    JobRequest,
    JobSummary,
    SummarizeFailuresRequest,
    SummarizeFailuresResponse,
)
from .utils import model_dump


class BackendClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self.base_url = self.settings.backend_base_url.rstrip("/")

    def create_job(self, request: JobRequest, google_api_key: str | None = None) -> JobSummary:
        response = httpx.post(
            f"{self.base_url}/api/jobs",
            json=model_dump(request),
            headers=self._google_headers(google_api_key),
            timeout=60.0,
        )
        response.raise_for_status()
        return JobSummary(**response.json())

    def get_job(self, job_id: str) -> JobSummary:
        response = httpx.get(f"{self.base_url}/api/jobs/{job_id}", timeout=30.0)
        response.raise_for_status()
        return JobSummary(**response.json())

    def get_artifacts(self, job_id: str) -> JobArtifactsResponse:
        response = httpx.get(f"{self.base_url}/api/jobs/{job_id}/artifacts", timeout=30.0)
        response.raise_for_status()
        return JobArtifactsResponse(**response.json())

    def extract_constraints(
        self,
        request: ExtractConstraintsRequest,
        gemini_api_key: str | None = None,
    ) -> ExtractConstraintsResponse:
        response = httpx.post(
            f"{self.base_url}/api/copilot/extract-constraints",
            json=model_dump(request),
            headers=self._copilot_headers(gemini_api_key),
            timeout=60.0,
        )
        response.raise_for_status()
        return ExtractConstraintsResponse(**response.json())

    def summarize_failures(
        self,
        request: SummarizeFailuresRequest,
        gemini_api_key: str | None = None,
    ) -> SummarizeFailuresResponse:
        response = httpx.post(
            f"{self.base_url}/api/copilot/summarize-failures",
            json=model_dump(request),
            headers=self._copilot_headers(gemini_api_key),
            timeout=60.0,
        )
        response.raise_for_status()
        return SummarizeFailuresResponse(**response.json())

    def _copilot_headers(self, gemini_api_key: str | None) -> dict[str, str]:
        if gemini_api_key and gemini_api_key.strip():
            return {"X-Gemini-API-Key": gemini_api_key.strip()}
        return {}

    def _google_headers(self, google_api_key: str | None) -> dict[str, str]:
        if google_api_key and google_api_key.strip():
            return {"X-Google-API-Key": google_api_key.strip()}
        return {}
