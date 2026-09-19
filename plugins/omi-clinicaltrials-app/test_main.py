"""Hermetic tests for the ClinicalTrials.gov Omi integration."""

import json
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

import clinicaltrials
from models import (
    ChatToolResponse,
    RecruitingTrialsRequest,
    SearchTrialsRequest,
    TrialDetailsRequest,
)

if _HAS_REAL_FASTAPI and _HAS_REAL_PYDANTIC:
    from fastapi.testclient import TestClient

    import main
else:
    TestClient = None
    main = None


SEARCH_PAYLOAD = {
    "totalCount": 2,
    "studies": [
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT00000001",
                    "briefTitle": "A study of treatment A",
                },
                "statusModule": {
                    "overallStatus": "RECRUITING",
                },
                "conditionsModule": {"conditions": ["Type 2 Diabetes"]},
                "designModule": {"phases": ["PHASE2"]},
                "contactsLocationsModule": {
                    "locations": [
                        {
                            "facility": "Example Hospital",
                            "city": "Boston",
                            "state": "Massachusetts",
                            "country": "United States",
                        }
                    ]
                },
            }
        },
        {
            "protocolSection": {
                "identificationModule": {
                    "nctId": "NCT00000002",
                    "briefTitle": "A study of treatment B",
                },
                "statusModule": {
                    "overallStatus": "RECRUITING",
                },
                "conditionsModule": {"conditions": ["Type 2 Diabetes"]},
                "designModule": {"phases": ["PHASE3"]},
                "contactsLocationsModule": {
                    "locations": [
                        {
                            "facility": "Another Hospital",
                            "city": "Chicago",
                            "state": "Illinois",
                            "country": "United States",
                        }
                    ]
                },
            }
        },
    ],
}

DETAIL_PAYLOAD = {
    "protocolSection": {
        "identificationModule": {
            "nctId": "NCT00000001",
            "officialTitle": "A randomized study of treatment A",
        },
        "statusModule": {
            "overallStatus": "RECRUITING",
            "startDateStruct": {"date": "2026-01-01"},
            "primaryCompletionDateStruct": {"date": "2027-01-01"},
        },
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example University"}},
        "descriptionModule": {"briefSummary": "A short public study summary."},
        "conditionsModule": {"conditions": ["Type 2 Diabetes"]},
        "designModule": {
            "studyType": "INTERVENTIONAL",
            "phases": ["PHASE2"],
            "enrollmentInfo": {"count": 120, "type": "ESTIMATED"},
        },
        "eligibilityModule": {"sex": "ALL", "minimumAge": "18 Years"},
        "contactsLocationsModule": {
            "locations": [
                {
                    "facility": "Example Hospital",
                    "city": "Boston",
                    "country": "United States",
                }
            ]
        },
    }
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
        return httpx.Response(
            status_code,
            content=content,
            request=request,
        )
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


@unittest.skipUnless(_HAS_REAL_PYDANTIC, "requires the real pydantic package")
class ModelTests(unittest.TestCase):
    def test_search_requires_a_term(self):
        with self.assertRaises(ValueError):
            SearchTrialsRequest()

    def test_detail_normalizes_nct_id(self):
        request = TrialDetailsRequest(nct_id="nct04280705")
        self.assertEqual(request.nct_id, "NCT04280705")

    def test_chat_response_requires_exactly_one_outcome(self):
        with self.assertRaises(ValueError):
            ChatToolResponse()
        with self.assertRaises(ValueError):
            ChatToolResponse(result="ok", error="bad")


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_builds_provider_query_and_formats_results(self):
        seen = {}

        def handler(request):
            seen.update(parse_qs(request.url.query.decode()))
            return _response(200, json=SEARCH_PAYLOAD, request=request)

        async with _client(handler) as client:
            result = await clinicaltrials.search_trials(
                client,
                SearchTrialsRequest(
                    condition="type 2 diabetes",
                    location="Boston",
                    phase="PHASE2",
                    page_size=2,
                ),
            )

        self.assertEqual(seen["query.cond"], ["type 2 diabetes"])
        self.assertEqual(seen["query.locn"], ["Boston"])
        self.assertEqual(seen["filter.overallStatus"], ["RECRUITING"])
        self.assertEqual(seen["filter.advanced"], ["AREA[Phase](PHASE2)"])
        self.assertNotIn("uid", seen)
        self.assertIn("Found 2 matching studies", result)
        self.assertIn("NCT00000001", result)
        self.assertIn("Example Hospital, Boston", result)
        self.assertIn("not medical advice", result)

    async def test_search_empty_result_is_successful(self):
        def handler(request):
            return _response(
                200, json={"totalCount": 0, "studies": []}, request=request
            )

        async with _client(handler) as client:
            result = await clinicaltrials.search_trials(
                client,
                SearchTrialsRequest(condition="a very rare condition"),
            )

        self.assertIn("No ClinicalTrials.gov studies matched", result)

    async def test_get_trial_formats_details(self):
        def handler(request):
            self.assertTrue(request.url.path.endswith("/NCT00000001"))
            return _response(200, json=DETAIL_PAYLOAD, request=request)

        async with _client(handler) as client:
            result = await clinicaltrials.get_trial(client, "NCT00000001")

        self.assertIn("NCT00000001", result)
        self.assertIn("Example University", result)
        self.assertIn("Enrollment: 120", result)
        self.assertIn("https://clinicaltrials.gov/study/NCT00000001", result)

    async def test_provider_404_returns_safe_error(self):
        def handler(request):
            return _response(404, json={"error": "not found"}, request=request)

        async with _client(handler) as client:
            with self.assertRaisesRegex(
                clinicaltrials.ClinicalTrialsError, "study not found"
            ):
                await clinicaltrials.get_trial(client, "NCT00000001")

    async def test_malformed_payload_fails_closed(self):
        def handler(request):
            return _response(200, content=b"[]", request=request)

        async with _client(handler) as client:
            with self.assertRaisesRegex(
                clinicaltrials.ClinicalTrialsError, "unexpected response shape"
            ):
                await clinicaltrials.get_trial(client, "NCT00000001")

    async def test_response_size_limit(self):
        def handler(request):
            return _response(
                200,
                content=b"{" + b" " * clinicaltrials.MAX_RESPONSE_BYTES + b"}",
                request=request,
            )

        async with _client(handler) as client:
            with self.assertRaisesRegex(
                clinicaltrials.ClinicalTrialsError, "size limit"
            ):
                await clinicaltrials.get_trial(client, "NCT00000001")


@unittest.skipUnless(
    _HAS_REAL_FASTAPI and _HAS_REAL_PYDANTIC and _HAS_REAL_HTTPX,
    "requires the real FastAPI, httpx, and pydantic packages",
)
class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.handler = lambda request: _response(
            200, json=SEARCH_PAYLOAD, request=request
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
                "search_clinical_trials",
                "find_recruiting_trials",
                "get_clinical_trial",
            },
        )

    def test_validation_errors_use_chat_tool_envelope(self):
        response = self.test_client.post(
            "/tools/search_clinical_trials", json={"uid": "ignored"}
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["result"])
        self.assertIn("invalid clinical-trials request", payload["error"])

    def test_endpoint_returns_result_and_ignores_uid(self):
        response = self.test_client.post(
            "/tools/search_clinical_trials",
            json={"uid": "not-forwarded", "condition": "diabetes"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["error"])
        self.assertIn("NCT00000001", payload["result"])


if __name__ == "__main__":
    unittest.main()
