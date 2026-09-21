"""Hermetic tests for error handling and sensitive exception leak prevention in Crossref app."""
import asyncio
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

_STUBBED_MODULES = ("fastapi", "httpx", "models")


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class Response:
    def __init__(self, result=None, error=None, **kwargs):
        self.result = result
        self.error = error


class HTTPError(Exception):
    pass


class HTTPStatusError(HTTPError):
    def __init__(self, message="", *, response=None):
        super().__init__(message)
        self.response = response


class ResponseMock:
    def __init__(self, status_code):
        self.status_code = status_code


def _make_stubs():
    httpx = types.ModuleType("httpx")
    httpx.AsyncClient = object
    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = Framework

    models = types.ModuleType("models")
    models.AuthorWorksInput = Framework
    models.ChatToolResponse = Response
    models.GetWorkInput = Framework
    models.SearchWorksInput = Framework

    return {
        "fastapi": fastapi,
        "httpx": httpx,
        "models": models,
    }


_stubs = _make_stubs()
_spec = importlib.util.spec_from_file_location(
    "crossref_app_error_test", Path(__file__).with_name("main.py")
)
crossref = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, _stubs):
    _spec.loader.exec_module(crossref)


def _run(coro):
    return asyncio.run(coro)


class CrossrefErrorSanitizationTests(unittest.TestCase):
    def test_search_works_http_error_sanitization(self):
        sensitive_msg = "ConnectError to https://api.crossref.org/works?token=secret_xyz_token"
        err = crossref.httpx.HTTPError(sensitive_msg)

        payload = SimpleNamespace(query="quantum computing", max_results=5)
        with patch.object(crossref, "crossref_get", new=AsyncMock(side_effect=err)):
            resp = _run(crossref.search_crossref_works(payload))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Crossref request failed.")
        self.assertNotIn("secret_xyz_token", resp.error)
        self.assertNotIn("api.crossref.org", resp.error)

    def test_search_works_unexpected_exception_sanitization(self):
        sensitive_msg = "RuntimeError: Database conn failed at postgres://user:secret@10.0.0.99:5432"
        err = RuntimeError(sensitive_msg)

        payload = SimpleNamespace(query="quantum computing", max_results=5)
        with patch.object(crossref, "crossref_get", new=AsyncMock(side_effect=err)):
            resp = _run(crossref.search_crossref_works(payload))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Unexpected error processing request.")
        self.assertNotIn("10.0.0.99", resp.error)
        self.assertNotIn("secret", resp.error)

    def test_get_work_http_status_404(self):
        err = crossref.httpx.HTTPStatusError("Not Found", response=ResponseMock(404))

        payload = SimpleNamespace(doi="10.1038/nphys1170")
        with patch.object(crossref, "crossref_get", new=AsyncMock(side_effect=err)):
            resp = _run(crossref.get_crossref_work(payload))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Work not found.")

    def test_get_work_http_error_sanitization(self):
        sensitive_msg = "Connection reset by peer at 192.168.1.55:443 (internal_token=xyz)"
        err = crossref.httpx.HTTPError(sensitive_msg)

        payload = SimpleNamespace(doi="10.1038/nphys1170")
        with patch.object(crossref, "crossref_get", new=AsyncMock(side_effect=err)):
            resp = _run(crossref.get_crossref_work(payload))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Crossref request failed.")
        self.assertNotIn("192.168.1.55", resp.error)
        self.assertNotIn("internal_token", resp.error)

    def test_get_work_unexpected_exception_sanitization(self):
        sensitive_msg = "KeyError: /var/secrets/api_keys.json: 'private_key'"
        err = KeyError(sensitive_msg)

        payload = SimpleNamespace(doi="10.1038/nphys1170")
        with patch.object(crossref, "crossref_get", new=AsyncMock(side_effect=err)):
            resp = _run(crossref.get_crossref_work(payload))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Unexpected error processing request.")
        self.assertNotIn("/var/secrets", resp.error)

    def test_get_works_by_author_http_status_404(self):
        err = crossref.httpx.HTTPStatusError("Not Found", response=ResponseMock(404))

        payload = SimpleNamespace(author="Albert Einstein", max_results=5)
        with patch.object(crossref, "crossref_get", new=AsyncMock(side_effect=err)):
            resp = _run(crossref.get_crossref_works_by_author(payload))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Author not found.")

    def test_get_works_by_author_http_error_sanitization(self):
        sensitive_msg = "Gateway timeout via proxy http://corp-proxy.internal:8080"
        err = crossref.httpx.HTTPError(sensitive_msg)

        payload = SimpleNamespace(author="Albert Einstein", max_results=5)
        with patch.object(crossref, "crossref_get", new=AsyncMock(side_effect=err)):
            resp = _run(crossref.get_crossref_works_by_author(payload))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Crossref request failed.")
        self.assertNotIn("corp-proxy.internal", resp.error)

    def test_get_works_by_author_unexpected_exception_sanitization(self):
        sensitive_msg = "MemoryError: failed to allocate buffer in worker-7"
        err = MemoryError(sensitive_msg)

        payload = SimpleNamespace(author="Albert Einstein", max_results=5)
        with patch.object(crossref, "crossref_get", new=AsyncMock(side_effect=err)):
            resp = _run(crossref.get_crossref_works_by_author(payload))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Unexpected error processing request.")
        self.assertNotIn("worker-7", resp.error)


if __name__ == "__main__":
    unittest.main()
