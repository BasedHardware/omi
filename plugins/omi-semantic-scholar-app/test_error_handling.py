"""Hermetic error-handling tests for the Semantic Scholar chat tools.

Standard library only: httpx, fastapi, and pydantic are replaced with minimal
stubs before importing the module under test (models.py loads against the
pydantic stub), so the suite runs without site-packages (the manifest lane
runs plain python3). The async chat-tool handlers are invoked through
asyncio.run with the `api_get` seam stubbed — no network access.

Covers the exception-text leak class fixed on top of BasedHardware/omi
precedents (#15522, #15493, #15484, #15361, #15471, #15477, #15587):
`except httpx.HTTPError as exc: error=f"...{exc}"` and
`except Exception as exc: error=f"Unexpected error: {exc}"` reflected DNS /
errno / internal details into chat tool responses. Now transport failures and
unexpected errors produce fixed messages; HTTP status mappings (404/other)
are preserved.
"""

import asyncio
import os
import sys
import types
import unittest
from unittest import mock
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_STUBBED_MODULES = ("httpx", "fastapi", "fastapi.exceptions", "fastapi.responses", "pydantic")


def _install_module_stubs():
    httpx = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message="", *, response=None):
            super().__init__(message)
            self.response = response

    class ConnectError(HTTPError):
        pass

    class TimeoutException(HTTPError):
        pass

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def get(self, *args, **kwargs):
            raise AssertionError("tests must stub main.api_get; no network allowed")

    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.ConnectError = ConnectError
    httpx.TimeoutException = TimeoutException
    httpx.AsyncClient = _AsyncClient
    sys.modules["httpx"] = httpx

    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def exception_handler(self, exc_class):
            def decorator(func):
                return func
            return decorator

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

    class Request:
        pass

    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    sys.modules["fastapi"] = fastapi

    exceptions = types.ModuleType("fastapi.exceptions")

    class RequestValidationError(Exception):
        pass

    exceptions.RequestValidationError = RequestValidationError
    sys.modules["fastapi.exceptions"] = exceptions

    responses = types.ModuleType("fastapi.responses")

    class JSONResponse:
        def __init__(self, *args, **kwargs):
            pass

    responses.JSONResponse = JSONResponse
    sys.modules["fastapi.responses"] = responses

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)

    pydantic.BaseModel = BaseModel

    def Field(*args, **kwargs):
        return kwargs.get("default") if "default" in kwargs else None

    pydantic.Field = Field

    def field_validator(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    def model_validator(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    pydantic.field_validator = field_validator
    pydantic.model_validator = model_validator
    sys.modules["pydantic"] = pydantic


_saved_modules = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
_install_module_stubs()
try:
    import main  # noqa: E402
finally:
    for _name, _original in _saved_modules.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original
    del _name, _original, _saved_modules

SCARY_TRANSPORT = (
    "could not resolve api.semanticscholar.org: [Errno -2] Name or service not known "
    "from host omi-plugins-7f9c via 10.0.2.15"
)


def _transport_exc():
    return main.httpx.ConnectError(SCARY_TRANSPORT)


def _status_exc(status):
    return main.httpx.HTTPStatusError(
        "upstream exploded", response=types.SimpleNamespace(status_code=status))


class TransportSanitizationTests(unittest.TestCase):
    def test_search_transport_error_is_sanitized(self):
        with patch.object(main, "api_get", AsyncMock(side_effect=_transport_exc())):
            resp = asyncio.run(main.search_papers(main.SearchPapersRequest(query="transformers")))
        self.assertEqual(
            resp.error,
            "Semantic Scholar request failed: the API could not be reached. Please try again later.")
        self.assertNotIn("Errno", resp.error)
        self.assertNotIn("10.0.2.15", resp.error)
        self.assertNotIn("omi-plugins-7f9c", resp.error)

    def test_get_paper_transport_error_is_sanitized(self):
        with patch.object(main, "api_get", AsyncMock(side_effect=_transport_exc())):
            resp = asyncio.run(
                main.get_paper(main.GetPaperRequest(paper_id_or_doi="10.1000/xyz")))
        self.assertEqual(
            resp.error,
            "Semantic Scholar request failed: the API could not be reached. Please try again later.")
        self.assertNotIn("Errno", resp.error)

    def test_author_papers_transport_error_is_sanitized(self):
        with patch.object(main, "api_get", AsyncMock(side_effect=_transport_exc())):
            resp = asyncio.run(
                main.get_author_papers(main.GetAuthorPapersRequest(author_id="12345")))
        self.assertEqual(
            resp.error,
            "Semantic Scholar request failed: the API could not be reached. Please try again later.")
        self.assertNotIn("Errno", resp.error)


class StatusMappingTests(unittest.TestCase):
    def test_paper_404_mapping_preserved(self):
        with patch.object(main, "api_get", AsyncMock(side_effect=_status_exc(404))):
            resp = asyncio.run(
                main.get_paper(main.GetPaperRequest(paper_id_or_doi="10.1000/gone")))
        self.assertEqual(resp.error, "Paper not found.")

    def test_author_404_mapping_preserved(self):
        with patch.object(main, "api_get", AsyncMock(side_effect=_status_exc(404))):
            resp = asyncio.run(
                main.get_author_papers(main.GetAuthorPapersRequest(author_id="42")))
        self.assertEqual(resp.error, "Author not found.")

    def test_other_status_reported_without_exception_text(self):
        with patch.object(main, "api_get", AsyncMock(side_effect=_status_exc(429))):
            resp = asyncio.run(
                main.get_paper(main.GetPaperRequest(paper_id_or_doi="DOI:10.1000/x")))
        self.assertIn("429", resp.error)
        self.assertNotIn("upstream exploded", resp.error)


class UnexpectedExceptionTests(unittest.TestCase):
    def test_internal_error_text_never_reaches_response(self):
        secret = RuntimeError("confidential failure in /home/z/app/secret.key loader")
        with patch.object(main, "api_get", AsyncMock(side_effect=secret)):
            resp = asyncio.run(main.search_papers(main.SearchPapersRequest(query="x")))
        self.assertEqual(
            resp.error,
            "Semantic Scholar request failed unexpectedly. Please try again later.")
        self.assertNotIn("secret", resp.error)
        self.assertNotIn("/home/z", resp.error)

    def test_author_papers_internal_error_sanitized(self):
        with patch.object(main, "api_get", AsyncMock(side_effect=ValueError("redis socket blew up"))):
            resp = asyncio.run(
                main.get_author_papers(main.GetAuthorPapersRequest(author_id="42")))
        self.assertEqual(
            resp.error,
            "Semantic Scholar request failed unexpectedly. Please try again later.")
        self.assertNotIn("redis", resp.error)


class BehaviorPreservationTests(unittest.TestCase):
    def test_search_happy_path_unchanged(self):
        payload = {"data": [{
            "title": "Attention Is All You Need", "year": 2017,
            "authors": [{"name": "Vaswani"}], "citationCount": 90000,
            "url": "", "venue": "NeurIPS"}]}
        with patch.object(main, "api_get", AsyncMock(return_value=payload)):
            resp = asyncio.run(main.search_papers(main.SearchPapersRequest(query="attention")))
        self.assertIsNone(resp.error)
        self.assertIn("Attention Is All You Need", resp.result)

    def test_empty_search_still_reports_no_papers(self):
        with patch.object(main, "api_get", AsyncMock(return_value={"data": []})):
            resp = asyncio.run(main.search_papers(main.SearchPapersRequest(query="nothing")))
        self.assertEqual(resp.result, "No papers found.")


if __name__ == "__main__":
    unittest.main()
