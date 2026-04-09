from kargo_backend.routing_utils import assign_stops_to_centers
from kargo_backend.schemas import Stop


def test_preserve_existing_center_keeps_current_assignment():
    stops = [
        Stop(id="1", merkez="Merter Merkez", mahalle="A", formatted_address="A", lat=41.03, lng=28.88),
    ]
    centers = {
        "Merter Merkez": {"lat": 41.04, "lng": 28.85, "cap_km": 10},
        "Esenler Merkez": {"lat": 41.05, "lng": 28.87, "cap_km": 10},
    }

    grouped, warnings = assign_stops_to_centers(stops, centers, preserve_centers=True)

    assert len(grouped["Merter Merkez"]) == 1
    assert grouped["Merter Merkez"][0].merkez == "Merter Merkez"
    assert warnings == []


def test_reassign_center_moves_to_nearest_center():
    stops = [
        Stop(id="1", merkez="Merter Merkez", mahalle="A", formatted_address="A", lat=41.052, lng=28.871),
    ]
    centers = {
        "Merter Merkez": {"lat": 41.04, "lng": 28.85, "cap_km": 10},
        "Esenler Merkez": {"lat": 41.0527, "lng": 28.8751, "cap_km": 10},
    }

    grouped, warnings = assign_stops_to_centers(stops, centers, preserve_centers=False)

    assert len(grouped["Esenler Merkez"]) == 1
    assert grouped["Esenler Merkez"][0].merkez == "Esenler Merkez"
    assert warnings
