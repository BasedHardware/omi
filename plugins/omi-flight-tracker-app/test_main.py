"""
Hermetic unit test suite for Omi OpenSky Flight Tracker Integration App.
All tests run 100% offline with zero external network dependencies.
"""

import copy
import math
import os
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure the app directory is on sys.path for direct module resolution
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import httpx
from fastapi.testclient import TestClient

import main
from main import (
    LRUCache,
    SlidingWindowRateLimiter,
    app,
    bearing_to_compass,
    cache,
    calculate_bearing_deg,
    compute_bounding_box,
    format_flight_entry,
    haversine_distance_km,
    rate_limiter,
    resolve_coordinates,
)
from models import (
    AirspaceActivityRequest,
    ChatToolResponse,
    FlightsOverheadRequest,
    TrackFlightRequest,
)


# Sample realistic OpenSky state vectors
# [0: icao24, 1: callsign, 2: origin_country, 3: time_pos, 4: last_contact,
#  5: lon, 6: lat, 7: baro_altitude, 8: on_ground, 9: velocity,
#  10: true_track, 11: vertical_rate, 12: sensors, 13: geo_altitude,
#  14: squawk, 15: spi, 16: position_source]
MOCK_STATES = [
    [
        "a1234b",
        "UAL123  ",
        "United States",
        1700000000,
        1700000005,
        -73.9851,  # Near NYC
        40.7484,
        10500.0,  # ~34,448 ft
        False,
        230.5,    # ~448 kts
        90.0,     # Heading East
        2.5,      # Climbing
        None,
        10600.0,
        "4201",
        False,
        0
    ],
    [
        "4002a1",
        "BAW28   ",
        "United Kingdom",
        1700000000,
        1700000005,
        -0.4543,   # Near London Heathrow
        51.4700,
        1500.0,   # ~4,921 ft
        False,
        120.0,
        270.0,    # Heading West
        -3.0,     # Descending
        None,
        1550.0,
        "1200",
        False,
        0
    ],
    [
        "3c6444",
        "DLH400  ",
        "Germany",
        1700000000,
        1700000005,
        8.5706,    # Near Frankfurt
        50.0379,
        0.0,
        True,     # On ground
        15.0,
        180.0,
        0.0,
        None,
        0.0,
        "7000",
        False,
        0
    ]
]


class TestFlightTrackerApp(unittest.TestCase):
    def setUp(self):
        cache.clear()
        rate_limiter.history.clear()
        self.client = TestClient(app)

    def tearDown(self):
        cache.clear()
        rate_limiter.history.clear()

    # --- Landing Page & Metadata Tests ---

    def test_root_endpoint(self):
        """Root endpoint returns HTML landing page."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("Live Aviation Radar", response.text)

    def test_manifest_endpoint(self):
        """Manifest returns 3 valid registered tools."""
        response = self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["auth_required"], False)
        self.assertEqual(len(data["tools"]), 3)
        tool_names = [t["name"] for t in data["tools"]]
        self.assertIn("get_flights_overhead", tool_names)
        self.assertIn("track_flight_by_callsign", tool_names)
        self.assertIn("get_airspace_activity", tool_names)

    # --- Health Probe Tests ---

    @patch("httpx.AsyncClient.get")
    def test_health_healthy(self, mock_get):
        """Health check returns healthy when upstream OpenSky responds."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["upstream_connected"])

    @patch("httpx.AsyncClient.get")
    def test_health_degraded(self, mock_get):
        """Health check reports degraded on upstream exception."""
        mock_get.side_effect = httpx.RequestError("Connection timeout")

        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "degraded")
        self.assertFalse(data["upstream_connected"])

    # --- Geographic & Aviation Math Tests ---

    def test_haversine_distance_calculation(self):
        """Haversine formula calculates known distance accurately."""
        # Distance NYC (40.7128, -74.0060) to London (51.5074, -0.1278) is approx 5570 km
        dist = haversine_distance_km(40.7128, -74.0060, 51.5074, -0.1278)
        self.assertAlmostEqual(dist, 5570.0, delta=50.0)

    def test_calculate_bearing_and_compass(self):
        """Bearing calculation accurately maps to 16-point cardinal compass."""
        # Due north
        bearing_n = calculate_bearing_deg(0.0, 0.0, 1.0, 0.0)
        self.assertAlmostEqual(bearing_n, 0.0, delta=1.0)
        self.assertEqual(bearing_to_compass(bearing_n), "N")

        # Due east
        bearing_e = calculate_bearing_deg(0.0, 0.0, 0.0, 1.0)
        self.assertAlmostEqual(bearing_e, 90.0, delta=1.0)
        self.assertEqual(bearing_to_compass(bearing_e), "E")

    def test_compute_bounding_box(self):
        """Bounding box calculation preserves coordinate bounds."""
        lamin, lomin, lamax, lomax = compute_bounding_box(40.0, -74.0, radius_km=50.0)
        self.assertTrue(-90.0 <= lamin < lamax <= 90.0)
        self.assertTrue(-180.0 <= lomin < lomax <= 180.0)
        self.assertAlmostEqual((lamax - lamin) * 111.0 / 2.0, 50.0, delta=5.0)

    def test_resolve_coordinates_valid(self):
        """Resolves direct coordinates and known city names."""
        lat, lon, label = resolve_coordinates(40.71, -74.00, None)
        self.assertEqual(lat, 40.71)
        self.assertEqual(lon, -74.00)

        lat2, lon2, label2 = resolve_coordinates(None, None, "London")
        self.assertAlmostEqual(lat2, 51.5074, delta=0.01)
        self.assertIn("London", label2)

    def test_resolve_coordinates_errors(self):
        """Raises ValueError on unknown city or missing inputs."""
        with self.assertRaises(ValueError):
            resolve_coordinates(None, None, "AtlantisUnderTheSea")

        with self.assertRaises(ValueError):
            resolve_coordinates(None, None, None)

    def test_format_flight_entry(self):
        """Correctly converts OpenSky state vector into human and voice-friendly metadata."""
        flight = format_flight_entry(MOCK_STATES[0], observer_lat=40.7128, observer_lon=-74.0060)
        self.assertEqual(flight["callsign"], "UAL123")
        self.assertEqual(flight["country"], "United States")
        self.assertIn("ft", flight["altitude"])
        self.assertIn("Climbing", flight["vertical_status"])
        self.assertIsNotNone(flight["distance_km"])
        self.assertIsNotNone(flight["compass_direction"])

    # --- Tool 1: get_flights_overhead ---

    @patch("main.fetch_opensky_states")
    def test_get_flights_overhead_success(self, mock_fetch):
        """Tool returns nearby overhead flights formatted in Markdown."""
        mock_fetch.return_value = (1700000000, MOCK_STATES)

        payload = {
            "latitude": 40.7128,
            "longitude": -74.0060,
            "radius_km": 50.0,
            "limit": 5
        }
        response = self.client.post("/tools/get_flights_overhead", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["error"])
        self.assertIsNotNone(data["result"])
        self.assertIn("Live Overhead Radar", data["result"])
        self.assertIn("UAL123", data["result"])
        self.assertIn("United States", data["result"])

    @patch("main.fetch_opensky_states")
    def test_get_flights_overhead_by_city_name(self, mock_fetch):
        """Tool resolves city name and queries overhead flights."""
        mock_fetch.return_value = (1700000000, MOCK_STATES)

        payload = {"location": "London", "radius_km": 50.0}
        response = self.client.post("/tools/get_flights_overhead", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["error"])
        self.assertIn("BAW28", data["result"])

    @patch("main.fetch_opensky_states")
    def test_get_flights_overhead_empty(self, mock_fetch):
        """Tool returns graceful message when no flights are overhead."""
        mock_fetch.return_value = (1700000000, [])

        payload = {"latitude": 0.0, "longitude": 0.0, "radius_km": 20.0}
        response = self.client.post("/tools/get_flights_overhead", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("No active aircraft detected", data["result"])

    def test_get_flights_overhead_unknown_location(self):
        """Returns friendly error when location cannot be resolved."""
        payload = {"location": "NonExistentLocation123"}
        response = self.client.post("/tools/get_flights_overhead", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNotNone(data["error"])
        self.assertIn("not in the built-in city registry", data["error"])

    # --- Tool 2: track_flight_by_callsign ---

    @patch("main.fetch_opensky_states")
    def test_track_flight_by_callsign_success(self, mock_fetch):
        """Tracks active flight by exact callsign."""
        mock_fetch.return_value = (1700000000, MOCK_STATES)

        payload = {"callsign": "UAL123"}
        response = self.client.post("/tools/track_flight_by_callsign", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["error"])
        self.assertIn("Live Tracking: Flight UAL123", data["result"])
        self.assertIn("United States", data["result"])
        self.assertIn("Climbing", data["result"])

    @patch("main.fetch_opensky_states")
    def test_track_flight_by_icao(self, mock_fetch):
        """Tracks flight by 6-char ICAO address."""
        mock_fetch.return_value = (1700000000, MOCK_STATES)

        payload = {"callsign": "a1234b"}
        response = self.client.post("/tools/track_flight_by_callsign", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("UAL123", data["result"])

    @patch("main.fetch_opensky_states")
    def test_track_flight_not_found(self, mock_fetch):
        """Returns helpful message when callsign is not in active airspace."""
        mock_fetch.return_value = (1700000000, MOCK_STATES)

        payload = {"callsign": "VIR999"}
        response = self.client.post("/tools/track_flight_by_callsign", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("was not detected in active airspace", data["result"])

    def test_track_flight_invalid_callsign(self):
        """Rejects empty or whitespace-only callsign."""
        payload = {"callsign": "   "}
        response = self.client.post("/tools/track_flight_by_callsign", json=payload)
        self.assertEqual(response.status_code, 422)

    # --- Tool 3: get_airspace_activity ---

    @patch("main.fetch_opensky_states")
    def test_get_airspace_activity_global(self, mock_fetch):
        """Summarizes global airspace volume and top active flights."""
        mock_fetch.return_value = (1700000000, MOCK_STATES)

        payload = {"limit": 5}
        response = self.client.post("/tools/get_airspace_activity", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Airspace Activity Report", data["result"])
        self.assertIn("**Total Tracked Aircraft**: 3", data["result"])
        self.assertIn("**Airborne**: 2", data["result"])
        self.assertIn("**On Ground**: 1", data["result"])

    @patch("main.fetch_opensky_states")
    def test_get_airspace_activity_country_filter(self, mock_fetch):
        """Filters airspace report by country of origin."""
        mock_fetch.return_value = (1700000000, MOCK_STATES)

        payload = {"country": "United Kingdom"}
        response = self.client.post("/tools/get_airspace_activity", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("BAW28", data["result"])
        self.assertNotIn("UAL123", data["result"])

    @patch("main.fetch_opensky_states")
    def test_get_airspace_activity_altitude_filter(self, mock_fetch):
        """Filters aircraft by minimum barometric altitude."""
        mock_fetch.return_value = (1700000000, MOCK_STATES)

        # UAL123 is at 10,500m, BAW28 is at 1,500m
        payload = {"min_altitude_meters": 5000.0}
        response = self.client.post("/tools/get_airspace_activity", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("UAL123", data["result"])
        self.assertNotIn("BAW28", data["result"])

    # --- Upstream Error Handling Tests ---

    @patch("httpx.AsyncClient.get")
    def test_upstream_rate_limit_handled(self, mock_get):
        """Returns friendly error when upstream returns HTTP 429."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_get.return_value = mock_response

        payload = {"latitude": 40.71, "longitude": -74.00}
        response = self.client.post("/tools/get_flights_overhead", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNotNone(data["error"])
        self.assertIn("temporarily rate-limited", data["error"])

    @patch("httpx.AsyncClient.get")
    def test_upstream_server_error_handled(self, mock_get):
        """Returns friendly error when upstream returns HTTP 502/503."""
        mock_response = MagicMock()
        mock_response.status_code = 502
        mock_get.return_value = mock_response

        payload = {"callsign": "UAL123"}
        response = self.client.post("/tools/track_flight_by_callsign", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNotNone(data["error"])
        self.assertIn("temporarily unavailable", data["error"])

    # --- LRU Cache & Rate Limiting Unit Tests ---

    def test_lru_cache_operations(self):
        """LRU cache sets, retrieves, and respects capacity limits."""
        test_cache = LRUCache(capacity=2)
        test_cache.set("a", 1, ttl=10.0)
        test_cache.set("b", 2, ttl=10.0)
        self.assertEqual(test_cache.get("a"), 1)

        # Accessing 'a' makes 'b' least recently used; adding 'c' evicts 'b'
        test_cache.set("c", 3, ttl=10.0)
        self.assertEqual(test_cache.get("a"), 1)
        self.assertIsNone(test_cache.get("b"))
        self.assertEqual(test_cache.get("c"), 3)

    def test_lru_cache_ttl_expiry(self):
        """LRU cache expires items past TTL."""
        test_cache = LRUCache()
        test_cache.set("short_lived", "value", ttl=-1.0)  # already expired
        self.assertIsNone(test_cache.get("short_lived"))

    def test_lru_cache_deep_copy_isolation(self):
        """Mutating a cached object does not pollute the cache."""
        test_cache = LRUCache()
        original_data = {"flights": ["UAL123", "BAW28"]}
        test_cache.set("key", original_data, ttl=10.0)

        retrieved = test_cache.get("key")
        retrieved["flights"].append("POLLUTED_FLIGHT")

        second_retrieval = test_cache.get("key")
        self.assertNotIn("POLLUTED_FLIGHT", second_retrieval["flights"])

    def test_sliding_window_rate_limiter(self):
        """Rate limiter blocks requests that exceed threshold within window."""
        rl = SlidingWindowRateLimiter(max_requests=3, window_seconds=10.0)
        ip = "192.168.1.100"

        self.assertFalse(rl.is_rate_limited(ip))
        self.assertFalse(rl.is_rate_limited(ip))
        self.assertFalse(rl.is_rate_limited(ip))
        # 4th request exceeds max_requests
        self.assertTrue(rl.is_rate_limited(ip))

    def test_trusted_proxy_forwarded_ip_used(self):
        """Extracts client IP from X-Forwarded-For if peer is in trusted proxies."""
        request = MagicMock()
        request.client.host = "127.0.0.1"  # Default trusted
        request.headers = {"X-Forwarded-For": "203.0.113.195, 10.0.0.1"}

        client_ip = rate_limiter.get_client_ip(request)
        self.assertEqual(client_ip, "203.0.113.195")

    def test_untrusted_proxy_forwarded_ip_ignored(self):
        """Ignores spoofed X-Forwarded-For if peer is not in trusted proxies."""
        request = MagicMock()
        request.client.host = "198.51.100.42"  # Untrusted external IP
        request.headers = {"X-Forwarded-For": "203.0.113.195"}

        client_ip = rate_limiter.get_client_ip(request)
        self.assertEqual(client_ip, "198.51.100.42")


if __name__ == "__main__":
    unittest.main()
