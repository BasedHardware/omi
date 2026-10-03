"""Hermetic unit tests for arXiv input limit and author coercion.

Tests:
1. _clean_text returns empty string for booleans and None
2. _safe_limit falls back to default on boolean inputs rather than clamping 0 to 1
3. search_author rejects boolean, None, and empty author inputs with required error
4. get_paper_details rejects boolean paper_id inputs
"""

import asyncio
from pathlib import Path
import sys
import types
import unittest

PLUGIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PLUGIN_DIR))


def _install_module_stubs():
    for mod in ("httpx", "fastapi", "fastapi.responses", "fastapi.exceptions", "pydantic"):
        if mod not in sys.modules:
            stub = types.ModuleType(mod)
            if mod == "httpx":
                class HTTPError(Exception):
                    pass
                class HTTPStatusError(HTTPError):
                    pass
                class AsyncClient:
                    def __init__(self, *args, **kwargs):
                        self.is_closed = False
                    async def __aenter__(self):
                        return self
                    async def __aexit__(self, *exc):
                        return False
                    async def aclose(self):
                        pass
                stub.HTTPError = HTTPError
                stub.HTTPStatusError = HTTPStatusError
                stub.AsyncClient = AsyncClient
            elif mod == "fastapi":
                class FastAPI:
                    def __init__(self, *args, **kwargs):
                        pass
                    def get(self, *args, **kwargs):
                        return lambda f: f
                    post = get
                    def exception_handler(self, *args, **kwargs):
                        return lambda f: f
                stub.FastAPI = FastAPI
                stub.Request = object
            elif mod == "fastapi.responses":
                stub.HTMLResponse = object
                stub.JSONResponse = object
            elif mod == "fastapi.exceptions":
                class RequestValidationError(Exception):
                    pass
                stub.RequestValidationError = RequestValidationError
            elif mod == "pydantic":
                class BaseModel:
                    def __init__(self, **kwargs):
                        for k, v in kwargs.items():
                            setattr(self, k, v)
                    def model_dump(self):
                        return self.__dict__

                def Field(default=None, **kwargs):
                    if "default_factory" in kwargs:
                        return kwargs["default_factory"]()
                    return default

                stub.BaseModel = BaseModel
                stub.Field = Field
            sys.modules[mod] = stub


_install_module_stubs()

import main
import models


class ArxivLimitAndAuthorCoercionTests(unittest.TestCase):
    def test_clean_text_booleans_and_none(self):
        self.assertEqual(main._clean_text(False), "")
        self.assertEqual(main._clean_text(True), "")
        self.assertEqual(main._clean_text(None), "")
        self.assertEqual(main._clean_text("  Albert Einstein  "), "Albert Einstein")

    def test_safe_limit_booleans_fallback_to_default(self):
        # Must return default 5 rather than int(False) -> 0 -> 1 clamp
        self.assertEqual(main._safe_limit(False, default=5), 5)
        self.assertEqual(main._safe_limit(True, default=5), 5)
        self.assertEqual(main._safe_limit(None, default=5), 5)
        self.assertEqual(main._safe_limit("", default=5), 5)
        self.assertEqual(main._safe_limit("invalid", default=5), 5)

    def test_safe_limit_numeric_values(self):
        self.assertEqual(main._safe_limit(0, default=5), 1)
        self.assertEqual(main._safe_limit(3, default=5), 3)
        self.assertEqual(main._safe_limit(10, default=5), 10)
        self.assertEqual(main._safe_limit(25, default=5), 10)
        self.assertEqual(main._safe_limit("7", default=5), 7)

    def test_search_author_boolean_author_rejected(self):
        # Passing author=False must not search arXiv for author named 'False'
        resp_false = asyncio.run(main.search_author({"author": False}))
        self.assertEqual(resp_false.error, "Missing required field: author")

        resp_true = asyncio.run(main.search_author({"author": True}))
        self.assertEqual(resp_true.error, "Missing required field: author")

        resp_empty = asyncio.run(main.search_author({"author": "   "}))
        self.assertEqual(resp_empty.error, "Missing required field: author")

        resp_none = asyncio.run(main.search_author({"author": None}))
        self.assertEqual(resp_none.error, "Missing required field: author")

    def test_get_paper_details_boolean_paper_id_rejected(self):
        resp_false = asyncio.run(main.get_paper_details({"paper_id": False}))
        self.assertEqual(resp_false.error, "Provide a valid arXiv paper ID, such as 2401.01234.")

        resp_true = asyncio.run(main.get_paper_details({"paper_id": True}))
        self.assertEqual(resp_true.error, "Provide a valid arXiv paper ID, such as 2401.01234.")


if __name__ == "__main__":
    unittest.main()
