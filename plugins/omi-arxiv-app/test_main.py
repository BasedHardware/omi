"""
Hermetic test suite for the Omi arXiv Integration App.

Runs without network or API keys, testing request validation, query building,
error handling, feed parsing, and all FastAPI endpoints.
"""

from pathlib import Path
import sys
import types
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, quote_plus, urlencode, urlsplit
import unittest
import xml.etree.ElementTree as ET

# Ensure plugin directory is on sys.path so main and models can be imported hermetically
PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

# Provide lightweight stubs for third-party runtime dependencies so test_main.py
# runs hermetically on any clean standard library Python environment without
# requiring FastAPI, httpx, or Pydantic to be installed (such as the CI hygiene lane).
if "httpx" not in sys.modules:
    try:
        import httpx  # type: ignore
    except ImportError:
        httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
            def __init__(self, message="", *, request=None, response=None):
                super().__init__(message)
                self.request = request
                self.response = response

        class TimeoutException(HTTPError):
            pass

        class ConnectError(HTTPError):
            pass

        class Request:
            def __init__(self, method, url, params=None, headers=None):
                self.method = method
                if params:
                    self.url = f"{url}?{urlencode(params, quote_via=quote_plus)}"
                else:
                    self.url = url

        class Response:
            def __init__(self, status_code, *, request=None, text="", content=b""):
                self.status_code = status_code
                self.request = request
                self.text = text
                self.content = content

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                self.is_closed = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, *args, **kwargs):
                pass

            async def aclose(self):
                self.is_closed = True

        httpx.HTTPError = HTTPError
        httpx.HTTPStatusError = HTTPStatusError
        httpx.TimeoutException = TimeoutException
        httpx.ConnectError = ConnectError
        httpx.Request = Request
        httpx.Response = Response
        httpx.AsyncClient = AsyncClient
        sys.modules["httpx"] = httpx
else:
    import httpx  # type: ignore

if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
        import fastapi.exceptions  # type: ignore
        import fastapi.responses  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

            def exception_handler(self, *args, **kwargs):
                return lambda f: f

        class FastApiRequest:
            pass

        fastapi.FastAPI = FastAPI
        fastapi.Request = FastApiRequest
        sys.modules["fastapi"] = fastapi

        fastapi_exc = types.ModuleType("fastapi.exceptions")

        class RequestValidationError(Exception):
            pass

        fastapi_exc.RequestValidationError = RequestValidationError
        sys.modules["fastapi.exceptions"] = fastapi_exc
        fastapi.exceptions = fastapi_exc

        fastapi_resp = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            def __init__(self, content="", status_code=200, **kwargs):
                self.status_code = status_code
                self.body = content.encode("utf-8") if isinstance(content, str) else content

        class JSONResponse:
            def __init__(self, content=None, status_code=200, **kwargs):
                self.status_code = status_code
                self.content = content

        fastapi_resp.HTMLResponse = HTMLResponse
        fastapi_resp.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = fastapi_resp
        fastapi.responses = fastapi_resp

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
        from pydantic import ValidationError  # type: ignore
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        class ValidationError(Exception):
            pass

        class _FieldInfo:
            def __init__(self, default=..., description=None):
                self.default = default
                self.description = description

        def Field(default=..., **kwargs):
            return _FieldInfo(default=default, description=kwargs.get("description"))

        class BaseModel:
            def __init__(self, **kwargs):
                cls_fields = {}
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            if isinstance(v, _FieldInfo):
                                cls_fields[k] = v.default
                            else:
                                cls_fields[k] = v
                for k, default_val in cls_fields.items():
                    if default_val is ... and k not in kwargs:
                        raise ValidationError(f"Field '{k}' is required")
                    val = kwargs.get(k, None if default_val is ... else default_val)
                    setattr(self, k, val)
                for k, v in kwargs.items():
                    if k not in cls_fields:
                        setattr(self, k, v)

            def model_dump(self, *args, **kwargs):
                return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

            def dict(self, *args, **kwargs):
                return self.model_dump(*args, **kwargs)

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        pydantic.ValidationError = ValidationError
        sys.modules["pydantic"] = pydantic
else:
    from pydantic import ValidationError  # type: ignore

import main
import models

SAMPLE_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <link href="http://arxiv.org/api/query?search_query=all:transformer" rel="self" type="application/atom+xml"/>
  <title type="html">ArXiv Query: search_query=all:transformer</title>
  <id>http://arxiv.org/api/C5b6nQ9</id>
  <updated>2026-09-16T00:00:00-04:00</updated>
  <entry>
    <id>http://arxiv.org/abs/1706.03762v7</id>
    <updated>2023-08-02T01:09:47Z</updated>
    <published>2017-06-12T17:57:34Z</published>
    <title>Attention Is All You Need</title>
    <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <author><name>Niki Parmar</name></author>
    <category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
    <category term="cs.LG" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2005.14165v4</id>
    <updated>2020-07-22T21:40:48Z</updated>
    <published>2020-05-28T19:40:48Z</published>
    <title>Language Models are Few-Shot Learners</title>
    <summary>Recent work has demonstrated substantial gains on many NLP tasks and benchmarks by pre-training on a large corpus of text.</summary>
    <author><name>Tom B. Brown</name></author>
    <author><name>Benjamin Mann</name></author>
    <category term="cs.CL" scheme="http://arxiv.org/schemas/atom"/>
  </entry>
</feed>
"""

EMPTY_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title type="html">ArXiv Query: search_query=nonexistent</title>
  <updated>2026-09-16T00:00:00-04:00</updated>
</feed>
"""

SPARSE_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.99999</id>
  </entry>
</feed>
"""


def _encoded_search_query(params: dict) -> str:
    request = httpx.Request("GET", main.ARXIV_API_URL, params=params)
    return urlsplit(str(request.url)).query


class BuildSearchQueryTest(unittest.TestCase):
    """Preserve existing encoding contract tests."""

    def test_single_word_query_reaches_arxiv_unmangled(self):
        query = main._build_search_query({"query": "transformer"})
        encoded = _encoded_search_query({"search_query": query})
        self.assertEqual(parse_qs(encoded)["search_query"], ["all:transformer"])

    def test_multi_word_query_is_plus_joined_not_percent_2b(self):
        query = main._build_search_query({"query": "machine learning"})
        encoded = _encoded_search_query({"search_query": query})
        self.assertIn("search_query=all%3Amachine+learning", encoded)
        self.assertNotIn("%2B", encoded)
        self.assertEqual(parse_qs(encoded)["search_query"], ["all:machine learning"])

    def test_combined_fields_use_and_not_percent_2b(self):
        query = main._build_search_query({"query": "transformer", "title": "attention"})
        encoded = _encoded_search_query({"search_query": query})
        self.assertIn("search_query=all%3Atransformer+AND+ti%3Aattention", encoded)
        self.assertNotIn("%2B", encoded)

    def test_author_search_endpoint_query_is_not_double_encoded(self):
        encoded = _encoded_search_query({"search_query": f"au:{main._clean_text('Yann LeCun')}"})
        self.assertIn("search_query=au%3AYann+LeCun", encoded)
        self.assertNotIn("%2B", encoded)


class ModelValidationTests(unittest.TestCase):
    """Test Pydantic model validation and defaults."""

    def test_search_papers_request_defaults(self):
        req = models.SearchPapersRequest()
        self.assertIsNone(req.query)
        self.assertIsNone(req.title)
        self.assertIsNone(req.author)
        self.assertIsNone(req.category)
        self.assertEqual(req.sort_by, "relevance")
        self.assertEqual(req.limit, 5)

    def test_search_papers_request_with_params(self):
        req = models.SearchPapersRequest(
            query="quantum",
            category="quant-ph",
            sort_by="submittedDate",
            limit=8,
        )
        self.assertEqual(req.query, "quantum")
        self.assertEqual(req.category, "quant-ph")
        self.assertEqual(req.sort_by, "submittedDate")
        self.assertEqual(req.limit, 8)

    def test_get_paper_details_request_valid(self):
        req = models.GetPaperDetailsRequest(paper_id="2401.01234")
        self.assertEqual(req.paper_id, "2401.01234")

    def test_get_paper_details_request_missing_id(self):
        with self.assertRaises(ValidationError):
            models.GetPaperDetailsRequest()

    def test_search_author_request_valid(self):
        req = models.SearchAuthorRequest(author="Geoffrey Hinton", limit=3)
        self.assertEqual(req.author, "Geoffrey Hinton")
        self.assertEqual(req.limit, 3)

    def test_search_author_request_missing_author(self):
        with self.assertRaises(ValidationError):
            models.SearchAuthorRequest()


class HelperFunctionsTests(unittest.TestCase):
    """Test internal helper functions and boundary sanitizers."""

    def test_clean_text(self):
        self.assertEqual(main._clean_text(None), "")
        self.assertEqual(main._clean_text(""), "")
        self.assertEqual(main._clean_text("  hello   world  "), "hello world")
        self.assertEqual(main._clean_text("Cats &amp; Dogs &lt;3"), "Cats & Dogs <3")

    def test_safe_limit(self):
        self.assertEqual(main._safe_limit(None), 5)
        self.assertEqual(main._safe_limit(""), 5)
        self.assertEqual(main._safe_limit("7"), 7)
        self.assertEqual(main._safe_limit(0), 1)
        self.assertEqual(main._safe_limit(-5), 1)
        self.assertEqual(main._safe_limit(100), 10)
        self.assertEqual(main._safe_limit("invalid"), 5)

    def test_safe_category(self):
        self.assertEqual(main._safe_category("cs.AI"), "cs.ai")
        self.assertEqual(main._safe_category("stat.ML"), "stat.ml")
        self.assertEqual(main._safe_category("quant-ph"), "quant-ph")
        self.assertEqual(main._safe_category("INVALID;DROP TABLE"), "")
        self.assertEqual(main._safe_category(None), "")

    def test_safe_sort(self):
        self.assertEqual(main._safe_sort("relevance"), "relevance")
        self.assertEqual(main._safe_sort("lastUpdatedDate"), "lastUpdatedDate")
        self.assertEqual(main._safe_sort("submittedDate"), "submittedDate")
        self.assertEqual(main._safe_sort("invalid_sort"), "relevance")
        self.assertEqual(main._safe_sort(None), "relevance")

    def test_safe_paper_id(self):
        self.assertEqual(main._safe_paper_id("2401.01234"), "2401.01234")
        self.assertEqual(main._safe_paper_id("2401.01234v2"), "2401.01234")
        self.assertEqual(main._safe_paper_id("arXiv:2401.01234"), "2401.01234")
        self.assertEqual(main._safe_paper_id("https://arxiv.org/abs/2401.01234"), "2401.01234")
        self.assertEqual(main._safe_paper_id("http://arxiv.org/abs/2401.01234v1"), "2401.01234")
        self.assertEqual(main._safe_paper_id("cs/9901001"), "cs/9901001")
        self.assertEqual(main._safe_paper_id("math.GT/0309136v1"), "math.GT/0309136")
        self.assertIsNone(main._safe_paper_id("not-an-id"))
        self.assertIsNone(main._safe_paper_id(""))
        self.assertIsNone(main._safe_paper_id(None))

    def test_date_only(self):
        self.assertEqual(main._date_only("2026-09-16T10:00:00Z"), "2026-09-16")
        self.assertEqual(main._date_only("2026-09-16T10:00:00+03:00"), "2026-09-16")
        self.assertEqual(main._date_only("2026-09-16"), "2026-09-16")
        self.assertEqual(main._date_only("invalid"), "invalid")
        self.assertEqual(main._date_only(""), "unknown date")
        self.assertEqual(main._date_only(None), "unknown date")

    def test_arxiv_http_error_message(self):
        mock_resp_429 = httpx.Response(429, request=httpx.Request("GET", "http://test"))
        exc_429 = httpx.HTTPStatusError("rate limited", request=mock_resp_429.request, response=mock_resp_429)
        self.assertIn("rate limiting", main._arxiv_http_error_message(exc_429))

        mock_resp_503 = httpx.Response(503, request=httpx.Request("GET", "http://test"))
        exc_503 = httpx.HTTPStatusError("unavailable", request=mock_resp_503.request, response=mock_resp_503)
        self.assertIn("temporarily unavailable", main._arxiv_http_error_message(exc_503))

        mock_resp_500 = httpx.Response(500, request=httpx.Request("GET", "http://test"))
        exc_500 = httpx.HTTPStatusError("server error", request=mock_resp_500.request, response=mock_resp_500)
        self.assertIn("HTTP 500", main._arxiv_http_error_message(exc_500))

    def test_format_entry_sparse(self):
        root = ET.fromstring(SPARSE_ATOM_FEED)
        entry = root.find("atom:entry", main.ATOM_NS)
        formatted = main._format_entry(entry, 1)
        self.assertIn("1. Untitled", formatted)
        self.assertIn("unknown authors", formatted)
        self.assertIn("2401.99999", formatted)


class EndpointAsyncUnitTests(unittest.IsolatedAsyncioTestCase):
    """Test FastAPI application endpoints in isolation."""

    async def test_root_endpoint(self):
        res = await main.root()
        self.assertEqual(res.status_code, 200)
        self.assertIn("arXiv x Omi", res.body.decode("utf-8"))

    async def test_health_endpoint(self):
        res = await main.health()
        self.assertEqual(res, {"status": "ok"})

    async def test_manifest_endpoint(self):
        manifest = await main.get_omi_tools_manifest()
        self.assertIn("tools", manifest)
        tool_names = [t["name"] for t in manifest["tools"]]
        self.assertIn("search_papers", tool_names)
        self.assertIn("get_paper_details", tool_names)
        self.assertIn("search_author", tool_names)

    async def test_search_papers_success(self):
        req = models.SearchPapersRequest(query="transformer")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=SAMPLE_ATOM_FEED)):
            res = await main.search_papers(req)

        self.assertIsNone(res.error)
        self.assertIsNotNone(res.result)
        self.assertIn("Attention Is All You Need", res.result)
        self.assertIn("Ashish Vaswani", res.result)
        self.assertIn("1706.03762v7", res.result)
        self.assertIn("Language Models are Few-Shot Learners", res.result)

    async def test_search_papers_no_results(self):
        req = models.SearchPapersRequest(query="xyznonexistenttopic999")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=EMPTY_ATOM_FEED)):
            res = await main.search_papers(req)

        self.assertIsNone(res.error)
        self.assertEqual(res.result, "No arXiv papers found.")

    async def test_search_papers_missing_all_criteria(self):
        req = models.SearchPapersRequest()
        res = await main.search_papers(req)
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Provide query, title, author, or category.")

    async def test_search_papers_rate_limited(self):
        req = models.SearchPapersRequest(query="attention")
        mock_resp = httpx.Response(429, request=httpx.Request("GET", "http://test"))
        exc = httpx.HTTPStatusError("429", request=mock_resp.request, response=mock_resp)
        with patch.object(main, "_request_arxiv", new=AsyncMock(side_effect=exc)):
            res = await main.search_papers(req)

        self.assertIsNone(res.result)
        self.assertIn("rate limiting", res.error)

    async def test_search_papers_service_unavailable(self):
        req = models.SearchPapersRequest(query="attention")
        mock_resp = httpx.Response(503, request=httpx.Request("GET", "http://test"))
        exc = httpx.HTTPStatusError("503", request=mock_resp.request, response=mock_resp)
        with patch.object(main, "_request_arxiv", new=AsyncMock(side_effect=exc)):
            res = await main.search_papers(req)

        self.assertIsNone(res.result)
        self.assertIn("temporarily unavailable", res.error)

    async def test_search_papers_timeout(self):
        req = models.SearchPapersRequest(query="attention")
        with patch.object(main, "_request_arxiv", new=AsyncMock(side_effect=httpx.TimeoutException("timeout"))):
            res = await main.search_papers(req)

        self.assertIsNone(res.result)
        self.assertIn("timed out", res.error)

    async def test_search_papers_unreadable_xml(self):
        req = models.SearchPapersRequest(query="attention")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value="NOT XML")):
            res = await main.search_papers(req)

        self.assertIsNone(res.result)
        self.assertIn("unreadable Atom feed", res.error)

    async def test_get_paper_details_success(self):
        req = models.GetPaperDetailsRequest(paper_id="1706.03762")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=SAMPLE_ATOM_FEED)):
            res = await main.get_paper_details(req)

        self.assertIsNone(res.error)
        self.assertIn("Attention Is All You Need", res.result)
        self.assertIn("Ashish Vaswani", res.result)

    async def test_get_paper_details_not_found(self):
        req = models.GetPaperDetailsRequest(paper_id="2401.99999")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=EMPTY_ATOM_FEED)):
            res = await main.get_paper_details(req)

        self.assertIsNone(res.error)
        self.assertIn("No arXiv paper found for 2401.99999.", res.result)

    async def test_get_paper_details_invalid_id(self):
        req = models.GetPaperDetailsRequest(paper_id="invalid-not-an-arxiv-id")
        res = await main.get_paper_details(req)
        self.assertIsNone(res.result)
        self.assertIn("Provide a valid arXiv paper ID", res.error)

    async def test_get_paper_details_versioned_id(self):
        req = models.GetPaperDetailsRequest(paper_id="1706.03762v7")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=SAMPLE_ATOM_FEED)) as mock_req:
            res = await main.get_paper_details(req)
            mock_req.assert_called_once_with({"id_list": "1706.03762", "max_results": 1})

        self.assertIsNone(res.error)
        self.assertIn("Attention Is All You Need", res.result)

    async def test_get_paper_details_url_id(self):
        req = models.GetPaperDetailsRequest(paper_id="https://arxiv.org/abs/1706.03762")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=SAMPLE_ATOM_FEED)) as mock_req:
            res = await main.get_paper_details(req)
            mock_req.assert_called_once_with({"id_list": "1706.03762", "max_results": 1})

        self.assertIsNone(res.error)

    async def test_search_author_success(self):
        req = models.SearchAuthorRequest(author="Ashish Vaswani")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=SAMPLE_ATOM_FEED)):
            res = await main.search_author(req)

        self.assertIsNone(res.error)
        self.assertIn("Recent arXiv papers by Ashish Vaswani:", res.result)
        self.assertIn("Attention Is All You Need", res.result)

    async def test_search_author_empty_results(self):
        req = models.SearchAuthorRequest(author="UnknownAuthor99999")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=EMPTY_ATOM_FEED)):
            res = await main.search_author(req)

        self.assertIsNone(res.error)
        self.assertIn("No arXiv papers found for author UnknownAuthor99999.", res.result)

    async def test_search_author_missing_name(self):
        req = models.SearchAuthorRequest(author="   ")
        res = await main.search_author(req)
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Missing required field: author")

    async def test_search_author_timeout(self):
        req = models.SearchAuthorRequest(author="Vaswani")
        with patch.object(main, "_request_arxiv", new=AsyncMock(side_effect=httpx.TimeoutException("timed out"))):
            res = await main.search_author(req)

        self.assertIsNone(res.result)
        self.assertIn("timed out", res.error)


if __name__ == "__main__":
    unittest.main()
