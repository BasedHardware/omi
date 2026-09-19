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
        self.exception_handlers = {}

    def get(self, path, **_kwargs):
        return self._route("GET", path)

    def post(self, path, **_kwargs):
        return self._route("POST", path)

    def exception_handler(self, exc_class):
        def decorator(func):
            self.exception_handlers[exc_class] = func
            return func

        return decorator

    def _route(self, method, path):
        def decorator(func):
            self.routes.append((method, path, func))
            return func

        return decorator

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            path = scope.get("path", "")
            method = scope.get("method", "GET")
            body_bytes = b""
            if receive:
                while True:
                    msg = await receive()
                    body_bytes += msg.get("body", b"")
                    if not msg.get("more_body", False):
                        break
            for r_method, r_path, handler in self.routes:
                if r_method == method and r_path == path:
                    import inspect
                    import json

                    sig = inspect.signature(handler)
                    kwargs = {}
                    if body_bytes:
                        try:
                            parsed_body = json.loads(body_bytes.decode("utf-8"))
                        except Exception:
                            parsed_body = None
                    else:
                        parsed_body = None

                    for param_name, param in sig.parameters.items():
                        annotation = param.annotation
                        model_cls = None
                        if isinstance(annotation, str):
                            stripped = annotation.replace("Optional[", "").rstrip("]").strip()
                            model_cls = getattr(main, stripped, None)
                        elif annotation is not inspect.Parameter.empty and hasattr(annotation, "__mro__"):
                            model_cls = annotation

                        if model_cls is not None and callable(model_cls):
                            if parsed_body is not None and isinstance(parsed_body, dict):
                                kwargs[param_name] = model_cls(**parsed_body)
                            else:
                                kwargs[param_name] = None
                        elif param_name == "request":
                            kwargs[param_name] = DummyRequest(parsed_body)
                        elif param_name == "payload":
                            kwargs[param_name] = parsed_body

                    try:
                        resp = await handler(**kwargs)
                    except Exception as exc:
                        handler_exc = None
                        for exc_cls, eh in self.exception_handlers.items():
                            if isinstance(exc, exc_cls):
                                handler_exc = eh
                                break
                        if handler_exc:
                            resp = await handler_exc(DummyRequest(parsed_body), exc)
                        else:
                            raise

                    if callable(resp):
                        await resp(scope, receive, send)
                        return

                    status_code = getattr(resp, "status_code", 200)
                    if hasattr(resp, "model_dump"):
                        content = resp.model_dump()
                    elif hasattr(resp, "dict"):
                        content = resp.dict()
                    elif isinstance(resp, dict):
                        content = resp
                    else:
                        content = getattr(resp, "content", {})
                    content_bytes = json.dumps(content).encode("utf-8")
                    await send({
                        "type": "http.response.start",
                        "status": status_code,
                        "headers": [[b"content-type", b"application/json"]],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": content_bytes,
                    })
                    return

            await send({"type": "http.response.start", "status": 404, "headers": []})
            await send({"type": "http.response.body", "body": b"Not Found"})


class DummyBaseModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

    def dict(self):
        res = {}
        for cls in reversed(self.__class__.__mro__):
            for k, v in getattr(cls, "__dict__", {}).items():
                if not k.startswith("_") and not callable(v):
                    res[k] = v
        res.update(self.__dict__)
        return res

    def model_dump(self):
        return self.dict()

    def json(self):
        import json

        return json.dumps(self.dict())


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
    fastapi.Request = DummyRequest

    class DummyJSONResponse:
        def __init__(self, content=None, status_code=200, **kwargs):
            self.content = content or {}
            self.status_code = status_code

        async def __call__(self, scope, receive, send):
            if send is not None:
                await send({
                    "type": "http.response.start",
                    "status": self.status_code,
                    "headers": [[b"content-type", b"application/json"]],
                })
                import json
                body = json.dumps(self.content).encode("utf-8")
                await send({
                    "type": "http.response.body",
                    "body": body,
                })

    class DummyRequestValidationError(Exception):
        def __init__(self, errors=None):
            self._errors = errors or []

        def errors(self):
            return self._errors

    fastapi.responses = types.ModuleType("fastapi.responses")
    fastapi.responses.JSONResponse = DummyJSONResponse
    fastapi.exceptions = types.ModuleType("fastapi.exceptions")
    fastapi.exceptions.RequestValidationError = DummyRequestValidationError

    sys.modules.setdefault("fastapi", fastapi)
    sys.modules.setdefault("fastapi.responses", fastapi.responses)
    sys.modules.setdefault("fastapi.exceptions", fastapi.exceptions)

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel

    def field_stub(default=None, **_kwargs):
        return default

    pydantic.Field = field_stub
    sys.modules.setdefault("pydantic", pydantic)

    httpx = types.ModuleType("httpx")
    httpx.HTTPError = Exception
    httpx.HTTPStatusError = type(
        "HTTPStatusError",
        (Exception,),
        {"response": types.SimpleNamespace(status_code=500)},
    )
    httpx.TimeoutException = type("TimeoutException", (Exception,), {})

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

    def test_clean_event_id_direct_and_whitespace(self):
        self.assertEqual(main._clean_event_id("us7000abcd"), "us7000abcd")
        self.assertEqual(main._clean_event_id("  nc12345678  "), "nc12345678")
        self.assertEqual(main._clean_event_id("#us7000abcd"), "us7000abcd")
        self.assertEqual(main._clean_event_id("ci12345/"), "ci12345")

    def test_clean_event_id_usgs_eventpage_urls(self):
        url1 = "https://earthquake.usgs.gov/earthquakes/eventpage/us7000m8v4/executive"
        self.assertEqual(main._clean_event_id(url1), "us7000m8v4")

        url2 = "https://earthquake.usgs.gov/earthquakes/eventpage/nc75001234#executive"
        self.assertEqual(main._clean_event_id(url2), "nc75001234")

        url3 = "https://earthquake.usgs.gov/fdsnws/event/1/query?eventid=ci39876543&format=geojson"
        self.assertEqual(main._clean_event_id(url3), "ci39876543")

    def test_clean_event_id_empty_and_non_string(self):
        self.assertEqual(main._clean_event_id(None), "")
        self.assertEqual(main._clean_event_id(""), "")
        self.assertEqual(main._clean_event_id("   "), "")
        self.assertEqual(main._clean_event_id(12345), "12345")

    def test_clean_event_id_unparseable_url_does_not_squash_host(self):
        self.assertEqual(main._clean_event_id("https://earthquake.usgs.gov/"), "")
        self.assertEqual(main._clean_event_id("https://earthquake.usgs.gov/earthquakes"), "")
        self.assertEqual(main._clean_event_id("https://example.com/some/path"), "")

    def test_earthquake_details_extracts_id_from_url(self):
        captured_params = []

        async def fake_usgs_get(params, client=None):
            captured_params.append(params)
            return {
                "type": "Feature",
                "id": params.get("eventid"),
                "properties": {"mag": 5.1, "place": "Near URL Test"},
                "geometry": {"coordinates": [10.0, 20.0, 5.0]},
            }

        original_usgs_get = main._usgs_get
        main._usgs_get = fake_usgs_get
        try:
            req = DummyRequest(
                {
                    "event_id": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000url1/executive"
                }
            )
            resp = asyncio.run(main.tool_earthquake_details(req))
            self.assertTrue(resp.success)
            self.assertEqual(captured_params[0]["eventid"], "us7000url1")
            self.assertEqual(resp.data["earthquake"]["event_id"], "us7000url1")
        finally:
            main._usgs_get = original_usgs_get

    def test_status_endpoint(self):
        status_data = asyncio.run(main.status())
        self.assertEqual(status_data["status"], "ok")
        self.assertEqual(status_data["service"], "omi-usgs-earthquake-app")
        self.assertIn("usgs_query_url", status_data)
        self.assertIn("timeout_seconds", status_data)
        self.assertIn("timestamp", status_data)

    def test_validation_exception_handler(self):
        handler = getattr(main, "validation_exception_handler", None)
        self.assertIsNotNone(handler)

        class FakeValidationError:
            def errors(self):
                return [{"loc": ("body", "latitude"), "msg": "Field required", "type": "missing"}]

        resp = asyncio.run(handler(DummyRequest(), FakeValidationError()))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.content["success"])
        self.assertIn("Field required", resp.content["message"])
        self.assertEqual(resp.content["data"]["error"], "validation_error")

    def test_validation_handler_middleware_dispatch_executes_callable_response(self):
        handler = getattr(main, "validation_exception_handler", None)
        self.assertIsNotNone(handler)

        class FakeValidationError:
            def errors(self):
                return [
                    {
                        "loc": ("body", "min_magnitude"),
                        "msg": "Input should be a valid number",
                        "type": "float_parsing",
                    }
                ]

        response = asyncio.run(handler(DummyRequest(), FakeValidationError()))
        self.assertTrue(callable(response), "Starlette exception middleware requires response to be callable")

        events = []

        async def fake_send(message):
            events.append(message)

        async def run_asgi():
            await response({"type": "http", "method": "POST"}, None, fake_send)

        asyncio.run(run_asgi())
        self.assertTrue(any(e.get("type") == "http.response.start" and e.get("status") == 200 for e in events))
        self.assertTrue(any(e.get("type") == "http.response.body" for e in events))

    def test_tool_endpoints_accept_typed_request_models(self):
        try:
            from models import NearbyEarthquakesRequest, RecentEarthquakesRequest
        except ImportError:
            from .models import NearbyEarthquakesRequest, RecentEarthquakesRequest

        async def fake_usgs_get(params, client=None):
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "event-model-1",
                        "properties": {"mag": 4.5, "place": "Typed Model City"},
                        "geometry": {"coordinates": [-120.0, 36.0, 10.0]},
                    }
                ],
                "metadata": {"count": 1},
            }

        original_usgs_get = main._usgs_get
        main._usgs_get = fake_usgs_get
        try:
            recent_req = RecentEarthquakesRequest(hours=48, min_magnitude=3.0, limit=3)
            recent_resp = asyncio.run(main.tool_recent_earthquakes(recent_req))
            self.assertTrue(recent_resp.success)
            self.assertEqual(recent_resp.data["count"], 1)

            nearby_req = NearbyEarthquakesRequest(latitude=36.0, longitude=-120.0, radius_km=100.0)
            nearby_resp = asyncio.run(main.tool_nearby_earthquakes(nearby_req))
            self.assertTrue(nearby_resp.success)
            self.assertEqual(nearby_resp.data["count"], 1)
        finally:
            main._usgs_get = original_usgs_get

    def test_end_to_end_app_stack_with_transport_mock(self):
        try:
            from models import EarthquakeDetailsRequest, NearbyEarthquakesRequest, RecentEarthquakesRequest
        except ImportError:
            from .models import EarthquakeDetailsRequest, NearbyEarthquakesRequest, RecentEarthquakesRequest

        async def fake_usgs_get(params, client=None):
            event_id = params.get("eventid", "")
            if event_id:
                return {
                    "type": "Feature",
                    "id": event_id,
                    "properties": {
                        "mag": 6.2,
                        "place": "Off Coast of Northern California",
                        "time": 1700000000000,
                        "url": f"https://earthquake.usgs.gov/earthquakes/eventpage/{event_id}",
                        "status": "reviewed",
                        "alert": "green",
                    },
                    "geometry": {"coordinates": [-124.5, 40.3, 10.0]},
                }
            return {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "event-e2e-1",
                        "properties": {"mag": 4.8, "place": "30km S of San Jose, CA", "time": 1700000000000},
                        "geometry": {"coordinates": [-121.8, 37.1, 8.5]},
                    }
                ],
                "metadata": {"count": 1},
            }

        original_usgs_get = main._usgs_get
        main._usgs_get = fake_usgs_get

        async def asgi_request(app, method, path, json_data=None):
            import json

            body_bytes = json.dumps(json_data).encode("utf-8") if json_data is not None else b""
            events = []

            async def receive():
                return {"type": "http.request", "body": body_bytes, "more_body": False}

            async def send(message):
                events.append(message)

            scope = {
                "type": "http",
                "method": method,
                "path": path,
                "headers": [[b"content-type", b"application/json"]] if json_data is not None else [],
            }
            await app(scope, receive, send)

            status = None
            body = b""
            for event in events:
                if event["type"] == "http.response.start":
                    status = event["status"]
                elif event["type"] == "http.response.body":
                    body += event.get("body", b"")
            parsed_json = json.loads(body.decode("utf-8")) if body else None
            return status, parsed_json

        try:
            # 1. Direct typed Pydantic model calls (verifying .json() synchronous method does not cause TypeError)
            recent_req = RecentEarthquakesRequest(hours=12, min_magnitude=4.0, limit=3)
            self.assertTrue(hasattr(recent_req, "json") and callable(recent_req.json))
            self.assertIsInstance(recent_req.json(), str)
            direct_recent = asyncio.run(main.tool_recent_earthquakes(recent_req))
            self.assertTrue(direct_recent.success)
            self.assertEqual(direct_recent.data["count"], 1)

            nearby_req = NearbyEarthquakesRequest(latitude=37.7, longitude=-122.4, radius_km=150.0)
            self.assertTrue(hasattr(nearby_req, "json") and callable(nearby_req.json))
            self.assertIsInstance(nearby_req.json(), str)
            direct_nearby = asyncio.run(main.tool_nearby_earthquakes(nearby_req))
            self.assertTrue(direct_nearby.success)
            self.assertEqual(direct_nearby.data["count"], 1)

            details_req = EarthquakeDetailsRequest(event_id="https://earthquake.usgs.gov/earthquakes/eventpage/us7000e2e1/executive")
            self.assertTrue(hasattr(details_req, "json") and callable(details_req.json))
            self.assertIsInstance(details_req.json(), str)
            direct_details = asyncio.run(main.tool_earthquake_details(details_req))
            self.assertTrue(direct_details.success)
            self.assertEqual(direct_details.data["earthquake"]["event_id"], "us7000e2e1")

            # 2. Full HTTP ASGI stack requests with JSON payloads (simulating live FastAPI/Starlette dispatch)
            status, data = asyncio.run(
                asgi_request(main.app, "POST", "/tools/recent_earthquakes", {"hours": 12, "min_magnitude": 4.0, "limit": 3})
            )
            self.assertEqual(status, 200)
            self.assertTrue(data["success"])
            self.assertEqual(data["data"]["count"], 1)

            status, data = asyncio.run(
                asgi_request(main.app, "POST", "/tools/nearby_earthquakes", {"latitude": 37.7, "longitude": -122.4})
            )
            self.assertEqual(status, 200)
            self.assertTrue(data["success"])
            self.assertEqual(data["data"]["count"], 1)

            status, data = asyncio.run(
                asgi_request(
                    main.app,
                    "POST",
                    "/tools/earthquake_details",
                    {"event_id": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000e2e1/executive"},
                )
            )
            self.assertEqual(status, 200)
            self.assertTrue(data["success"])
            self.assertEqual(data["data"]["earthquake"]["event_id"], "us7000e2e1")
        finally:
            main._usgs_get = original_usgs_get


if __name__ == "__main__":
    unittest.main()
