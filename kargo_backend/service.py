from __future__ import annotations

import csv
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Tuple

from .config import Settings, load_settings
from .copilot import OperationsCopilot
from .schemas import ArtifactPaths, JobRequest, JobSummary, RoutePlan, Stop
from .storage import FileJobStore
from .utils import model_dump, write_json

if TYPE_CHECKING:
    from .providers import GoogleRouteOptimizationProvider, LocalOrtoolsProvider
    from .providers.base import ProviderError


def render_route_plan(route_plan: RoutePlan, artifacts: ArtifactPaths):
    from .rendering import render_route_plan as _render_route_plan

    return _render_route_plan(route_plan, artifacts)


class RoutingOrchestrator:
    def __init__(self, settings: Settings | None = None, job_store: FileJobStore | None = None):
        self.settings = settings or load_settings()
        self.job_store = job_store or FileJobStore(self.settings)
        self.local_provider: LocalOrtoolsProvider | None = None
        self.google_provider: GoogleRouteOptimizationProvider | None = None
        self.copilot = OperationsCopilot(self.settings)

    def create_job(self, request: JobRequest) -> JobSummary:
        return self.job_store.create_job(request)

    def process_job(self, job_id: str, request: JobRequest) -> None:
        self.job_store.mark_running(job_id)
        try:
            summary, route_plan = self._run_job(request, self.job_store.get_summary(job_id).artifact_paths, job_id)
            self.job_store.mark_completed(summary)
            if route_plan.warnings:
                self.job_store.append_log(job_id, "Warnings: " + " | ".join(route_plan.warnings))
        except Exception as exc:
            self.job_store.mark_failed(job_id, str(exc))
            self.job_store.append_log(job_id, f"Job failed: {exc}")

    def run_job_sync(
        self,
        request: JobRequest,
        job_dir: Optional[Path] = None,
        output_html: Optional[Path] = None,
    ) -> Tuple[JobSummary, RoutePlan]:
        if job_dir is None:
            summary = self.create_job(request)
            job_id = summary.job_id
            artifacts = summary.artifact_paths
        else:
            job_dir.mkdir(parents=True, exist_ok=True)
            artifacts = ArtifactPaths(
                job_dir=str(job_dir),
                request_json=str(job_dir / "request.json"),
                normalized_csv=str(job_dir / "normalized.csv"),
                route_plan_json=str(job_dir / "route_plan.json"),
                metrics_json=str(job_dir / "metrics.json"),
                route_map_html=str(output_html or (job_dir / "route_map.html")),
                vehicle_maps_dir=str(job_dir / "vehicle_maps"),
                logs_path=str(job_dir / "job.log"),
            )
            request_payload = model_dump(request)
            request_payload.pop("google_api_key", None)
            write_json(Path(artifacts.request_json or ""), request_payload)
            job_id = job_dir.name

        summary, route_plan = self._run_job(request, artifacts, job_id)
        if job_dir is None:
            self.job_store.mark_completed(summary)
        return summary, route_plan

    def get_job(self, job_id: str) -> JobSummary:
        return self.job_store.get_summary(job_id)

    def get_artifacts(self, job_id: str) -> ArtifactPaths:
        return self.job_store.get_artifacts(job_id)

    def _run_job(self, request: JobRequest, artifacts: ArtifactPaths, job_id: str) -> Tuple[JobSummary, RoutePlan]:
        stops = self._load_stops(request)
        self._write_normalized_csv(stops, Path(artifacts.normalized_csv or ""))

        requested_provider = request.provider
        if requested_provider == "local":
            route_plan = self._get_local_provider().optimize(
                stops,
                request.vehicle_config,
                request.preserve_centers,
                Path(artifacts.job_dir),
                runtime_google_api_key=request.google_api_key,
            )
        elif requested_provider == "google":
            route_plan = self._get_google_provider().optimize(
                stops,
                request.vehicle_config,
                request.preserve_centers,
                Path(artifacts.job_dir),
                runtime_google_api_key=request.google_api_key,
            )
        else:
            try:
                route_plan = self._get_google_provider().optimize(
                    stops,
                    request.vehicle_config,
                    request.preserve_centers,
                    Path(artifacts.job_dir),
                    runtime_google_api_key=request.google_api_key,
                )
                route_plan.warnings.append("provider=auto için Google Route Optimization kullanıldı.")
            except self._provider_error_type() as exc:
                route_plan = self._get_local_provider().optimize(
                    stops,
                    request.vehicle_config,
                    request.preserve_centers,
                    Path(artifacts.job_dir),
                    runtime_google_api_key=request.google_api_key,
                )
                route_plan.warnings.append(f"Google provider başarısız oldu, local fallback kullanıldı: {exc}")

        route_plan.provider_requested = requested_provider
        write_json(Path(artifacts.route_plan_json or ""), model_dump(route_plan))
        write_json(
            Path(artifacts.metrics_json or ""),
            {
                "provider_requested": requested_provider,
                "provider_used": route_plan.provider_used,
                "graph_version": route_plan.graph_version,
                "total_distance_km": route_plan.total_distance_km,
                "total_duration_seconds": route_plan.total_duration_seconds,
                "vehicle_count": route_plan.vehicle_count,
                "stop_count": route_plan.stop_count,
                "warnings": route_plan.warnings,
            },
        )
        self._render_route_plan(route_plan, artifacts)

        summary = JobSummary(
            job_id=job_id,
            status="completed",
            provider_requested=requested_provider,
            provider_used=route_plan.provider_used,
            total_distance_km=route_plan.total_distance_km,
            total_duration_seconds=route_plan.total_duration_seconds,
            vehicle_count=route_plan.vehicle_count,
            stop_count=route_plan.stop_count,
            warnings=route_plan.warnings,
            artifact_paths=artifacts,
        )
        return summary, route_plan

    def _load_stops(self, request: JobRequest) -> List[Stop]:
        if request.stops:
            return [Stop(**model_dump(stop)) for stop in request.stops]
        if request.normalized_csv_path:
            with Path(request.normalized_csv_path).open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                stops = []
                for row in reader:
                    payload = dict(row)
                    payload["lat"] = float(payload["lat"])
                    payload["lng"] = float(payload["lng"])
                    stops.append(Stop(**payload))
                return stops
        raise ValueError("JobRequest içinde stops veya normalized_csv_path verilmelidir.")

    def _write_normalized_csv(self, stops: List[Stop], output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = ["id", "merkez", "mahalle", "cadde_sokak", "formatted_address", "lat", "lng"]
        with output_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for stop in stops:
                payload = model_dump(stop)
                writer.writerow({name: payload.get(name, "") for name in fieldnames})

    def _get_local_provider(self):
        if self.local_provider is None:
            from .providers import LocalOrtoolsProvider

            self.local_provider = LocalOrtoolsProvider(self.settings)
        return self.local_provider

    def _get_google_provider(self):
        if self.google_provider is None:
            from .providers import GoogleRouteOptimizationProvider

            self.google_provider = GoogleRouteOptimizationProvider(self.settings)
        return self.google_provider

    def _provider_error_type(self):
        from .providers import ProviderError

        return ProviderError

    def _render_route_plan(self, route_plan: RoutePlan, artifacts: ArtifactPaths) -> None:
        render_route_plan(route_plan, artifacts)
