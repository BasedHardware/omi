"""Hermetic unit test suite for Omi CityBikes Global Micro-Mobility App.

All tests run in total network isolation using mocked CityBikes API fixtures.
"""

import importlib.util
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, patch

# Ensure plugin directory is in sys.path and dynamically load modules
_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

# Load models module
models_path = os.path.join(_plugin_dir, "models.py")
spec_models = importlib.util.spec_from_file_location("models", models_path)
models_module = importlib.util.module_from_spec(spec_models)
sys.modules["models"] = models_module
spec_models.loader.exec_module(models_module)

# Load main module
main_path = os.path.join(_plugin_dir, "main.py")
spec_main = importlib.util.spec_from_file_location("main", main_path)
main_module = importlib.util.module_from_spec(spec_main)
sys.modules["main"] = main_module
spec_main.loader.exec_module(main_module)

app = main_module.app
clear_cache = main_module.clear_cache
clear_rate_limits = main_module.clear_rate_limits
haversine_distance = main_module.haversine_distance

# Try importing TestClient from starlette/fastapi
try:
    from starlette.testclient import TestClient
except ImportError:
    from fastapi.testclient import TestClient

# Realistic test fixtures
MOCK_NETWORKS_RESPONSE = {
    "networks": [
        {
            "id": "citi-bike-nyc",
            "name": "Citi Bike",
            "location": {
                "city": "New York, NY",
                "country": "US",
                "latitude": 40.7143528,
                "longitude": -74.0059731,
            },
        },
        {
            "id": "velib-metropole",
            "name": "Vélib' Métropole",
            "location": {
                "city": "Paris",
                "country": "FR",
                "latitude": 48.856614,
                "longitude": 2.3522219,
            },
        },
        {
            "id": "santander-cycles",
            "name": "Santander Cycles",
            "location": {
                "city": "London",
                "country": "GB",
                "latitude": 51.5073509,
                "longitude": -0.1277583,
            },
        },
        {
            "id": "bicing",
            "name": "Bicing",
            "location": {
                "city": "Barcelona",
                "country": "ES",
                "latitude": 41.3850639,
                "longitude": 2.1734035,
            },
        },
    ]
}

MOCK_NYC_DETAILS_RESPONSE = {
    "network": {
        "id": "citi-bike-nyc",
        "name": "Citi Bike",
        "location": {
            "city": "New York, NY",
            "country": "US",
            "latitude": 40.7143528,
            "longitude": -74.0059731,
        },
        "stations": [
            {
                "id": "station-broadway-1",
                "name": "Broadway & E 14th St",
                "latitude": 40.7345,
                "longitude": -73.9907,
                "free_bikes": 14,
                "empty_slots": 16,
                "timestamp": "2026-09-06T18:00:00Z",
                "extra": {"ebikes": 5, "has_ebikes": True},
            },
            {
                "id": "station-broadway-2",
                "name": "Broadway & W 42nd St",
                "latitude": 40.7558,
                "longitude": -73.9865,
                "free_bikes": 6,
                "empty_slots": 24,
                "timestamp": "2026-09-06T18:00:00Z",
                "extra": {"ebikes": 2, "has_ebikes": True},
            },
            {
                "id": "station-grand-central",
                "name": "Grand Central Terminal - 42nd St",
                "latitude": 40.7527,
                "longitude": -73.9772,
                "free_bikes": 22,
                "empty_slots": 8,
                "timestamp": "2026-09-06T18:00:00Z",
                "extra": {"ebikes": 8, "has_ebikes": True},
            },
        ],
    }
}


class MockResponse:
    """Mocked HTTP response object."""

    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


class TestCityBikesApp(unittest.TestCase):
    """Hermetic unit tests for CityBikes plugin endpoints."""

    def setUp(self):
        clear_cache()
        clear_rate_limits()
        self.client = TestClient(app)

    def tearDown(self):
        clear_cache()
        clear_rate_limits()

    # --- System & Metadata Tests ---

    def test_root_endpoint(self):
        """GET / returns HTML landing page."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("Omi CityBikes Integration App", resp.text)

    def test_health_endpoint(self):
        """GET /health returns 200 with service status."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "omi-citybikes-app")

    def test_manifest_endpoint(self):
        """GET /.well-known/omi-tools.json returns valid discovery manifest."""
        resp = self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["schema_version"], "v1")
        self.assertIn("tools", data)
        self.assertEqual(len(data["tools"]), 4)

        tool_names = [t["name"] for t in data["tools"]]
        self.assertIn("search_bike_networks", tool_names)
        self.assertIn("get_nearby_bike_stations", tool_names)
        self.assertIn("check_bike_station_status", tool_names)
        self.assertIn("get_city_bike_overview", tool_names)

    # --- Math & Distance Helper Tests ---

    def test_haversine_distance_calculation(self):
        """Verify Haversine formula calculation between known geographic coordinates."""
        # Distance between Paris (48.8566, 2.3522) and London (51.5074, -0.1278) ~ 343 km
        dist = haversine_distance(48.8566, 2.3522, 51.5074, -0.1278)
        self.assertAlmostEqual(dist, 343.5, delta=5.0)

        # Distance to same point should be 0.0
        dist_zero = haversine_distance(40.7128, -74.0060, 40.7128, -74.0060)
        self.assertAlmostEqual(dist_zero, 0.0, places=4)

    # --- Tool 1: search_bike_networks ---

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_search_bike_networks_by_city(self, mock_get):
        """Search networks matching city name."""
        mock_get.return_value = MockResponse(200, MOCK_NETWORKS_RESPONSE)

        payload = {"query": "Paris", "limit": 5}
        resp = self.client.post("/tools/search_bike_networks", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("Vélib' Métropole", data["result"])
        self.assertIn("velib-metropole", data["result"])

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_search_bike_networks_by_brand(self, mock_get):
        """Search networks matching brand name or network ID."""
        mock_get.return_value = MockResponse(200, MOCK_NETWORKS_RESPONSE)

        payload = {"query": "Citi Bike", "limit": 5}
        resp = self.client.post("/tools/search_bike_networks", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("Citi Bike", data["result"])
        self.assertIn("citi-bike-nyc", data["result"])

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_search_bike_networks_no_match(self, mock_get):
        """Search returns helpful message when no networks match query."""
        mock_get.return_value = MockResponse(200, MOCK_NETWORKS_RESPONSE)

        payload = {"query": "NonexistentCityXYZ", "limit": 5}
        resp = self.client.post("/tools/search_bike_networks", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("No bike-share networks found", data["result"])

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_search_bike_networks_upstream_error(self, mock_get):
        """Handle upstream HTTP failure gracefully."""
        mock_get.return_value = MockResponse(500, {})

        payload = {"query": "New York"}
        resp = self.client.post("/tools/search_bike_networks", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data["error"])
        self.assertIn("Failed to search bike networks", data["error"])

    # --- Tool 2: get_nearby_bike_stations ---

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_get_nearby_bike_stations_query_filter(self, mock_get):
        """Filter stations within a network by street name query."""
        mock_get.return_value = MockResponse(200, MOCK_NYC_DETAILS_RESPONSE)

        payload = {"network_id": "citi-bike-nyc", "query": "Broadway"}
        resp = self.client.post("/tools/get_nearby_bike_stations", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("Broadway & E 14th St", data["result"])
        self.assertIn("Broadway & W 42nd St", data["result"])
        self.assertNotIn("Grand Central", data["result"])

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_get_nearby_bike_stations_distance_sort(self, mock_get):
        """Sort stations by GPS proximity when coordinates are provided."""
        mock_get.return_value = MockResponse(200, MOCK_NYC_DETAILS_RESPONSE)

        # Near Grand Central (40.7527, -73.9772)
        payload = {
            "network_id": "citi-bike-nyc",
            "latitude": 40.7527,
            "longitude": -73.9772,
            "limit": 3,
        }
        resp = self.client.post("/tools/get_nearby_bike_stations", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        # Grand Central should be first because distance is 0m away
        lines = data["result"].split("\n")
        first_station_line = [l for l in lines if l.startswith("1. ")][0]
        self.assertIn("Grand Central", first_station_line)
        self.assertIn("0m away", first_station_line)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_get_nearby_bike_stations_network_not_found(self, mock_get):
        """Return clear error when network_id does not exist."""
        mock_get.return_value = MockResponse(404, {})

        payload = {"network_id": "unknown-network-xyz"}
        resp = self.client.post("/tools/get_nearby_bike_stations", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data["error"])
        self.assertIn("not found", data["error"])

    # --- Tool 3: check_bike_station_status ---

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_check_bike_station_status_by_name(self, mock_get):
        """Find station by name and return live counts."""
        mock_get.return_value = MockResponse(200, MOCK_NYC_DETAILS_RESPONSE)

        payload = {
            "network_id": "citi-bike-nyc",
            "station_id_or_name": "Grand Central",
        }
        resp = self.client.post("/tools/check_bike_station_status", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("Grand Central Terminal - 42nd St", data["result"])
        self.assertIn("**Available Bikes**: 22", data["result"])
        self.assertIn("*Includes E-Bikes*: 8", data["result"])
        self.assertIn("**Empty Return Docks**: 8", data["result"])

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_check_bike_station_status_by_id(self, mock_get):
        """Find station by exact ID."""
        mock_get.return_value = MockResponse(200, MOCK_NYC_DETAILS_RESPONSE)

        payload = {
            "network_id": "citi-bike-nyc",
            "station_id_or_name": "station-broadway-1",
        }
        resp = self.client.post("/tools/check_bike_station_status", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("Broadway & E 14th St", data["result"])
        self.assertIn("**Available Bikes**: 14", data["result"])

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_check_bike_station_status_not_found(self, mock_get):
        """Return error if station does not exist in network."""
        mock_get.return_value = MockResponse(200, MOCK_NYC_DETAILS_RESPONSE)

        payload = {
            "network_id": "citi-bike-nyc",
            "station_id_or_name": "Nonexistent Station 999",
        }
        resp = self.client.post("/tools/check_bike_station_status", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data["error"])
        self.assertIn("No station matching", data["error"])

    # --- Tool 4: get_city_bike_overview ---

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_get_city_bike_overview_by_city(self, mock_get):
        """Generate citywide statistics by city name."""
        mock_get.side_effect = [
            MockResponse(200, MOCK_NETWORKS_RESPONSE),
            MockResponse(200, MOCK_NYC_DETAILS_RESPONSE),
        ]

        payload = {"city_or_network": "New York"}
        resp = self.client.post("/tools/get_city_bike_overview", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("Micro-Mobility Overview: Citi Bike", data["result"])
        self.assertIn("**Active Stations**: 3", data["result"])
        # Total bikes = 14 + 6 + 22 = 42
        self.assertIn("**Available Bikes Fleet**: 42", data["result"])
        # Total empty = 16 + 24 + 8 = 48
        self.assertIn("**Empty Return Docks**: 48", data["result"])

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_get_city_bike_overview_unknown(self, mock_get):
        """Return error when city or network cannot be located."""
        mock_get.return_value = MockResponse(200, MOCK_NETWORKS_RESPONSE)

        payload = {"city_or_network": "AtlantisCity"}
        resp = self.client.post("/tools/get_city_bike_overview", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsNotNone(data["error"])
        self.assertIn("Could not find a bike-share system", data["error"])

    # --- Validation & Caching & Rate Limiting ---

    def test_request_validation_error(self):
        """Empty query triggers 422 with structured ChatToolResponse error."""
        resp = self.client.post("/tools/search_bike_networks", json={"query": "   "})
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertIsNotNone(data["error"])
        self.assertIn("Validation error", data["error"])

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_caching_behavior(self, mock_get):
        """Verify network list is cached and doesn't hit upstream on consecutive calls."""
        mock_get.return_value = MockResponse(200, MOCK_NETWORKS_RESPONSE)

        # First call
        resp1 = self.client.post("/tools/search_bike_networks", json={"query": "Paris"})
        self.assertEqual(resp1.status_code, 200)

        # Second call
        resp2 = self.client.post("/tools/search_bike_networks", json={"query": "London"})
        self.assertEqual(resp2.status_code, 200)

        # mock_get should only be called once due to in-memory TTL caching
        self.assertEqual(mock_get.call_count, 1)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_rate_limiting(self, mock_get):
        """Verify 61st request in the window triggers HTTP 429."""
        mock_get.return_value = MockResponse(200, MOCK_NETWORKS_RESPONSE)

        # Exhaust 60 allowed requests
        for _ in range(60):
            r = self.client.post("/tools/search_bike_networks", json={"query": "Paris"})
            self.assertEqual(r.status_code, 200)

        # 61st request should be blocked by rate limiter
        blocked = self.client.post("/tools/search_bike_networks", json={"query": "Paris"})
        self.assertEqual(blocked.status_code, 429)
        self.assertIn("Rate limit exceeded", blocked.json()["error"])


if __name__ == "__main__":
    unittest.main()
