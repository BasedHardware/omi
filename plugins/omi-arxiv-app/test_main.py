"""
Hermetic regression and unit tests for plugins/omi-arxiv-app.

Standard library only: httpx, fastapi, and pydantic are replaced with minimal
stubs before importing the modules under test so the suite runs without
site-packages (the manifest lane runs plain python3 -S).

Covers:
- BasedHardware/omi#14181: typed request validation, defensive Atom XML parsing,
  rate-limit error mapping, and ToU throttle timestamp preservation.
- Preserves original regression coverage for httpx URL query string encoding.
"""

import asyncio
from datetime import datetime
import os
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, quote_plus, urlencode, urlsplit
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_STUBBED_MODULES = ("httpx", "fastapi", "fastapi.responses", "fastapi.exceptions", "pydantic")


def _install_module_stubs():
    httpx = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message="", *, request=None, response=None):
            super().__init__(message)
            self.request = request
            self.response = response or types.SimpleNamespace(status_code=500)

    class ConnectError(HTTPError):
        pass

    class TimeoutException(HTTPError):
        pass

    class Request:
        def __init__(self, method, url, params=None):
            self.method = method
            if params:
                query_str = urlencode(params, quote_via=quote_plus)
                self.url = f"{url}?{query_str}"
            else:
                self.url = url

    class Response:
        def __init__(self, status_code=200, *, request=None, text=""):
            self.status_code = status_code
            self.request = request or Request("GET", "http://test")
            self.text = text

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            self.is_closed = True
            return False

        async def aclose(self):
            self.is_closed = True

        async def get(self, *args, **kwargs):
            raise AssertionError("tests must stub _request_arxiv; no network allowed")

    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.ConnectError = ConnectError
    httpx.TimeoutException = TimeoutException
    httpx.Request = Request
    httpx.Response = Response
    httpx.AsyncClient = _AsyncClient
    sys.modules["httpx"] = httpx

    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            self.routes = []

        def get(self, path, **kwargs):
            return lambda f: f

        def post(self, path, **kwargs):
            return lambda f: f

        def exception_handler(self, exc_class):
            return lambda f: f

    class FastAPIRequest:
        pass

    fastapi.FastAPI = FastAPI
    fastapi.Request = FastAPIRequest
    sys.modules["fastapi"] = fastapi

    fastapi_responses = types.ModuleType("fastapi.responses")

    class HTMLResponse:
        def __init__(self, content="", status_code=200):
            self.body = content.encode("utf-8") if isinstance(content, str) else content
            self.status_code = status_code

    class JSONResponse:
        def __init__(self, content=None, status_code=200):
            self.content = content
            self.status_code = status_code

    fastapi_responses.HTMLResponse = HTMLResponse
    fastapi_responses.JSONResponse = JSONResponse
    sys.modules["fastapi.responses"] = fastapi_responses

    fastapi_exceptions = types.ModuleType("fastapi.exceptions")

    class RequestValidationError(Exception):
        def __init__(self, errors=None):
            self._errors = errors or []

        def errors(self):
            return self._errors

    fastapi_exceptions.RequestValidationError = RequestValidationError
    sys.modules["fastapi.exceptions"] = fastapi_exceptions

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)
            for name in dir(type(self)):
                if not name.startswith("_") and not hasattr(self, name):
                    val = getattr(type(self), name)
                    if not callable(val):
                        setattr(self, name, val)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def Field(default=None, **kwargs):
        if "default_factory" in kwargs:
            return kwargs["default_factory"]()
        return default

    pydantic.BaseModel = BaseModel
    pydantic.Field = Field
    sys.modules["pydantic"] = pydantic


_saved_modules = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
_install_module_stubs()
try:
    import models  # noqa: E402
    import main  # noqa: E402
finally:
    for _name, _original in _saved_modules.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original
    del _name, _original, _saved_modules

# Expose httpx module reference from main for test helpers and exact exception identity
httpx = main.httpx


SAMPLE_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>https://arxiv.org/abs/1706.03762v7</id>
    <published>2017-06-12T17:57:34Z</published>
    <updated>2023-08-02T01:09:44Z</updated>
    <title>Attention Is All You Need</title>
    <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.</summary>
    <author><name>Ashish Vaswani</name></author>
    <author><name>Noam Shazeer</name></author>
    <author><name>Niki Parmar</name></author>
    <category term="cs.CL"/>
    <category term="cs.LG"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2005.14165v4</id>
    <published>2020-05-28T17:50:00Z</published>
    <updated>2020-07-22T17:50:00Z</updated>
    <title>Language Models are Few-Shot Learners</title>
    <summary>Recent work has demonstrated substantial gains on many NLP tasks.</summary>
    <author><name>Tom B. Brown</name></author>
    <category term="cs.CL"/>
  </entry>
</feed>
"""

SPARSE_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://arxiv.org/abs/2401.99999</id>
    <published>invalid-date-format</published>
  </entry>
</feed>
"""

EMPTY_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>
"""


def _run(coro):
    return asyncio.run(coro)


def _encoded_search_query(params: dict) -> str:
    """Round-trips params through httpx's own request builder, exactly like
    _request_arxiv does, so the test exercises the real encoding path."""
    request = httpx.Request("GET", main.ARXIV_API_URL, params=params)
    return urlsplit(str(request.url)).query


class BuildSearchQueryTest(unittest.TestCase):
    """Preserve existing regression tests for query encoding."""

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


class SanitizerAndHelperTests(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(main._clean_text(None), "")
        self.assertEqual(main._clean_text(""), "")
        self.assertEqual(main._clean_text("  hello   world  "), "hello world")
        self.assertEqual(main._clean_text("&lt;test&gt;"), "<test>")
        self.assertEqual(main._clean_text(12345), "12345")

    def test_safe_limit(self):
        self.assertEqual(main._safe_limit(None, 5), 5)
        self.assertEqual(main._safe_limit("", 5), 5)
        self.assertEqual(main._safe_limit("invalid", 5), 5)
        self.assertEqual(main._safe_limit(0), 1)
        self.assertEqual(main._safe_limit(-10), 1)
        self.assertEqual(main._safe_limit(7), 7)
        self.assertEqual(main._safe_limit(100), 10)
        self.assertEqual(main._safe_limit("8"), 8)

    def test_safe_category(self):
        self.assertEqual(main._safe_category("cs.AI"), "cs.ai")
        self.assertEqual(main._safe_category("stat.ML"), "stat.ml")
        self.assertEqual(main._safe_category("quant-ph"), "quant-ph")
        self.assertEqual(main._safe_category("  math.PR  "), "math.pr")
        self.assertEqual(main._safe_category("invalid_cat;DROP TABLE"), "")
        self.assertEqual(main._safe_category(None), "")

    def test_safe_sort(self):
        self.assertEqual(main._safe_sort("relevance"), "relevance")
        self.assertEqual(main._safe_sort("lastUpdatedDate"), "lastUpdatedDate")
        self.assertEqual(main._safe_sort("submittedDate"), "submittedDate")
        self.assertEqual(main._safe_sort("unknown"), "relevance")
        self.assertEqual(main._safe_sort(None), "relevance")

    def test_safe_paper_id(self):
        self.assertEqual(main._safe_paper_id("2401.01234"), "2401.01234")
        self.assertEqual(main._safe_paper_id("1706.03762v7"), "1706.03762")
        self.assertEqual(main._safe_paper_id("arXiv:2401.01234"), "2401.01234")
        self.assertEqual(main._safe_paper_id("https://arxiv.org/abs/2401.01234"), "2401.01234")
        self.assertEqual(main._safe_paper_id("http://arxiv.org/abs/cs/9901001v2"), "cs/9901001")
        self.assertEqual(main._safe_paper_id("cs/9901001"), "cs/9901001")
        self.assertIsNone(main._safe_paper_id("invalid-id"))
        self.assertIsNone(main._safe_paper_id(""))
        self.assertIsNone(main._safe_paper_id(None))

    def test_date_only(self):
        self.assertEqual(main._date_only("2023-08-02T01:09:44Z"), "2023-08-02")
        self.assertEqual(main._date_only("2017-06-12"), "2017-06-12")
        self.assertEqual(main._date_only("short"), "short")
        self.assertEqual(main._date_only(None), "unknown date")
        self.assertEqual(main._date_only(""), "unknown date")


class AtomFeedParsingTests(unittest.TestCase):
    def test_parse_entries_valid(self):
        entries = main._parse_entries(SAMPLE_ATOM_FEED)
        self.assertEqual(len(entries), 2)

    def test_parse_entries_empty_and_whitespace(self):
        self.assertEqual(main._parse_entries(EMPTY_ATOM_FEED), [])
        self.assertEqual(main._parse_entries(""), [])
        self.assertEqual(main._parse_entries("   "), [])

    def test_format_entry_full(self):
        root = ET.fromstring(SAMPLE_ATOM_FEED)
        entry = root.find("atom:entry", main.ATOM_NS)
        formatted = main._format_entry(entry, 1)
        self.assertIn("1. Attention Is All You Need", formatted)
        self.assertIn("arXiv: 1706.03762v7", formatted)
        self.assertIn("Published: 2017-06-12", formatted)
        self.assertIn("Ashish Vaswani", formatted)
        self.assertIn("Categories: cs.CL, cs.LG", formatted)
        self.assertIn("https://arxiv.org/abs/1706.03762v7", formatted)

    def test_format_entry_sparse(self):
        root = ET.fromstring(SPARSE_ATOM_FEED)
        entry = root.find("atom:entry", main.ATOM_NS)
        formatted = main._format_entry(entry, 1)
        self.assertIn("1. Untitled", formatted)
        self.assertIn("unknown authors", formatted)
        self.assertIn("2401.99999", formatted)

    def test_format_entry_long_summary_truncated(self):
        long_summary = "a" * 600
        feed = f"""<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <entry>
            <id>https://arxiv.org/abs/2401.12345</id>
            <summary>{long_summary}</summary>
          </entry>
        </feed>"""
        root = ET.fromstring(feed)
        entry = root.find("atom:entry", main.ATOM_NS)
        formatted = main._format_entry(entry, 1)
        self.assertIn("...", formatted)

    def test_entry_arxiv_id_fallback(self):
        feed = """<entry xmlns="http://www.w3.org/2005/Atom"></entry>"""
        entry = ET.fromstring(feed)
        self.assertEqual(main._entry_arxiv_id(entry), "unknown")


class ErrorMessageTests(unittest.TestCase):
    def test_arxiv_http_error_message(self):
        resp_429 = types.SimpleNamespace(status_code=429)
        exc_429 = httpx.HTTPStatusError("rate limited", response=resp_429)
        self.assertIn("rate limiting", main._arxiv_http_error_message(exc_429))

        resp_503 = types.SimpleNamespace(status_code=503)
        exc_503 = httpx.HTTPStatusError("unavailable", response=resp_503)
        self.assertIn("temporarily unavailable", main._arxiv_http_error_message(exc_503))

        resp_500 = types.SimpleNamespace(status_code=500)
        exc_500 = httpx.HTTPStatusError("server error", response=resp_500)
        self.assertIn("HTTP 500", main._arxiv_http_error_message(exc_500))


class ModelValidationTests(unittest.TestCase):
    def test_search_papers_request_defaults(self):
        req = models.SearchPapersRequest()
        self.assertIsNone(req.query)
        self.assertEqual(req.sort_by, "relevance")
        self.assertEqual(req.limit, 5)

    def test_get_paper_details_request(self):
        req = models.GetPaperDetailsRequest(paper_id="2401.01234")
        self.assertEqual(req.paper_id, "2401.01234")

    def test_search_author_request(self):
        req = models.SearchAuthorRequest(author="Yann LeCun")
        self.assertEqual(req.author, "Yann LeCun")
        self.assertEqual(req.limit, 5)

    def test_validation_exception_handler(self):
        exc = types.SimpleNamespace(
            errors=lambda: [{"loc": ["body", "limit"], "msg": "Input should be a valid integer"}]
        )
        res = _run(main.validation_exception_handler(types.SimpleNamespace(), exc))
        self.assertEqual(res.status_code, 200)
        self.assertIn("invalid tool request: limit:", res.content["error"])


class EndpointUnitTests(unittest.TestCase):
    def test_root_endpoint(self):
        res = _run(main.root())
        self.assertEqual(res.status_code, 200)
        self.assertIn("arXiv x Omi", res.body.decode("utf-8"))

    def test_health_endpoint(self):
        res = _run(main.health())
        self.assertEqual(res, {"status": "ok"})

    def test_manifest_endpoint(self):
        manifest = _run(main.get_omi_tools_manifest())
        self.assertIn("tools", manifest)
        tool_names = [t["name"] for t in manifest["tools"]]
        self.assertIn("search_papers", tool_names)
        self.assertIn("get_paper_details", tool_names)
        self.assertIn("search_author", tool_names)

    def test_search_papers_success(self):
        req = models.SearchPapersRequest(query="transformer")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=SAMPLE_ATOM_FEED)):
            res = _run(main.search_papers(req))

        self.assertIsNone(res.error)
        self.assertIsNotNone(res.result)
        self.assertIn("Attention Is All You Need", res.result)
        self.assertIn("Ashish Vaswani", res.result)
        self.assertIn("1706.03762v7", res.result)

    def test_search_papers_no_results(self):
        req = models.SearchPapersRequest(query="nonexistentquery999")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=EMPTY_ATOM_FEED)):
            res = _run(main.search_papers(req))

        self.assertIsNone(res.error)
        self.assertEqual(res.result, "No arXiv papers found.")

    def test_search_papers_missing_all_criteria(self):
        req = models.SearchPapersRequest()
        res = _run(main.search_papers(req))
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Provide query, title, author, or category.")

    def test_search_papers_rate_limited(self):
        req = models.SearchPapersRequest(query="attention")
        resp = types.SimpleNamespace(status_code=429)
        exc = httpx.HTTPStatusError("429", response=resp)
        with patch.object(main, "_request_arxiv", new=AsyncMock(side_effect=exc)):
            res = _run(main.search_papers(req))

        self.assertIsNone(res.result)
        self.assertIn("rate limiting", res.error)

    def test_search_papers_service_unavailable(self):
        req = models.SearchPapersRequest(query="attention")
        resp = types.SimpleNamespace(status_code=503)
        exc = httpx.HTTPStatusError("503", response=resp)
        with patch.object(main, "_request_arxiv", new=AsyncMock(side_effect=exc)):
            res = _run(main.search_papers(req))

        self.assertIsNone(res.result)
        self.assertIn("temporarily unavailable", res.error)

    def test_search_papers_timeout(self):
        req = models.SearchPapersRequest(query="attention")
        with patch.object(main, "_request_arxiv", new=AsyncMock(side_effect=httpx.TimeoutException("timed out"))):
            res = _run(main.search_papers(req))

        self.assertIsNone(res.result)
        self.assertIn("arXiv search failed: timed out", res.error)

    def test_search_papers_unreadable_xml(self):
        req = models.SearchPapersRequest(query="attention")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value="NOT XML")):
            res = _run(main.search_papers(req))

        self.assertIsNone(res.result)
        self.assertIn("unreadable Atom feed", res.error)

    def test_search_papers_none_and_dict_payloads(self):
        res = _run(main.search_papers(None))
        self.assertEqual(res.error, "Provide query, title, author, or category.")

        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=SAMPLE_ATOM_FEED)):
            res_dict = _run(main.search_papers({"query": "transformer"}))
            self.assertIn("Attention Is All You Need", res_dict.result)

    def test_get_paper_details_success(self):
        req = models.GetPaperDetailsRequest(paper_id="1706.03762")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=SAMPLE_ATOM_FEED)):
            res = _run(main.get_paper_details(req))

        self.assertIsNone(res.error)
        self.assertIn("Attention Is All You Need", res.result)
        self.assertIn("Ashish Vaswani", res.result)

    def test_get_paper_details_not_found(self):
        req = models.GetPaperDetailsRequest(paper_id="2401.99999")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=EMPTY_ATOM_FEED)):
            res = _run(main.get_paper_details(req))

        self.assertIsNone(res.error)
        self.assertIn("No arXiv paper found for 2401.99999.", res.result)

    def test_get_paper_details_invalid_id(self):
        req = models.GetPaperDetailsRequest(paper_id="invalid-not-an-arxiv-id")
        res = _run(main.get_paper_details(req))
        self.assertIsNone(res.result)
        self.assertIn("Provide a valid arXiv paper ID", res.error)

    def test_get_paper_details_versioned_id(self):
        req = models.GetPaperDetailsRequest(paper_id="1706.03762v7")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=SAMPLE_ATOM_FEED)) as mock_req:
            res = _run(main.get_paper_details(req))
            mock_req.assert_called_once_with({"id_list": "1706.03762", "max_results": 1})

        self.assertIsNone(res.error)
        self.assertIn("Attention Is All You Need", res.result)

    def test_get_paper_details_url_id(self):
        req = models.GetPaperDetailsRequest(paper_id="https://arxiv.org/abs/1706.03762")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=SAMPLE_ATOM_FEED)) as mock_req:
            res = _run(main.get_paper_details(req))
            mock_req.assert_called_once_with({"id_list": "1706.03762", "max_results": 1})

        self.assertIsNone(res.error)

    def test_get_paper_details_none_and_dict_payload(self):
        res = _run(main.get_paper_details(None))
        self.assertIn("Provide a valid arXiv paper ID", res.error)

        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=SAMPLE_ATOM_FEED)):
            res_dict = _run(main.get_paper_details({"paper_id": "1706.03762"}))
            self.assertIn("Attention Is All You Need", res_dict.result)

    def test_search_author_success(self):
        req = models.SearchAuthorRequest(author="Ashish Vaswani")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=SAMPLE_ATOM_FEED)):
            res = _run(main.search_author(req))

        self.assertIsNone(res.error)
        self.assertIn("Recent arXiv papers by Ashish Vaswani:", res.result)
        self.assertIn("Attention Is All You Need", res.result)

    def test_search_author_empty_results(self):
        req = models.SearchAuthorRequest(author="UnknownAuthor99999")
        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=EMPTY_ATOM_FEED)):
            res = _run(main.search_author(req))

        self.assertIsNone(res.error)
        self.assertIn("No arXiv papers found for author UnknownAuthor99999.", res.result)

    def test_search_author_missing_name(self):
        req = models.SearchAuthorRequest(author="   ")
        res = _run(main.search_author(req))
        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Missing required field: author")

    def test_search_author_timeout(self):
        req = models.SearchAuthorRequest(author="Vaswani")
        with patch.object(main, "_request_arxiv", new=AsyncMock(side_effect=httpx.TimeoutException("timed out"))):
            res = _run(main.search_author(req))

        self.assertIsNone(res.result)
        self.assertIn("arXiv author search failed: timed out", res.error)

    def test_search_author_none_and_dict_payload(self):
        res = _run(main.search_author(None))
        self.assertEqual(res.error, "Missing required field: author")

        with patch.object(main, "_request_arxiv", new=AsyncMock(return_value=SAMPLE_ATOM_FEED)):
            res_dict = _run(main.search_author({"author": "Vaswani"}))
            self.assertIn("Recent arXiv papers by Vaswani:", res_dict.result)


class RateLimitThrottleTests(unittest.TestCase):
    def test_request_arxiv_stamps_timestamp_on_error(self):
        initial_time = main._last_arxiv_request_at

        async def fail():
            mock_client = AsyncMock()
            mock_client.get.side_effect = Exception("network fail")
            with patch.object(main, "_get_arxiv_client", new=AsyncMock(return_value=mock_client)):
                try:
                    await main._request_arxiv({"query": "test"})
                except Exception:
                    pass

        _run(fail())
        self.assertGreater(main._last_arxiv_request_at, initial_time)


if __name__ == "__main__":
    unittest.main()
