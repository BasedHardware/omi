"""Hermetic type-guard tests for the USGS earthquake app (#17549).

Booleans must never be coerced into coordinates, bounds, or event IDs:
in Python ``isinstance(True, int)`` is true, so without explicit guards
``float(False) == 0.0`` silently turns ``{"latitude": False}`` into a real
geographic search, and ``int(False) == 0`` gets clamped instead of falling
back to the default.
"""

import asyncio
import sys
import types
import unittest


class DummyState:
    def __init__(self):
        self.http_client = None


class DummyFastAPI:
    def __init__(self, **_kwargs):
        self.routes = []
        self.state = DummyState()

    def get(self, path, **_kwargs):
        return self._route("GET", path)

    def post(self, path, **_kwargs):
        return self._route("POST", path)

    def _route(self, method, path):
        def decorator(func):
            self.routes.append((method, path, func))
            return func

        return decorator


class DummyBaseModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class DummyRequest:
    def __init__(self, payload=None, json_error=None):
        self.payload = payload
        self.json_error = json_error

    async def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


def install_dependency_stubs():
    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    fastapi.Request = object
    sys.modules.setdefault("fastapi", fastapi)

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel

    def field_stub(default=None, **_kwargs):
        return default

    pydantic.Field = field_stub
    sys.modules.setdefault("pydantic", pydantic)

    httpx = types.ModuleType("httpx")
    httpx.HTTPError = Exception

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def get(self, *args, **kwargs):
            raise AssertionError("network must not be touched by hermetic tests")

        async def aclose(self):
            self.is_closed = True

    httpx.AsyncClient = DummyAsyncClient
    sys.modules.setdefault("httpx", httpx)


install_dependency_stubs()
import main


class CoordinateAndTypeGuardTest(unittest.TestCase):
    def test_parse_float_rejects_booleans(self):
        self.assertIsNone(main._parse_float(True))
        self.assertIsNone(main._parse_float(False))

    def test_parse_float_still_accepts_numeric_strings(self):
        self.assertEqual(main._parse_float("12.5"), 12.5)
        self.assertEqual(main._parse_float(0), 0.0)

    def test_safe_int_returns_default_for_false(self):
        # int(False) == 0 would otherwise be clamped to minimum=1
        # instead of falling back to the 24h default.
        self.assertEqual(main._safe_int(False, default=24, minimum=1, maximum=168), 24)

    def test_safe_int_returns_default_for_true(self):
        self.assertEqual(main._safe_int(True, default=5, minimum=1, maximum=10), 5)

    def test_safe_float_returns_default_for_bool(self):
        self.assertEqual(
            main._safe_float(True, default=250.0, minimum=1.0, maximum=2000.0), 250.0
        )
        self.assertEqual(
            main._safe_float(False, default=250.0, minimum=1.0, maximum=2000.0), 250.0
        )

    def test_nearby_earthquakes_rejects_boolean_coordinates(self):
        response = asyncio.run(
            main.tool_nearby_earthquakes(
                DummyRequest({"latitude": False, "longitude": True})
            )
        )
        self.assertFalse(response.success)
        self.assertEqual(response.message, "latitude and longitude are required")

    def test_earthquake_details_rejects_boolean_event_id(self):
        response = asyncio.run(
            main.tool_earthquake_details(DummyRequest({"event_id": True}))
        )
        self.assertFalse(response.success)
        self.assertEqual(response.message, "event_id is required")


if __name__ == "__main__":
    unittest.main()
