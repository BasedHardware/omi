"""Hermetic regression tests for sensitive exception leak prevention in ShipBob app.

Verifies that low-level network errors and runtime exceptions never leak internal credentials,
hostnames, IPs, or exception tracebacks into chat tool responses or OAuth templates.
"""
import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get
    exception_handler = get
    mount = lambda *args, **kwargs: None


class Response:
    def __init__(self, result=None, error=None, **kwargs):
        self.result = result
        self.error = error


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


class FakeTemplateResponse:
    def __init__(self, template_name, context):
        self.template_name = template_name
        self.context = context


stubs = {
    "requests": module("requests", RequestException=OSError, get=Mock(), post=Mock(), put=Mock(), delete=Mock()),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module(
        "fastapi",
        **{
            name: Framework for name in ("Depends", "FastAPI", "HTTPException", "Request", "Query")
        },
    ),
    "fastapi.responses": module(
        "fastapi.responses",
        **{
            name: Framework
            for name in ("HTMLResponse", "RedirectResponse", "JSONResponse")
        },
    ),
    "fastapi.staticfiles": module("fastapi.staticfiles", StaticFiles=Framework),
    "fastapi.templating": module(
        "fastapi.templating",
        Jinja2Templates=lambda **kwargs: types.SimpleNamespace(TemplateResponse=FakeTemplateResponse),
    ),
    "fastapi.exceptions": module("fastapi.exceptions", RequestValidationError=Framework),
    "shipbob_tools_auth": module("shipbob_tools_auth", require_shipbob_tools_auth=Mock()),
    "db": module(
        "db",
        **{
            name: Mock()
            for name in (
                "store_shipbob_tokens",
                "get_shipbob_tokens",
                "delete_shipbob_tokens",
                "store_oauth_state",
                "get_oauth_state",
                "delete_oauth_state",
                "update_shipbob_channel",
                "get_user_settings",
            )
        },
    ),
    "models": module(
        "models",
        ChatToolResponse=Response,
        **{
            name: Response
            for name in (
                "GetInventoryRequest",
                "GetProductsRequest",
                "CreateWroRequest",
                "GetWrosRequest",
                "CancelWroRequest",
                "GetOrdersRequest",
                "GetFulfillmentCentersRequest",
            )
        },
    ),
}

spec = importlib.util.spec_from_file_location(
    "shipbob_under_test", Path(__file__).with_name("main.py")
)
shipbob = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shipbob)


def _run(coro):
    return asyncio.run(coro)


class ShipbobErrorSanitizationTests(unittest.TestCase):
    def test_api_request_exception_sanitization(self):
        sensitive_msg = "ConnectTimeout to https://api.shipbob.com/1.0/channel?token=sb_pat_secret_999"
        err = Exception(sensitive_msg)

        with patch.object(shipbob, "refresh_token_if_needed", return_value=True), \
             patch.object(shipbob, "get_shipbob_headers", return_value={"Authorization": "Bearer tok"}), \
             patch.object(shipbob.requests, "get", side_effect=err):
            result = shipbob.make_shipbob_request("user1", "GET", "/1.0/channel")

        self.assertIn("error", result)
        self.assertEqual(result["error"], "Request failed")
        self.assertNotIn("sb_pat_secret_999", result["error"])
        self.assertNotIn("https://api.shipbob.com", result["error"])

    def test_oauth_callback_exception_sanitization(self):
        sensitive_msg = "OAuthTokenExchangeError: client_secret=sb_sec_private leaked in handshake"
        req = Mock()

        state = "user1:valid_token_123"
        with patch.object(shipbob, "get_oauth_state", return_value=state), \
             patch.object(shipbob.requests, "post", side_effect=Exception(sensitive_msg)):
            resp = _run(shipbob.handle_shipbob_callback(req, code="auth-code", state=state))

        self.assertIsInstance(resp, FakeTemplateResponse)
        self.assertFalse(resp.context["authenticated"])
        self.assertEqual(resp.context["error"], "Failed to exchange authorization code")
        self.assertNotIn("sb_sec_private", resp.context["error"])

    def test_tool_get_inventory_unexpected_exception_sanitization(self):
        sensitive_msg = "RuntimeError: Database pool exhausted at postgres://user:pass@10.0.1.55:5432"
        req = Mock(json=AsyncMock(return_value={"uid": "user1"}))

        with patch.object(shipbob, "get_shipbob_headers", side_effect=RuntimeError(sensitive_msg)):
            resp = _run(shipbob.tool_get_inventory(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to get inventory")
        self.assertNotIn("10.0.1.55", resp.error)
        self.assertNotIn("pass", resp.error)

    def test_tool_get_products_unexpected_exception_sanitization(self):
        sensitive_msg = "KeyError: /var/secrets/shipbob_key.json: 'private_key'"
        req = Mock(json=AsyncMock(return_value={"uid": "user1"}))

        with patch.object(shipbob, "get_shipbob_headers", side_effect=KeyError(sensitive_msg)):
            resp = _run(shipbob.tool_get_products(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to get products")
        self.assertNotIn("/var/secrets", resp.error)

    def test_tool_create_wro_unexpected_exception_sanitization(self):
        sensitive_msg = "MemoryError: Shipbob worker thread pool exhausted at 0x7fffbeef"
        req = Mock(json=AsyncMock(return_value={"uid": "user1", "product_name": "Hat", "quantity": 10}))

        with patch.object(shipbob, "get_shipbob_headers", side_effect=MemoryError(sensitive_msg)):
            resp = _run(shipbob.tool_create_wro(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to create WRO")
        self.assertNotIn("0x7fffbeef", resp.error)

    def test_tool_get_wros_unexpected_exception_sanitization(self):
        sensitive_msg = "ConnectionResetError: peer closed socket at 192.168.1.200"
        req = Mock(json=AsyncMock(return_value={"uid": "user1"}))

        with patch.object(shipbob, "get_shipbob_headers", side_effect=ConnectionResetError(sensitive_msg)):
            resp = _run(shipbob.tool_get_wros(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to get WROs")
        self.assertNotIn("192.168.1.200", resp.error)

    def test_tool_cancel_wro_unexpected_exception_sanitization(self):
        sensitive_msg = "Timeout accessing proxy http://gateway.corp:3128 with auth=secret_sb"
        req = Mock(json=AsyncMock(return_value={"uid": "user1", "wro_id": "12345"}))

        with patch.object(shipbob, "get_shipbob_headers", side_effect=TimeoutError(sensitive_msg)):
            resp = _run(shipbob.tool_cancel_wro(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to cancel WRO")
        self.assertNotIn("gateway.corp", resp.error)
        self.assertNotIn("secret_sb", resp.error)

    def test_tool_get_orders_unexpected_exception_sanitization(self):
        sensitive_msg = "ValueError: Bad internal state at /etc/ssl/certs/internal.crt"
        req = Mock(json=AsyncMock(return_value={"uid": "user1"}))

        with patch.object(shipbob, "get_shipbob_headers", side_effect=ValueError(sensitive_msg)):
            resp = _run(shipbob.tool_get_orders(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to get orders")
        self.assertNotIn("/etc/ssl", resp.error)

    def test_tool_get_fulfillment_centers_unexpected_exception_sanitization(self):
        sensitive_msg = "Exception: Internal token sb_bearer_999 leaked in stack"
        req = Mock(json=AsyncMock(return_value={"uid": "user1"}))

        with patch.object(shipbob, "get_shipbob_headers", side_effect=Exception(sensitive_msg)):
            resp = _run(shipbob.tool_get_fulfillment_centers(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to get fulfillment centers")
        self.assertNotIn("sb_bearer_999", resp.error)


if __name__ == "__main__":
    unittest.main()
