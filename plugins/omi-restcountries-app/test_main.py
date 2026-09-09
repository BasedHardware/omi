"""Hermetic unit tests for Omi REST Countries & Geographic Intelligence App."""

import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

from data import find_country, search_by_capital_city
from main import SimpleTTLCache, app, app_cache
from models import (
    ChatToolResponse,
    CompareCountriesRequest,
    GetBorderCountriesRequest,
    GetCountryInfoRequest,
    SearchByCapitalRequest,
    SearchByCurrencyRequest,
    SearchByLanguageRequest,
)


class TestChatToolModels(unittest.TestCase):
    """Test Pydantic contract and validation invariants."""

    def test_response_mutual_exclusivity(self):
        """Ensure exactly one of result or error must be set."""
        # Valid result
        resp_res = ChatToolResponse(result="Valid result text")
        self.assertIsNotNone(resp_res.result)
        self.assertIsNone(resp_res.error)

        # Valid error
        resp_err = ChatToolResponse(error="Valid error text")
        self.assertIsNone(resp_err.result)
        self.assertIsNotNone(resp_err.error)

        # Neither result nor error -> must raise
        with self.assertRaises(ValueError):
            ChatToolResponse()

        # Both result and error -> must raise
        with self.assertRaises(ValueError):
            ChatToolResponse(result="res", error="err")

    def test_input_sanitization(self):
        """Ensure whitespace is stripped and empty strings rejected."""
        req = GetCountryInfoRequest(country="  France   ")
        self.assertEqual(req.country, "France")

        with self.assertRaises(ValueError):
            GetCountryInfoRequest(country="   ")

        req_cap = SearchByCapitalRequest(capital="  Tokyo \t")
        self.assertEqual(req_cap.capital, "Tokyo")

        with self.assertRaises(ValueError):
            SearchByCapitalRequest(capital="   ")


class TestSimpleTTLCache(unittest.TestCase):
    """Test in-memory cache eviction and expiration."""

    def test_cache_lru_and_expiration(self):
        cache = SimpleTTLCache(maxsize=2, ttl_seconds=10)
        cache.set("a", "val_a")
        cache.set("b", "val_b")
        self.assertEqual(cache.get("a"), "val_a")

        # Adding 3rd item evicts least recently used ('b' because 'a' was read)
        cache.set("c", "val_c")
        self.assertIsNotNone(cache.get("a"))
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("c"), "val_c")

        # Expiration
        with patch("time.time", return_value=9999999999.0):
            self.assertIsNone(cache.get("a"))


class TestCountryEndpoints(unittest.TestCase):
    """Hermetic API endpoint tests."""

    def setUp(self):
        self.client = TestClient(app)
        app_cache.clear()

    def test_health_check(self):
        """GET /health must return status ok."""
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("service"), "omi-restcountries-app")

    def test_manifest_schema(self):
        """GET /.well-known/omi-tools.json must list all 6 registered tools."""
        resp = self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("schema_version"), "1.0")
        self.assertEqual(data.get("auth"), {"type": "none"})

        tools = data.get("tools", [])
        self.assertEqual(len(tools), 6)

        tool_names = {t["name"] for t in tools}
        expected_names = {
            "get_country_info",
            "search_by_capital",
            "get_border_countries",
            "search_by_currency",
            "search_by_language",
            "compare_countries",
        }
        self.assertEqual(tool_names, expected_names)

        for t in tools:
            self.assertTrue(t["endpoint"].startswith("/tools/"))
            self.assertEqual(t["method"], "POST")
            self.assertFalse(t["auth_required"])
            self.assertIn("properties", t["parameters"])

    def test_validation_error_contract_omits_null_result(self):
        """Validation errors must return HTTP 200 with error and NO result: null."""
        # Missing required parameter
        resp = self.client.post("/tools/get_country_info", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertNotIn("result", data)  # Critical invariant: must NOT contain "result": null

    def test_get_country_info_by_name(self):
        """Lookup by country name (France)."""
        resp = self.client.post("/tools/get_country_info", json={"country": "France"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn("error", data)
        self.assertIn("result", data)
        self.assertIn("Paris", data["result"])
        self.assertIn("Euro", data["result"])
        self.assertIn("FRA", data["result"])

    def test_get_country_info_by_code(self):
        """Lookup by CCA2 and CCA3 codes."""
        resp_cca2 = self.client.post("/tools/get_country_info", json={"country": "JP"})
        self.assertEqual(resp_cca2.status_code, 200)
        self.assertIn("Tokyo", resp_cca2.json()["result"])

        resp_cca3 = self.client.post("/tools/get_country_info", json={"country": "DEU"})
        self.assertEqual(resp_cca3.status_code, 200)
        self.assertIn("Berlin", resp_cca3.json()["result"])

    def test_get_country_info_by_alias(self):
        """Lookup by common alias ('USA', 'UK')."""
        resp_usa = self.client.post("/tools/get_country_info", json={"country": "USA"})
        self.assertEqual(resp_usa.status_code, 200)
        self.assertIn("Washington", resp_usa.json()["result"])

        resp_uk = self.client.post("/tools/get_country_info", json={"country": "UK"})
        self.assertEqual(resp_uk.status_code, 200)
        self.assertIn("London", resp_uk.json()["result"])

    def test_get_country_info_unknown_country(self):
        """Unknown country returns structured error."""
        resp = self.client.post("/tools/get_country_info", json={"country": "NonExistentLandia"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertIn("NonExistentLandia", data["error"])
        self.assertNotIn("result", data)

    def test_search_by_capital(self):
        """Find country by capital city."""
        resp = self.client.post("/tools/search_by_capital", json={"capital": "Canberra"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn("error", data)
        self.assertIn("Australia", data["result"])

    def test_search_by_capital_unknown(self):
        """Unknown capital returns helpful error."""
        resp = self.client.post("/tools/search_by_capital", json={"capital": "AtlantisCity"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertNotIn("result", data)

    def test_get_border_countries_multiple_neighbors(self):
        """Germany borders 9 nations."""
        resp = self.client.post("/tools/get_border_countries", json={"country": "Germany"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn("error", data)
        self.assertIn("shares land borders with 9 countries", data["result"])
        self.assertIn("France", data["result"])
        self.assertIn("Austria", data["result"])

    def test_get_border_countries_island(self):
        """Island nations (Japan) have zero land borders."""
        resp = self.client.post("/tools/get_border_countries", json={"country": "Japan"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn("error", data)
        self.assertIn("no land borders", data["result"])

    def test_get_border_countries_unknown(self):
        """Unknown country returns structured error."""
        resp = self.client.post("/tools/get_border_countries", json={"country": "Narnia"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertNotIn("result", data)

    def test_search_by_currency(self):
        """Find countries using EUR."""
        resp = self.client.post("/tools/search_by_currency", json={"currency": "EUR"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn("error", data)
        self.assertIn("France", data["result"])
        self.assertIn("Germany", data["result"])

    def test_search_by_currency_unknown(self):
        """Unknown currency returns structured error."""
        resp = self.client.post("/tools/search_by_currency", json={"currency": "XYZFAKE"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertNotIn("result", data)

    def test_search_by_language(self):
        """Find countries speaking Spanish."""
        resp = self.client.post("/tools/search_by_language", json={"language": "Spanish"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn("error", data)
        self.assertIn("Spain", data["result"])
        self.assertIn("Mexico", data["result"])
        self.assertIn("Argentina", data["result"])

    def test_search_by_language_unknown(self):
        """Unknown language returns structured error."""
        resp = self.client.post("/tools/search_by_language", json={"language": "Klingon"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertNotIn("result", data)

    def test_compare_countries(self):
        """Compare Japan vs Germany."""
        resp = self.client.post("/tools/compare_countries", json={"country_a": "Japan", "country_b": "Germany"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn("error", data)
        self.assertIn("Comparison: 🇯🇵 Japan vs 🇩🇪 Germany", data["result"])
        self.assertIn("Population:", data["result"])
        self.assertIn("Area:", data["result"])

    def test_compare_countries_invalid_first(self):
        """Invalid first country returns error."""
        resp = self.client.post("/tools/compare_countries", json={"country_a": "UnknownLand", "country_b": "Germany"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertIn("First country 'UnknownLand' not found", data["error"])

    def test_compare_countries_invalid_second(self):
        """Invalid second country returns error."""
        resp = self.client.post("/tools/compare_countries", json={"country_a": "France", "country_b": "UnknownLand"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertIn("Second country 'UnknownLand' not found", data["error"])

    def test_root_landing_page(self):
        """GET / returns HTML landing page."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("Omi REST Countries", resp.text)


if __name__ == "__main__":
    unittest.main()
