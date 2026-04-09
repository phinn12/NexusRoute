from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Tuple

import networkx as nx
import osmnx as ox

from ..graph import load_or_create_graph
from ..google_maps import build_route_navigation_url, build_stop_navigation_url
from ..routing_utils import assign_stops_to_centers, haversine_km, load_center_coordinates, sweep_sort_key
from ..schemas import RoutePlan, RouteStop, Stop, VehicleConfig, VehicleRoute
from ..utils import model_dump, read_json, sha1_json, write_json
from .base import RouteProvider


MAX_COST = 999999999


def _bit_count(value: int) -> int:
    return bin(value).count("1")


class LocalOrtoolsProvider(RouteProvider):
    name = "local"

    def optimize(
        self,
        stops: List[Stop],
        vehicle_config: Dict[str, VehicleConfig],
        preserve_centers: bool,
        job_dir: Path,
        runtime_google_api_key: str | None = None,
    ) -> RoutePlan:
        if not stops:
            return RoutePlan(provider_used="local", stop_count=0, vehicle_count=0, warnings=["Durak bulunamadı."])

        centers = load_center_coordinates(self.settings.root_dir, stops)
        grouped_stops, warnings = assign_stops_to_centers(stops, centers, preserve_centers)

        routes: List[VehicleRoute] = []
        total_distance_km = 0.0
        total_duration_seconds = 0
        graph_versions: List[str] = []

        for center_name in sorted(grouped_stops.keys()):
            grouped = grouped_stops[center_name]
            if not grouped:
                continue

            config = vehicle_config.get(center_name) or VehicleConfig(
                arac_sayisi=1,
                kapasite=max(1, len(grouped)),
                kisi_sayisi=1,
            )
            if center_name not in vehicle_config:
                warnings.append(f"{center_name} için araç konfigürasyonu verilmedi; varsayılan konfig kullanıldı.")

            center = centers[center_name]
            graph, graph_version, cost_weight, graph_warnings = self._prepare_graph_for_center(
                center_name=center_name,
                center_lat=center["lat"],
                center_lng=center["lng"],
                stops=grouped,
            )
            warnings.extend(graph_warnings)
            graph_versions.append(graph_version)

            vehicle_buckets, overflow = self._assign_to_vehicles(grouped, config, center["lat"], center["lng"])
            if overflow:
                overflow_ids = ", ".join(stop.id for stop in overflow)
                warnings.append(f"{center_name} kapasite aşımı nedeniyle atanamayan duraklar: {overflow_ids}")

            for vehicle_index, bucket in enumerate(vehicle_buckets, start=1):
                vehicle_id = f"{center_name}-Arac-{vehicle_index}"
                route = self._optimize_vehicle(
                    graph=graph,
                    graph_version=graph_version,
                    cost_weight=cost_weight,
                    center_name=center_name,
                    center_lat=center["lat"],
                    center_lng=center["lng"],
                    center_cap_km=center["cap_km"],
                    vehicle_id=vehicle_id,
                    config=config,
                    stops=bucket,
                    job_dir=job_dir,
                )
                routes.append(route)
                total_distance_km += route.total_distance_km
                total_duration_seconds += route.total_duration_seconds or 0

        return RoutePlan(
            provider_used="local",
            graph_version=",".join(graph_versions),
            total_distance_km=round(total_distance_km, 3),
            total_duration_seconds=total_duration_seconds,
            vehicle_count=len(routes),
            stop_count=len(stops),
            warnings=warnings,
            routes=routes,
        )

    def _prepare_graph_for_center(
        self,
        center_name: str,
        center_lat: float,
        center_lng: float,
        stops: List[Stop],
    ):
        fallback_version = f"geo-{sha1_json({'center': center_name, 'stops': [stop.id for stop in stops]})}"
        if len(stops) > self.settings.road_network_max_stops_per_center:
            return (
                None,
                fallback_version,
                "length",
                [
                    f"{center_name} için {len(stops)} durak bulundu. Sunucu belleğini korumak için "
                    "yaklaşık mesafe fallback kullanıldı."
                ],
            )

        active_points = [(center_lat, center_lng)]
        active_points.extend((stop.lat, stop.lng) for stop in stops)
        try:
            graph, graph_version, _ = load_or_create_graph(self.settings, active_points)
            return graph, graph_version, self._cost_weight(graph), []
        except Exception as exc:
            return (
                None,
                fallback_version,
                "length",
                [f"{center_name} için yol ağı alınamadı ({exc.__class__.__name__}); yaklaşık mesafe fallback kullanıldı."],
            )

    def _assign_to_vehicles(
        self,
        stops: List[Stop],
        config: VehicleConfig,
        center_lat: float,
        center_lng: float,
    ) -> Tuple[List[List[Stop]], List[Stop]]:
        ordered = sorted(stops, key=lambda stop: sweep_sort_key(stop, center_lat, center_lng))
        buckets = [[] for _ in range(config.arac_sayisi)]
        overflow: List[Stop] = []

        vehicle_index = 0
        for stop in ordered:
            while vehicle_index < len(buckets) and len(buckets[vehicle_index]) >= config.kapasite:
                vehicle_index += 1
            if vehicle_index >= len(buckets):
                overflow.append(stop)
                continue
            buckets[vehicle_index].append(stop)

        return buckets, overflow

    def _matrix_cache_path(
        self,
        graph_version: str,
        center_name: str,
        stops: List[Stop],
        config: VehicleConfig,
    ) -> Path:
        key = sha1_json(
            {
                "provider": self.name,
                "graph_version": graph_version,
                "center_name": center_name,
                "stops": [
                    {"id": stop.id, "lat": round(stop.lat, 6), "lng": round(stop.lng, 6), "merkez": stop.merkez}
                    for stop in stops
                ],
                "vehicle": model_dump(config),
            }
        )
        self.settings.matrix_cache_dir.mkdir(parents=True, exist_ok=True)
        return self.settings.matrix_cache_dir / f"{key}.json"

    def _build_cost_matrix(self, graph, node_ids: List[int], weight: str) -> List[List[int]]:
        matrix: List[List[int]] = []
        for source_node in node_ids:
            lengths = nx.single_source_dijkstra_path_length(graph, source_node, weight=weight)
            row = []
            for target_node in node_ids:
                if source_node == target_node:
                    row.append(0)
                else:
                    row.append(int(lengths.get(target_node, MAX_COST)))
            matrix.append(row)
        return matrix

    def _build_geodesic_cost_matrix(
        self,
        center_lat: float,
        center_lng: float,
        stops: List[Stop],
    ) -> List[List[int]]:
        points = [(center_lat, center_lng)] + [(stop.lat, stop.lng) for stop in stops]
        matrix: List[List[int]] = []
        for source_lat, source_lng in points:
            row = []
            for target_lat, target_lng in points:
                if source_lat == target_lat and source_lng == target_lng:
                    row.append(0)
                    continue
                row.append(max(1, int(haversine_km(source_lat, source_lng, target_lat, target_lng) * 1000)))
            matrix.append(row)
        return matrix

    def _solve_route(self, distance_matrix: List[List[int]]) -> List[int]:
        stop_count = max(0, len(distance_matrix) - 1)
        if stop_count <= 1:
            return [0, 0] if stop_count == 0 else [0, 1, 0]
        if stop_count <= 11:
            return self._solve_route_exact(distance_matrix)
        return self._solve_route_heuristic(distance_matrix)

    def _solve_route_exact(self, distance_matrix: List[List[int]]) -> List[int]:
        node_count = len(distance_matrix)
        stop_count = node_count - 1
        full_mask = (1 << stop_count) - 1
        dp: dict[tuple[int, int], tuple[int, tuple[int, ...]]] = {}

        for stop_index in range(1, node_count):
            mask = 1 << (stop_index - 1)
            dp[(mask, stop_index)] = (distance_matrix[0][stop_index], (stop_index,))

        for subset_size in range(2, stop_count + 1):
            next_dp: dict[tuple[int, int], tuple[int, tuple[int, ...]]] = {}
            for mask in range(1, full_mask + 1):
                if _bit_count(mask) != subset_size:
                    continue
                for last in range(1, node_count):
                    if not (mask & (1 << (last - 1))):
                        continue
                    prev_mask = mask ^ (1 << (last - 1))
                    best_cost = math.inf
                    best_path: tuple[int, ...] | None = None
                    for prev in range(1, node_count):
                        if not (prev_mask & (1 << (prev - 1))):
                            continue
                        prev_entry = dp.get((prev_mask, prev))
                        if prev_entry is None:
                            continue
                        candidate_path = prev_entry[1] + (last,)
                        candidate_cost = prev_entry[0] + distance_matrix[prev][last]
                        if candidate_cost < best_cost or (
                            candidate_cost == best_cost and (best_path is None or candidate_path < best_path)
                        ):
                            best_cost = candidate_cost
                            best_path = candidate_path
                    if best_path is not None:
                        next_dp[(mask, last)] = (int(best_cost), best_path)
            dp.update(next_dp)

        best_total = math.inf
        best_path: tuple[int, ...] | None = None
        for last in range(1, node_count):
            entry = dp.get((full_mask, last))
            if entry is None:
                continue
            candidate_total = entry[0] + distance_matrix[last][0]
            candidate_path = entry[1]
            if candidate_total < best_total or (
                candidate_total == best_total and (best_path is None or candidate_path < best_path)
            ):
                best_total = candidate_total
                best_path = candidate_path

        if best_path is None:
            return self._solve_route_heuristic(distance_matrix)
        return [0] + list(best_path) + [0]

    def _solve_route_heuristic(self, distance_matrix: List[List[int]]) -> List[int]:
        route = self._nearest_neighbor_route(distance_matrix)
        if max(0, len(distance_matrix) - 1) > self.settings.heuristic_two_opt_max_stops:
            return route
        return self._two_opt(route, distance_matrix)

    def _nearest_neighbor_route(self, distance_matrix: List[List[int]]) -> List[int]:
        unvisited = set(range(1, len(distance_matrix)))
        route = [0]
        current = 0

        while unvisited:
            next_node = min(
                unvisited,
                key=lambda node: (distance_matrix[current][node], node),
            )
            route.append(next_node)
            unvisited.remove(next_node)
            current = next_node

        route.append(0)
        return route

    def _two_opt(self, route: List[int], distance_matrix: List[List[int]]) -> List[int]:
        if len(route) <= 4:
            return route

        improved = True
        while improved:
            improved = False
            for left in range(1, len(route) - 2):
                for right in range(left + 1, len(route) - 1):
                    old_cost = distance_matrix[route[left - 1]][route[left]] + distance_matrix[route[right]][route[right + 1]]
                    new_cost = distance_matrix[route[left - 1]][route[right]] + distance_matrix[route[left]][route[right + 1]]
                    if new_cost >= old_cost:
                        continue
                    route = route[:left] + list(reversed(route[left : right + 1])) + route[right + 1 :]
                    improved = True
                    break
                if improved:
                    break
        return route

    def _optimize_vehicle(
        self,
        graph,
        graph_version: str,
        cost_weight: str,
        center_name: str,
        center_lat: float,
        center_lng: float,
        center_cap_km: float,
        vehicle_id: str,
        config: VehicleConfig,
        stops: List[Stop],
        job_dir: Path,
    ) -> VehicleRoute:
        warnings: List[str] = []
        if not stops:
            return VehicleRoute(
                vehicle_id=vehicle_id,
                center_name=center_name,
                center_lat=center_lat,
                center_lng=center_lng,
                stop_count=0,
                total_distance_km=0.0,
                total_duration_seconds=0,
                warnings=warnings,
            )

        filtered_stops = []
        for stop in stops:
            distance_from_center = haversine_km(center_lat, center_lng, stop.lat, stop.lng)
            if distance_from_center > center_cap_km:
                warnings.append(f"{stop.id} kapsama alanı dışında kaldı ve rotaya eklenmedi.")
                continue
            filtered_stops.append(stop)

        if not filtered_stops:
            return VehicleRoute(
                vehicle_id=vehicle_id,
                center_name=center_name,
                center_lat=center_lat,
                center_lng=center_lng,
                stop_count=0,
                total_distance_km=0.0,
                total_duration_seconds=0,
                warnings=warnings,
            )

        if graph is None:
            return self._optimize_vehicle_geodesic(
                graph_version=graph_version,
                center_name=center_name,
                center_lat=center_lat,
                center_lng=center_lng,
                vehicle_id=vehicle_id,
                config=config,
                stops=filtered_stops,
                warnings=warnings,
            )

        center_node = ox.distance.nearest_nodes(graph, center_lng, center_lat)
        stop_nodes = [(ox.distance.nearest_nodes(graph, stop.lng, stop.lat), stop) for stop in filtered_stops]
        matrix_cache_path = self._matrix_cache_path(graph_version, center_name, filtered_stops, config)
        matrix_payload = read_json(matrix_cache_path)

        if matrix_payload is None:
            node_ids = [center_node] + [node_id for node_id, _ in stop_nodes]
            cost_matrix = self._build_cost_matrix(graph, node_ids, cost_weight)
            write_json(matrix_cache_path, {"distance_matrix": cost_matrix})
        else:
            cost_matrix = matrix_payload["distance_matrix"]

        route_indices = self._solve_route(cost_matrix)
        ordered_stops = [stop_nodes[index - 1][1] for index in route_indices[1:-1] if 0 < index <= len(stop_nodes)]
        route_node_ids = [center_node] + [stop_nodes[index - 1][0] for index in route_indices[1:-1] if 0 < index <= len(stop_nodes)] + [center_node]

        route_coordinates: List[List[float]] = []
        total_length_m = 0.0
        total_duration_seconds = 0.0
        for source_node, target_node in zip(route_node_ids, route_node_ids[1:]):
            try:
                path = nx.shortest_path(graph, source_node, target_node, weight=cost_weight)
            except nx.NetworkXNoPath:
                warnings.append(f"{vehicle_id} için {source_node} -> {target_node} arasında yol bulunamadı.")
                continue

            route_coordinates.extend([[graph.nodes[node]["y"], graph.nodes[node]["x"]] for node in path])
            total_length_m += float(nx.path_weight(graph, path, weight="length"))
            if cost_weight == "travel_time":
                total_duration_seconds += float(nx.path_weight(graph, path, weight="travel_time"))

        if not total_duration_seconds:
            total_duration_seconds = (total_length_m / 1000.0) / self.settings.average_speed_kmh * 3600

        return VehicleRoute(
            vehicle_id=vehicle_id,
            center_name=center_name,
            center_lat=center_lat,
            center_lng=center_lng,
            stop_count=len(ordered_stops),
            total_distance_km=round(total_length_m / 1000.0, 3),
            total_duration_seconds=int(total_duration_seconds),
            route_coordinates=route_coordinates,
            ordered_stops=[
                RouteStop(
                    id=stop.id,
                    merkez=stop.merkez,
                    mahalle=stop.mahalle,
                    formatted_address=stop.formatted_address,
                    lat=stop.lat,
                    lng=stop.lng,
                    sequence=index,
                    google_maps_url=build_stop_navigation_url(
                        stop.lat,
                        stop.lng,
                        f"Sıra {index}: {stop.formatted_address or stop.id}",
                    ),
                )
                for index, stop in enumerate(ordered_stops, start=1)
            ],
            google_maps_url=build_route_navigation_url([(stop.lat, stop.lng) for stop in ordered_stops]),
            warnings=warnings,
        )

    def _optimize_vehicle_geodesic(
        self,
        graph_version: str,
        center_name: str,
        center_lat: float,
        center_lng: float,
        vehicle_id: str,
        config: VehicleConfig,
        stops: List[Stop],
        warnings: List[str],
    ) -> VehicleRoute:
        matrix_cache_path = self._matrix_cache_path(graph_version, center_name, stops, config)
        matrix_payload = read_json(matrix_cache_path)

        if matrix_payload is None:
            cost_matrix = self._build_geodesic_cost_matrix(center_lat, center_lng, stops)
            write_json(matrix_cache_path, {"distance_matrix": cost_matrix})
        else:
            cost_matrix = matrix_payload["distance_matrix"]

        route_indices = self._solve_route(cost_matrix)
        ordered_stops = [stops[index - 1] for index in route_indices[1:-1] if 0 < index <= len(stops)]
        route_coordinates = [[center_lat, center_lng]]
        route_coordinates.extend([[stop.lat, stop.lng] for stop in ordered_stops])
        route_coordinates.append([center_lat, center_lng])

        total_distance_km = 0.0
        for source, target in zip(route_coordinates, route_coordinates[1:]):
            total_distance_km += haversine_km(source[0], source[1], target[0], target[1])
        total_duration_seconds = int((total_distance_km / self.settings.average_speed_kmh) * 3600) if total_distance_km else 0

        return VehicleRoute(
            vehicle_id=vehicle_id,
            center_name=center_name,
            center_lat=center_lat,
            center_lng=center_lng,
            stop_count=len(ordered_stops),
            total_distance_km=round(total_distance_km, 3),
            total_duration_seconds=total_duration_seconds,
            route_coordinates=route_coordinates,
            ordered_stops=[
                RouteStop(
                    id=stop.id,
                    merkez=stop.merkez,
                    mahalle=stop.mahalle,
                    formatted_address=stop.formatted_address,
                    lat=stop.lat,
                    lng=stop.lng,
                    sequence=index,
                    google_maps_url=build_stop_navigation_url(
                        stop.lat,
                        stop.lng,
                        f"Sıra {index}: {stop.formatted_address or stop.id}",
                    ),
                )
                for index, stop in enumerate(ordered_stops, start=1)
            ],
            google_maps_url=build_route_navigation_url([(stop.lat, stop.lng) for stop in ordered_stops]),
            warnings=warnings,
        )

    def _cost_weight(self, graph) -> str:
        has_travel_time = any("travel_time" in edge_data for _, _, edge_data in graph.edges(data=True))
        return "travel_time" if has_travel_time else "length"
