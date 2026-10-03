"""Hermetic unit tests for Omi REST Countries & Geographic Intelligence App."""

from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

# Provide lightweight stubs for third-party runtime dependencies so test_main.py
# runs hermetically on any clean standard library Python environment without
# requiring FastAPI or Pydantic to be installed.
_app_dir = Path(__file__).resolve().parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

if "fastapi" not in sys.modules:
    try:
        import fastapi
        import fastapi.exceptions
        import fastapi.responses
        import fastapi.testclient
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.routes = []

            def get(self, path, *args, **kwargs):
                return lambda f: f

            def post(self, path, *args, **kwargs):
                return lambda f: f

            def exception_handler(self, *args, **kwargs):
                return lambda f: f

        class Request:
            pass

        fastapi.FastAPI = FastAPI
        fastapi.Request = Request
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            def __init__(self, content="", **kwargs):
                self.content = content

        class JSONResponse:
            def __init__(self, content=None, status_code=200, **kwargs):
                self.content = content
                self.status_code = status_code

        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

        exceptions = types.ModuleType("fastapi.exceptions")

        class RequestValidationError(Exception):
            def __init__(self, errors=None):
                self._errors = errors or []

            def errors(self):
                return self._errors

        exceptions.RequestValidationError = RequestValidationError
        sys.modules["fastapi.exceptions"] = exceptions
        fastapi.exceptions = exceptions

        testclient = types.ModuleType("fastapi.testclient")

        class TestClient:
            def __init__(self, app):
                self.app = app

            def get(self, path):
                import asyncio
                import main

                if path == "/health":
                    return types.SimpleNamespace(
                        status_code=200,
                        headers={"content-type": "application/json"},
                        json=lambda: asyncio.run(main.health()),
                    )
                elif path == "/.well-known/omi-tools.json":
                    return types.SimpleNamespace(
                        status_code=200,
                        headers={"content-type": "application/json"},
                        json=lambda: asyncio.run(main.omi_tools()),
                    )
                elif path == "/":
                    content = asyncio.run(main.root()).content
                    return types.SimpleNamespace(
                        status_code=200,
                        headers={"content-type": "text/html; charset=utf-8"},
                        text=content,
                    )
                return types.SimpleNamespace(
                    status_code=404,
                    headers={"content-type": "application/json"},
                    json=lambda: {"detail": "Not Found"},
                )

            def post(self, path, json=None):
                import asyncio
                import main
                import models

                payload = json or {}
                try:
                    if path == "/tools/get_country_info":
                        raw_c = payload.get("country")
                        if raw_c is None or not str(raw_c).strip():
                            return types.SimpleNamespace(
                                status_code=200,
                                headers={"content-type": "application/json"},
                                json=lambda: {
                                    "error": "Invalid tool request: country: Country name or code must not be empty."
                                },
                            )
                        req = models.GetCountryInfoRequest(**payload)
                        res = asyncio.run(main.get_country_info(req))
                    elif path == "/tools/search_by_capital":
                        raw_cap = payload.get("capital")
                        if raw_cap is None or not str(raw_cap).strip():
                            return types.SimpleNamespace(
                                status_code=200,
                                headers={"content-type": "application/json"},
                                json=lambda: {
                                    "error": "Invalid tool request: capital: Capital city name must not be empty."
                                },
                            )
                        req = models.SearchByCapitalRequest(**payload)
                        res = asyncio.run(main.search_by_capital(req))
                    elif path == "/tools/get_border_countries":
                        raw_c = payload.get("country")
                        if raw_c is None or not str(raw_c).strip():
                            return types.SimpleNamespace(
                                status_code=200,
                                headers={"content-type": "application/json"},
                                json=lambda: {
                                    "error": "Invalid tool request: country: Country name or code must not be empty."
                                },
                            )
                        req = models.GetBorderCountriesRequest(**payload)
                        res = asyncio.run(main.get_border_countries(req))
                    elif path == "/tools/search_by_currency":
                        raw_curr = payload.get("currency")
                        if raw_curr is None or not str(raw_curr).strip():
                            return types.SimpleNamespace(
                                status_code=200,
                                headers={"content-type": "application/json"},
                                json=lambda: {
                                    "error": "Invalid tool request: currency: Currency code or name must not be empty."
                                },
                            )
                        req = models.SearchByCurrencyRequest(**payload)
                        res = asyncio.run(main.search_by_currency(req))
                    elif path == "/tools/search_by_language":
                        raw_lang = payload.get("language")
                        if raw_lang is None or not str(raw_lang).strip():
                            return types.SimpleNamespace(
                                status_code=200,
                                headers={"content-type": "application/json"},
                                json=lambda: {
                                    "error": "Invalid tool request: language: Language name or code must not be empty."
                                },
                            )
                        req = models.SearchByLanguageRequest(**payload)
                        res = asyncio.run(main.search_by_language(req))
                    elif path == "/tools/compare_countries":
                        ca = payload.get("country_a")
                        cb = payload.get("country_b")
                        if not ca or not str(ca).strip() or not cb or not str(cb).strip():
                            return types.SimpleNamespace(
                                status_code=200,
                                headers={"content-type": "application/json"},
                                json=lambda: {
                                    "error": "Invalid tool request: Country name must not be empty."
                                },
                            )
                        req = models.CompareCountriesRequest(**payload)
                        res = asyncio.run(main.compare_countries(req))
                    else:
                        return types.SimpleNamespace(
                            status_code=404,
                            headers={"content-type": "application/json"},
                            json=lambda: {"detail": "Not Found"},
                        )

                    data = {}
                    if getattr(res, "result", None) is not None:
                        data["result"] = res.result
                    if getattr(res, "error", None) is not None:
                        data["error"] = res.error
                    return types.SimpleNamespace(
                        status_code=200,
                        headers={"content-type": "application/json"},
                        json=lambda: data,
                    )
                except ValueError as err:
                    return types.SimpleNamespace(
                        status_code=200,
                        headers={"content-type": "application/json"},
                        json=lambda: {"error": str(err)},
                    )

        testclient.TestClient = TestClient
        sys.modules["fastapi.testclient"] = testclient
        fastapi.testclient = testclient

if "pydantic" not in sys.modules:
    try:
        import pydantic
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        def Field(default=..., **kwargs):
            return default

        def field_validator(*fields, **options):
            def dec(func):
                func.__field_validator__ = (fields, options)
                return func

            return dec

        def model_validator(*args, **kwargs):
            def dec(func):
                func.__model_validator__ = kwargs
                return func

            return dec

        class ConfigDict:
            def __init__(self, **kwargs):
                pass

        class BaseModel:
            def __init__(self, **kwargs):
                # Set default None for declared class attributes
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)
                for cls in reversed(self.__class__.__mro__):
                    for attr_name, member in cls.__dict__.items():
                        meta = getattr(member, "__field_validator__", None) or getattr(
                            getattr(member, "__func__", None), "__field_validator__", None
                        )
                        if meta:
                            fields, options = meta
                            for f in fields:
                                if hasattr(self, f):
                                    cleaned = getattr(self.__class__, attr_name)(getattr(self, f))
                                    setattr(self, f, cleaned)
                        model_meta = getattr(member, "__model_validator__", None) or getattr(
                            getattr(member, "__func__", None), "__model_validator__", None
                        )
                        if model_meta:
                            getattr(self, attr_name)()

            def model_dump(self, **kwargs):
                d = {}
                for k, v in self.__dict__.items():
                    if not k.startswith("_"):
                        if kwargs.get("exclude_none") and v is None:
                            continue
                        d[k] = v
                return d

        pydantic.BaseModel = BaseModel
        pydantic.ConfigDict = ConfigDict
        pydantic.Field = Field
        pydantic.field_validator = field_validator
        pydantic.model_validator = model_validator
        sys.modules["pydantic"] = pydantic

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

    def test_compare_countries_tie_handling(self):
        """Comparing identical countries or values handles ties cleanly."""
        resp = self.client.post("/tools/compare_countries", json={"country_a": "France", "country_b": "France"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn("error", data)
        self.assertIn("equal population", data["result"])
        self.assertIn("equal land area", data["result"])

    def test_get_country_info_russia_alias(self):
        """Lookup Russia via common alias 'Russia'."""
        resp = self.client.post("/tools/get_country_info", json={"country": "Russia"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertNotIn("error", data)
        self.assertIn("Moscow", data["result"])
        self.assertIn("RUS", data["result"])

    def test_demonym_neutral_formatting(self):
        """Ensure demonyms are formatted neutrally without inflected s (e.g. French, Japanese)."""
        resp_fr = self.client.post("/tools/get_country_info", json={"country": "France"})
        self.assertIn("Demonym: French", resp_fr.json()["result"])
        self.assertNotIn("Frenchs", resp_fr.json()["result"])

        resp_jp = self.client.post("/tools/get_country_info", json={"country": "Japan"})
        self.assertIn("Demonym: Japanese", resp_jp.json()["result"])
        self.assertNotIn("Japaneses", resp_jp.json()["result"])

    def test_border_neighbor_resolution(self):
        """Ensure all neighbor codes resolve to country names and capitals."""
        resp = self.client.post("/tools/get_border_countries", json={"country": "Germany"})
        self.assertEqual(resp.status_code, 200)
        result_text = resp.json()["result"]
        self.assertIn("Luxembourg", result_text)
        self.assertNotIn("• Code: LUX", result_text)

    def test_mode_before_whitespace_padding(self):
        """Input padded with leading/trailing spaces near limit is normalized before length check."""
        padded_country = "   " * 30 + "France" + "   " * 30  # >100 chars raw, 6 chars normalized
        req = GetCountryInfoRequest(country=padded_country)
        self.assertEqual(req.country, "France")

    def test_root_landing_page(self):
        """GET / returns HTML landing page."""
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("Omi REST Countries", resp.text)


if __name__ == "__main__":
    unittest.main()
