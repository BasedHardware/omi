"""Hermetic regression tests for plugins/omi-wikipedia-app/main.py.

Standard library only: fastapi, fastapi.responses, fastapi.exceptions, httpx
and pydantic are replaced with minimal stubs before importing the modules
under test, so the suite runs without site-packages (the manifest lane runs
plain python3). ``models`` is NOT stubbed — the real models.py is imported
against the pydantic stub, whose BaseModel executes mode="before" field
validators so normalization behavior is exercised for real.

Covers the crashes reported in #13948: a null ``query`` block or non-dict
items in search/random results raised AttributeError/TypeError, a null
``content_urls``/``desktop`` chain crashed ``_format_summary``, non-dict
upstream JSON crashed every handler, there was no lifespan client pooling or
closed-client fallback, and payloads were untyped dicts with no trimming or
limit bounds.
"""

import asyncio
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_module_stubs():
    fastapi = types.ModuleType("fastapi")

    class _App:
        def __init__(self, *args, **kwargs):
            self.state = types.SimpleNamespace()
            self.exception_handlers = {}

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get
        put = get
        delete = get

        def exception_handler(self, exc_class):
            def decorator(handler):
                self.exception_handlers[exc_class] = handler
                return handler

            return decorator

    fastapi.FastAPI = _App

    responses = types.ModuleType("fastapi.responses")

    class _JSONResponse:
        def __init__(self, content=None, status_code=200, **kwargs):
            self.content = content
            self.status_code = status_code

    responses.HTMLResponse = str
    responses.JSONResponse = _JSONResponse

    exceptions = types.ModuleType("fastapi.exceptions")

    class _RequestValidationError(Exception):
        def __init__(self, errors=()):
            super().__init__("request validation failed")
            self._errors = list(errors)

        def errors(self):
            return list(self._errors)

    exceptions.RequestValidationError = _RequestValidationError
    fastapi.exceptions = exceptions

    pydantic = types.ModuleType("pydantic")

    def _field_validator(*field_names, mode="after", **kwargs):
        def decorator(fn):
            target = fn.__func__ if isinstance(fn, (classmethod, staticmethod)) else fn
            target.__validator_fields__ = field_names
            target.__validator_mode__ = mode
            return fn

        return decorator

    class _BaseModel:
        def __init__(self, **data):
            cls = type(self)
            annotations = {}
            for klass in reversed(cls.__mro__):
                annotations.update(getattr(klass, "__annotations__", {}))
            for klass in reversed(cls.__mro__):
                for member in vars(klass).values():
                    func = member.__func__ if isinstance(member, (classmethod, staticmethod)) else member
                    fields = getattr(func, "__validator_fields__", ())
                    if getattr(func, "__validator_mode__", "after") != "before":
                        continue
                    for field in fields:
                        if field not in annotations:
                            continue
                        if field not in data and not hasattr(cls, field):
                            continue
                        bound = (
                            member.__get__(None, cls)
                            if isinstance(member, (classmethod, staticmethod))
                            else func
                        )
                        data[field] = bound(data.get(field))
            for field in annotations:
                if field in data:
                    setattr(self, field, data[field])
                elif hasattr(cls, field):
                    setattr(self, field, getattr(cls, field))
                else:
                    raise TypeError(f"missing required field: {field}")

        def model_dump(self, exclude_none=False, **kwargs):
            annotations = {}
            for klass in reversed(type(self).__mro__):
                annotations.update(getattr(klass, "__annotations__", {}))
            result = {}
            for field in annotations:
                value = getattr(self, field, None)
                if exclude_none and value is None:
                    continue
                result[field] = value
            return result

    pydantic.BaseModel = _BaseModel
    pydantic.field_validator = _field_validator

    httpx = types.ModuleType("httpx")

    class _HTTPError(Exception):
        pass

    class _HTTPStatusError(_HTTPError):
        def __init__(self, status_code=500, message="HTTP error"):
            super().__init__(message)
            self.response = types.SimpleNamespace(status_code=status_code)

    class _AsyncClient:
        """Stubbed pooled client: constructing is allowed, network is not."""

        def __init__(self, *args, **kwargs):
            self.is_closed = False
            self.kwargs = kwargs

        async def get(self, *args, **kwargs):
            raise AssertionError("network access is not allowed in tests")

        async def aclose(self):
            self.is_closed = True

    httpx.HTTPError = _HTTPError
    httpx.HTTPStatusError = _HTTPStatusError
    httpx.AsyncClient = _AsyncClient

    sys.modules["fastapi"] = fastapi
    sys.modules["fastapi.responses"] = responses
    sys.modules["fastapi.exceptions"] = exceptions
    sys.modules["pydantic"] = pydantic
    sys.modules["httpx"] = httpx


_install_module_stubs()

import main  # noqa: E402
import models  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


class _FakeResponse:
    def __init__(self, payload=None, status_error=None):
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error is not None:
            raise self._status_error

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, responses=(), is_closed=False):
        self.is_closed = is_closed
        self._responses = list(responses)
        self.calls = []

    async def get(self, url, params=None):
        self.calls.append({"url": url, "params": params})
        if self._responses:
            return self._responses.pop(0)
        return _FakeResponse({})

    async def aclose(self):
        self.is_closed = True


def _set_state_client(client):
    """Swap app.state.http_client, restoring the previous value afterwards."""
    return mock.patch.object(main.app.state, "http_client", client, create=True)


def _patched_request(payload=None, side_effect=None):
    if side_effect is not None:
        replacement = mock.AsyncMock(side_effect=side_effect)
    else:
        replacement = mock.AsyncMock(return_value=payload)
    return mock.patch.object(main, "_request_json", replacement)


class ModelTests(unittest.TestCase):
    def test_search_request_strips_query(self):
        request = models.SearchArticlesRequest(query="  Mercury (planet)  ")
        self.assertEqual(request.query, "Mercury (planet)")

    def test_search_request_clamps_limit(self):
        for raw, expected in ((50, 10), (0, 1), (-3, 1), ("7", 7), ("junk", 5), (None, 5), (True, 5)):
            with self.subTest(raw=raw):
                request = models.SearchArticlesRequest(query="x", limit=raw)
                self.assertEqual(request.limit, expected)

    def test_language_normalized_on_all_requests(self):
        self.assertEqual(models.SearchArticlesRequest(query="x", language=" EN ").language, "en")
        self.assertEqual(models.GetArticleSummaryRequest(title="t", language="pt-br").language, "pt-br")
        self.assertEqual(models.GetRandomArticleRequest(language="123").language, "en")
        self.assertEqual(models.GetRandomArticleRequest(language=None).language, "en")

    def test_summary_request_strips_title(self):
        request = models.GetArticleSummaryRequest(title="  Ada Lovelace ")
        self.assertEqual(request.title, "Ada Lovelace")


class FormatSummaryTests(unittest.TestCase):
    def test_null_content_urls_falls_back_to_article_url(self):
        """#13948: {"content_urls": null} must not AttributeError."""
        data = {"title": "Ada Lovelace", "extract": "First programmer.", "content_urls": None}
        result = main._format_summary(data, "en")
        self.assertIn("Ada Lovelace", result)
        self.assertIn("https://en.wikipedia.org/wiki/Ada_Lovelace", result)

    def test_null_desktop_falls_back_to_article_url(self):
        """#13948: {"content_urls": {"desktop": null}} must not AttributeError."""
        data = {
            "title": "Ada Lovelace",
            "extract": "First programmer.",
            "content_urls": {"desktop": None},
        }
        result = main._format_summary(data, "en")
        self.assertIn("https://en.wikipedia.org/wiki/Ada_Lovelace", result)

    def test_full_summary_renders_all_fields(self):
        data = {
            "title": "Ada Lovelace",
            "description": "English mathematician",
            "extract": "First programmer.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Ada_Lovelace"}},
        }
        result = main._format_summary(data, "en")
        self.assertIn("English mathematician", result)
        self.assertIn("First programmer.", result)
        self.assertIn("https://en.wikipedia.org/wiki/Ada_Lovelace", result)

    def test_non_dict_payload_renders_fallback(self):
        """#13948: a list/string payload must not crash _format_summary."""
        for bad in (["not", "a", "dict"], "error string", None):
            with self.subTest(bad=bad):
                result = main._format_summary(bad, "en")
                self.assertIn("Untitled", result)


class SearchArticlesTests(unittest.IsolatedAsyncioTestCase):
    async def test_renders_numbered_results_with_clean_snippet(self):
        payload = {
            "query": {
                "search": [
                    {"title": "Ada Lovelace", "snippet": "English <b>mathematician</b> &amp; writer"},
                    {"title": "Alan Turing", "snippet": None},
                ]
            }
        }
        with _patched_request(payload):
            response = await main.search_articles(models.SearchArticlesRequest(query="computing"))
        self.assertIsNone(response.error)
        self.assertIn("1. Ada Lovelace", response.result)
        self.assertIn("English mathematician & writer", response.result)
        self.assertIn("2. Alan Turing", response.result)
        self.assertIn("https://en.wikipedia.org/wiki/Alan_Turing", response.result)

    async def test_null_query_block_returns_no_results(self):
        """#13948: {"query": null} previously crashed with AttributeError."""
        with _patched_request({"query": None}):
            response = await main.search_articles(models.SearchArticlesRequest(query="x"))
        self.assertIsNone(response.error)
        self.assertEqual(response.result, "No Wikipedia articles found for 'x'.")

    async def test_filters_non_dict_items(self):
        """#13948: string/None items in the search list previously crashed .get."""
        payload = {"query": {"search": ["oops", None, 42, {"title": "Real", "snippet": "ok"}]}}
        with _patched_request(payload):
            response = await main.search_articles(models.SearchArticlesRequest(query="x"))
        self.assertIsNone(response.error)
        self.assertIn("1. Real", response.result)
        self.assertNotIn("oops", response.result)

    async def test_missing_query_returns_error(self):
        response = await main.search_articles(models.SearchArticlesRequest(query="   "))
        self.assertIsNone(response.result)
        self.assertEqual(response.error, "Missing required field: query")

    async def test_limit_constraint_enforced_upstream(self):
        payload = {"query": {"search": []}}
        with _patched_request(payload) as request_mock:
            await main.search_articles(models.SearchArticlesRequest(query="x", limit=99))
        params = request_mock.await_args.args[1]
        self.assertEqual(params["srlimit"], 10)

    async def test_http_status_error_returns_error(self):
        error = main.httpx.HTTPStatusError(503)
        with _patched_request(side_effect=error):
            response = await main.search_articles(models.SearchArticlesRequest(query="x"))
        self.assertIsNone(response.result)
        self.assertIn("503", response.error)


class GetArticleSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_renders_summary(self):
        payload = {
            "title": "Ada Lovelace",
            "extract": "First programmer.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Ada_Lovelace"}},
        }
        with _patched_request(payload):
            response = await main.get_article_summary(
                models.GetArticleSummaryRequest(title="Ada Lovelace")
            )
        self.assertIsNone(response.error)
        self.assertIn("Ada Lovelace", response.result)
        self.assertIn("First programmer.", response.result)

    async def test_null_content_urls_does_not_crash(self):
        """#13948: summary payload with null content_urls previously crashed."""
        payload = {"title": "Ada Lovelace", "extract": "First programmer.", "content_urls": None}
        with _patched_request(payload):
            response = await main.get_article_summary(
                models.GetArticleSummaryRequest(title="Ada Lovelace")
            )
        self.assertIsNone(response.error)
        self.assertIn("https://en.wikipedia.org/wiki/Ada_Lovelace", response.result)

    async def test_disambiguation_appends_guidance(self):
        payload = {
            "type": "disambiguation",
            "title": "Mercury",
            "extract": "Mercury may refer to:",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Mercury"}},
        }
        with _patched_request(payload):
            response = await main.get_article_summary(models.GetArticleSummaryRequest(title="Mercury"))
        self.assertIsNone(response.error)
        self.assertIn("disambiguation page", response.result)

    async def test_404_returns_not_found_error(self):
        error = main.httpx.HTTPStatusError(404)
        with _patched_request(side_effect=error):
            response = await main.get_article_summary(models.GetArticleSummaryRequest(title="Nope"))
        self.assertIsNone(response.result)
        self.assertIn("No Wikipedia article found for 'Nope'", response.error)

    async def test_missing_title_returns_error(self):
        response = await main.get_article_summary(models.GetArticleSummaryRequest(title="  "))
        self.assertIsNone(response.result)
        self.assertEqual(response.error, "Missing required field: title")


class GetRandomArticleTests(unittest.IsolatedAsyncioTestCase):
    async def test_null_query_block_returns_no_article(self):
        """#13948: {"query": null} previously crashed with AttributeError."""
        with _patched_request({"query": None}):
            response = await main.get_random_article(models.GetRandomArticleRequest())
        self.assertIsNone(response.error)
        self.assertEqual(response.result, "No random Wikipedia article was returned.")

    async def test_empty_random_list_returns_no_article(self):
        """#13948: indexing random_items[0] on an empty list crashed."""
        with _patched_request({"query": {"random": []}}):
            response = await main.get_random_article(models.GetRandomArticleRequest())
        self.assertIsNone(response.error)
        self.assertEqual(response.result, "No random Wikipedia article was returned.")

    async def test_non_dict_item_returns_no_article(self):
        """#13948: random_items[0].get on a string crashed with AttributeError."""
        with _patched_request({"query": {"random": ["oops"]}}):
            response = await main.get_random_article(models.GetRandomArticleRequest())
        self.assertIsNone(response.error)
        self.assertEqual(response.result, "No random Wikipedia article was returned.")

    async def test_missing_title_returns_without_title(self):
        with _patched_request({"query": {"random": [{"title": None}]}}):
            response = await main.get_random_article(models.GetRandomArticleRequest())
        self.assertIsNone(response.error)
        self.assertEqual(response.result, "Wikipedia returned a random article without a title.")

    async def test_happy_path_fetches_summary(self):
        random_payload = {"query": {"random": [{"title": "Ada Lovelace"}]}}
        summary_payload = {
            "title": "Ada Lovelace",
            "extract": "First programmer.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Ada_Lovelace"}},
        }
        with _patched_request(side_effect=[random_payload, summary_payload]):
            response = await main.get_random_article(models.GetRandomArticleRequest())
        self.assertIsNone(response.error)
        self.assertTrue(response.result.startswith("Random Wikipedia article:"))
        self.assertIn("First programmer.", response.result)


class RequestJsonTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_dict_payload_returns_empty_dict(self):
        """#13948: a list/string JSON body must not reach .get() callers."""
        client = _FakeClient([_FakeResponse(["unexpected", "list"])])
        with _set_state_client(client):
            self.assertEqual(await main._request_json("https://x.test"), {})

    async def test_reuses_pooled_state_client(self):
        client = _FakeClient([_FakeResponse({"ok": True})])
        with _set_state_client(client):
            result = await main._request_json("https://x.test")
            self.assertIs(main.app.state.http_client, client)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(client.calls), 1)

    async def test_closed_client_falls_back_to_fresh_client(self):
        """#13948: a closed pooled client must be replaced, not reused."""
        stale = _FakeClient(is_closed=True)
        fresh = _FakeClient([_FakeResponse({"ok": True})])
        with _set_state_client(stale):
            with mock.patch.object(main, "_build_http_client", return_value=fresh) as build:
                result = await main._request_json("https://x.test")
                self.assertIs(main.app.state.http_client, fresh)
        self.assertEqual(result, {"ok": True})
        build.assert_called_once_with()
        self.assertEqual(len(fresh.calls), 1)
        self.assertEqual(len(stale.calls), 0)


class LifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_creates_and_closes_client(self):
        """#13948: the pooled client lives on app.state for the app lifetime."""
        fake_app = types.SimpleNamespace(state=types.SimpleNamespace())
        async with main.lifespan(fake_app):
            client = fake_app.state.http_client
            self.assertIsInstance(client, main.httpx.AsyncClient)
            self.assertFalse(client.is_closed)
        self.assertTrue(client.is_closed)


class ValidationExceptionHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_required_field_error(self):
        exc = main.RequestValidationError([{"loc": ("body", "query"), "type": "missing"}])
        response = await main.validation_exception_handler(None, exc)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content["error"], "Missing required field: query")

    async def test_invalid_field_error(self):
        exc = main.RequestValidationError([{"loc": ("body", "limit"), "type": "int_parsing"}])
        response = await main.validation_exception_handler(None, exc)
        self.assertEqual(response.content["error"], "Invalid field: limit")


if __name__ == "__main__":
    unittest.main()
