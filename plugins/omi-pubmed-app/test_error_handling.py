"""Hermetic tests for error handling and sensitive exception leak prevention in PubMed app."""
import asyncio
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

_STUBBED_MODULES = ("fastapi", "fastapi.responses", "httpx", "models")


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class RequestMock:
    def __init__(self, json_data):
        self._json_data = json_data

    async def json(self):
        return self._json_data


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


class _AsyncClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


def _make_stubs():
    httpx = types.ModuleType("httpx")
    httpx.AsyncClient = _AsyncClient
    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = Framework
    fastapi.Request = RequestMock

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    fastapi.responses = responses

    models = types.ModuleType("models")
    models.ChatToolResponse = Response

    return {
        "fastapi": fastapi,
        "fastapi.responses": responses,
        "httpx": httpx,
        "models": models,
    }


_stubs = _make_stubs()
_spec = importlib.util.spec_from_file_location(
    "pubmed_app_error_test", Path(__file__).with_name("main.py")
)
pubmed = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, _stubs):
    _spec.loader.exec_module(pubmed)


def _run(coro):
    return asyncio.run(coro)


class PubMedErrorSanitizationTests(unittest.TestCase):
    def test_search_pubmed_http_error_sanitization(self):
        sensitive_msg = "ConnectError to https://eutils.ncbi.nlm.nih.gov/key=secret_xyz"
        err = pubmed.httpx.HTTPError(sensitive_msg)

        req = RequestMock({"query": "crispr cas9", "max_results": 5})
        with patch.object(pubmed, "_search_ids", new=AsyncMock(side_effect=err)):
            resp = _run(pubmed.search_pubmed(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "PubMed search failed.")
        self.assertNotIn("secret_xyz", resp.error)
        self.assertNotIn("eutils.ncbi.nlm.nih.gov", resp.error)

    def test_search_pubmed_unexpected_exception_sanitization(self):
        sensitive_msg = "RuntimeError: Database conn failed at postgres://user:secret@10.0.0.99:5432"
        err = RuntimeError(sensitive_msg)

        req = RequestMock({"query": "crispr cas9", "max_results": 5})
        with patch.object(pubmed, "_search_ids", new=AsyncMock(side_effect=err)):
            resp = _run(pubmed.search_pubmed(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Unexpected error processing request.")
        self.assertNotIn("10.0.0.99", resp.error)
        self.assertNotIn("secret", resp.error)

    def test_get_article_http_status_404(self):
        err = pubmed.httpx.HTTPStatusError("Not Found", response=ResponseMock(404))

        req = RequestMock({"pmid": "12345678"})
        with patch.object(pubmed, "_fetch_summaries", new=AsyncMock(side_effect=err)):
            resp = _run(pubmed.get_pubmed_article(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "PubMed article not found.")

    def test_get_article_http_error_sanitization(self):
        sensitive_msg = "Connection reset by peer at 192.168.1.55:443 (internal_token=xyz)"
        err = pubmed.httpx.HTTPError(sensitive_msg)

        req = RequestMock({"pmid": "12345678"})
        with patch.object(pubmed, "_fetch_summaries", new=AsyncMock(side_effect=err)):
            resp = _run(pubmed.get_pubmed_article(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to fetch PubMed article.")
        self.assertNotIn("192.168.1.55", resp.error)
        self.assertNotIn("internal_token", resp.error)

    def test_get_article_unexpected_exception_sanitization(self):
        sensitive_msg = "KeyError: /var/secrets/api_keys.json: 'private_key'"
        err = KeyError(sensitive_msg)

        req = RequestMock({"pmid": "12345678"})
        with patch.object(pubmed, "_fetch_summaries", new=AsyncMock(side_effect=err)):
            resp = _run(pubmed.get_pubmed_article(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Unexpected error processing request.")
        self.assertNotIn("/var/secrets", resp.error)

    def test_get_related_http_status_404(self):
        err = pubmed.httpx.HTTPStatusError("Not Found", response=ResponseMock(404))

        req = RequestMock({"pmid": "12345678"})
        with patch.object(pubmed, "_fetch_json", new=AsyncMock(side_effect=err)):
            resp = _run(pubmed.get_related_pubmed(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Related PubMed articles not found.")

    def test_get_related_http_error_sanitization(self):
        sensitive_msg = "Gateway timeout via proxy http://corp-proxy.internal:8080"
        err = pubmed.httpx.HTTPError(sensitive_msg)

        req = RequestMock({"pmid": "12345678"})
        with patch.object(pubmed, "_fetch_json", new=AsyncMock(side_effect=err)):
            resp = _run(pubmed.get_related_pubmed(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to fetch related PubMed articles.")
        self.assertNotIn("corp-proxy.internal", resp.error)

    def test_get_related_unexpected_exception_sanitization(self):
        sensitive_msg = "MemoryError: failed to allocate buffer in worker-7"
        err = MemoryError(sensitive_msg)

        req = RequestMock({"pmid": "12345678"})
        with patch.object(pubmed, "_fetch_json", new=AsyncMock(side_effect=err)):
            resp = _run(pubmed.get_related_pubmed(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Unexpected error processing request.")
        self.assertNotIn("worker-7", resp.error)


if __name__ == "__main__":
    unittest.main()
