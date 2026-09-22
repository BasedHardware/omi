"""Hermetic tests for error sanitization in Semantic Scholar app.

Verifies that internal exception details (IPs, hostnames, proxy details, tracebacks)
are never leaked in ChatToolResponse.error.
"""

import asyncio
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


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

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

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

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

    fastapi.FastAPI = FastAPI
    sys.modules["fastapi"] = fastapi

    pydantic = types.ModuleType("pydantic")

    def model_validator(*args, **kwargs):
        def decorator(fn):
            fn.__model_validator__ = True
            return fn

        return decorator

    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)
            for name in dir(type(self)):
                member = getattr(type(self), name, None)
                if getattr(member, "__model_validator__", False):
                    member(self)

    def Field(*args, **kwargs):
        if "default_factory" in kwargs:
            return kwargs["default_factory"]()
        return kwargs.get("default")

    pydantic.BaseModel = BaseModel
    pydantic.Field = Field
    pydantic.model_validator = model_validator
    sys.modules["pydantic"] = pydantic


_install_module_stubs()

if "main" in sys.modules:
    del sys.modules["main"]
import main  # noqa: E402


class TestSemanticScholarErrorSanitization(unittest.TestCase):
    def test_search_papers_http_error_sanitized(self):
        req = main.SearchPapersRequest(query="deep learning")
        with mock.patch.object(main, "api_get", side_effect=main.httpx.HTTPError("proxy 10.20.30.40 connection reset")):
            res = asyncio.run(main.search_papers(req))
            self.assertEqual("Semantic Scholar request failed due to a network error.", res.error)
            self.assertNotIn("10.20.30.40", res.error)
            self.assertNotIn("HTTPError", res.error)

    def test_search_papers_unexpected_exception_sanitized(self):
        req = main.SearchPapersRequest(query="deep learning")
        with mock.patch.object(main, "api_get", side_effect=RuntimeError("critical backend auth secret leaked")):
            res = asyncio.run(main.search_papers(req))
            self.assertEqual("Semantic Scholar request failed.", res.error)
            self.assertNotIn("critical backend auth secret", res.error)
            self.assertNotIn("RuntimeError", res.error)

    def test_get_paper_http_error_sanitized(self):
        req = main.GetPaperRequest(paper_id_or_doi="10.1038/nature12373")
        with mock.patch.object(main, "api_get", side_effect=main.httpx.HTTPError("timeout to 192.168.1.5:443")):
            res = asyncio.run(main.get_paper(req))
            self.assertEqual("Semantic Scholar request failed due to a network error.", res.error)
            self.assertNotIn("192.168.1.5", res.error)
            self.assertNotIn("HTTPError", res.error)

    def test_get_paper_unexpected_exception_sanitized(self):
        req = main.GetPaperRequest(paper_id_or_doi="10.1038/nature12373")
        with mock.patch.object(main, "api_get", side_effect=KeyError("sensitive_internal_key")):
            res = asyncio.run(main.get_paper(req))
            self.assertEqual("Semantic Scholar request failed.", res.error)
            self.assertNotIn("sensitive_internal_key", res.error)
            self.assertNotIn("KeyError", res.error)

    def test_get_author_papers_http_error_sanitized(self):
        req = main.GetAuthorPapersRequest(author_id="1741101")
        with mock.patch.object(main, "api_get", side_effect=main.httpx.HTTPError("internal dns resolution fail to s2.internal:80")):
            res = asyncio.run(main.get_author_papers(req))
            self.assertEqual("Semantic Scholar request failed due to a network error.", res.error)
            self.assertNotIn("s2.internal", res.error)
            self.assertNotIn("HTTPError", res.error)

    def test_get_author_papers_unexpected_exception_sanitized(self):
        req = main.GetAuthorPapersRequest(author_id="1741101")
        with mock.patch.object(main, "api_get", side_effect=TypeError("unhandled internal type crash")):
            res = asyncio.run(main.get_author_papers(req))
            self.assertEqual("Semantic Scholar request failed.", res.error)
            self.assertNotIn("unhandled internal type crash", res.error)
            self.assertNotIn("TypeError", res.error)


if __name__ == "__main__":
    unittest.main()
