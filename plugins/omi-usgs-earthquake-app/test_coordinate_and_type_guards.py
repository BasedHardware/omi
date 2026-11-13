"""Hermetic regression tests for USGS Earthquake coordinate and type guards.

Tests:
1. _parse_float rejects boolean values (preventing boolean False/True from bypassing coordinate validation as 0.0/1.0)
2. _safe_int and _safe_float fall back to default for boolean inputs
3. tool_nearby_earthquakes rejects boolean coordinates with required error
4. tool_earthquake_details rejects boolean event_id with required error
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

PLUGIN_DIR = Path(__file__).resolve().parent
MAIN_FILE = PLUGIN_DIR / "main.py"


def _load_main_module():
    sys.path.insert(0, str(PLUGIN_DIR))

    # Minimal stubs if dependencies are missing
    for mod_name in ["fastapi", "httpx"]:
        if mod_name not in sys.modules:
            try:
                __import__(mod_name)
            except Exception:
                stub = types.ModuleType(mod_name)
                if mod_name == "fastapi":
                    class DummyFastAPI:
                        def __init__(self, *args, **kwargs):
                            pass
                        def get(self, *args, **kwargs):
                            return lambda f: f
                        post = get
                    stub.FastAPI = DummyFastAPI
                    stub.Request = object
                elif mod_name == "httpx":
                    class DummyAsyncClient:
                        def __init__(self, *args, **kwargs):
                            pass
                        async def aclose(self):
                            pass
                    stub.AsyncClient = DummyAsyncClient
                    class HTTPError(Exception):
                        pass
                    stub.HTTPError = HTTPError
                sys.modules[mod_name] = stub

    spec = importlib.util.spec_from_file_location("usgs_main", str(MAIN_FILE))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


main = _load_main_module()


class DummyRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    async def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


class UsgsCoordinateAndTypeGuardTests(unittest.TestCase):
    def test_parse_float_booleans_rejected(self):
        # Crucial: False must NOT evaluate to 0.0 and True must NOT evaluate to 1.0
        self.assertIsNone(main._parse_float(False))
        self.assertIsNone(main._parse_float(True))
        self.assertIsNone(main._parse_float(None))
        self.assertIsNone(main._parse_float("invalid"))

    def test_parse_float_valid_numbers(self):
        self.assertEqual(main._parse_float(0.0), 0.0)
        self.assertEqual(main._parse_float(0), 0.0)
        self.assertEqual(main._parse_float("37.77"), 37.77)
        self.assertEqual(main._parse_float("-122.41"), -122.41)

    def test_safe_int_booleans_fallback_to_default(self):
        self.assertEqual(main._safe_int(False, default=24, minimum=1, maximum=168), 24)
        self.assertEqual(main._safe_int(True, default=24, minimum=1, maximum=168), 24)
        self.assertEqual(main._safe_int(None, default=24, minimum=1, maximum=168), 24)
        self.assertEqual(main._safe_int("invalid", default=24, minimum=1, maximum=168), 24)
        self.assertEqual(main._safe_int(48, default=24, minimum=1, maximum=168), 48)

    def test_safe_float_booleans_fallback_to_default(self):
        self.assertEqual(main._safe_float(False, default=250.0, minimum=1.0, maximum=2000.0), 250.0)
        self.assertEqual(main._safe_float(True, default=250.0, minimum=1.0, maximum=2000.0), 250.0)
        self.assertEqual(main._safe_float(None, default=250.0, minimum=1.0, maximum=2000.0), 250.0)


class UsgsEndpointGuardTests(unittest.TestCase):
    def test_nearby_earthquakes_boolean_coords_rejected(self):
        # Both boolean
        req = DummyRequest({"latitude": False, "longitude": True})
        resp = asyncio.run(main.tool_nearby_earthquakes(req))
        self.assertFalse(resp.success)
        self.assertEqual(resp.message, "latitude and longitude are required")

        # One boolean
        req2 = DummyRequest({"latitude": 37.77, "longitude": False})
        resp2 = asyncio.run(main.tool_nearby_earthquakes(req2))
        self.assertFalse(resp2.success)
        self.assertEqual(resp2.message, "latitude and longitude are required")

        req3 = DummyRequest({"latitude": True, "longitude": -122.41})
        resp3 = asyncio.run(main.tool_nearby_earthquakes(req3))
        self.assertFalse(resp3.success)
        self.assertEqual(resp3.message, "latitude and longitude are required")

    def test_earthquake_details_boolean_event_id_rejected(self):
        req_true = DummyRequest({"event_id": True})
        resp_true = asyncio.run(main.tool_earthquake_details(req_true))
        self.assertFalse(resp_true.success)
        self.assertEqual(resp_true.message, "event_id is required")

        req_false = DummyRequest({"event_id": False})
        resp_false = asyncio.run(main.tool_earthquake_details(req_false))
        self.assertFalse(resp_false.success)
        self.assertEqual(resp_false.message, "event_id is required")

    def test_recent_earthquakes_boolean_filters_use_defaults(self):
        # Should not crash or clamp False to 1 hour; should run with defaults
        req = DummyRequest({"hours": False, "limit": False, "min_magnitude": False})
        with patch.object(main, "_list_earthquakes", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = {"count": 0, "earthquakes": [], "data_note": ""}
            resp = asyncio.run(main.tool_recent_earthquakes(req))
            self.assertTrue(resp.success)
            args = mock_list.call_args[0][0]
            self.assertEqual(args["limit"], 5)
            self.assertEqual(args["minmagnitude"], 2.5)


if __name__ == "__main__":
    unittest.main()
