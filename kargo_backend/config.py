from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


def _path_from_env(value: str | None, default: Path) -> Path:
    if value:
        return Path(value).expanduser().resolve()
    return default


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    output_dir: Path
    graph_cache_dir: Path
    matrix_cache_dir: Path
    logs_dir: Path
    backend_host: str
    backend_port: int
    backend_base_url: str
    google_parent: str | None
    google_api_key: str | None
    google_bearer_token: str | None
    gemini_api_key: str | None
    gemini_model: str
    gemini_fallback_models: tuple[str, ...]
    ortools_time_limit_seconds: int
    average_speed_kmh: float
    road_network_timeout_seconds: int
    road_network_max_stops_per_center: int
    heuristic_two_opt_max_stops: int


def load_settings(root_dir: Path | None = None) -> Settings:
    resolved_root = (root_dir or Path(__file__).resolve().parent.parent).resolve()

    output_dir = _path_from_env(os.getenv("OUTPUT_DIR"), resolved_root / "yerelden_output")
    graph_cache_dir = _path_from_env(os.getenv("GRAPH_CACHE_DIR"), resolved_root / "graph_cache")
    logs_dir = _path_from_env(os.getenv("LOG_DIR"), resolved_root / "logs")
    matrix_cache_dir = graph_cache_dir / "distance_matrices"

    backend_host = os.getenv("BACKEND_HOST", "127.0.0.1")
    backend_port = int(os.getenv("BACKEND_PORT", "8010"))
    backend_base_url = os.getenv("BACKEND_BASE_URL", f"http://{backend_host}:{backend_port}")

    google_parent = os.getenv("GOOGLE_ROUTE_OPTIMIZATION_PARENT")
    google_api_key = os.getenv("GOOGLE_ROUTE_OPTIMIZATION_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")
    google_bearer_token = os.getenv("GOOGLE_ROUTE_OPTIMIZATION_BEARER_TOKEN")
    gemini_fallback_models = tuple(
        model.strip()
        for model in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-2.5-flash-lite").split(",")
        if model.strip()
    )

    return Settings(
        root_dir=resolved_root,
        output_dir=output_dir,
        graph_cache_dir=graph_cache_dir,
        matrix_cache_dir=matrix_cache_dir,
        logs_dir=logs_dir,
        backend_host=backend_host,
        backend_port=backend_port,
        backend_base_url=backend_base_url,
        google_parent=google_parent,
        google_api_key=google_api_key,
        google_bearer_token=google_bearer_token,
        gemini_api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3-flash-preview"),
        gemini_fallback_models=gemini_fallback_models,
        ortools_time_limit_seconds=int(os.getenv("ORTOOLS_TIME_LIMIT_SECONDS", "30")),
        average_speed_kmh=float(os.getenv("AVERAGE_SPEED_KMH", "30")),
        road_network_timeout_seconds=int(os.getenv("ROAD_NETWORK_TIMEOUT_SECONDS", "30")),
        road_network_max_stops_per_center=int(os.getenv("ROAD_NETWORK_MAX_STOPS_PER_CENTER", "120")),
        heuristic_two_opt_max_stops=int(os.getenv("HEURISTIC_TWO_OPT_MAX_STOPS", "80")),
    )
