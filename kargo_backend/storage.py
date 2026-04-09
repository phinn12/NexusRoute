from __future__ import annotations

from pathlib import Path
import threading
import uuid

from .config import Settings
from .schemas import ArtifactPaths, JobRequest, JobSummary
from .utils import model_dump, read_json, utc_now_iso, write_json


class FileJobStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.jobs_root = settings.output_dir / "jobs"
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._recover_interrupted_jobs()

    def create_job(self, request: JobRequest) -> JobSummary:
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        job_dir = self.jobs_root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        artifact_paths = ArtifactPaths(
            job_dir=str(job_dir),
            request_json=str(job_dir / "request.json"),
            normalized_csv=str(job_dir / "normalized.csv"),
            route_plan_json=str(job_dir / "route_plan.json"),
            metrics_json=str(job_dir / "metrics.json"),
            route_map_html=str(job_dir / "route_map.html"),
            vehicle_maps_dir=str(job_dir / "vehicle_maps"),
            logs_path=str(job_dir / "job.log"),
        )
        summary = JobSummary(
            job_id=job_id,
            status="pending",
            provider_requested=request.provider,
            stop_count=len(request.stops or []),
            artifact_paths=artifact_paths,
        )
        request_payload = model_dump(request)
        request_payload.pop("google_api_key", None)
        write_json(Path(artifact_paths.request_json), request_payload)
        self._write_summary(summary)
        return summary

    def mark_running(self, job_id: str) -> None:
        summary = self.get_summary(job_id)
        summary.status = "running"
        self._write_summary(summary)

    def mark_completed(self, summary: JobSummary) -> None:
        summary.status = "completed"
        self._write_summary(summary)

    def mark_failed(self, job_id: str, error: str, warnings: list[str] | None = None) -> None:
        summary = self.get_summary(job_id)
        summary.status = "failed"
        summary.error = error
        summary.warnings = warnings or summary.warnings
        self._write_summary(summary)

    def get_summary(self, job_id: str) -> JobSummary:
        summary_path = self.jobs_root / job_id / "summary.json"
        payload = read_json(summary_path)
        if payload is None:
            raise FileNotFoundError(f"Job bulunamadı: {job_id}")
        return JobSummary(**payload)

    def get_artifacts(self, job_id: str) -> ArtifactPaths:
        return self.get_summary(job_id).artifact_paths

    def append_log(self, job_id: str, message: str) -> None:
        summary = self.get_summary(job_id)
        log_path = Path(summary.artifact_paths.logs_path or "")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        timestamped = f"[{utc_now_iso()}] {message}\n"
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(timestamped)

    def _write_summary(self, summary: JobSummary) -> None:
        summary_path = self.jobs_root / summary.job_id / "summary.json"
        with self._lock:
            write_json(summary_path, model_dump(summary))

    def _recover_interrupted_jobs(self) -> None:
        for summary_path in self.jobs_root.glob("*/summary.json"):
            payload = read_json(summary_path)
            if not payload:
                continue
            summary = JobSummary(**payload)
            if summary.status not in {"pending", "running"}:
                continue
            summary.status = "failed"
            summary.error = "İş arka planda çalışırken servis yeniden başladı veya bellek nedeniyle durdu. Lütfen işi tekrar başlatın."
            self._write_summary(summary)
            log_path = Path(summary.artifact_paths.logs_path or "")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(
                    f"[{utc_now_iso()}] Job recovery: servis yeniden başlatıldığı için job failed işaretlendi.\n"
                )
