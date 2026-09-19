"""Hermetic tests for the Launch Library 2 Omi integration."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


_HAS_REAL_HTTPX = importlib.util.find_spec("httpx") is not None
_HAS_REAL_FASTAPI = importlib.util.find_spec("fastapi") is not None
_HAS_REAL_PYDANTIC = importlib.util.find_spec("pydantic") is not None

if not _HAS_REAL_HTTPX:
    httpx = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message, *, request, response):
            super().__init__(message)
            self.request = request
            self.response = response

    class RequestError(HTTPError):
        pass

    class AsyncClient:
        pass

    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.RequestError = RequestError
    httpx.AsyncClient = AsyncClient
    sys.modules["httpx"] = httpx
else:
    import httpx

if not _HAS_REAL_PYDANTIC:
    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for cls in reversed(self.__class__.__mro__):
                for key, value in getattr(cls, "__dict__", {}).items():
                    if not key.startswith("_") and not callable(value):
                        setattr(self, key, None if value is ... else value)
            for key, value in kwargs.items():
                setattr(self, key, value)

        def model_dump(self):
            return {
                key: value
                for key, value in self.__dict__.items()
                if not key.startswith("_")
            }

    def Field(default=None, **_kwargs):
        return default

    def ConfigDict(**_kwargs):
        return {}

    def field_validator(*_args, **_kwargs):
        return lambda function: function

    def model_validator(*_args, **_kwargs):
        return lambda function: function

    pydantic.BaseModel = BaseModel
    pydantic.Field = Field
    pydantic.ConfigDict = ConfigDict
    pydantic.ValidationInfo = object
    pydantic.field_validator = field_validator
    pydantic.model_validator = model_validator
    sys.modules["pydantic"] = pydantic

if not _HAS_REAL_FASTAPI:
    fastapi = types.ModuleType("fastapi")
    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_exceptions = types.ModuleType("fastapi.exceptions")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda function: function

        def post(self, *args, **kwargs):
            return lambda function: function

        def exception_handler(self, *args, **kwargs):
            return lambda function: function

    class HTMLResponse:
        pass

    class JSONResponse:
        pass

    class RequestValidationError(Exception):
        pass

    fastapi.FastAPI = FastAPI
    fastapi.RequestValidationError = RequestValidationError
    fastapi.responses = fastapi_responses
    fastapi.exceptions = fastapi_exceptions
    fastapi_responses.HTMLResponse = HTMLResponse
    fastapi_responses.JSONResponse = JSONResponse
    fastapi_exceptions.RequestValidationError = RequestValidationError
    sys.modules["fastapi"] = fastapi
    sys.modules["fastapi.responses"] = fastapi_responses
    sys.modules["fastapi.exceptions"] = fastapi_exceptions


APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

import launchlibrary
from models import (
    ChatToolResponse,
    LaunchDetailsRequest,
    SearchLaunchesRequest,
    UpcomingLaunchesRequest,
    normalize_utc_datetime,
)

if _HAS_REAL_FASTAPI and _HAS_REAL_PYDANTIC:
    from fastapi.testclient import TestClient

    import main
else:
    TestClient = None
    main = None


LAUNCH_ID = "5af31461-bce5-4cfb-a0ee-b527cf285d90"


def _launch_payload():
    return {
        "id": LAUNCH_ID,
        "name": "Falcon 9 Block 5 | Starlink Group 15-27",
        "status": {
            "id": 1,
            "name": "Go for Launch",
            "abbrev": "Go",
        },
        "last_updated": "2026-09-19T10:00:00Z",
        "net": "2026-09-20T01:47:00Z",
        "window_start": "2026-09-20T01:47:00Z",
        "window_end": "2026-09-20T05:47:00Z",
        "launch_service_provider": {
            "id": 121,
            "name": "SpaceX",
        },
        "rocket": {
            "configuration": {
                "id": 164,
                "name": "Falcon 9",
                "full_name": "Falcon 9 Block 5",
            }
        },
        "mission": {
            "name": "Starlink Group 15-27",
            "type": "Communications",
            "description": "A batch of Starlink satellites.",
            "orbit": {"name": "Low Earth Orbit"},
        },
        "pad": {
            "name": "Space Launch Complex 4E",
            "location": {
                "name": ("Vandenberg Space Force Base, California, United States")
            },
        },
        "webcast_live": False,
    }


class _FakeRequest:
    def __init__(self, url):
        parsed = urlsplit(url)
        self.url = types.SimpleNamespace(
            path=parsed.path,
            query=parsed.query.encode(),
        )


class _FakeResponse:
    def __init__(self, status_code=200, *, payload=None, content=b"", request=None):
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.request = request

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=self.request,
                response=self,
            )

    def json(self):
        return self._payload


def _response(status_code=200, *, json=None, content=b"", request=None):
    if _HAS_REAL_HTTPX:
        if json is not None:
            return httpx.Response(status_code, json=json, request=request)
        return httpx.Response(status_code, content=content, request=request)
    return _FakeResponse(
        status_code,
        payload=json,
        content=content,
        request=request,
    )


class _StdlibClient:
    def __init__(self, handler):
        self.handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url, params=None):
        if params:
            from urllib.parse import urlencode

            url = f"{url}?{urlencode(params)}"
        return self.handler(_FakeRequest(url))


def _client(handler):
    if _HAS_REAL_HTTPX:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return _StdlibClient(handler)


class UtilityTests(unittest.TestCase):
    def test_normalize_utc_datetime(self):
        self.assertEqual(
            normalize_utc_datetime("2026-09-20"),
            "2026-09-20T00:00:00Z",
        )
        self.assertEqual(
            normalize_utc_datetime("2026-09-20", end_of_day=True),
            "2026-09-20T23:59:59Z",
        )
        self.assertEqual(
            normalize_utc_datetime("2026-09-20T09:30:00+08:00"),
            "2026-09-20T01:30:00Z",
        )
        with self.assertRaises(ValueError):
            normalize_utc_datetime("not-a-date")


@unittest.skipUnless(_HAS_REAL_PYDANTIC, "requires the real pydantic package")
class ModelTests(unittest.TestCase):
    def test_search_requires_a_filter(self):
        with self.assertRaises(ValueError):
            SearchLaunchesRequest()

    def test_launch_id_accepts_uuid_from_url(self):
        request = LaunchDetailsRequest(
            launch_id=f"https://ll.thespacedevs.com/2.3.0/launches/{LAUNCH_ID}/"
        )
        self.assertEqual(request.launch_id, LAUNCH_ID)

    def test_chat_response_requires_exactly_one_outcome(self):
        with self.assertRaises(ValueError):
            ChatToolResponse()
        with self.assertRaises(ValueError):
            ChatToolResponse(result="ok", error="bad")


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_upcoming_builds_filters_and_formats(self):
        seen = {}

        def handler(request):
            seen.update(parse_qs(request.url.query.decode()))
            return _response(
                200,
                json={"count": 1, "results": [_launch_payload()]},
                request=request,
            )

        async with _client(handler) as client:
            result = await launchlibrary.get_upcoming_launches(
                client,
                UpcomingLaunchesRequest(
                    days=14,
                    provider="SpaceX",
                    rocket="Falcon",
                    limit=3,
                ),
            )

        self.assertEqual(seen["limit"], ["3"])
        self.assertEqual(seen["lsp__name"], ["SpaceX"])
        self.assertEqual(
            seen["rocket__configuration__full_name__icontains"],
            ["Falcon"],
        )
        self.assertIn("2026-09-20 01:47 UTC", result)
        self.assertIn("SpaceX", result)
        self.assertIn("Falcon 9 Block 5", result)
        self.assertNotIn("uid", seen)

    async def test_search_builds_text_and_date_filters(self):
        seen = {}

        def handler(request):
            seen.update(parse_qs(request.url.query.decode()))
            return _response(
                200,
                json={"count": 1, "results": [_launch_payload()]},
                request=request,
            )

        async with _client(handler) as client:
            result = await launchlibrary.search_launches(
                client,
                SearchLaunchesRequest(
                    query="Starlink",
                    start_date="2026-09-01",
                    end_date="2026-09-30",
                ),
            )

        self.assertEqual(seen["search"], ["Starlink"])
        self.assertEqual(seen["net__gte"], ["2026-09-01T00:00:00Z"])
        self.assertEqual(seen["net__lte"], ["2026-09-30T23:59:59Z"])
        self.assertIn("Found 1 matching launches", result)

    async def test_empty_search_is_successful(self):
        def handler(request):
            return _response(
                200,
                json={"count": 0, "results": []},
                request=request,
            )

        async with _client(handler) as client:
            result = await launchlibrary.search_launches(
                client,
                SearchLaunchesRequest(query="no such launch"),
            )

        self.assertIn("No Launch Library 2 launches matched", result)

    async def test_get_launch_formats_details(self):
        def handler(request):
            self.assertTrue(request.url.path.endswith(f"/{LAUNCH_ID}/"))
            return _response(200, json=_launch_payload(), request=request)

        async with _client(handler) as client:
            result = await launchlibrary.get_launch(
                client,
                LaunchDetailsRequest(launch_id=LAUNCH_ID),
            )

        self.assertIn("Launch Library ID", result)
        self.assertIn("Go for Launch", result)
        self.assertIn("Vandenberg Space Force Base", result)
        self.assertIn("thespacedevs.com/llapi", result)

    async def test_provider_404_returns_safe_error(self):
        def handler(request):
            return _response(404, json={"detail": "not found"}, request=request)

        async with _client(handler) as client:
            with self.assertRaisesRegex(
                launchlibrary.LaunchLibraryError,
                "launch not found",
            ):
                await launchlibrary.get_launch(
                    client,
                    LaunchDetailsRequest(launch_id=LAUNCH_ID),
                )

    async def test_rate_limit_returns_safe_error(self):
        def handler(request):
            return _response(429, json={"detail": "throttled"}, request=request)

        async with _client(handler) as client:
            with self.assertRaisesRegex(
                launchlibrary.LaunchLibraryError,
                "15 requests per hour",
            ):
                await launchlibrary.search_launches(
                    client,
                    SearchLaunchesRequest(query="Starlink"),
                )

    async def test_malformed_payload_fails_closed(self):
        def handler(request):
            return _response(200, content=b"[]", request=request)

        async with _client(handler) as client:
            with self.assertRaisesRegex(
                launchlibrary.LaunchLibraryError,
                "unexpected response shape",
            ):
                await launchlibrary.search_launches(
                    client,
                    SearchLaunchesRequest(query="Starlink"),
                )

    async def test_non_list_results_fails_closed(self):
        def handler(request):
            return _response(
                200,
                json={"count": 1, "results": {"bad": "shape"}},
                request=request,
            )

        async with _client(handler) as client:
            with self.assertRaisesRegex(
                launchlibrary.LaunchLibraryError,
                "unexpected results payload",
            ):
                await launchlibrary.search_launches(
                    client,
                    SearchLaunchesRequest(query="Starlink"),
                )

    async def test_response_size_limit(self):
        def handler(request):
            return _response(
                200,
                content=b"{" + b" " * launchlibrary.MAX_RESPONSE_BYTES + b"}",
                request=request,
            )

        async with _client(handler) as client:
            with self.assertRaisesRegex(
                launchlibrary.LaunchLibraryError,
                "size limit",
            ):
                await launchlibrary.search_launches(
                    client,
                    SearchLaunchesRequest(query="Starlink"),
                )


@unittest.skipUnless(
    _HAS_REAL_FASTAPI and _HAS_REAL_PYDANTIC and _HAS_REAL_HTTPX,
    "requires the real FastAPI, httpx, and pydantic packages",
)
class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.handler = lambda request: _response(
            200,
            json={"count": 1, "results": [_launch_payload()]},
            request=request,
        )
        self.test_client = TestClient(main.app)
        self.test_client.__enter__()
        self.client = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: self.handler(request))
        )
        main.app.state.http_client = self.client

    def tearDown(self):
        self.test_client.__exit__(None, None, None)

    def test_health_and_manifest(self):
        self.assertEqual(self.test_client.get("/health").json(), {"status": "ok"})
        manifest = self.test_client.get("/.well-known/omi-tools.json").json()
        self.assertEqual(len(manifest["tools"]), 3)
        self.assertEqual(
            {tool["name"] for tool in manifest["tools"]},
            {
                "get_upcoming_launches",
                "search_launches",
                "get_launch",
            },
        )

    def test_validation_errors_use_chat_tool_envelope(self):
        response = self.test_client.post(
            "/tools/search_launches",
            json={"uid": "ignored"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["result"])
        self.assertIn("invalid launch request", payload["error"])

    def test_endpoint_ignores_uid(self):
        response = self.test_client.post(
            "/tools/search_launches",
            json={"uid": "not-forwarded", "query": "Starlink"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["error"])
        self.assertIn("Falcon 9", payload["result"])


if __name__ == "__main__":
    unittest.main()
