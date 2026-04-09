from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List

from ..config import Settings
from ..schemas import RoutePlan, Stop, VehicleConfig


class ProviderError(RuntimeError):
    pass


class ProviderConfigError(ProviderError):
    pass


class RouteProvider(ABC):
    name = "base"

    def __init__(self, settings: Settings):
        self.settings = settings

    @abstractmethod
    def optimize(
        self,
        stops: List[Stop],
        vehicle_config: Dict[str, VehicleConfig],
        preserve_centers: bool,
        job_dir: Path,
        runtime_google_api_key: str | None = None,
    ) -> RoutePlan:
        raise NotImplementedError
