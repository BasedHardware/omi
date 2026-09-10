import asyncio
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from main import (
    CATEGORY_TAGS,
    _format_distance,
    _haversine_meters,
    _normalize_category,
    _parse_coordinates,
    _search_places,
    _walking_minutes,
    app,
)

client = TestClient(app)

PHARMACY_ELEMENTS = [
    {
        "type": "node",
        "id": 2,
        "lat": 48.8600,
        "lon": 2.2950,
        "tags": {
            "name": "Pharmacie du Centre",
            "addr:street": "Rue de Rivoli",
            "addr:housenumber": "10",
            "opening_hours": "Mo-Sa 09:00-19:00",
            "phone": "+33 1 23 45 67 89",
        },
    },
    {
        "type": "way",
        "id": 3,
        "center": {"lat": 48.8700, "lon": 2.3000},
        "tags": {"name": "Pharmacie du Parc"},
    },
]


def test_normalize_category_accepts_canonical_and_aliases():
    assert _normalize_category("pharmacy") == "pharmacy"
    assert _normalize_category("  Pharmacy ") == "pharmacy"
    assert _normalize_category("drugstore") == "pharmacy"
    assert _normalize_category("chemist") == "pharmacy"
    assert _normalize_category("ev") == "charging_station"
    assert _normalize_category("EV charging") == "charging_station"
    assert _normalize_category("wc") == "toilets"
    assert _normalize_category("gas") == "fuel"
    assert _normalize_category("train-station") == "train_station"


def test_normalize_category_rejects_unknown():
    assert _normalize_category("moon base") is None
    assert _normalize_category("") is None


def test_parse_coordinates_accepts_pairs_and_rejects_junk():
    assert _parse_coordinates("48.8584, 2.2945") == (48.8584, 2.2945)
    assert _parse_coordinates("0,0") == (0.0, 0.0)
    assert _parse_coordinates("Eiffel Tower") is None
    assert _parse_coordinates("48.8584") is None
    assert _parse_coordinates("91, 10") is None
    assert _parse_coordinates("10, 181") is None
    assert _parse_coordinates("north, west") is None


def test_haversine_matches_known_distance():
    # Paris to London is roughly 344 km.
    meters = _haversine_meters(48.8566, 2.3522, 51.5074, -0.1278)
    assert 340000 < meters < 348000
    assert _haversine_meters(10.0, 20.0, 10.0, 20.0) == 0


def test_walking_minutes_and_distance_formatting():
    assert _walking_minutes(0) == 1
    assert _walking_minutes(80) == 1
    assert _walking_minutes(640) == 10
    assert _walking_minutes(810) == 13
    assert _format_distance(250) == "250 m"
    assert _format_distance(1500) == "1.5 km"


def test_search_places_uses_mapped_tag_and_radius():
    captured = {}

    async def fake_request_json(_client, url, params):
        captured["url"] = url
        captured["params"] = params
        return {"elements": PHARMACY_ELEMENTS}

    async def run_search():
        async with httpx.AsyncClient() as http_client:
            return await _search_places(
                http_client, (48.8584, 2.2945), "amenity", "pharmacy", 1500, 5
            )

    with patch("main._request_json", new=fake_request_json):
        places = asyncio.run(run_search())

    query = captured["params"]["data"]
    assert '["amenity"="pharmacy"]' in query
    assert "around:1500,48.8584,2.2945" in query
    assert captured["url"].endswith("/api/interpreter")
    # Nearest first.
    assert places[0]["id"] == 2


def test_find_nearby_places_formats_results():
    with patch("main._resolve_location", new_callable=AsyncMock) as resolve, patch(
        "main._search_places", new_callable=AsyncMock
    ) as search:
        resolve.return_value = ((48.8584, 2.2945), "Eiffel Tower, Paris", None)
        search.return_value = PHARMACY_ELEMENTS

        response = client.post(
            "/tools/find_nearby_places",
            json={"location": "Eiffel Tower", "category": "drugstore", "limit": 2},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["error"] is None
    assert "Nearest pharmacy around Eiffel Tower, Paris" in data["result"]
    assert "1. Pharmacie du Centre" in data["result"]
    assert "2. Pharmacie du Parc" in data["result"]
    assert "Rue de Rivoli 10" in data["result"]
    assert "hours: Mo-Sa 09:00-19:00" in data["result"]
    assert "phone: +33 1 23 45 67 89" in data["result"]
    assert "straight-line estimates" in data["result"]


def test_find_nearest_place_asks_for_one_result():
    with patch("main._resolve_location", new_callable=AsyncMock) as resolve, patch(
        "main._search_places", new_callable=AsyncMock
    ) as search:
        resolve.return_value = ((48.8584, 2.2945), "Eiffel Tower, Paris", None)
        search.return_value = PHARMACY_ELEMENTS[:1]

        response = client.post(
            "/tools/find_nearest_place",
            json={"location": "48.8584, 2.2945", "category": "pharmacy"},
        )

    assert response.status_code == 200
    assert search.await_args.args[5] == 1
    assert "1. Pharmacie du Centre" in response.json()["result"]


def test_empty_result_is_reported_without_error():
    with patch("main._resolve_location", new_callable=AsyncMock) as resolve, patch(
        "main._search_places", new_callable=AsyncMock
    ) as search:
        resolve.return_value = ((0.0, 0.0), "Null Island", None)
        search.return_value = []

        response = client.post(
            "/tools/find_nearby_places",
            json={"location": "Null Island", "category": "pharmacy"},
        )

    data = response.json()
    assert data["error"] is None
    assert "No pharmacy found within 1.0 km of Null Island." == data["result"]


def test_unknown_category_errors_before_any_network_call():
    with patch("main._resolve_location", new_callable=AsyncMock) as resolve:
        response = client.post(
            "/tools/find_nearby_places",
            json={"location": "Paris", "category": "teleporter"},
        )
        resolve.assert_not_awaited()

    assert response.status_code == 200
    data = response.json()
    assert data["result"] is None
    assert "Unsupported category 'teleporter'" in data["error"]
    assert "pharmacy" in data["error"]


def test_map_service_failure_returns_error_not_500():
    with patch(
        "main._resolve_location",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("boom"),
    ):
        response = client.post(
            "/tools/find_nearby_places",
            json={"location": "Paris", "category": "atm"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["result"] is None
    assert "did not respond" in data["error"]
    assert "ConnectError" in data["error"]


def test_unresolvable_location_returns_helpful_error():
    with patch("main._resolve_location", new_callable=AsyncMock) as resolve:
        resolve.return_value = (None, None, "I could not find a place called 'Atlantis'.")
        response = client.post(
            "/tools/find_nearby_places",
            json={"location": "Atlantis", "category": "cafe"},
        )

    assert response.json()["error"] == "I could not find a place called 'Atlantis'."


def test_list_place_categories_and_manifest():
    categories = client.post("/tools/list_place_categories", json={}).json()
    assert categories["error"] is None
    for expected in ("pharmacy", "atm", "toilets", "train_station"):
        assert expected in categories["result"]

    manifest = client.get("/.well-known/omi-tools.json").json()
    assert manifest["schema_version"] == "1.0"
    tool_names = [tool["name"] for tool in manifest["tools"]]
    assert tool_names == [
        "find_nearby_places",
        "find_nearest_place",
        "list_place_categories",
    ]


def test_health_and_index():
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/").status_code == 200


def test_every_category_has_a_tag_pair():
    for category, tag in CATEGORY_TAGS.items():
        assert isinstance(category, str) and category
        assert len(tag) == 2
        assert all(isinstance(part, str) and part for part in tag)
