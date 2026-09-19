"""Hermetic tests for the SEC EDGAR Omi integration."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


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

import sec
from models import (
    ChatToolResponse,
    CompanyRequest,
    FinancialSnapshotRequest,
    RecentFilingsRequest,
)

if _HAS_REAL_FASTAPI and _HAS_REAL_PYDANTIC:
    from fastapi.testclient import TestClient

    import main
else:
    TestClient = None
    main = None


def _ticker_payload():
    return {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {
            "cik_str": 789019,
            "ticker": "MSFT",
            "title": "Microsoft Corporation",
        },
        "2": {"cik_str": 111111, "ticker": "DAL", "title": "Delta Air Lines"},
        "3": {"cik_str": 222222, "ticker": "DLT", "title": "Delta Labs"},
    }


def _submissions_payload():
    return {
        "cik": "0000320193",
        "name": "Apple Inc.",
        "tickers": ["AAPL"],
        "exchanges": ["Nasdaq"],
        "sic": "3571",
        "sicDescription": "Electronic Computers",
        "category": "Large accelerated filer",
        "fiscalYearEnd": "0926",
        "stateOfIncorporationDescription": "CA",
        "website": "https://www.apple.com/",
        "addresses": {
            "business": {
                "street1": "ONE APPLE PARK WAY",
                "city": "CUPERTINO",
                "stateOrCountry": "CA",
                "zipCode": "95014",
            }
        },
        "filings": {
            "recent": {
                "form": ["10-K", "8-K", "10-Q", "10-K"],
                "filingDate": ["2025-10-31", "2025-10-30", "2025-08-01", "2024-11-01"],
                "reportDate": ["2025-09-27", "2025-10-30", "2025-06-28", "2024-09-28"],
                "accessionNumber": [
                    "0000320193-25-000079",
                    "0000320193-25-000077",
                    "0000320193-25-000073",
                    "0000320193-24-000123",
                ],
                "primaryDocument": [
                    "aapl-20250927.htm",
                    "aapl-20251030.htm",
                    "aapl-20250628.htm",
                    "aapl-20240928.htm",
                ],
                "primaryDocDescription": [
                    "10-K",
                    "8-K",
                    "10-Q",
                    "10-K",
                ],
            }
        },
    }


def _facts_payload():
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {
                                "start": "2023-10-01",
                                "end": "2024-09-28",
                                "val": 391035000000,
                                "fy": 2024,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2024-11-01",
                            },
                            {
                                "start": "2024-09-29",
                                "end": "2025-09-27",
                                "val": 416161000000,
                                "fy": 2025,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2025-10-31",
                            },
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {
                        "USD": [
                            {
                                "start": "2024-09-29",
                                "end": "2025-09-27",
                                "val": 112010000000,
                                "form": "10-K",
                                "filed": "2025-10-31",
                            }
                        ]
                    }
                },
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "end": "2025-09-27",
                                "val": 359241000000,
                                "form": "10-K",
                                "filed": "2025-10-31",
                            },
                            {
                                "end": "2024-09-28",
                                "val": 364980000000,
                                "form": "10-K",
                                "filed": "2024-11-01",
                            },
                        ]
                    }
                },
                "EarningsPerShareDiluted": {
                    "units": {
                        "USD/shares": [
                            {
                                "start": "2024-09-29",
                                "end": "2025-09-27",
                                "val": 7.39,
                                "form": "10-K",
                                "filed": "2025-10-31",
                            }
                        ]
                    }
                },
            }
        },
    }


class _FakeResponse:
    def __init__(
        self,
        request,
        *,
        status_code=200,
        payload=None,
        content=b"",
        content_type="application/json",
    ):
        self.request = request
        self.status_code = status_code
        self._payload = payload
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=self.request,
                response=self,
            )

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


def _response(
    request,
    *,
    status_code=200,
    json=None,
    content=b"",
    content_type="application/json",
):
    if _HAS_REAL_HTTPX:
        if json is not None:
            return httpx.Response(
                status_code,
                json=json,
                headers={"content-type": content_type},
                request=request,
            )
        return httpx.Response(
            status_code,
            content=content,
            headers={"content-type": content_type},
            request=request,
        )
    return _FakeResponse(
        request,
        status_code=status_code,
        payload=json,
        content=content,
        content_type=content_type,
    )


class _StdlibClient:
    def __init__(self, handler):
        self.handler = handler

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url):
        return self.handler(types.SimpleNamespace(url=url))


def _client(handler):
    if _HAS_REAL_HTTPX:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return _StdlibClient(handler)


class UtilityTests(unittest.TestCase):
    def test_normalize_cik(self):
        self.assertEqual(sec.normalize_cik("320193"), "0000320193")
        self.assertEqual(sec.normalize_cik("CIK0000320193"), "0000320193")
        with self.assertRaises(ValueError):
            sec.normalize_cik("AAPL")


@unittest.skipUnless(_HAS_REAL_PYDANTIC, "requires the real pydantic package")
class ModelTests(unittest.TestCase):
    def test_chat_response_requires_exactly_one_outcome(self):
        with self.assertRaises(ValueError):
            ChatToolResponse()
        with self.assertRaises(ValueError):
            ChatToolResponse(result="ok", error="bad")

    def test_null_optional_numbers_use_defaults(self):
        self.assertEqual(
            RecentFilingsRequest(company="AAPL", limit=None).limit,
            5,
        )
        self.assertEqual(
            FinancialSnapshotRequest(company="AAPL", years=None).years,
            3,
        )


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        sec._ticker_cache = None

    async def test_profile_resolves_ticker(self):
        def handler(request):
            if str(request.url).endswith("company_tickers.json"):
                return _response(request, json=_ticker_payload())
            return _response(request, json=_submissions_payload())

        async with _client(handler) as client:
            result = await sec.get_company_profile(
                client,
                CompanyRequest(company="AAPL"),
            )

        self.assertIn("Apple Inc.", result)
        self.assertIn("CIK: 0000320193", result)
        self.assertIn("Electronic Computers", result)
        self.assertIn("ONE APPLE PARK WAY", result)

    async def test_profile_accepts_direct_cik(self):
        calls = []

        def handler(request):
            calls.append(str(request.url))
            return _response(request, json=_submissions_payload())

        async with _client(handler) as client:
            result = await sec.get_company_profile(
                client,
                CompanyRequest(company="CIK0000320193"),
            )

        self.assertEqual(len(calls), 1)
        self.assertIn("CIK0000320193.json", calls[0])
        self.assertIn("Apple Inc.", result)

    async def test_ambiguous_company_name_lists_choices(self):
        def handler(request):
            return _response(request, json=_ticker_payload())

        async with _client(handler) as client:
            with self.assertRaisesRegex(sec.SecEdgarError, "Multiple"):
                await sec.get_company_profile(
                    client,
                    CompanyRequest(company="Delta"),
                )

    async def test_recent_filings_filter_and_archive_url(self):
        def handler(request):
            if str(request.url).endswith("company_tickers.json"):
                return _response(request, json=_ticker_payload())
            return _response(request, json=_submissions_payload())

        async with _client(handler) as client:
            result = await sec.list_recent_filings(
                client,
                RecentFilingsRequest(company="AAPL", form_type="10-K", limit=2),
            )

        self.assertIn("2025-10-31", result)
        self.assertIn("2024-11-01", result)
        self.assertNotIn("8-K |", result)
        self.assertIn("/Archives/edgar/data/320193/", result)

    async def test_financial_snapshot_formats_annual_facts(self):
        def handler(request):
            if str(request.url).endswith("company_tickers.json"):
                return _response(request, json=_ticker_payload())
            if "companyfacts" in str(request.url):
                return _response(request, json=_facts_payload())
            return _response(request, json=_submissions_payload())

        async with _client(handler) as client:
            result = await sec.get_financial_snapshot(
                client,
                FinancialSnapshotRequest(company="AAPL", years=2),
            )

        self.assertIn("Revenue:", result)
        self.assertIn("$416.16B", result)
        self.assertIn("Net income:", result)
        self.assertIn("$112.01B", result)
        self.assertIn("Diluted EPS:", result)
        self.assertIn("$7.39", result)
        self.assertIn("2024-09-28", result)
        self.assertIn("not investment advice", result)

    async def test_sec_denial_returns_safe_error(self):
        def handler(request):
            return _response(
                request,
                status_code=403,
                json={"message": "forbidden"},
            )

        async with _client(handler) as client:
            with self.assertRaisesRegex(sec.SecEdgarError, "SEC_USER_AGENT"):
                await sec.get_company_profile(
                    client,
                    CompanyRequest(company="CIK0000320193"),
                )

    async def test_non_json_response_fails_closed(self):
        def handler(request):
            return _response(
                request,
                content=b"<html>not json</html>",
                content_type="text/html",
            )

        async with _client(handler) as client:
            with self.assertRaisesRegex(sec.SecEdgarError, "non-JSON"):
                await sec.get_company_profile(
                    client,
                    CompanyRequest(company="CIK0000320193"),
                )

    async def test_response_size_limit(self):
        def handler(request):
            return _response(
                request,
                content=b"{" + b" " * sec.MAX_RESPONSE_BYTES + b"}",
            )

        async with _client(handler) as client:
            with self.assertRaisesRegex(sec.SecEdgarError, "size limit"):
                await sec.get_company_profile(
                    client,
                    CompanyRequest(company="CIK0000320193"),
                )


@unittest.skipUnless(
    _HAS_REAL_FASTAPI and _HAS_REAL_PYDANTIC and _HAS_REAL_HTTPX,
    "requires the real FastAPI, httpx, and pydantic packages",
)
class EndpointTests(unittest.TestCase):
    def setUp(self):
        sec._ticker_cache = None

        def handler(request):
            if request.url.path.endswith("company_tickers.json"):
                return _response(request, json=_ticker_payload())
            if "companyfacts" in request.url.path:
                return _response(request, json=_facts_payload())
            return _response(request, json=_submissions_payload())

        self.test_client = TestClient(main.app)
        self.test_client.__enter__()
        self.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
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
                "get_company_profile",
                "list_recent_filings",
                "get_financial_snapshot",
            },
        )

    def test_validation_errors_use_chat_tool_envelope(self):
        response = self.test_client.post(
            "/tools/get_company_profile",
            json={"uid": "ignored"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["result"])
        self.assertIn("invalid SEC request", payload["error"])

    def test_endpoint_ignores_uid(self):
        response = self.test_client.post(
            "/tools/get_company_profile",
            json={"uid": "not-forwarded", "company": "AAPL"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsNone(payload["error"])
        self.assertIn("Apple Inc.", payload["result"])

    def test_null_optional_numbers_are_accepted(self):
        filings = self.test_client.post(
            "/tools/list_recent_filings",
            json={"company": "0000320193", "limit": None},
        )
        self.assertEqual(filings.status_code, 200)
        self.assertIsNone(filings.json()["error"])

        facts = self.test_client.post(
            "/tools/get_financial_snapshot",
            json={"company": "0000320193", "years": None},
        )
        self.assertEqual(facts.status_code, 200)
        self.assertIsNone(facts.json()["error"])


if __name__ == "__main__":
    unittest.main()
