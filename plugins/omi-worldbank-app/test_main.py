"""Unit tests for Omi World Bank Global Economic Intelligence App."""

import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


def install_dependency_stubs():
    """Install stubs for third-party libraries if they are not installed in the environment."""
    if "fastapi" not in sys.modules:
        try:
            import fastapi  # noqa: F401
        except ImportError:
            fastapi = types.ModuleType("fastapi")

            class DummyState:
                pass

            class DummyFastAPI:
                def __init__(self, **_kwargs):
                    self.routes = []
                    self.exception_handlers = {}
                    self.state = DummyState()

                def get(self, path, **_kwargs):
                    return self._route("GET", path)

                def post(self, path, **_kwargs):
                    return self._route("POST", path)

                def exception_handler(self, exc_class):
                    def decorator(func):
                        self.exception_handlers[exc_class] = func
                        return func
                    return decorator

                def middleware(self, middleware_type):
                    def decorator(func):
                        return func
                    return decorator

                def _route(self, method, path):
                    def decorator(func):
                        self.routes.append((method, path, func))
                        return func
                    return decorator

            fastapi.FastAPI = DummyFastAPI
            fastapi.Request = object
            fastapi.__path__ = []

            exceptions = types.ModuleType("fastapi.exceptions")

            class DummyRequestValidationError(Exception):
                pass

            exceptions.RequestValidationError = DummyRequestValidationError
            sys.modules["fastapi.exceptions"] = exceptions
            fastapi.exceptions = exceptions

            responses = types.ModuleType("fastapi.responses")

            class DummyResponse:
                def __init__(self, content, status_code=200, media_type=None):
                    self.content = content
                    self.status_code = status_code
                    self.media_type = media_type

            responses.HTMLResponse = DummyResponse
            responses.JSONResponse = DummyResponse
            fastapi.responses = responses
            sys.modules["fastapi"] = fastapi
            sys.modules["fastapi.responses"] = responses

    if "pydantic" not in sys.modules:
        try:
            import pydantic  # noqa: F401
        except ImportError:
            pydantic = types.ModuleType("pydantic")

            class DummyBaseModel:
                def __init__(self, **kwargs):
                    for k, v in kwargs.items():
                        setattr(self, k, v)

                def model_dump(self, **kwargs):
                    return {
                        k: v for k, v in self.__dict__.items()
                        if not k.startswith("_")
                    }

            def DummyField(*args, default=None, **kwargs):
                if args and args[0] is not ...:
                    return args[0]
                return default

            def dummy_decorator(*args, **kwargs):
                def wrapper(f):
                    return f
                return wrapper

            pydantic.BaseModel = DummyBaseModel
            pydantic.Field = DummyField
            pydantic.field_validator = dummy_decorator
            pydantic.model_validator = dummy_decorator
            sys.modules["pydantic"] = pydantic

    if "httpx" not in sys.modules:
        try:
            import httpx  # noqa: F401
        except ImportError:
            httpx = types.ModuleType("httpx")
            httpx.HTTPError = Exception
            httpx.RequestError = Exception
            httpx.TimeoutException = Exception

            class DummyAsyncClient:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, *args):
                    pass

                async def get(self, *args, **kwargs):
                    raise NotImplementedError

            httpx.AsyncClient = DummyAsyncClient
            sys.modules["httpx"] = httpx


install_dependency_stubs()

import main  # noqa: E402
import models  # noqa: E402


class WorldBankAppUnitTests(unittest.TestCase):
    """Unit test suite covering World Bank Omi integration app."""

    def test_manifest_structure(self):
        """Verify the Omi tools manifest meets the protocol specifications."""
        manifest = asyncio.run(main.get_manifest())

        self.assertIn("tools", manifest)
        tools = manifest["tools"]
        self.assertEqual(len(tools), 4)

        tool_names = {t["name"] for t in tools}
        expected_names = {
            "get_country_profile",
            "get_economic_indicator",
            "compare_country_economies",
            "search_countries_by_region",
        }
        self.assertEqual(tool_names, expected_names)

        for tool in tools:
            self.assertFalse(tool["auth_required"])
            self.assertTrue(tool["endpoint"].startswith("/tools/"))
            self.assertIn("description", tool)
            self.assertIn("parameters", tool)
            self.assertIn("status_message", tool)

    def test_country_alias_resolver(self):
        """Verify country name and ISO alias resolution."""
        self.assertEqual(asyncio.run(main._resolve_country_code("US"))[0], "USA")
        self.assertEqual(asyncio.run(main._resolve_country_code("united states"))[0], "USA")
        self.assertEqual(asyncio.run(main._resolve_country_code("america"))[0], "USA")
        self.assertEqual(asyncio.run(main._resolve_country_code("UK"))[0], "GBR")
        self.assertEqual(asyncio.run(main._resolve_country_code("britain"))[0], "GBR")
        self.assertEqual(asyncio.run(main._resolve_country_code("united kingdom"))[0], "GBR")
        self.assertEqual(asyncio.run(main._resolve_country_code("germany"))[0], "DEU")
        self.assertEqual(asyncio.run(main._resolve_country_code("india"))[0], "IND")
        self.assertEqual(asyncio.run(main._resolve_country_code("japan"))[0], "JPN")
        self.assertEqual(asyncio.run(main._resolve_country_code("china"))[0], "CHN")
        self.assertEqual(asyncio.run(main._resolve_country_code("france"))[0], "FRA")
        self.assertEqual(asyncio.run(main._resolve_country_code("brazil"))[0], "BRA")

        # Fallback to uppercase 3-letter code
        self.assertEqual(asyncio.run(main._resolve_country_code("CAN"))[0], "CAN")
        self.assertEqual(asyncio.run(main._resolve_country_code("mex"))[0], "MEX")

    def test_number_formatting(self):
        """Verify numerical formatting handles trillions, billions, millions, and percentages."""
        self.assertEqual(main._format_compact(27360000000000), "$27.36T")
        self.assertEqual(main._format_compact(1420000000, currency_prefix=""), "1.42B")
        self.assertEqual(main._format_compact(35500000, currency_prefix=""), "35.50M")
        self.assertEqual(main._format_compact(81695.2), "$81.70K")
        self.assertEqual(main._format_compact(None), "N/A")

        self.assertEqual(main._format_percent(3.41), "+3.41%")
        self.assertEqual(main._format_percent(-1.20), "-1.20%")
        self.assertEqual(main._format_percent(None), "N/A")

    @patch("main._fetch_country_metadata", new_callable=AsyncMock)
    @patch("main._fetch_indicator_value", new_callable=AsyncMock)
    def test_country_profile_success(self, mock_ind, mock_meta):
        """Verify country profile returns synthesized text."""
        mock_meta.return_value = {
            "id": "USA",
            "iso2Code": "US",
            "name": "United States",
            "region": {"value": "North America"},
            "incomeLevel": {"value": "High income"},
            "capitalCity": "Washington, D.C.",
            "longitude": "-77.032",
            "latitude": "38.8895",
        }
        mock_ind.return_value = [{"date": "2023", "value": 27360935000000}]

        req = models.CountryProfileRequest(country="USA")
        resp = asyncio.run(main.get_country_profile(req))

        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("United States", resp.result)
        self.assertIn("Washington, D.C.", resp.result)
        self.assertIn("North America", resp.result)

    @patch("main._fetch_indicator_value", new_callable=AsyncMock)
    def test_economic_indicator_success(self, mock_ind):
        """Verify single indicator query returns historical trend."""
        mock_ind.return_value = [
            {"date": "2023", "value": 3.4},
            {"date": "2022", "value": 8.0},
            {"date": "2021", "value": 4.7},
        ]

        req = models.EconomicIndicatorRequest(country="USA", indicator="inflation", years=3)
        resp = asyncio.run(main.get_economic_indicator(req))

        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("INFLATION", resp.result.upper())
        self.assertIn("2023", resp.result)
        self.assertIn("3.40%", resp.result)

    def test_unknown_indicator_returns_helpful_error(self):
        """Verify unknown indicator returns available indicators list."""
        req = models.EconomicIndicatorRequest(country="USA", indicator="crypto_yield")
        resp = asyncio.run(main.get_economic_indicator(req))

        self.assertIsNone(resp.result)
        self.assertIsNotNone(resp.error)
        self.assertIn("Unsupported indicator", resp.error)
        self.assertIn("gdp", resp.error)
        self.assertIn("inflation", resp.error)

    @patch("main._fetch_country_metadata", new_callable=AsyncMock)
    @patch("main._fetch_indicator_value", new_callable=AsyncMock)
    def test_compare_economies(self, mock_ind, mock_meta):
        """Verify economy comparison tool compares 2 nations."""
        mock_meta.side_effect = [
            {"id": "USA", "name": "United States", "region": {"value": "North America"}, "incomeLevel": {"value": "High income"}},
            {"id": "IND", "name": "India", "region": {"value": "South Asia"}, "incomeLevel": {"value": "Lower middle income"}},
        ]

        mock_ind.side_effect = [
            [{"date": "2023", "value": 27360000000000}],  # USA GDP
            [{"date": "2023", "value": 3550000000000}],   # IND GDP
            [{"date": "2023", "value": 81695}],           # USA GDP/cap
            [{"date": "2023", "value": 2484}],            # IND GDP/cap
            [{"date": "2023", "value": 3.4}],             # USA Inf
            [{"date": "2023", "value": 5.4}],             # IND Inf
            [{"date": "2023", "value": 334914895}],       # USA Pop
            [{"date": "2023", "value": 1428627663}],      # IND Pop
            [{"date": "2023", "value": 77.5}],            # USA Life
            [{"date": "2023", "value": 67.2}],            # IND Life
        ]

        req = models.CompareEconomiesRequest(country_a="USA", country_b="IND")
        resp = asyncio.run(main.compare_country_economies(req))

        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("United States", resp.result)
        self.assertIn("India", resp.result)
        self.assertIn("GDP", resp.result)

    def test_compare_economies_requires_different_countries(self):
        """Verify compare economies rejects comparing a country to itself."""
        req = models.CompareEconomiesRequest(country_a="USA", country_b="USA")
        resp = asyncio.run(main.compare_country_economies(req))

        self.assertIsNone(resp.result)
        self.assertIsNotNone(resp.error)
        self.assertIn("Cannot compare a country to itself", resp.error)

    def test_search_countries_matching(self):
        """Verify country search filters cached countries."""
        main.app.state.country_cache = [
            {
                "id": "USA",
                "iso2Code": "US",
                "name": "United States",
                "capitalCity": "Washington, D.C.",
                "region": {"value": "North America"},
                "incomeLevel": {"value": "High income"},
            },
            {
                "id": "ARE",
                "iso2Code": "AE",
                "name": "United Arab Emirates",
                "capitalCity": "Abu Dhabi",
                "region": {"value": "Middle East & North Africa"},
                "incomeLevel": {"value": "High income"},
            },
            {
                "id": "GBR",
                "iso2Code": "GB",
                "name": "United Kingdom",
                "capitalCity": "London",
                "region": {"value": "Europe & Central Asia"},
                "incomeLevel": {"value": "High income"},
            },
        ]

        req = models.SearchCountriesRequest(query="United")
        resp = asyncio.run(main.search_countries(req))

        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("United States", resp.result)
        self.assertIn("USA", resp.result)
        self.assertIn("United Kingdom", resp.result)


if __name__ == "__main__":
    unittest.main()
