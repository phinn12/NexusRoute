from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from .schemas import Stop
from .utils import model_dump, read_json


DEFAULT_CENTER_RADIUS_KM = 10.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def load_center_coordinates(root_dir: Path, stops: Iterable[Stop]) -> Dict[str, Dict[str, float]]:
    centers_file = root_dir / "merkez_koordinatlari.json"
    if centers_file.exists():
        raw = read_json(centers_file, default={}) or {}
        centers: Dict[str, Dict[str, float]] = {}
        for center_name, center_data in raw.items():
            centers[center_name] = {
                "lat": float(center_data["lat"]),
                "lng": float(center_data["lng"]),
                "cap_km": float(center_data.get("cap_km", DEFAULT_CENTER_RADIUS_KM)),
            }
        if centers:
            return centers

    grouped: Dict[str, List[Stop]] = {}
    for stop in stops:
        center_name = (stop.merkez or "").strip()
        if center_name:
            grouped.setdefault(center_name, []).append(stop)

    derived: Dict[str, Dict[str, float]] = {}
    for center_name, grouped_stops in grouped.items():
        avg_lat = sum(stop.lat for stop in grouped_stops) / len(grouped_stops)
        avg_lng = sum(stop.lng for stop in grouped_stops) / len(grouped_stops)
        derived[center_name] = {"lat": avg_lat, "lng": avg_lng, "cap_km": DEFAULT_CENTER_RADIUS_KM}
    return derived


def resolve_nearest_center(centers: Dict[str, Dict[str, float]], stop: Stop) -> str:
    return min(
        centers.keys(),
        key=lambda name: haversine_km(stop.lat, stop.lng, centers[name]["lat"], centers[name]["lng"]),
    )


def assign_stops_to_centers(
    stops: List[Stop],
    centers: Dict[str, Dict[str, float]],
    preserve_centers: bool,
) -> Tuple[Dict[str, List[Stop]], List[str]]:
    grouped = {name: [] for name in centers}
    warnings: List[str] = []

    for stop in stops:
        center_name = (stop.merkez or "").strip()
        if preserve_centers and center_name in centers:
            chosen = center_name
        else:
            chosen = resolve_nearest_center(centers, stop)
            if center_name and center_name != chosen:
                warnings.append(f"{stop.id} mevcut merkezinden '{chosen}' merkezine yeniden atandı.")

        payload = model_dump(stop)
        payload["merkez"] = chosen
        grouped.setdefault(chosen, []).append(Stop(**payload))

    return grouped, warnings


def sweep_sort_key(stop: Stop, center_lat: float, center_lng: float) -> Tuple[float, float, str]:
    angle = math.atan2(stop.lat - center_lat, stop.lng - center_lng)
    radial_distance = (stop.lat - center_lat) ** 2 + (stop.lng - center_lng) ** 2
    return angle, radial_distance, stop.id
