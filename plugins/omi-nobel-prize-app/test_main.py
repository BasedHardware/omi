"""Hermetic unit tests for Omi Nobel Prize Integration App.

All external HTTP requests to api.nobelprize.org are mocked.
Tests run in milliseconds and require zero network access.
"""

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

# Resolve plugin directory reliably regardless of invocation path
CURRENT_DIR = Path(__file__).resolve().parent

try:
    import fastapi
    import httpx
    import pydantic
    from fastapi.testclient import TestClient
    DEPS_AVAILABLE = True
except ImportError as e:
    DEPS_AVAILABLE = False
    IMPORT_ERROR = str(e)

if DEPS_AVAILABLE:
    # Programmatically load models.py
    _MODELS_PATH = CURRENT_DIR / "models.py"
    _MODELS_SPEC = importlib.util.spec_from_file_location("models", _MODELS_PATH)
    assert _MODELS_SPEC is not None and _MODELS_SPEC.loader is not None
    models = importlib.util.module_from_spec(_MODELS_SPEC)
    sys.modules["models"] = models
    _MODELS_SPEC.loader.exec_module(models)

    # Programmatically load main.py
    _MAIN_PATH = CURRENT_DIR / "main.py"
    _MAIN_SPEC = importlib.util.spec_from_file_location("main", _MAIN_PATH)
    assert _MAIN_SPEC is not None and _MAIN_SPEC.loader is not None
    main = importlib.util.module_from_spec(_MAIN_SPEC)
    sys.modules["main"] = main
    _MAIN_SPEC.loader.exec_module(main)

    app = main.app
    clear_cache = main.clear_cache
    clear_rate_limits = main.clear_rate_limits
    NOBEL_CATEGORY_MAP = models.NOBEL_CATEGORY_MAP
    resolve_nobel_category = models.resolve_nobel_category
    NobelPrizesRequest = models.NobelPrizesRequest
    SearchLaureatesRequest = models.SearchLaureatesRequest
    CategoryPrizesRequest = models.CategoryPrizesRequest
    LaureateDetailsRequest = models.LaureateDetailsRequest
    ChatToolResponse = models.ChatToolResponse
    get_current_year = models.get_current_year


# Sample Mock Data
MOCK_PRIZES_PAYLOAD = {
    "nobelPrizes": [
        {
            "awardYear": "2023",
            "category": {"en": "Physics"},
            "categoryFullName": {"en": "The Nobel Prize in Physics"},
            "laureates": [
                {
                    "id": "1024",
                    "knownName": {"en": "Pierre Agostini"},
                    "portion": "1/3",
                    "motivation": {
                        "en": "for experimental methods that generate attosecond pulses of light"
                    },
                },
                {
                    "id": "1025",
                    "knownName": {"en": "Ferenc Krausz"},
                    "portion": "1/3",
                    "motivation": {
                        "en": "for experimental methods that generate attosecond pulses of light"
                    },
                },
            ],
        }
    ]
}

MOCK_LAUREATE_SEARCH_PAYLOAD = {
    "laureates": [
        {
            "id": "26",
            "knownName": {"en": "Albert Einstein"},
            "fullName": {"en": "Albert Einstein"},
            "gender": "male",
            "birth": {
                "date": "1879-03-14",
                "place": {"city": {"en": "Ulm"}, "country": {"en": "Germany"}},
            },
            "death": {
                "date": "1955-04-18",
                "place": {"city": {"en": "Princeton, NJ"}, "country": {"en": "USA"}},
            },
            "nobelPrizes": [
                {
                    "awardYear": "1921",
                    "category": {"en": "Physics"},
                    "categoryFullName": {"en": "The Nobel Prize in Physics"},
                    "portion": "1",
                    "motivation": {
                        "en": "for his services to Theoretical Physics, and especially for his discovery of the law of the photoelectric effect"
                    },
                    "affiliations": [
                        {
                            "name": {"en": "Kaiser-Wilhelm-Institut für Physik"},
                            "city": {"en": "Berlin"},
                            "country": {"en": "Germany"},
                        }
                    ],
                }
            ],
            "wikipedia": {"english": "https://en.wikipedia.org/wiki/Albert_Einstein"},
        }
    ]
}


class MockResponse:
    """Mocked httpx.Response object."""

    def __init__(self, status_code: int, json_data: dict):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


@unittest.skipUnless(DEPS_AVAILABLE, f"Missing required dependencies: {globals().get('IMPORT_ERROR', '')}")
class TestOmiNobelPrizeApp(unittest.TestCase):
    """Hermetic unit tests for Omi Nobel Prize app."""

    def setUp(self):
        clear_cache()
        clear_rate_limits()
        self.client = TestClient(app, raise_server_exceptions=False)

    def test_root_endpoint(self):
        """GET / returns HTML landing page."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Omi Nobel Prize Integration App", response.text)
        self.assertIn("text/html", response.headers.get("content-type", ""))

    def test_health_check(self):
        """GET /health returns 200 with service status."""
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "service": "omi-nobel-prize-app"})

    def test_omi_tools_manifest(self):
        """GET /.well-known/omi-tools.json returns valid tools definition."""
        response = self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("schema_version"), "v1")
        tools = data.get("tools", [])
        tool_names = [t.get("name") for t in tools]
        self.assertIn("get_nobel_prizes", tool_names)
        self.assertIn("search_nobel_laureates", tool_names)
        self.assertIn("get_nobel_prize_by_category", tool_names)
        self.assertIn("get_nobel_laureate_details", tool_names)

    def test_category_resolver_valid_and_aliases(self):
        """Category resolver accurately maps aliases to canonical codes."""
        self.assertEqual(resolve_nobel_category("physics"), "phy")
        self.assertEqual(resolve_nobel_category("PHY"), "phy")
        self.assertEqual(resolve_nobel_category("medicine"), "med")
        self.assertEqual(resolve_nobel_category("physiology"), "med")
        self.assertEqual(resolve_nobel_category("peace"), "pea")
        self.assertEqual(resolve_nobel_category("economics"), "eco")
        self.assertIsNone(resolve_nobel_category(None))

    def test_category_resolver_invalid(self):
        """Category resolver raises descriptive ValueError for unknown categories."""
        with self.assertRaises(ValueError) as ctx:
            resolve_nobel_category("astrology")
        self.assertIn("Unknown Nobel category", str(ctx.exception))

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_get_nobel_prizes_success(self, mock_get):
        """POST /tools/get_nobel_prizes returns formatted markdown on success."""
        mock_get.return_value = MockResponse(200, MOCK_PRIZES_PAYLOAD)

        response = self.client.post(
            "/tools/get_nobel_prizes",
            json={"year": 2023, "category": "physics", "limit": 5},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        result = data.get("result", "")
        self.assertIn("The Nobel Prize in Physics (2023)", result)
        self.assertIn("Pierre Agostini", result)
        self.assertIn("Ferenc Krausz", result)
        self.assertIn("attosecond pulses of light", result)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_get_nobel_prizes_empty(self, mock_get):
        """POST /tools/get_nobel_prizes returns friendly message when no records match."""
        mock_get.return_value = MockResponse(200, {"nobelPrizes": []})

        response = self.client.post(
            "/tools/get_nobel_prizes",
            json={"year": 1940, "category": "peace"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("No Nobel Prize records found", data.get("result", ""))

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_get_nobel_prizes_api_error(self, mock_get):
        """POST /tools/get_nobel_prizes handles upstream HTTP error gracefully."""
        mock_get.return_value = MockResponse(502, {})

        response = self.client.post(
            "/tools/get_nobel_prizes",
            json={"year": 2020},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("result"))
        self.assertIn("Nobel Prize API error (HTTP 502)", data.get("error", ""))

    def test_get_nobel_prizes_invalid_year_bounds(self):
        """POST /tools/get_nobel_prizes rejects year before 1901 and future years."""
        # Pre-1901
        res_old = self.client.post("/tools/get_nobel_prizes", json={"year": 1850})
        self.assertEqual(res_old.status_code, 422)
        self.assertIn("year", res_old.json().get("error", "").lower())

        # Future year (current_year + 1)
        next_year = get_current_year() + 1
        res_future = self.client.post("/tools/get_nobel_prizes", json={"year": next_year})
        self.assertEqual(res_future.status_code, 422)
        self.assertIn("year", res_future.json().get("error", "").lower())

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_search_nobel_laureates_success(self, mock_get):
        """POST /tools/search_nobel_laureates returns matching laureates."""
        mock_get.return_value = MockResponse(200, MOCK_LAUREATE_SEARCH_PAYLOAD)

        response = self.client.post(
            "/tools/search_nobel_laureates",
            json={"query": "Einstein", "limit": 5},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        result = data.get("result", "")
        self.assertIn("Albert Einstein", result)
        self.assertIn("photoelectric effect", result)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_search_nobel_laureates_empty_results(self, mock_get):
        """POST /tools/search_nobel_laureates handles zero matches."""
        mock_get.return_value = MockResponse(200, {"laureates": []})

        response = self.client.post(
            "/tools/search_nobel_laureates",
            json={"query": "NonexistentPerson"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("No Nobel laureates found matching", data.get("result", ""))

    def test_search_nobel_laureates_blank_query(self):
        """POST /tools/search_nobel_laureates rejects whitespace-only query."""
        response = self.client.post(
            "/tools/search_nobel_laureates",
            json={"query": "   "},
        )
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertIn("error", data)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_get_nobel_prize_by_category_success(self, mock_get):
        """POST /tools/get_nobel_prize_by_category retrieves prizes for valid category alias."""
        mock_get.return_value = MockResponse(200, MOCK_PRIZES_PAYLOAD)

        response = self.client.post(
            "/tools/get_nobel_prize_by_category",
            json={"category": "physics", "limit": 3},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("Recent Nobel Prizes in Physics", data.get("result", ""))

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_get_nobel_laureate_details_numeric_id(self, mock_get):
        """POST /tools/get_nobel_laureate_details retrieves single laureate by ID."""
        mock_get.return_value = MockResponse(200, [MOCK_LAUREATE_SEARCH_PAYLOAD["laureates"][0]])

        response = self.client.post(
            "/tools/get_nobel_laureate_details",
            json={"identifier": "26"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        result = data.get("result", "")
        self.assertIn("Albert Einstein", result)
        self.assertIn("Ulm, Germany", result)
        self.assertIn("Wikipedia", result)

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_get_nobel_laureate_details_name_query(self, mock_get):
        """POST /tools/get_nobel_laureate_details searches by name if non-numeric."""
        mock_get.return_value = MockResponse(200, MOCK_LAUREATE_SEARCH_PAYLOAD)

        response = self.client.post(
            "/tools/get_nobel_laureate_details",
            json={"identifier": "Albert Einstein"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("Albert Einstein", data.get("result", ""))

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_get_nobel_laureate_details_404(self, mock_get):
        """POST /tools/get_nobel_laureate_details returns error when ID is not found."""
        mock_get.return_value = MockResponse(404, {})

        response = self.client.post(
            "/tools/get_nobel_laureate_details",
            json={"identifier": "999999"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("result"))
        self.assertIn("No Nobel laureate found with ID '999999'", data.get("error", ""))

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_network_timeout_handling(self, mock_get):
        """Tool endpoints gracefully catch network errors and return error message."""
        mock_get.side_effect = httpx.RequestError("Connection timeout")

        response = self.client.post(
            "/tools/get_nobel_prizes",
            json={"year": 2023},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("result"))
        self.assertIn("Failed to communicate with Nobel Prize API", data.get("error", ""))

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_short_lived_cache_avoids_redundant_upstream_calls(self, mock_get):
        """Second identical request serves from cache without hitting upstream API."""
        mock_get.return_value = MockResponse(200, MOCK_PRIZES_PAYLOAD)

        # Call 1: Populates cache
        resp1 = self.client.post("/tools/get_nobel_prizes", json={"year": 2023, "category": "physics"})
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(mock_get.call_count, 1)

        # Call 2: Hit cache
        resp2 = self.client.post("/tools/get_nobel_prizes", json={"year": 2023, "category": "physics"})
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(mock_get.call_count, 1)  # Still 1, served from cache!
        self.assertEqual(resp1.json(), resp2.json())

    @patch("httpx.AsyncClient.get", new_callable=AsyncMock)
    def test_server_side_rate_limiting(self, mock_get):
        """Exceeding rate limit triggers 429 response."""
        mock_get.return_value = MockResponse(200, MOCK_PRIZES_PAYLOAD)

        # Send 60 requests (allowed)
        for i in range(60):
            # Vary query so it tests rate limiter and not just cache
            resp = self.client.post("/tools/get_nobel_prizes", json={"limit": (i % 5) + 1})
            self.assertEqual(resp.status_code, 200)

        # 61st request should be throttled with 429
        throttled = self.client.post("/tools/get_nobel_prizes", json={"limit": 1})
        self.assertEqual(throttled.status_code, 429)
        self.assertIn("Rate limit exceeded", throttled.json().get("error", ""))


if __name__ == "__main__":
    unittest.main()
