from __future__ import annotations

from typing import Optional

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException

from .config import load_settings
from .schemas import (
    ExtractConstraintsRequest,
    ExtractConstraintsResponse,
    JobArtifactsResponse,
    JobRequest,
    JobSummary,
    SummarizeFailuresRequest,
    SummarizeFailuresResponse,
)
from .service import RoutingOrchestrator


app = FastAPI(title="Kargo Optimization Backend", version="1.0.0")
app.state.settings = load_settings()
app.state.orchestrator = None


def get_orchestrator() -> RoutingOrchestrator:
    orchestrator = app.state.orchestrator
    if orchestrator is None:
        orchestrator = RoutingOrchestrator(app.state.settings)
        app.state.orchestrator = orchestrator
    return orchestrator


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/jobs", response_model=JobSummary)
def create_job(
    request: JobRequest,
    background_tasks: BackgroundTasks,
    x_google_api_key: Optional[str] = Header(default=None, alias="X-Google-API-Key"),
) -> JobSummary:
    orchestrator = get_orchestrator()
    if x_google_api_key and x_google_api_key.strip():
        request.google_api_key = x_google_api_key.strip()
    summary = orchestrator.create_job(request)
    background_tasks.add_task(orchestrator.process_job, summary.job_id, request)
    return summary


@app.get("/api/jobs/{job_id}", response_model=JobSummary)
def get_job(job_id: str) -> JobSummary:
    orchestrator = get_orchestrator()
    try:
        return orchestrator.get_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/jobs/{job_id}/artifacts", response_model=JobArtifactsResponse)
def get_artifacts(job_id: str) -> JobArtifactsResponse:
    orchestrator = get_orchestrator()
    try:
        return JobArtifactsResponse(job_id=job_id, artifact_paths=orchestrator.get_artifacts(job_id))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/copilot/extract-constraints", response_model=ExtractConstraintsResponse)
def extract_constraints(
    request: ExtractConstraintsRequest,
    x_gemini_api_key: Optional[str] = Header(default=None, alias="X-Gemini-API-Key"),
) -> ExtractConstraintsResponse:
    orchestrator = get_orchestrator()
    return orchestrator.copilot.extract_constraints(request.text, request.known_centers, gemini_api_key=x_gemini_api_key)


@app.post("/api/copilot/summarize-failures", response_model=SummarizeFailuresResponse)
def summarize_failures(
    request: SummarizeFailuresRequest,
    x_gemini_api_key: Optional[str] = Header(default=None, alias="X-Gemini-API-Key"),
) -> SummarizeFailuresResponse:
    orchestrator = get_orchestrator()
    return orchestrator.copilot.summarize_failures(
        request.warnings,
        request.failed_deliveries,
        request.metrics,
        gemini_api_key=x_gemini_api_key,
    )
