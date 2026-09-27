"""Hermetic error-handling regression suite for omi-shopify-app.

Raw exception text must never reach a client. The shared `shopify_api_request`
helper and every chat-tool handler answered failures with `str(e)`, reflecting
internal socket errors, filesystem paths and provider details back to the OMI
backend and chat clients. The handlers now log the detail server-side and
answer with a fixed message.

Stdlib only: `main.py` is loaded against stub `fastapi`, `requests`, `db` and
`models` modules, so the suite runs in CI with no third-party packages.

Run: python3 plugins/omi-shopify-app/test_error_handling.py
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

APP_DIR = Path(__file__).resolve().parent

# A trace that must never appear in a client response: a filesystem path and a
# provider-side exception class.
SECRET_TRACE = "/srv/app/.secrets/shopify_token_store.json"
LEAK_MARKERS = (SECRET_TRACE, "RuntimeError", "RequestException", "Traceback")


class _ChatToolResponse:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error


class _JSONResponse:
    def __init__(self, content, status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code


class _HTMLResponse(_JSONResponse):
    pass


class _RedirectResponse(_JSONResponse):
    def __init__(self, url, status_code=307, **kwargs):
        self.url = url
        self.status_code = status_code


class _HTTPException(Exception):
    def __init__(self, status_code, detail=None, **kwargs):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _Request:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


def _load_app(requests_mod):
    framework = types.ModuleType("fastapi")
    app = MagicMock()
    for method in ("get", "post", "put", "patch", "delete", "on_event"):
        getattr(app, method).side_effect = lambda *a, **k: (lambda handler: handler)
    framework.FastAPI = lambda **kwargs: app
    framework.Request = object
    framework.HTTPException = _HTTPException
    framework.Query = lambda *a, **k: None
    framework.Form = lambda *a, **k: None

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = _HTMLResponse
    responses.RedirectResponse = _RedirectResponse
    responses.JSONResponse = _JSONResponse

    staticfiles = types.ModuleType("fastapi.staticfiles")
    staticfiles.StaticFiles = MagicMock()

    templating = types.ModuleType("fastapi.templating")
    templating.Jinja2Templates = MagicMock()

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *a, **k: None

    models = types.ModuleType("models")
    models.ChatToolResponse = _ChatToolResponse
    for name in ("ShopifyOrder", "ShopifyCustomer", "ShopifyLineItem", "ShopifyAnalytics", "ShopifyShop"):
        setattr(models, name, MagicMock())

    db = types.ModuleType("db")
    db.get_shopify_tokens = MagicMock(return_value={"access_token": "tok", "shop_domain": "example.myshopify.com"})
    db.store_shopify_tokens = MagicMock()
    db.delete_shopify_tokens = MagicMock()
    db.store_default_store = MagicMock()
    db.get_default_store = MagicMock(return_value=None)
    db.get_user_settings = MagicMock(return_value={})

    modules = {
        "fastapi": framework,
        "fastapi.responses": responses,
        "fastapi.staticfiles": staticfiles,
        "fastapi.templating": templating,
        "dotenv": dotenv,
        "requests": requests_mod,
        "models": models,
        "db": db,
    }
    with patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location("omi_shopify_app_main", APP_DIR / "main.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


class ShopifyErrorHandlingTests(unittest.TestCase):
    def setUp(self):
        requests_mod = types.ModuleType("requests")

        class _RequestException(Exception):
            pass

        requests_mod.RequestException = _RequestException
        for method in ("get", "post", "put", "delete"):
            setattr(requests_mod, method, MagicMock(side_effect=_RequestException(SECRET_TRACE)))
        self.requests_mod = requests_mod
        self.module = _load_app(requests_mod)

    def _assert_no_leak(self, response):
        text = f"{response.result} {response.error}"
        for marker in LEAK_MARKERS:
            self.assertNotIn(marker, text, f"response leaked {marker!r}: {text!r}")

    def test_api_helper_answers_generically(self):
        result = self.module.shopify_api_request("uid-1", "GET", "/orders.json")

        self.assertEqual(result, {"error": "Shopify API request failed"})

    def test_get_analytics_does_not_reflect_the_exception(self):
        with patch.object(self.module, "shopify_api_request", side_effect=RuntimeError(SECRET_TRACE)):
            response = asyncio.run(self.module.tool_get_analytics(_Request({"uid": "uid-1"})))

        self._assert_no_leak(response)
        self.assertIn("internal error", response.error)

    def test_get_orders_does_not_reflect_the_exception(self):
        with patch.object(self.module, "shopify_api_request", side_effect=RuntimeError(SECRET_TRACE)):
            response = asyncio.run(self.module.tool_get_orders(_Request({"uid": "uid-1"})))

        self._assert_no_leak(response)
        self.assertIn("internal error", response.error)

    def test_get_order_details_does_not_reflect_the_exception(self):
        with patch.object(self.module, "shopify_api_request", side_effect=RuntimeError(SECRET_TRACE)):
            response = asyncio.run(
                self.module.tool_get_order_details(_Request({"uid": "uid-1", "order_id": "123"}))
            )

        self._assert_no_leak(response)
        self.assertIn("internal error", response.error)

    def test_create_order_auth_failure_does_not_reflect_the_exception(self):
        with patch.object(self.module, "get_shopify_tokens", side_effect=RuntimeError(SECRET_TRACE)):
            response = asyncio.run(
                self.module.tool_create_order(_Request({"uid": "uid-1", "line_items": [{"title": "x", "quantity": 1}]}))
            )

        self._assert_no_leak(response)
        self.assertIn("authenticate", response.error)

    def test_get_customers_does_not_reflect_the_exception(self):
        with patch.object(self.module, "shopify_api_request", side_effect=RuntimeError(SECRET_TRACE)):
            response = asyncio.run(self.module.tool_get_customers(_Request({"uid": "uid-1"})))

        self._assert_no_leak(response)
        self.assertIn("internal error", response.error)

    def test_create_customer_does_not_reflect_the_exception(self):
        with patch.object(self.module, "shopify_api_request", side_effect=RuntimeError(SECRET_TRACE)):
            response = asyncio.run(
                self.module.tool_create_customer(_Request({"uid": "uid-1", "email": "a@example.com", "first_name": "A"}))
            )

        self._assert_no_leak(response)
        self.assertIn("internal error", response.error)

    def test_no_except_block_interpolates_the_exception_into_a_response(self):
        """Pin the class, not the string: a non-exception `str(e)` is fine.

        `shopify_api_request` legitimately joins the provider's own error entries
        with `str(e)`; what must not exist is an except handler whose response
        expression interpolates the caught exception.
        """
        import ast
        import re

        source = (APP_DIR / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        response_calls = {"ChatToolResponse", "JSONResponse", "HTMLResponse", "HTTPException"}
        offenders = []
        for handler in ast.walk(tree):
            if not isinstance(handler, ast.ExceptHandler):
                continue
            suspects = []
            for stmt in ast.walk(handler):
                if isinstance(stmt, (ast.Return, ast.Raise)):
                    suspects.append(stmt)
                elif isinstance(stmt, ast.Call):
                    func = stmt.func
                    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                    if name in response_calls:
                        suspects.append(stmt)
            for stmt in suspects:
                segment = ast.get_source_segment(source, stmt) or ""
                if re.search(r"str\((e|exc)\)|\{(e|exc)\}", segment):
                    offenders.append(stmt.lineno)
        self.assertEqual(offenders, [], f"exception text interpolated in a response at lines {offenders}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
