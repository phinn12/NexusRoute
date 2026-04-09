from __future__ import annotations

from typing import Iterable
from urllib.parse import quote


MAX_GOOGLE_MAPS_ROUTE_STOPS = 9


def build_stop_navigation_url(lat: float, lng: float, label: str) -> str:
    encoded_label = quote(label, safe="")
    return (
        "https://www.google.com/maps/dir/?api=1"
        f"&destination={lat},{lng}"
        "&travelmode=driving"
        "&dir_action=navigate"
        f"&label={encoded_label}"
    )


def build_route_navigation_url(points: Iterable[tuple[float, float]]) -> str | None:
    unique_points = list(points)
    if not unique_points:
        return None
    if len(unique_points) > MAX_GOOGLE_MAPS_ROUTE_STOPS:
        return None

    destination_lat, destination_lng = unique_points[-1]
    waypoints = "|".join(f"{lat},{lng}" for lat, lng in unique_points[:-1])
    url = (
        "https://www.google.com/maps/dir/?api=1"
        f"&destination={destination_lat},{destination_lng}"
        "&travelmode=driving"
        "&dir_action=navigate"
    )
    if waypoints:
        url += f"&waypoints={waypoints}"
    return url


def decode_polyline(encoded: str) -> list[list[float]]:
    if not encoded:
        return []

    coordinates: list[list[float]] = []
    index = 0
    lat = 0
    lng = 0

    while index < len(encoded):
        lat_change, index = _decode_value(encoded, index)
        lng_change, index = _decode_value(encoded, index)
        lat += lat_change
        lng += lng_change
        coordinates.append([lat / 1e5, lng / 1e5])

    return coordinates


def _decode_value(encoded: str, index: int) -> tuple[int, int]:
    result = 0
    shift = 0

    while True:
        byte = ord(encoded[index]) - 63
        index += 1
        result |= (byte & 0x1F) << shift
        shift += 5
        if byte < 0x20:
            break

    if result & 1:
        return ~(result >> 1), index
    return result >> 1, index
