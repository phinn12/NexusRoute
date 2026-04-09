from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class AppBaseModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class Stop(AppBaseModel):
    id: str
    merkez: Optional[str] = None
    mahalle: str = ""
    cadde_sokak: str = ""
    formatted_address: str = ""
    lat: float
    lng: float


class VehicleConfig(AppBaseModel):
    arac_sayisi: int = Field(default=1, ge=1)
    kapasite: int = Field(default=1, ge=1)
    kisi_sayisi: int = Field(default=1, ge=1)


class ArtifactPaths(AppBaseModel):
    job_dir: str
    normalized_csv: Optional[str] = None
    request_json: Optional[str] = None
    route_plan_json: Optional[str] = None
    metrics_json: Optional[str] = None
    route_map_html: Optional[str] = None
    vehicle_maps_dir: Optional[str] = None
    vehicle_maps: Dict[str, str] = Field(default_factory=dict)
    logs_path: Optional[str] = None


class RouteStop(AppBaseModel):
    id: str
    merkez: Optional[str] = None
    mahalle: str = ""
    formatted_address: str = ""
    lat: float
    lng: float
    sequence: int
    google_maps_url: Optional[str] = None


class VehicleRoute(AppBaseModel):
    vehicle_id: str
    center_name: str
    center_lat: float
    center_lng: float
    stop_count: int
    total_distance_km: float
    total_duration_seconds: Optional[int] = None
    route_coordinates: List[List[float]] = Field(default_factory=list)
    ordered_stops: List[RouteStop] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    google_maps_url: Optional[str] = None


class RoutePlan(AppBaseModel):
    provider_requested: Literal["local", "google", "auto"] = "local"
    provider_used: Literal["local", "google"] = "local"
    graph_version: Optional[str] = None
    total_distance_km: float = 0.0
    total_duration_seconds: Optional[int] = None
    vehicle_count: int = 0
    stop_count: int = 0
    warnings: List[str] = Field(default_factory=list)
    routes: List[VehicleRoute] = Field(default_factory=list)
    raw_provider_response: Optional[Dict[str, Any]] = None


class JobRequest(AppBaseModel):
    stops: Optional[List[Stop]] = None
    normalized_csv_path: Optional[str] = None
    vehicle_config: Dict[str, VehicleConfig] = Field(default_factory=dict)
    provider: Literal["local", "google", "auto"] = "local"
    preserve_centers: bool = True
    google_api_key: Optional[str] = None


class JobSummary(AppBaseModel):
    job_id: str
    status: Literal["pending", "running", "completed", "failed"]
    provider_requested: Literal["local", "google", "auto"] = "local"
    provider_used: Optional[Literal["local", "google"]] = None
    total_distance_km: float = 0.0
    total_duration_seconds: Optional[int] = None
    vehicle_count: int = 0
    stop_count: int = 0
    warnings: List[str] = Field(default_factory=list)
    artifact_paths: ArtifactPaths
    error: Optional[str] = None


class JobArtifactsResponse(AppBaseModel):
    job_id: str
    artifact_paths: ArtifactPaths


class DeliveryConstraints(AppBaseModel):
    preferred_center: Optional[str] = None
    preserve_centers: Optional[bool] = None
    max_stops_per_vehicle: Optional[int] = None
    max_vehicle_capacity: Optional[int] = None
    delivery_notes: List[str] = Field(default_factory=list)
    risk_flags: List[str] = Field(default_factory=list)


class FailureSummary(AppBaseModel):
    summary: str = ""
    priority_actions: List[str] = Field(default_factory=list)
    warning_types: List[str] = Field(default_factory=list)
    route_risks: List[str] = Field(default_factory=list)


class ExtractConstraintsRequest(AppBaseModel):
    text: str
    known_centers: List[str] = Field(default_factory=list)


class ExtractConstraintsResponse(AppBaseModel):
    available: bool
    model: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    constraints: Optional[DeliveryConstraints] = None


class SummarizeFailuresRequest(AppBaseModel):
    warnings: List[str] = Field(default_factory=list)
    failed_deliveries: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)


class SummarizeFailuresResponse(AppBaseModel):
    available: bool
    model: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    summary: Optional[FailureSummary] = None
