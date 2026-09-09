import asyncio
import sys
import types
import unittest


class DummyFastAPI:
    def __init__(self, **_kwargs):
        self.routes = []

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
    sys.modules.setdefault("pydantic", pydantic)

    httpx = types.ModuleType("httpx")
    httpx.HTTPError = Exception
    httpx.AsyncClient = object
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
        self.assertNotIn("filters", result.data)
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
        cases = [(-1, -1.0), (-0.5, -0.5), ("-2.5", -2.5), (0, 0.0),
                 (2.5, 2.5), (12, 10.0), (None, 2.5), ("invalid", 2.5),
                 ("nan", 2.5), ("inf", 2.5), ("-inf", 2.5)]
        for handler in (main.tool_recent_earthquakes, main.tool_nearby_earthquakes):
            for requested, expected in cases:
                with self.subTest(handler=handler.__name__, minimum=requested):
                    captured = {}

                    async def fake_usgs_get(params):
                        captured.update(params)
                        return {"features": [{"id": "negative-event",
                                              "properties": {"mag": -0.4}}]
                                if params["minmagnitude"] <= -0.4 else []}

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
                        self.assertEqual(result.data["earthquakes"][0]["magnitude"], -0.4)
                    if handler is main.tool_nearby_earthquakes:
                        self.assertEqual(captured["latitude"], 37.7)
                        self.assertEqual(captured["maxradiuskm"], 250.0)

    def test_nearby_earthquakes_requires_latitude_and_longitude(self):
        result = asyncio.run(
            main.tool_nearby_earthquakes(DummyRequest({"latitude": 37.7}))
        )

        self.assertFalse(result.success)
        self.assertEqual(result.message, "latitude and longitude are required")

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


if __name__ == "__main__":
    unittest.main()
