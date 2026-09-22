"""Hermetic tests for error sanitization in Crossref app.

Verifies that internal exception details (IPs, hostnames, proxy details, tracebacks)
are never leaked in ChatToolResponse.error.
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN_DIR = Path(__file__).resolve().parent


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class Model:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class Response:
    def __init__(self, result=None, error=None, **kwargs):
        self.result = result
        self.error = error


class HTTPError(Exception):
    pass


class HTTPStatusError(HTTPError):
    def __init__(self, message="", response=None):
        super().__init__(message)
        self.response = response


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


fastapi_responses = module("fastapi.responses", HTMLResponse=lambda *a, **k: None)
stubs = {
    "fastapi": module("fastapi", FastAPI=Framework, responses=fastapi_responses),
    "fastapi.responses": fastapi_responses,
    "httpx": module(
        "httpx",
        AsyncClient=object,
        HTTPError=HTTPError,
        HTTPStatusError=HTTPStatusError,
    ),
    "models": module(
        "models",
        AuthorWorksInput=Model,
        ChatToolResponse=Response,
        GetWorkInput=Model,
        SearchWorksInput=Model,
    ),
}


def load_main():
    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("crossref_main", PLUGIN_DIR / "main.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod


main = load_main()


class TestCrossrefErrorSanitization(unittest.TestCase):
    def test_search_crossref_works_http_error_sanitized(self):
        async def _run():
            with patch.object(main, "crossref_get", side_effect=main.httpx.HTTPError("sensitive proxy 10.0.0.1:8080 timeout")):
                res = await main.search_crossref_works(main.SearchWorksInput(query="quantum", max_results=5))
                self.assertEqual("Crossref request failed due to a network error.", res.error)
                self.assertNotIn("10.0.0.1", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_search_crossref_works_unexpected_exception_sanitized(self):
        async def _run():
            with patch.object(main, "crossref_get", side_effect=RuntimeError("internal crossref secret key leak")):
                res = await main.search_crossref_works(main.SearchWorksInput(query="quantum", max_results=5))
                self.assertEqual("Crossref request failed.", res.error)
                self.assertNotIn("internal crossref secret key leak", res.error)
                self.assertNotIn("RuntimeError", res.error)

        asyncio.run(_run())

    def test_get_crossref_work_http_error_sanitized(self):
        async def _run():
            with patch.object(main, "crossref_get", side_effect=main.httpx.HTTPError("upstream internal host fail")):
                res = await main.get_crossref_work(main.GetWorkInput(doi="10.1038/nphys1170"))
                self.assertEqual("Crossref request failed due to a network error.", res.error)
                self.assertNotIn("upstream internal host fail", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_get_crossref_work_unexpected_exception_sanitized(self):
        async def _run():
            with patch.object(main, "crossref_get", side_effect=RuntimeError("critical database error")):
                res = await main.get_crossref_work(main.GetWorkInput(doi="10.1038/nphys1170"))
                self.assertEqual("Crossref request failed.", res.error)
                self.assertNotIn("critical database error", res.error)
                self.assertNotIn("RuntimeError", res.error)

        asyncio.run(_run())

    def test_get_crossref_works_by_author_http_error_sanitized(self):
        async def _run():
            with patch.object(main, "crossref_get", side_effect=main.httpx.HTTPError("connection reset 192.168.1.1")):
                res = await main.get_crossref_works_by_author(main.AuthorWorksInput(author="Einstein", max_results=5))
                self.assertEqual("Crossref request failed due to a network error.", res.error)
                self.assertNotIn("192.168.1.1", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_get_crossref_works_by_author_unexpected_exception_sanitized(self):
        async def _run():
            with patch.object(main, "crossref_get", side_effect=RuntimeError("secret author search error")):
                res = await main.get_crossref_works_by_author(main.AuthorWorksInput(author="Einstein", max_results=5))
                self.assertEqual("Crossref request failed.", res.error)
                self.assertNotIn("secret author search error", res.error)
                self.assertNotIn("RuntimeError", res.error)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
