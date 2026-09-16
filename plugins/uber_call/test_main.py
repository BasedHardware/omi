"""Hermetic regression tests for plugins/uber_call/main.py.

Standard library only: fastapi and pydantic are stubbed when not installed so
the suite executes cleanly without external site-packages (under python3 -S).
"""

from __future__ import annotations

from pathlib import Path
import sys
import types
import unittest

if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class HTTPException(Exception):
            def __init__(self, status_code: int, detail: str = ""):
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.routes = {}

            def get(self, path: str, *args, **kwargs):
                def decorator(fn):
                    self.routes[("GET", path)] = fn
                    return fn
                return decorator

            def post(self, path: str, *args, **kwargs):
                def decorator(fn):
                    self.routes[("POST", path)] = fn
                    return fn
                return decorator

        fastapi.HTTPException = HTTPException
        fastapi.FastAPI = FastAPI
        sys.modules["fastapi"] = fastapi

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        def Field(default=None, **kwargs):
            return default

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        sys.modules["pydantic"] = pydantic

PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import main


class CallUberEndpointTests(unittest.TestCase):
    def test_health_endpoint(self):
        self.assertEqual(main.health(), {"status": "ok"})

    def test_manifest_parameters_are_json_schema_object(self):
        manifest = main.omi_tools_manifest()
        self.assertIn("tools", manifest)
        self.assertEqual(len(manifest["tools"]), 1)
        tool = manifest["tools"][0]
        self.assertEqual(tool["name"], "call_uber")
        parameters = tool["parameters"]
        self.assertEqual(parameters["type"], "object")
        self.assertIn("destination", parameters["required"])

    def test_valid_call_uber_generates_links(self):
        req = main.CallUberRequest(
            destination="SFO Airport",
            pickup_address="1455 Market St",
            pickup_latitude=37.775818,
            pickup_longitude=-122.418028,
        )
        res = main.call_uber(req)
        self.assertIn("result", res)
        self.assertIn("web_link", res)
        self.assertIn("app_link", res)
        self.assertIn("action=setPickup", res["web_link"])
        self.assertIn("dropoff[formatted_address]=SFO%20Airport", res["web_link"])

    def test_call_uber_with_geolocation(self):
        req = main.CallUberRequest(
            destination="Downtown",
            geolocation={"latitude": 37.77, "longitude": -122.41, "address": "Market St"},
        )
        res = main.call_uber(req)
        self.assertIn("Downtown", res["result"])
        self.assertIn("pickup[latitude]=37.77", res["web_link"])

    def test_missing_destination_and_dropoff_raises_400(self):
        req = main.CallUberRequest(destination=None)
        with self.assertRaises(main.HTTPException) as cm:
            main.call_uber(req)
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("A destination or dropoff location is required", cm.exception.detail)

    def test_invalid_coordinates_raise_400(self):
        req = main.CallUberRequest(
            destination="SFO",
            pickup_latitude=95.0,
            pickup_longitude=0.0,
        )
        with self.assertRaises(main.HTTPException) as cm:
            main.call_uber(req)
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("Invalid coordinates", cm.exception.detail)

    def test_bad_geolocation_type_raises_400(self):
        req = main.CallUberRequest(
            destination="SFO Airport",
            geolocation={"latitude": "nearby", "longitude": "-122.418028"},
        )
        with self.assertRaises(main.HTTPException) as cm:
            main.call_uber(req)
        self.assertEqual(cm.exception.status_code, 400)
        self.assertIn("could not convert string to float", cm.exception.detail)


if __name__ == "__main__":
    unittest.main()
