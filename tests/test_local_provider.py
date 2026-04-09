from pathlib import Path

import networkx as nx

from kargo_backend.config import load_settings
from kargo_backend.providers.local import LocalOrtoolsProvider
from kargo_backend.schemas import Stop, VehicleConfig


def test_matrix_cache_path_changes_with_vehicle_config(tmp_path):
    settings = load_settings(tmp_path)
    provider = LocalOrtoolsProvider(settings)
    stops = [Stop(id="1", merkez="Merter Merkez", mahalle="A", formatted_address="A", lat=41.0, lng=28.8)]
    first = provider._matrix_cache_path("graph1", "Merter Merkez", stops, VehicleConfig(arac_sayisi=1, kapasite=10, kisi_sayisi=1))
    second = provider._matrix_cache_path("graph1", "Merter Merkez", stops, VehicleConfig(arac_sayisi=2, kapasite=10, kisi_sayisi=1))
    assert first != second


def test_local_provider_creates_deterministic_route(monkeypatch, tmp_path):
    settings = load_settings(tmp_path)
    provider = LocalOrtoolsProvider(settings)

    graph = nx.Graph()
    graph.add_node(0, x=28.85, y=41.04)
    graph.add_node(1, x=28.86, y=41.05)
    graph.add_node(2, x=28.87, y=41.06)
    graph.add_edge(0, 1, length=100.0, travel_time=10.0)
    graph.add_edge(1, 2, length=100.0, travel_time=10.0)
    graph.add_edge(0, 2, length=220.0, travel_time=22.0)

    monkeypatch.setattr("kargo_backend.providers.local.load_or_create_graph", lambda settings, points: (graph, "graphv1", Path("graph.graphml")))

    def fake_nearest_nodes(_graph, lng, lat):
        if lat < 41.045:
            return 0
        if lat < 41.055:
            return 1
        return 2

    monkeypatch.setattr("kargo_backend.providers.local.ox.distance.nearest_nodes", fake_nearest_nodes)

    stops = [
        Stop(id="1", merkez="Merter Merkez", mahalle="A", formatted_address="A", lat=41.05, lng=28.86),
        Stop(id="2", merkez="Merter Merkez", mahalle="B", formatted_address="B", lat=41.06, lng=28.87),
    ]
    vehicle_config = {"Merter Merkez": VehicleConfig(arac_sayisi=1, kapasite=10, kisi_sayisi=1)}

    plan = provider.optimize(stops, vehicle_config, preserve_centers=True, job_dir=tmp_path)

    assert plan.provider_used == "local"
    assert plan.vehicle_count == 1
    assert [stop.id for stop in plan.routes[0].ordered_stops] == ["1", "2"]
    assert plan.routes[0].ordered_stops[0].google_maps_url is not None
    assert "google.com/maps/dir/" in plan.routes[0].ordered_stops[0].google_maps_url


def test_local_provider_reports_capacity_overflow(monkeypatch, tmp_path):
    settings = load_settings(tmp_path)
    provider = LocalOrtoolsProvider(settings)

    graph = nx.Graph()
    graph.add_node(0, x=28.85, y=41.04)
    graph.add_node(1, x=28.86, y=41.05)
    graph.add_edge(0, 1, length=100.0, travel_time=10.0)

    monkeypatch.setattr("kargo_backend.providers.local.load_or_create_graph", lambda settings, points: (graph, "graphv1", Path("graph.graphml")))
    monkeypatch.setattr("kargo_backend.providers.local.ox.distance.nearest_nodes", lambda _graph, lng, lat: 0 if lat < 41.045 else 1)

    stops = [
        Stop(id="1", merkez="Merter Merkez", mahalle="A", formatted_address="A", lat=41.05, lng=28.86),
        Stop(id="2", merkez="Merter Merkez", mahalle="B", formatted_address="B", lat=41.051, lng=28.861),
    ]
    vehicle_config = {"Merter Merkez": VehicleConfig(arac_sayisi=1, kapasite=1, kisi_sayisi=1)}

    plan = provider.optimize(stops, vehicle_config, preserve_centers=True, job_dir=tmp_path)

    assert any("kapasite aşımı" in warning for warning in plan.warnings)


def test_local_provider_falls_back_when_graph_unavailable(monkeypatch, tmp_path):
    settings = load_settings(tmp_path)
    provider = LocalOrtoolsProvider(settings)

    monkeypatch.setattr(
        "kargo_backend.providers.local.load_or_create_graph",
        lambda settings, points: (_ for _ in ()).throw(RuntimeError("overpass timeout")),
    )

    stops = [
        Stop(id="1", merkez="Merter Merkez", mahalle="A", formatted_address="A", lat=41.05, lng=28.86),
        Stop(id="2", merkez="Merter Merkez", mahalle="B", formatted_address="B", lat=41.06, lng=28.87),
    ]
    vehicle_config = {"Merter Merkez": VehicleConfig(arac_sayisi=1, kapasite=10, kisi_sayisi=1)}

    plan = provider.optimize(stops, vehicle_config, preserve_centers=True, job_dir=tmp_path)

    assert plan.provider_used == "local"
    assert plan.vehicle_count == 1
    assert plan.routes[0].route_coordinates[0] == [plan.routes[0].center_lat, plan.routes[0].center_lng]
    assert any("fallback" in warning for warning in plan.warnings)


def test_local_provider_skips_road_network_for_large_center(monkeypatch, tmp_path):
    monkeypatch.setenv("ROAD_NETWORK_MAX_STOPS_PER_CENTER", "2")
    settings = load_settings(tmp_path)
    provider = LocalOrtoolsProvider(settings)

    def fail_if_called(*args, **kwargs):
        raise AssertionError("road network should not be loaded for large center groups")

    monkeypatch.setattr("kargo_backend.providers.local.load_or_create_graph", fail_if_called)

    stops = [
        Stop(id="1", merkez="Merter Merkez", mahalle="A", formatted_address="A", lat=41.05, lng=28.86),
        Stop(id="2", merkez="Merter Merkez", mahalle="B", formatted_address="B", lat=41.051, lng=28.861),
        Stop(id="3", merkez="Merter Merkez", mahalle="C", formatted_address="C", lat=41.052, lng=28.862),
    ]
    vehicle_config = {"Merter Merkez": VehicleConfig(arac_sayisi=1, kapasite=10, kisi_sayisi=1)}

    plan = provider.optimize(stops, vehicle_config, preserve_centers=True, job_dir=tmp_path)

    assert plan.provider_used == "local"
    assert any("fallback" in warning.lower() for warning in plan.warnings)


def test_large_routes_skip_two_opt(monkeypatch, tmp_path):
    monkeypatch.setenv("HEURISTIC_TWO_OPT_MAX_STOPS", "2")
    settings = load_settings(tmp_path)
    provider = LocalOrtoolsProvider(settings)

    called = {"two_opt": 0}

    def fake_two_opt(route, distance_matrix):
        called["two_opt"] += 1
        return route

    monkeypatch.setattr(provider, "_two_opt", fake_two_opt)
    route = provider._solve_route_heuristic(
        [
            [0, 1, 2, 3],
            [1, 0, 1, 1],
            [2, 1, 0, 1],
            [3, 1, 1, 0],
        ]
    )

    assert route[0] == 0
    assert route[-1] == 0
    assert called["two_opt"] == 0
