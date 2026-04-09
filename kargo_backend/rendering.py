from __future__ import annotations

from html import escape
from pathlib import Path

import folium

from .schemas import ArtifactPaths, RoutePlan
from .utils import safe_filename


ROUTE_COLORS = ["red", "blue", "green", "orange", "purple", "darkred", "cadetblue", "black"]


def _numbered_div_icon(sequence: int, color: str) -> folium.DivIcon:
    html = f"""
    <div style="
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: {color};
        border: 2px solid #ffffff;
        color: #ffffff;
        font-weight: 700;
        font-size: 12px;
        line-height: 24px;
        text-align: center;
        box-shadow: 0 1px 6px rgba(0, 0, 0, 0.35);
    ">{sequence}</div>
    """
    return folium.DivIcon(html=html, icon_size=(28, 28), icon_anchor=(14, 14))


def _stop_popup_html(vehicle_id: str, stop) -> str:
    lines = [
        f"<b>{escape(vehicle_id)}</b>",
        f"<b>Sıra:</b> {stop.sequence}",
        escape(stop.formatted_address or stop.id),
    ]
    if stop.google_maps_url:
        lines.append(f'<a href="{escape(stop.google_maps_url)}" target="_blank">Google Maps ile Navigasyon</a>')
    return "<br>".join(lines)


def _center_popup_html(route) -> str:
    lines = [
        f"<b>{escape(route.vehicle_id)}</b>",
        escape(route.center_name),
    ]
    if route.google_maps_url:
        lines.append(f'<a href="{escape(route.google_maps_url)}" target="_blank">Google Maps rota linki</a>')
    return "<br>".join(lines)


def render_route_plan(plan: RoutePlan, artifacts: ArtifactPaths) -> ArtifactPaths:
    route_map_path = Path(artifacts.route_map_html or "")
    route_map_path.parent.mkdir(parents=True, exist_ok=True)
    vehicle_maps_dir = Path(artifacts.vehicle_maps_dir or "")
    vehicle_maps_dir.mkdir(parents=True, exist_ok=True)

    center_points = [(route.center_lat, route.center_lng) for route in plan.routes] or [(41.042, 28.877)]
    center_lat = sum(lat for lat, _ in center_points) / len(center_points)
    center_lng = sum(lng for _, lng in center_points) / len(center_points)

    overview = folium.Map(location=[center_lat, center_lng], zoom_start=12, tiles="OpenStreetMap")

    vehicle_maps: dict[str, str] = {}
    for index, route in enumerate(plan.routes):
        color = ROUTE_COLORS[index % len(ROUTE_COLORS)]
        folium.Marker(
            [route.center_lat, route.center_lng],
            popup=folium.Popup(_center_popup_html(route), max_width=320),
            icon=folium.Icon(color="red", icon="star"),
        ).add_to(overview)

        if route.route_coordinates:
            folium.PolyLine(route.route_coordinates, color=color, weight=4, opacity=0.8).add_to(overview)

        for stop in route.ordered_stops:
            folium.Marker(
                [stop.lat, stop.lng],
                popup=folium.Popup(_stop_popup_html(route.vehicle_id, stop), max_width=320),
                tooltip=f"{route.vehicle_id} / {stop.sequence}",
                icon=_numbered_div_icon(stop.sequence, color),
            ).add_to(overview)

        vehicle_map = folium.Map(location=[route.center_lat, route.center_lng], zoom_start=13, tiles="OpenStreetMap")
        folium.Marker(
            [route.center_lat, route.center_lng],
            popup=folium.Popup(_center_popup_html(route), max_width=320),
            icon=folium.Icon(color="red", icon="star"),
        ).add_to(vehicle_map)

        if route.route_coordinates:
            folium.PolyLine(route.route_coordinates, color=color, weight=4, opacity=0.8).add_to(vehicle_map)

        for stop in route.ordered_stops:
            folium.Marker(
                [stop.lat, stop.lng],
                popup=folium.Popup(_stop_popup_html(route.vehicle_id, stop), max_width=320),
                tooltip=f"Sıra {stop.sequence}",
                icon=_numbered_div_icon(stop.sequence, color),
            ).add_to(vehicle_map)

        file_name = f"{safe_filename(route.vehicle_id)}.html"
        vehicle_path = vehicle_maps_dir / file_name
        vehicle_map.save(str(vehicle_path))
        vehicle_maps[route.vehicle_id] = str(vehicle_path)

    overview.save(str(route_map_path))
    artifacts.vehicle_maps = vehicle_maps
    return artifacts
