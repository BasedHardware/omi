"""Hermetic unit tests for REST Countries & Global World Info Omi integration.

No third-party runtime dependencies required. Runs deterministically under
both standard library `python3 -S` and `pytest`.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


def load_app():
    class DummyState:
        pass

    class DummyFastAPI:
        def __init__(self, **kwargs):
            self.routes = []
            self.lifespan = kwargs.get("lifespan")
            self.state = DummyState()

        def get(self, path, **kwargs):
            return self._route("GET", path, kwargs.get("response_model"))

        def post(self, path, **kwargs):
            return self._route("POST", path, kwargs.get("response_model"))

        def exception_handler(self, exc_class):
            def decorator(func):
                return func

            return decorator

        def _route(self, method, path, response_model):
            def decorator(func):
                self.routes.append({
                    "method": method,
                    "path": path,
                    "func": func,
                    "response_model": response_model,
                })
                return func

            return decorator

    class DummyBaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def Field(default=None, **_kwargs):
        return default

    def field_validator(*_args, **_kwargs):
        def decorator(func):
            return func

        return decorator

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message=None, response=None):
            super().__init__(message)
            self.response = response or types.SimpleNamespace(status_code=500, text="Internal Server Error")

    class TimeoutException(HTTPError):
        pass

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            self.is_closed = True

        async def aclose(self):
            self.is_closed = True

        async def get(self, url, params=None):
            raise NotImplementedError

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    fastapi.Request = object
    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = str
    fastapi_responses.JSONResponse = dict
    fastapi_exceptions = types.ModuleType("fastapi.exceptions")

    class RequestValidationError(Exception):
        pass

    fastapi_exceptions.RequestValidationError = RequestValidationError

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel
    pydantic.Field = Field
    pydantic.field_validator = field_validator

    httpx = types.ModuleType("httpx")
    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.TimeoutException = TimeoutException
    httpx.AsyncClient = DummyAsyncClient

    models_spec = importlib.util.spec_from_file_location("models", Path(__file__).with_name("models.py"))
    models_mod = importlib.util.module_from_spec(models_spec)

    main_spec = importlib.util.spec_from_file_location("countries_app_hermetic", Path(__file__).with_name("main.py"))
    main_mod = importlib.util.module_from_spec(main_spec)

    with patch.dict(
        sys.modules,
        {
            "fastapi": fastapi,
            "fastapi.responses": fastapi_responses,
            "fastapi.exceptions": fastapi_exceptions,
            "pydantic": pydantic,
            "httpx": httpx,
            "models": models_mod,
        },
    ):
        models_spec.loader.exec_module(models_mod)
        main_spec.loader.exec_module(main_mod)
    return main_mod, models_mod


main, models = load_app()


def _run(coro):
    return asyncio.run(coro)


class RouteRegistrationTests(unittest.TestCase):
    def test_routes_registered_with_correct_methods_and_paths(self):
        registered = {(r["method"], r["path"]): r for r in main.app.routes}
        expected_endpoints = {
            ("GET", "/"),
            ("GET", "/health"),
            ("GET", "/privacy"),
            ("GET", "/manifest.json"),
            ("GET", "/.well-known/ai-plugin.json"),
            ("POST", "/tools/country_overview"),
            ("POST", "/tools/search_by_capital"),
            ("POST", "/tools/search_by_currency"),
            ("POST", "/tools/search_by_language"),
        }
        for endpoint in expected_endpoints:
            self.assertIn(endpoint, registered, f"Endpoint {endpoint} was not registered")


class FormattingHelperTests(unittest.TestCase):
    def test_format_population(self):
        self.assertEqual(main._format_population(125800000), "125,800,000")
        self.assertEqual(main._format_population(0), "0")
        self.assertEqual(main._format_population(None), "Unknown")

    def test_format_currencies(self):
        cur = {"JPY": {"name": "Japanese yen", "symbol": "¥"}}
        self.assertEqual(main._format_currencies(cur), "Japanese yen (¥, JPY)")
        self.assertEqual(main._format_currencies({}), "Not available")
        self.assertEqual(main._format_currencies(None), "Not available")

    def test_format_languages(self):
        langs = {"jpn": "Japanese", "eng": "English"}
        self.assertEqual(main._format_languages(langs), "Japanese, English")
        self.assertEqual(main._format_languages({}), "Not available")
        self.assertEqual(main._format_languages(None), "Not available")


class ToolEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.sample_japan = {
            "name": {"common": "Japan", "official": "Japan"},
            "flag": "🇯🇵",
            "capital": ["Tokyo"],
            "region": "Asia",
            "subregion": "Eastern Asia",
            "population": 125800000,
            "currencies": {"JPY": {"name": "Japanese yen", "symbol": "¥"}},
            "languages": {"jpn": "Japanese"},
            "borders": [],
            "timezones": ["UTC+09:00"],
            "maps": {"googleMaps": "https://goo.gl/maps/japan"},
        }

        self.sample_germany = {
            "name": {"common": "Germany", "official": "Federal Republic of Germany"},
            "flag": "🇩🇪",
            "capital": ["Berlin"],
            "region": "Europe",
            "subregion": "Western Europe",
            "population": 83240525,
            "currencies": {"EUR": {"name": "Euro", "symbol": "€"}},
            "languages": {"deu": "German"},
            "borders": ["AUT", "BEL", "CZE", "DNK", "FRA", "LUX", "NLD", "POL", "CHE"],
            "timezones": ["UTC+01:00"],
            "maps": {"googleMaps": "https://goo.gl/maps/germany"},
        }

    def test_country_overview_by_name(self):
        with patch.object(main, "_query_rest_countries", new=AsyncMock(return_value=[self.sample_japan])):
            req = models.CountryOverviewRequest(country="Japan")
            res = _run(main.country_overview(req))
            self.assertIsNone(res.error)
            self.assertIn("### 🇯🇵 Japan", res.result)
            self.assertIn("Tokyo", res.result)
            self.assertIn("125,800,000", res.result)
            self.assertIn("Japanese yen (¥, JPY)", res.result)
            self.assertIn("None (Island / Territory)", res.result)

    def test_country_overview_by_code(self):
        with patch.object(main, "_query_rest_countries", new=AsyncMock(return_value=[self.sample_germany])):
            req = models.CountryOverviewRequest(country="DE")
            res = _run(main.country_overview(req))
            self.assertIsNone(res.error)
            self.assertIn("### 🇩🇪 Germany", res.result)
            self.assertIn("Berlin", res.result)
            self.assertIn("AUT, BEL, CZE", res.result)

    def test_country_overview_not_found(self):
        with patch.object(main, "_query_rest_countries", new=AsyncMock(return_value={"not_found": True})):
            req = models.CountryOverviewRequest(country="Atlantis")
            res = _run(main.country_overview(req))
            self.assertIsNone(res.error)
            self.assertIn("No country found matching 'Atlantis'", res.result)

    def test_country_overview_error(self):
        with patch.object(main, "_query_rest_countries", new=AsyncMock(return_value={"error": "API down"})):
            req = models.CountryOverviewRequest(country="Japan")
            res = _run(main.country_overview(req))
            self.assertEqual(res.error, "API down")
            self.assertIsNone(res.result)

    def test_search_by_capital_success(self):
        with patch.object(main, "_query_rest_countries", new=AsyncMock(return_value=[self.sample_japan])):
            req = models.CapitalSearchRequest(capital="Tokyo")
            res = _run(main.search_by_capital(req))
            self.assertIsNone(res.error)
            self.assertIn("### 🇯🇵 Japan", res.result)
            self.assertIn("Tokyo", res.result)

    def test_search_by_capital_not_found(self):
        with patch.object(main, "_query_rest_countries", new=AsyncMock(return_value={"not_found": True})):
            req = models.CapitalSearchRequest(capital="NonexistentCity")
            res = _run(main.search_by_capital(req))
            self.assertIsNone(res.error)
            self.assertIn("No country found with capital city 'NonexistentCity'", res.result)

    def test_search_by_currency_success(self):
        countries = [self.sample_germany] * 12
        with patch.object(main, "_query_rest_countries", new=AsyncMock(return_value=countries)):
            req = models.CurrencySearchRequest(currency="EUR", limit=5)
            res = _run(main.search_by_currency(req))
            self.assertIsNone(res.error)
            self.assertIn("Countries using currency 'EUR' (12 total):", res.result)
            self.assertIn("- 🇩🇪 **Germany**", res.result)
            self.assertIn("and 7 more countries", res.result)

    def test_search_by_currency_not_found(self):
        with patch.object(main, "_query_rest_countries", new=AsyncMock(return_value={"not_found": True})):
            req = models.CurrencySearchRequest(currency="FAKECOIN")
            res = _run(main.search_by_currency(req))
            self.assertIsNone(res.error)
            self.assertIn("No countries found using currency 'FAKECOIN'", res.result)

    def test_search_by_language_success(self):
        countries = [self.sample_japan]
        with patch.object(main, "_query_rest_countries", new=AsyncMock(return_value=countries)):
            req = models.LanguageSearchRequest(language="Japanese", limit=10)
            res = _run(main.search_by_language(req))
            self.assertIsNone(res.error)
            self.assertIn("Countries speaking 'Japanese' (1 total):", res.result)
            self.assertIn("- 🇯🇵 **Japan** (Capital: Tokyo)", res.result)

    def test_search_by_language_not_found(self):
        with patch.object(main, "_query_rest_countries", new=AsyncMock(return_value={"not_found": True})):
            req = models.LanguageSearchRequest(language="Klingon")
            res = _run(main.search_by_language(req))
            self.assertIsNone(res.error)
            self.assertIn("No countries found with official language 'Klingon'", res.result)


class MetadataEndpointsTests(unittest.TestCase):
    def test_index_html(self):
        html_content = _run(main.index())
        self.assertIn("REST Countries & World Info for Omi", html_content)
        self.assertIn("POST /tools/country_overview", html_content)

    def test_health_json(self):
        data = _run(main.health())
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "omi-countries-info-app")

    def test_privacy_json(self):
        data = _run(main.privacy())
        self.assertIn("privacy_policy", data)

    def test_manifest_json(self):
        data = _run(main.plugin_manifest())
        self.assertEqual(data["schema_version"], "v1")
        self.assertEqual(data["name_for_model"], "countries_world_info")


if __name__ == "__main__":
    unittest.main()
