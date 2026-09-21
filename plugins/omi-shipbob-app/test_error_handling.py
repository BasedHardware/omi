"""Hermetic error-handling regression suite for omi-shipbob-app.

Verifies that internal exceptions, unhandled errors, and sensitive system traces
never leak into client HTTP responses or chat-tool errors across all ShipBob app endpoints.
Uses Python standard library unittest only.

Run: python3 plugins/omi-shipbob-app/test_error_handling.py
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

SENTINEL_ERROR = "INTERNAL_DB_DISCONNECTED_AT_10.240.0.1_PASSWORD_LEAK"


class FakeRequest:
    def __init__(self, data=None, method="GET"):
        self._data = data or {}
        self.method = method

    async def json(self):
        return self._data

    async def form(self):
        return self._data


def load_shipbob_app():
    """Load plugins/omi-shipbob-app/main.py hermetically without external dependencies."""
    class Framework:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda fn: fn

        post = get
        exception_handler = get
        mount = lambda *args, **kwargs: None

    class ChatToolResponse:
        def __init__(self, result=None, error=None, **kwargs):
            self.result = result
            self.error = error

    def make_module(name, **attrs):
        m = types.ModuleType(name)
        m.__dict__.update(attrs)
        return m

    fastapi_mod = make_module(
        "fastapi",
        **{name: Framework for name in ("Depends", "FastAPI", "HTTPException", "Request", "Query")},
    )
    fastapi_mod.__path__ = []

    class FakeTemplates:
        def __init__(self, *args, **kwargs):
            pass

        def TemplateResponse(self, name, context):
            return context

    stubs = {
        "requests": make_module("requests", RequestException=Exception, get=lambda *a, **k: None, post=lambda *a, **k: None),
        "dotenv": make_module("dotenv", load_dotenv=lambda *a, **k: None),
        "fastapi": fastapi_mod,
        "fastapi.exceptions": make_module("fastapi.exceptions", RequestValidationError=Framework),
        "fastapi.responses": make_module(
            "fastapi.responses",
            **{name: lambda *a, **k: object() for name in ("HTMLResponse", "JSONResponse", "RedirectResponse")},
        ),
        "fastapi.staticfiles": make_module("fastapi.staticfiles", StaticFiles=lambda *a, **k: object()),
        "fastapi.templating": make_module("fastapi.templating", Jinja2Templates=FakeTemplates),
        "db": make_module(
            "db",
            get_shipbob_tokens=lambda uid: {"access_token": "valid_token"},
            store_shipbob_tokens=lambda *a, **k: None,
            update_shipbob_tokens=lambda *a, **k: None,
            delete_shipbob_tokens=lambda *a, **k: None,
            is_token_expired=lambda *a, **k: False,
            store_oauth_state=lambda *a, **k: None,
            get_oauth_state=lambda *a, **k: None,
            delete_oauth_state=lambda *a, **k: None,
            update_shipbob_channel=lambda *a, **k: None,
            store_user_setting=lambda *a, **k: None,
            get_user_setting=lambda *a, **k: None,
            get_user_settings=lambda *a, **k: None,
        ),
        "models": make_module(
            "models",
            ChatToolResponse=ChatToolResponse,
            GetInventoryRequest=object,
            GetProductsRequest=object,
            CreateWroRequest=object,
            GetWrosRequest=object,
            CancelWroRequest=object,
            GetOrdersRequest=object,
            GetFulfillmentCentersRequest=object,
        ),
        "shipbob_tools_auth": make_module("shipbob_tools_auth", require_shipbob_tools_auth=lambda *a, **k: None),
    }

    # Search candidates for main.py
    candidates = [
        Path(__file__).parent / "main.py",
        Path(__file__).parent / "shipbob_hardened_main.py",
        Path("scratch/shipbob_hardened_main.py"),
    ]
    main_py_path = None
    for c in candidates:
        if c.exists():
            main_py_path = c
            break

    spec = importlib.util.spec_from_file_location("shipbob_main_app", main_py_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


class TestShipbobErrorHandling(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = load_shipbob_app()

    def setUp(self):
        self.app.get_shipbob_tokens = lambda uid: {"access_token": "valid_token"}

    def test_make_shipbob_request_does_not_leak_exception(self):
        """make_shipbob_request masks raw Exception from callers."""
        self.app.get_shipbob_headers = lambda uid: {"Authorization": "Bearer token"}
        self.app.refresh_token_if_needed = lambda uid: None
        with patch.object(self.app.requests, "get", side_effect=Exception(SENTINEL_ERROR)):
            res = self.app.make_shipbob_request("uid123", "GET", "/inventory")
            self.assertIn("error", res)
            self.assertNotIn(SENTINEL_ERROR, res["error"])
            self.assertEqual(res["error"], "ShipBob API request failed")

    def test_oauth_callback_does_not_leak_exception(self):
        """handle_shipbob_callback masks raw Exception during OAuth code exchange."""
        req = FakeRequest()
        state_val = "uid123:valid_nonce_token"
        with patch.object(self.app, "get_oauth_state", return_value=state_val):
            with patch.object(self.app.requests, "post", side_effect=Exception(SENTINEL_ERROR)):
                res = asyncio.run(self.app.handle_shipbob_callback(req, code="auth_code_123", state=state_val))
                self.assertIsInstance(res, dict)
                self.assertIn("error", res)
                self.assertNotIn(SENTINEL_ERROR, res["error"])
                self.assertEqual(res["error"], "Failed to exchange authorization code")

    def test_tool_get_inventory_does_not_leak_exception(self):
        """tool_get_inventory masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123", "query": "item"})
        with patch.object(self.app, "get_shipbob_headers", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_get_inventory(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to get inventory")

    def test_tool_get_products_does_not_leak_exception(self):
        """tool_get_products masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123", "query": "shirt"})
        with patch.object(self.app, "get_shipbob_headers", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_get_products(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to get products")

    def test_tool_create_wro_does_not_leak_exception(self):
        """tool_create_wro masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123", "product_name": "Box", "quantity": 5, "fulfillment_center_id": 1})
        with patch.object(self.app, "get_shipbob_headers", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_create_wro(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to create WRO")

    def test_tool_get_wros_does_not_leak_exception(self):
        """tool_get_wros masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123"})
        with patch.object(self.app, "get_shipbob_headers", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_get_wros(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to get WROs")

    def test_tool_cancel_wro_does_not_leak_exception(self):
        """tool_cancel_wro masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123", "wro_id": 100})
        with patch.object(self.app, "get_shipbob_headers", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_cancel_wro(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to cancel WRO")

    def test_tool_get_orders_does_not_leak_exception(self):
        """tool_get_orders masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123"})
        with patch.object(self.app, "get_shipbob_headers", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_get_orders(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to get orders")

    def test_tool_get_fulfillment_centers_does_not_leak_exception(self):
        """tool_get_fulfillment_centers masks unexpected exceptions in ChatToolResponse."""
        req = FakeRequest({"uid": "uid123"})
        with patch.object(self.app, "get_shipbob_headers", side_effect=Exception(SENTINEL_ERROR)):
            res = asyncio.run(self.app.tool_get_fulfillment_centers(req))
            self.assertIsNotNone(res.error)
            self.assertNotIn(SENTINEL_ERROR, res.error)
            self.assertEqual(res.error, "Failed to get fulfillment centers")


if __name__ == "__main__":
    unittest.main()
