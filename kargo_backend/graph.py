from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

import osmnx as ox

from .config import Settings
from .utils import sha1_json, write_json


Point = Tuple[float, float]


def _compute_bbox(points: Iterable[Point]) -> tuple[float, float, float, float]:
    all_points = list(points)
    if not all_points:
        raise ValueError("Graf oluşturmak için en az bir koordinat gerekli.")

    lats = [lat for lat, _ in all_points]
    lngs = [lng for _, lng in all_points]

    lat_span = max(lats) - min(lats)
    lng_span = max(lngs) - min(lngs)

    lat_pad = max(0.01, lat_span * 0.2)
    lng_pad = max(0.01, lng_span * 0.2)

    left = round(min(lngs) - lng_pad, 6)
    bottom = round(min(lats) - lat_pad, 6)
    right = round(max(lngs) + lng_pad, 6)
    top = round(max(lats) + lat_pad, 6)
    return left, bottom, right, top


def _graph_signature(points: Iterable[Point]) -> dict[str, object]:
    bbox = _compute_bbox(points)
    return {
        "bbox": bbox,
        "network_type": "drive",
        "version": 2,
    }


def load_or_create_graph(settings: Settings, points: Iterable[Point]):
    settings.graph_cache_dir.mkdir(parents=True, exist_ok=True)
    ox.settings.requests_timeout = settings.road_network_timeout_seconds
    ox.settings.requests_kwargs = {"timeout": settings.road_network_timeout_seconds}
    signature = _graph_signature(points)
    graph_version = sha1_json(signature)
    graph_path = settings.graph_cache_dir / f"graph_{graph_version}.graphml"
    metadata_path = settings.graph_cache_dir / f"graph_{graph_version}.json"
    invalidate_broken_graph_cache(graph_path)

    if graph_path.exists() and graph_path.stat().st_size > 0:
        try:
            graph = ox.load_graphml(graph_path)
            return graph, graph_version, graph_path
        except Exception:
            graph_path.unlink(missing_ok=True)

    bbox = signature["bbox"]
    graph = ox.graph_from_bbox(bbox, network_type="drive")
    graph = ox.add_edge_speeds(graph)
    graph = ox.add_edge_travel_times(graph)
    ox.save_graphml(graph, graph_path)
    write_json(metadata_path, signature)
    return graph, graph_version, graph_path


def invalidate_broken_graph_cache(graph_path: Path) -> None:
    if graph_path.exists() and graph_path.stat().st_size == 0:
        graph_path.unlink(missing_ok=True)
