"""Tests for error handling and sensitive exception leak prevention in Semantic Scholar app."""
import asyncio
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_STUBBED_MODULES = ("httpx", "fastapi", "pydantic")


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


def _run(coro):
    return asyncio.run(coro)


class ErrorHandlingSanitizationTests(unittest.TestCase):
    def test_search_papers_http_error_sanitization(self):
        sensitive_msg = "ConnectError to https://internal-api.service.local/key=secret_xyz"
        err = main.httpx.HTTPError(sensitive_msg)

        req = main.SearchPapersRequest(query="deep learning")
        with mock.patch.object(main, "api_get", new=mock.AsyncMock(side_effect=err)):
            resp = _run(main.search_papers(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Semantic Scholar request failed.")
        self.assertNotIn("internal-api.service.local", resp.error)
        self.assertNotIn("secret_xyz", resp.error)

    def test_search_papers_unexpected_exception_sanitization(self):
        sensitive_msg = "RuntimeError: Database conn failed at postgres://user:secret@10.0.0.99:5432"
        err = RuntimeError(sensitive_msg)

        req = main.SearchPapersRequest(query="machine learning")
        with mock.patch.object(main, "api_get", new=mock.AsyncMock(side_effect=err)):
            resp = _run(main.search_papers(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Unexpected error processing request.")
        self.assertNotIn("10.0.0.99", resp.error)
        self.assertNotIn("secret", resp.error)

    def test_get_paper_http_error_sanitization(self):
        sensitive_msg = "Connection reset by peer at 192.168.1.100:443 (api_token=xyz_tok)"
        err = main.httpx.HTTPError(sensitive_msg)

        req = main.GetPaperRequest(paper_id_or_doi="10.1234/test")
        with mock.patch.object(main, "api_get", new=mock.AsyncMock(side_effect=err)):
            resp = _run(main.get_paper(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Semantic Scholar request failed.")
        self.assertNotIn("192.168.1.100", resp.error)
        self.assertNotIn("xyz_tok", resp.error)

    def test_get_paper_unexpected_exception_sanitization(self):
        sensitive_msg = "ValueError: Internal corrupted cache state /var/secrets/keys.json"
        err = ValueError(sensitive_msg)

        req = main.GetPaperRequest(paper_id_or_doi="10.1234/test")
        with mock.patch.object(main, "api_get", new=mock.AsyncMock(side_effect=err)):
            resp = _run(main.get_paper(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Unexpected error processing request.")
        self.assertNotIn("/var/secrets/keys.json", resp.error)

    def test_get_author_papers_http_error_sanitization(self):
        sensitive_msg = "Timeout accessing proxy http://gateway-int.corp:3128"
        err = main.httpx.HTTPError(sensitive_msg)

        req = main.GetAuthorPapersRequest(author_id="12345")
        with mock.patch.object(main, "api_get", new=mock.AsyncMock(side_effect=err)):
            resp = _run(main.get_author_papers(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Semantic Scholar request failed.")
        self.assertNotIn("gateway-int.corp", resp.error)

    def test_get_author_papers_unexpected_exception_sanitization(self):
        sensitive_msg = "Exception: Memory map failure at addr 0x7fffbeef1234"
        err = Exception(sensitive_msg)

        req = main.GetAuthorPapersRequest(author_id="12345")
        with mock.patch.object(main, "api_get", new=mock.AsyncMock(side_effect=err)):
            resp = _run(main.get_author_papers(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Unexpected error processing request.")
        self.assertNotIn("0x7fffbeef1234", resp.error)


if __name__ == "__main__":
    unittest.main()
