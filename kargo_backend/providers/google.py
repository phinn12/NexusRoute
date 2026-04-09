from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import httpx

from ..google_maps import build_route_navigation_url, build_stop_navigation_url, decode_polyline
from ..routing_utils import assign_stops_to_centers, load_center_coordinates
from ..schemas import RoutePlan, RouteStop, Stop, VehicleConfig, VehicleRoute
from ..utils import model_dump
from .base import ProviderConfigError, ProviderError, RouteProvider
from .local import LocalOrtoolsProvider


def _parse_duration_seconds(value) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.endswith("s"):
        try:
            return int(float(value[:-1]))
        except ValueError:
            return 0
    return 0


class GoogleRouteOptimizationProvider(RouteProvider):
    name = "google"

    def __init__(self, settings):
        super().__init__(settings)
        self.local_provider = LocalOrtoolsProvider(settings)

    def optimize(
        self,
        stops: List[Stop],
        vehicle_config: Dict[str, VehicleConfig],
        preserve_centers: bool,
        job_dir: Path,
        runtime_google_api_key: str | None = None,
    ) -> RoutePlan:
        google_api_key = (runtime_google_api_key or self.settings.google_api_key or "").strip() or None
        google_bearer_token = self.settings.google_bearer_token

        if self.settings.google_parent and (google_api_key or google_bearer_token):
            return self._optimize_with_route_optimization(
                stops=stops,
                vehicle_config=vehicle_config,
                preserve_centers=preserve_centers,
                google_api_key=google_api_key,
                google_bearer_token=google_bearer_token,
            )

        if google_api_key:
            return self._optimize_with_routes_api(
                stops=stops,
                vehicle_config=vehicle_config,
                preserve_centers=preserve_centers,
                job_dir=job_dir,
                google_api_key=google_api_key,
            )

        raise ProviderConfigError(
            "Google provider için Google Maps API key gerekli. "
            "Gelişmiş çok araçlı optimizasyon için ayrıca GOOGLE_ROUTE_OPTIMIZATION_PARENT tanımlanmalıdır."
        )

    def _optimize_with_route_optimization(
        self,
        stops: List[Stop],
        vehicle_config: Dict[str, VehicleConfig],
        preserve_centers: bool,
        google_api_key: str | None,
        google_bearer_token: str | None,
    ) -> RoutePlan:
        centers = load_center_coordinates(self.settings.root_dir, stops)
        grouped_stops, warnings = assign_stops_to_centers(stops, centers, preserve_centers)

        routes: List[VehicleRoute] = []
        total_distance_km = 0.0
        total_duration_seconds = 0
        raw_responses: Dict[str, object] = {}

        for center_name in sorted(grouped_stops.keys()):
            center_stops = grouped_stops[center_name]
            if not center_stops:
                continue

            config = vehicle_config.get(center_name) or VehicleConfig(
                arac_sayisi=1,
                kapasite=max(1, len(center_stops)),
                kisi_sayisi=1,
            )
            center = centers[center_name]
            payload = self._build_route_optimization_payload(center_name, center_stops, center["lat"], center["lng"], config)
            response_payload = self._call_route_optimization_api(
                payload=payload,
                google_api_key=google_api_key,
                google_bearer_token=google_bearer_token,
            )
            raw_responses[center_name] = response_payload
            parsed_routes, route_warnings = self._parse_route_optimization_response(
                center_name=center_name,
                center_lat=center["lat"],
                center_lng=center["lng"],
                stops=center_stops,
                response_payload=response_payload,
            )
            warnings.extend(route_warnings)
            routes.extend(parsed_routes)
            total_distance_km += sum(route.total_distance_km for route in parsed_routes)
            total_duration_seconds += sum(route.total_duration_seconds or 0 for route in parsed_routes)

        return RoutePlan(
            provider_used="google",
            total_distance_km=round(total_distance_km, 3),
            total_duration_seconds=total_duration_seconds,
            vehicle_count=len(routes),
            stop_count=len(stops),
            warnings=warnings,
            routes=routes,
            raw_provider_response=raw_responses,
        )

    def _optimize_with_routes_api(
        self,
        stops: List[Stop],
        vehicle_config: Dict[str, VehicleConfig],
        preserve_centers: bool,
        job_dir: Path,
        google_api_key: str,
    ) -> RoutePlan:
        seed_plan = self.local_provider.optimize(
            stops=stops,
            vehicle_config=vehicle_config,
            preserve_centers=preserve_centers,
            job_dir=job_dir,
        )
        warnings = list(seed_plan.warnings)
        warnings.append(
            "Google Route Optimization parent tanımlı olmadığı için araç dağıtımı local heuristic ile yapıldı; "
            "durak sırası ve yol bilgisi Google Routes API ile üretildi."
        )

        raw_responses: Dict[str, object] = {}
        enriched_routes: List[VehicleRoute] = []
        google_success_count = 0

        for route in seed_plan.routes:
            enriched_route, response_payload = self._enrich_route_with_google_routes(route, google_api_key)
            if response_payload is not None:
                google_success_count += 1
                raw_responses[route.vehicle_id] = response_payload
            enriched_routes.append(enriched_route)

        if seed_plan.routes and google_success_count == 0:
            raise ProviderError("Google Routes API ile rota üretilemedi. API key veya servis yetkisini kontrol edin.")

        total_distance_km = sum(route.total_distance_km for route in enriched_routes)
        total_duration_seconds = sum(route.total_duration_seconds or 0 for route in enriched_routes)

        return RoutePlan(
            provider_used="google",
            graph_version=seed_plan.graph_version,
            total_distance_km=round(total_distance_km, 3),
            total_duration_seconds=total_duration_seconds,
            vehicle_count=len(enriched_routes),
            stop_count=len(stops),
            warnings=warnings,
            routes=enriched_routes,
            raw_provider_response=raw_responses or seed_plan.raw_provider_response,
        )

    def _build_route_optimization_payload(
        self,
        center_name: str,
        stops: List[Stop],
        center_lat: float,
        center_lng: float,
        config: VehicleConfig,
    ) -> dict:
        shipments = []
        for stop in stops:
            shipments.append(
                {
                    "label": stop.id,
                    "deliveries": [
                        {
                            "arrivalLocation": {"latitude": stop.lat, "longitude": stop.lng},
                            "duration": "0s",
                            "loadDemands": {"items": {"amount": "1"}},
                        }
                    ],
                }
            )

        vehicles = []
        for index in range(config.arac_sayisi):
            vehicles.append(
                {
                    "label": f"{center_name}-Arac-{index + 1}",
                    "startLocation": {"latitude": center_lat, "longitude": center_lng},
                    "endLocation": {"latitude": center_lat, "longitude": center_lng},
                    "loadLimits": {"items": {"maxLoad": str(config.kapasite)}},
                }
            )

        return {
            "timeout": f"{self.settings.ortools_time_limit_seconds}s",
            "searchMode": "RETURN_FAST",
            "model": {
                "shipments": shipments,
                "vehicles": vehicles,
            },
        }

    def _call_route_optimization_api(
        self,
        payload: dict,
        google_api_key: str | None,
        google_bearer_token: str | None,
    ) -> dict:
        headers = {"Content-Type": "application/json"}
        if google_bearer_token:
            headers["Authorization"] = f"Bearer {google_bearer_token}"
        if google_api_key:
            headers["X-Goog-Api-Key"] = google_api_key

        url = f"https://routeoptimization.googleapis.com/v1/{self.settings.google_parent}:optimizeTours"
        response = httpx.post(url, headers=headers, json=payload, timeout=60.0)
        if response.status_code >= 400:
            raise ProviderError(f"Google Route Optimization hatası: {response.status_code} {response.text}")
        return response.json()

    def _parse_route_optimization_response(
        self,
        center_name: str,
        center_lat: float,
        center_lng: float,
        stops: List[Stop],
        response_payload: dict,
    ) -> tuple[List[VehicleRoute], List[str]]:
        stop_by_id = {stop.id: stop for stop in stops}
        warnings: List[str] = []
        routes: List[VehicleRoute] = []
        visited_ids = set()

        for route_payload in response_payload.get("routes", []):
            visits = route_payload.get("visits", [])
            ordered: List[Stop] = []
            for visit in visits:
                label = visit.get("shipmentLabel")
                if label is None and "shipmentIndex" in visit:
                    try:
                        label = stops[int(visit["shipmentIndex"])].id
                    except Exception:
                        label = None
                if label and label in stop_by_id:
                    visited_ids.add(label)
                    ordered.append(stop_by_id[label])

            distance_m = (
                route_payload.get("metrics", {}).get("travelDistanceMeters")
                or route_payload.get("travelDistanceMeters")
                or 0
            )
            duration_s = (
                _parse_duration_seconds(route_payload.get("metrics", {}).get("totalDuration"))
                or _parse_duration_seconds(route_payload.get("routeTotalCost"))
            )
            route_coordinates = [[center_lat, center_lng]]
            route_coordinates.extend([[stop.lat, stop.lng] for stop in ordered])
            route_coordinates.append([center_lat, center_lng])

            routes.append(
                VehicleRoute(
                    vehicle_id=route_payload.get("vehicleLabel", f"{center_name}-Arac"),
                    center_name=center_name,
                    center_lat=center_lat,
                    center_lng=center_lng,
                    stop_count=len(ordered),
                    total_distance_km=round(float(distance_m) / 1000.0, 3),
                    total_duration_seconds=duration_s,
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
                        for index, stop in enumerate(ordered, start=1)
                    ],
                    google_maps_url=build_route_navigation_url([(stop.lat, stop.lng) for stop in ordered]),
                )
            )

        missing_ids = sorted(stop_by_id.keys() - visited_ids)
        if missing_ids:
            warnings.append(f"{center_name} için Google sonucu dışında kalan duraklar: {', '.join(missing_ids)}")

        return routes, warnings

    def _enrich_route_with_google_routes(
        self,
        route: VehicleRoute,
        google_api_key: str,
    ) -> tuple[VehicleRoute, dict | None]:
        route_payload = VehicleRoute(**model_dump(route))
        if not route_payload.ordered_stops:
            route_payload.google_maps_url = None
            return route_payload, None

        try:
            response_payload = self._call_routes_api(route_payload, google_api_key)
        except ProviderError as exc:
            route_payload.warnings.append(f"{route.vehicle_id} için Google Routes API başarısız oldu: {exc}")
            return route_payload, None

        routes = response_payload.get("routes") or []
        if not routes:
            route_payload.warnings.append(f"{route.vehicle_id} için Google Routes API rota döndürmedi.")
            return route_payload, None

        route_data = routes[0]
        optimized_indices = route_data.get("optimizedIntermediateWaypointIndex") or list(range(len(route_payload.ordered_stops)))
        if len(optimized_indices) != len(route_payload.ordered_stops):
            optimized_indices = list(range(len(route_payload.ordered_stops)))

        seed_stops = list(route_payload.ordered_stops)
        ordered_stops = [seed_stops[index] for index in optimized_indices]
        route_payload.ordered_stops = [
            RouteStop(
                **{
                    **model_dump(stop),
                    "sequence": sequence,
                    "google_maps_url": build_stop_navigation_url(
                        stop.lat,
                        stop.lng,
                        f"Sıra {sequence}: {stop.formatted_address or stop.id}",
                    ),
                }
            )
            for sequence, stop in enumerate(ordered_stops, start=1)
        ]
        route_payload.stop_count = len(route_payload.ordered_stops)
        route_payload.total_distance_km = round(float(route_data.get("distanceMeters", 0)) / 1000.0, 3)
        route_payload.total_duration_seconds = _parse_duration_seconds(route_data.get("duration"))
        encoded_polyline = ((route_data.get("polyline") or {}).get("encodedPolyline") or "").strip()
        route_payload.route_coordinates = decode_polyline(encoded_polyline)
        if not route_payload.route_coordinates:
            route_payload.route_coordinates = [[route_payload.center_lat, route_payload.center_lng]]
            route_payload.route_coordinates.extend([[stop.lat, stop.lng] for stop in route_payload.ordered_stops])
            route_payload.route_coordinates.append([route_payload.center_lat, route_payload.center_lng])
        route_payload.google_maps_url = build_route_navigation_url(
            [(stop.lat, stop.lng) for stop in route_payload.ordered_stops]
        )
        return route_payload, response_payload

    def _call_routes_api(self, route: VehicleRoute, google_api_key: str) -> dict:
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": google_api_key,
            "X-Goog-FieldMask": (
                "routes.distanceMeters,"
                "routes.duration,"
                "routes.polyline.encodedPolyline,"
                "routes.optimizedIntermediateWaypointIndex"
            ),
        }
        payload = {
            "origin": {"location": {"latLng": {"latitude": route.center_lat, "longitude": route.center_lng}}},
            "destination": {"location": {"latLng": {"latitude": route.center_lat, "longitude": route.center_lng}}},
            "intermediates": [
                {"location": {"latLng": {"latitude": stop.lat, "longitude": stop.lng}}}
                for stop in route.ordered_stops
            ],
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_UNAWARE",
            "optimizeWaypointOrder": True,
            "languageCode": "tr-TR",
            "units": "METRIC",
        }

        response = httpx.post(
            "https://routes.googleapis.com/directions/v2:computeRoutes",
            headers=headers,
            json=payload,
            timeout=60.0,
        )
        if response.status_code >= 400:
            raise ProviderError(f"Google Routes API hatası: {response.status_code} {response.text}")
        return response.json()
