import asyncio
import math
import sys
import types
import unittest
from datetime import datetime, timezone


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
            raise NotImplementedError

        async def aclose(self):
            self.is_closed = True

    httpx.AsyncClient = DummyAsyncClient
    sys.modules.setdefault("httpx", httpx)


install_dependency_stubs()
import main


class UsgsEarthquakeAppTest(unittest.TestCase):
    def test_manifest_exposes_expected_no_auth_tools(self):
        manifest = asyncio.run(main.get_omi_tools_manifest())

        tools = manifest["tools"]
        tool_names = {tool["name"] for tool in tools}
        self.assertEqual(
            tool_names,
            {
                "recent_earthquakes",
                "nearby_earthquakes",
                "earthquake_details",
            },
        )
        self.assertTrue(all(tool["auth_required"] is False for tool in tools))

    def test_manifest_alias_matches_manifest(self):
        alias = asyncio.run(main.get_manifest_alias())
        canonical = asyncio.run(main.get_omi_tools_manifest())
        self.assertEqual(alias, canonical)

    def test_health_check_returns_ok(self):
        health = asyncio.run(main.health())
        self.assertEqual(health, {"status": "ok", "service": "omi-usgs-earthquake-app"})

    def test_safe_int_helpers(self):
        self.assertEqual(main._safe_int(5, 24, 1, 168), 5)
        self.assertEqual(main._safe_int("10", 24, 1, 168), 10)
        self.assertEqual(main._safe_int(0, 24, 1, 168), 1)
        self.assertEqual(main._safe_int(200, 24, 1, 168), 168)
        self.assertEqual(main._safe_int("invalid", 24, 1, 168), 24)
        self.assertEqual(main._safe_int(None, 24, 1, 168), 24)

    def test_parse_float_finite_and_non_finite(self):
        self.assertEqual(main._parse_float(3.14), 3.14)
        self.assertEqual(main._parse_float("2.5"), 2.5)
        self.assertEqual(main._parse_float(0), 0.0)
        self.assertEqual(main._parse_float("-1.2"), -1.2)
        self.assertIsNone(main._parse_float("nan"))
        self.assertIsNone(main._parse_float(float("nan")))
        self.assertIsNone(main._parse_float("inf"))
        self.assertIsNone(main._parse_float(float("inf")))
        self.assertIsNone(main._parse_float("-inf"))
        self.assertIsNone(main._parse_float("abc"))
        self.assertIsNone(main._parse_float(None))

    def test_safe_float_clamping(self):
        self.assertEqual(main._safe_float(50.0, default=250.0, minimum=1.0, maximum=2000.0), 50.0)
        self.assertEqual(main._safe_float(0.5, default=250.0, minimum=1.0, maximum=2000.0), 1.0)
        self.assertEqual(main._safe_float(3000.0, default=250.0, minimum=1.0, maximum=2000.0), 2000.0)
        self.assertEqual(main._safe_float("nan", default=250.0, minimum=1.0, maximum=2000.0), 250.0)
        self.assertEqual(main._safe_float(None, default=250.0, minimum=1.0, maximum=2000.0), 250.0)

    def test_timestamp_to_utc_valid(self):
        # 1716200000000 ms is 2024-05-20T10:13:20Z
        iso = main._timestamp_to_utc(1716200000000)
        self.assertEqual(iso, "2024-05-20T10:13:20Z")

    def test_timestamp_to_utc_overflow_and_invalid_handled_safely(self):
        self.assertIsNone(main._timestamp_to_utc("nan"))
        self.assertIsNone(main._timestamp_to_utc("inf"))
        self.assertIsNone(main._timestamp_to_utc(None))
        self.assertIsNone(main._timestamp_to_utc("not_a_time"))
        # Extreme timestamps that would raise OSError / OverflowError
        self.assertIsNone(main._timestamp_to_utc(1e15))
        self.assertIsNone(main._timestamp_to_utc(-1e15))

    def test_safe_orderby(self):
        self.assertEqual(main._safe_orderby("magnitude"), "magnitude")
        self.assertEqual(main._safe_orderby("time-asc"), "time-asc")
        self.assertEqual(main._safe_orderby("unknown"), "time")
        self.assertEqual(main._safe_orderby(None), "time")

    def test_summarize_feature_resilient_to_malformed_data(self):
        # None or non-dict feature
        res = main._summarize_feature(None)
        self.assertEqual(res["place"], "Unknown location")
        self.assertIsNone(res["coordinates"]["latitude"])

        # Feature with non-dict properties and geometry
        res2 = main._summarize_feature({"properties": "not-a-dict", "geometry": []})
        self.assertEqual(res2["place"], "Unknown location")
        self.assertIsNone(res2["coordinates"]["longitude"])

        # Feature with non-list coordinates
        res3 = main._summarize_feature({
            "properties": {"place": "Alaska", "mag": 5.1},
            "geometry": {"coordinates": "not-a-list"},
        })
        self.assertEqual(res3["place"], "Alaska")
        self.assertEqual(res3["magnitude"], 5.1)
        self.assertIsNone(res3["coordinates"]["depth_km"])

    def test_recent_earthquakes_returns_summarized_feature(self):
        captured_params = {}

        async def fake_usgs_get(params):
            captured_params.update(params)
            return {
                "type": "FeatureCollection",
                "metadata": {"count": 1},
                "features": [
                    {
                        "id": "us7000test",
                        "properties": {
                            "mag": 4.6,
                            "place": "12 km S of Test City",
                            "time": 1716200000000,
                            "updated": 1716200300000,
                            "url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000test",
                            "detail": "https://earthquake.usgs.gov/fdsnws/event/1/query?eventid=us7000test",
                            "alert": "green",
                            "status": "reviewed",
                            "tsunami": 0,
                            "felt": 12,
                            "sig": 326,
                        },
                        "geometry": {"coordinates": [-122.4, 37.7, 8.2]},
                    }
                ],
            }

        original_usgs_get = main._usgs_get
        main._usgs_get = fake_usgs_get
        try:
            result = asyncio.run(
                main.tool_recent_earthquakes(
                    DummyRequest({"hours": 12, "min_magnitude": 4.0, "limit": 3})
                )
            )
        finally:
            main._usgs_get = original_usgs_get

        self.assertTrue(result.success)
        self.assertEqual(result.message, "Found 1 earthquake event(s).")
        self.assertEqual(captured_params["minmagnitude"], 4.0)
        self.assertEqual(captured_params["limit"], 3)
        self.assertEqual(captured_params["orderby"], "time")
        event = result.data["earthquakes"][0]
        self.assertEqual(event["event_id"], "us7000test")
        self.assertEqual(event["magnitude"], 4.6)
        self.assertEqual(
            event["coordinates"],
            {
                "latitude": 37.7,
                "longitude": -122.4,
                "depth_km": 8.2,
            },
        )

    def test_search_handlers_preserve_magnitude_filters(self):
        cases = [
            (-1, -1.0),
            (-0.5, -0.5),
            ("-2.5", -2.5),
            (0, 0.0),
            (2.5, 2.5),
            (12, 10.0),
            (None, 2.5),
            ("invalid", 2.5),
            ("nan", 2.5),
            ("inf", 2.5),
            ("-inf", 2.5),
        ]
        for handler in (main.tool_recent_earthquakes, main.tool_nearby_earthquakes):
            for requested, expected in cases:
                with self.subTest(handler=handler.__name__, minimum=requested):
                    captured = {}

                    async def fake_usgs_get(params):
                        captured.update(params)
                        return {
                            "features": [
                                {"id": "negative-event", "properties": {"mag": -0.4}}
                            ]
                            if params["minmagnitude"] <= -0.4
                            else []
                        }

                    original = main._usgs_get
                    main._usgs_get = fake_usgs_get
                    try:
                        body = {"latitude": 37.7, "longitude": -122.4}
                        if requested is not None:
                            body["min_magnitude"] = requested
                        result = asyncio.run(handler(DummyRequest(body)))
                    finally:
                        main._usgs_get = original

                    self.assertTrue(result.success)
                    self.assertEqual(captured["minmagnitude"], expected)
                    self.assertEqual(result.data["count"], int(expected <= -0.4))
                    if expected <= -0.4:
                        self.assertEqual(
                            result.data["earthquakes"][0]["magnitude"], -0.4
                        )
                    if handler is main.tool_nearby_earthquakes:
                        self.assertEqual(captured["latitude"], 37.7)
                        self.assertEqual(captured["maxradiuskm"], 250.0)

    def test_recent_earthquakes_empty_results(self):
        original = main._usgs_get
        main._usgs_get = lambda params: asyncio.sleep(0, result={"features": []})
        try:
            result = asyncio.run(main.tool_recent_earthquakes(DummyRequest({})))
            self.assertTrue(result.success)
            self.assertEqual(
                result.message, "No USGS earthquake events found for the requested filters."
            )
            self.assertEqual(result.data["count"], 0)
        finally:
            main._usgs_get = original

    def test_recent_earthquakes_non_dict_payload_handled_safely(self):
        original = main._usgs_get
        main._usgs_get = lambda params: asyncio.sleep(0, result=[])
        try:
            result = asyncio.run(main.tool_recent_earthquakes(DummyRequest({})))
            self.assertFalse(result.success)
            self.assertIn("unexpected response format", result.message)
        finally:
            main._usgs_get = original

    def test_recent_earthquakes_http_error_handled(self):
        original = main._usgs_get
        main._usgs_get = lambda params: asyncio.sleep(
            0, result={"error": "USGS request failed: connection timeout"}
        )
        try:
            result = asyncio.run(main.tool_recent_earthquakes(DummyRequest({})))
            self.assertFalse(result.success)
            self.assertIn("connection timeout", result.message)
        finally:
            main._usgs_get = original

    def test_nearby_earthquakes_requires_latitude_and_longitude(self):
        result = asyncio.run(
            main.tool_nearby_earthquakes(DummyRequest({"latitude": 37.7}))
        )
        self.assertFalse(result.success)
        self.assertEqual(result.message, "latitude and longitude are required")

        result2 = asyncio.run(
            main.tool_nearby_earthquakes(DummyRequest({"longitude": -122.4}))
        )
        self.assertFalse(result2.success)
        self.assertEqual(result2.message, "latitude and longitude are required")

    def test_nearby_earthquakes_rejects_out_of_bounds_coordinates(self):
        cases = [
            (95.0, 10.0),
            (-95.0, 10.0),
            (10.0, 185.0),
            (10.0, -185.0),
        ]
        for lat, lon in cases:
            with self.subTest(lat=lat, lon=lon):
                result = asyncio.run(
                    main.tool_nearby_earthquakes(
                        DummyRequest({"latitude": lat, "longitude": lon})
                    )
                )
                self.assertFalse(result.success)
                self.assertIn("coordinates are out of range", result.data["error"])

    def test_nearby_earthquakes_rejects_nan_and_inf_coordinates(self):
        for val in ["nan", "inf", "-inf"]:
            with self.subTest(val=val):
                result = asyncio.run(
                    main.tool_nearby_earthquakes(
                        DummyRequest({"latitude": val, "longitude": 0})
                    )
                )
                self.assertFalse(result.success)
                self.assertEqual(result.message, "latitude and longitude are required")

    def test_nearby_earthquakes_success(self):
        captured = {}

        async def fake_usgs(params):
            captured.update(params)
            return {
                "features": [
                    {
                        "id": "nearby1",
                        "properties": {"mag": 3.2, "place": "Near Coast"},
                        "geometry": {"coordinates": [-122.0, 37.0, 5.0]},
                    }
                ]
            }

        original = main._usgs_get
        main._usgs_get = fake_usgs
        try:
            result = asyncio.run(
                main.tool_nearby_earthquakes(
                    DummyRequest(
                        {
                            "latitude": 37.0,
                            "longitude": -122.0,
                            "radius_km": 100,
                            "hours": 48,
                        }
                    )
                )
            )
            self.assertTrue(result.success)
            self.assertEqual(result.message, "Found 1 nearby earthquake event(s).")
            self.assertEqual(captured["latitude"], 37.0)
            self.assertEqual(captured["longitude"], -122.0)
            self.assertEqual(captured["maxradiuskm"], 100.0)
        finally:
            main._usgs_get = original

    def test_nearby_earthquakes_empty_results(self):
        original = main._usgs_get
        main._usgs_get = lambda params: asyncio.sleep(0, result={"features": []})
        try:
            result = asyncio.run(
                main.tool_nearby_earthquakes(
                    DummyRequest({"latitude": 37.0, "longitude": -122.0})
                )
            )
            self.assertTrue(result.success)
            self.assertEqual(
                result.message, "No nearby USGS earthquake events found for the requested filters."
            )
        finally:
            main._usgs_get = original

    def test_earthquake_details_success(self):
        async def fake_get(params):
            return {
                "type": "Feature",
                "id": "us7000test",
                "properties": {
                    "mag": 5.5,
                    "place": "Central Italy",
                    "time": 1716200000000,
                    "status": "reviewed",
                },
                "geometry": {"coordinates": [13.2, 42.8, 10.0]},
            }

        original = main._usgs_get
        main._usgs_get = fake_get
        try:
            result = asyncio.run(
                main.tool_earthquake_details(
                    DummyRequest({"event_id": "us7000test"})
                )
            )
            self.assertTrue(result.success)
            self.assertIn("Earthquake event us7000test found", result.message)
            self.assertEqual(result.data["earthquake"]["magnitude"], 5.5)
            self.assertEqual(result.data["earthquake"]["place"], "Central Italy")
        finally:
            main._usgs_get = original

    def test_earthquake_details_missing_event_id(self):
        result = asyncio.run(main.tool_earthquake_details(DummyRequest({})))
        self.assertFalse(result.success)
        self.assertEqual(result.message, "event_id is required")

    def test_earthquake_details_not_found(self):
        async def fake_get(params):
            return {"type": "FeatureCollection", "features": []}

        original = main._usgs_get
        main._usgs_get = fake_get
        try:
            result = asyncio.run(
                main.tool_earthquake_details(
                    DummyRequest({"event_id": "nonexistent"})
                )
            )
            self.assertFalse(result.success)
            self.assertIn("No USGS earthquake event found for nonexistent", result.message)
            self.assertEqual(result.data["error"], "event not found")
        finally:
            main._usgs_get = original

    def test_earthquake_details_non_dict_payload(self):
        original = main._usgs_get
        main._usgs_get = lambda params: asyncio.sleep(0, result="unexpected string")
        try:
            result = asyncio.run(
                main.tool_earthquake_details(
                    DummyRequest({"event_id": "us123"})
                )
            )
            self.assertFalse(result.success)
            self.assertIn("No USGS earthquake event found", result.message)
        finally:
            main._usgs_get = original

    def test_earthquake_details_http_error(self):
        original = main._usgs_get
        main._usgs_get = lambda params: asyncio.sleep(
            0, result={"error": "USGS request failed: 404 Not Found"}
        )
        try:
            result = asyncio.run(
                main.tool_earthquake_details(
                    DummyRequest({"event_id": "us404"})
                )
            )
            self.assertFalse(result.success)
            self.assertIn("404 Not Found", result.message)
        finally:
            main._usgs_get = original

    def test_tool_endpoints_return_structured_error_for_invalid_json(self):
        handlers = [
            main.tool_recent_earthquakes,
            main.tool_nearby_earthquakes,
            main.tool_earthquake_details,
        ]

        for handler in handlers:
            with self.subTest(handler=handler.__name__):
                result = asyncio.run(
                    handler(DummyRequest(json_error=ValueError("bad json")))
                )

                self.assertFalse(result.success)
                self.assertEqual(result.message, "Invalid or missing JSON body")
                self.assertEqual(result.data, {"error": "invalid request body"})

    def test_tool_endpoints_return_structured_error_for_non_dict_body(self):
        handlers = [
            main.tool_recent_earthquakes,
            main.tool_nearby_earthquakes,
            main.tool_earthquake_details,
        ]

        for handler in handlers:
            with self.subTest(handler=handler.__name__):
                result = asyncio.run(
                    handler(DummyRequest(payload=["list", "body"]))
                )

                self.assertFalse(result.success)
                self.assertEqual(result.message, "Invalid or missing JSON body")
                self.assertEqual(result.data, {"error": "invalid request body"})

    def test_http_client_fallback_and_lifespan(self):
        # When app.state.http_client is None, creates temporary client
        main.app.state.http_client = None
        client, should_close = main._get_http_client()
        self.assertTrue(should_close)
        self.assertIsNotNone(client)

        # When app.state.http_client is active, reuses it
        dummy_client = types.SimpleNamespace(is_closed=False)
        main.app.state.http_client = dummy_client
        reused_client, should_close = main._get_http_client()
        self.assertFalse(should_close)
        self.assertIs(reused_client, dummy_client)
        main.app.state.http_client = None


if __name__ == "__main__":
    unittest.main()
