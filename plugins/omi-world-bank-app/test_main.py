"""Hermetic unit tests for World Bank Economic Indicators Omi integration.

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

    main_spec = importlib.util.spec_from_file_location("world_bank_app_hermetic", Path(__file__).with_name("main.py"))
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
            ("POST", "/tools/economic_snapshot"),
            ("POST", "/tools/indicator_history"),
            ("POST", "/tools/compare_indicator"),
        }
        for endpoint in expected_endpoints:
            self.assertIn(endpoint, registered, f"Endpoint {endpoint} was not registered")


class HelperFunctionTests(unittest.TestCase):
    def test_resolve_country_code(self):
        self.assertEqual(main._resolve_country_code("United States"), "USA")
        self.assertEqual(main._resolve_country_code("china"), "CHN")
        self.assertEqual(main._resolve_country_code("de"), "DE")
        self.assertEqual(main._resolve_country_code("IND"), "IND")

    def test_resolve_indicator(self):
        key, meta = main._resolve_indicator("gdp")
        self.assertEqual(key, "gdp")
        self.assertEqual(meta["id"], "NY.GDP.MKTP.CD")

        key2, meta2 = main._resolve_indicator("inflation")
        self.assertEqual(key2, "inflation")
        self.assertEqual(meta2["unit"], "%")

    def test_format_value_currency(self):
        self.assertEqual(main._format_value(27360000000000, "currency"), "$27.36 Trillion")
        self.assertEqual(main._format_value(4120000000, "currency"), "$4.12 Billion")
        self.assertEqual(main._format_value(500000, "currency"), "$500,000.00")

    def test_format_value_number(self):
        self.assertEqual(main._format_value(1420000000, "number"), "1.42 Billion")
        self.assertEqual(main._format_value(334900000, "number"), "334.90 Million")
        self.assertEqual(main._format_value(50000, "number"), "50,000")

    def test_format_value_percent_and_decimal(self):
        self.assertEqual(main._format_value(3.245, "percent"), "3.25%")
        self.assertEqual(main._format_value(77.567, "decimal"), "77.57")
        self.assertEqual(main._format_value(None, "decimal"), "N/A")


class ToolEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.sample_gdp_response = [
            {"page": 1, "pages": 1, "total": 3},
            [
                {
                    "indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP"},
                    "country": {"id": "US", "value": "United States"},
                    "date": "2023",
                    "value": 27360935000000,
                },
                {
                    "indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP"},
                    "country": {"id": "US", "value": "United States"},
                    "date": "2022",
                    "value": 25744108000000,
                },
            ],
        ]

        self.sample_china_gdp_response = [
            {"page": 1, "pages": 1, "total": 2},
            [
                {
                    "indicator": {"id": "NY.GDP.MKTP.CD", "value": "GDP"},
                    "country": {"id": "CN", "value": "China"},
                    "date": "2023",
                    "value": 17794782000000,
                },
            ],
        ]

        self.sample_pop_response = [
            {"page": 1, "pages": 1, "total": 1},
            [
                {
                    "indicator": {"id": "SP.POP.TOTL", "value": "Population"},
                    "country": {"id": "US", "value": "United States"},
                    "date": "2023",
                    "value": 334914895,
                },
            ],
        ]

    def test_economic_snapshot_success(self):
        async def mock_fetch(country, ind, per_page=3, client=None):
            if ind == "NY.GDP.MKTP.CD":
                return self.sample_gdp_response
            if ind == "SP.POP.TOTL":
                return self.sample_pop_response
            return [{"page": 1}, [{"date": "2023", "value": 3.4}]]

        with patch.object(main, "_fetch_indicator_data", new=mock_fetch):
            req = models.EconomicSnapshotRequest(country="United States")
            res = _run(main.economic_snapshot(req))
            self.assertIsNone(res.error)
            self.assertIn("Economic Snapshot: United States (USA)", res.result)
            self.assertIn("$27.36 Trillion (2023)", res.result)
            self.assertIn("334.91 Million (2023)", res.result)

    def test_economic_snapshot_not_found(self):
        with patch.object(main, "_fetch_indicator_data", new=AsyncMock(return_value=[{"page": 1}, []])):
            req = models.EconomicSnapshotRequest(country="Atlantis")
            res = _run(main.economic_snapshot(req))
            self.assertIsNone(res.error)
            self.assertIn("No economic data found for country 'Atlantis'", res.result)

    def test_economic_snapshot_upstream_error(self):
        with patch.object(main, "_fetch_indicator_data", new=AsyncMock(return_value={"error": "API unreachable"})):
            req = models.EconomicSnapshotRequest(country="US")
            res = _run(main.economic_snapshot(req))
            self.assertEqual(res.error, "API unreachable")
            self.assertIsNone(res.result)

    def test_indicator_history_success(self):
        with patch.object(main, "_fetch_indicator_data", new=AsyncMock(return_value=self.sample_gdp_response)):
            req = models.IndicatorHistoryRequest(country="US", indicator="gdp", years=2)
            res = _run(main.indicator_history(req))
            self.assertIsNone(res.error)
            self.assertIn("Gross Domestic Product (GDP) — United States", res.result)
            self.assertIn("- **2023**: $27.36 Trillion", res.result)
            self.assertIn("- **2022**: $25.74 Trillion", res.result)

    def test_indicator_history_empty(self):
        with patch.object(main, "_fetch_indicator_data", new=AsyncMock(return_value=[{"page": 1}, []])):
            req = models.IndicatorHistoryRequest(country="FakeCountry", indicator="inflation")
            res = _run(main.indicator_history(req))
            self.assertIsNone(res.error)
            self.assertIn("No Inflation Rate (CPI) data found", res.result)

    def test_compare_indicator_success(self):
        async def mock_fetch_compare(country, ind, per_page=3, client=None):
            if country == "USA":
                return self.sample_gdp_response
            return self.sample_china_gdp_response

        with patch.object(main, "_fetch_indicator_data", new=mock_fetch_compare):
            req = models.CompareIndicatorRequest(country_a="US", country_b="China", indicator="gdp")
            res = _run(main.compare_indicator(req))
            self.assertIsNone(res.error)
            self.assertIn("Comparison: Gross Domestic Product (GDP)", res.result)
            self.assertIn("- **United States (USA)**: $27.36 Trillion (2023)", res.result)
            self.assertIn("- **China (CHN)**: $17.79 Trillion (2023)", res.result)

    def test_compare_indicator_error(self):
        with patch.object(main, "_fetch_indicator_data", new=AsyncMock(return_value={"error": "Country A down"})):
            req = models.CompareIndicatorRequest(country_a="US", country_b="China", indicator="gdp")
            res = _run(main.compare_indicator(req))
            self.assertEqual(res.error, "Country A down")
            self.assertIsNone(res.result)


class MetadataEndpointsTests(unittest.TestCase):
    def test_index_html(self):
        html_content = _run(main.index())
        self.assertIn("World Bank Economic Indicators for Omi", html_content)
        self.assertIn("POST /tools/economic_snapshot", html_content)

    def test_health_json(self):
        data = _run(main.health())
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "omi-world-bank-app")

    def test_privacy_json(self):
        data = _run(main.privacy())
        self.assertIn("privacy_policy", data)

    def test_manifest_json(self):
        data = _run(main.plugin_manifest())
        self.assertEqual(data["schema_version"], "v1")
        self.assertEqual(data["name_for_model"], "world_bank_indicators")


if __name__ == "__main__":
    unittest.main()
