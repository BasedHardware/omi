"""Hermetic regression tests for sensitive exception leak prevention in Shopify app.

Verifies that network exceptions, auth errors, and runtime crashes never reflect internal credentials,
hostnames, IPs, or exception tracebacks into chat tool responses or API clients.
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
    mount = lambda *args, **kwargs: None


class Response:
    def __init__(self, result=None, error=None, **kwargs):
        self.result = result
        self.error = error


def module(name, **attributes):
    val = types.ModuleType(name)
    val.__dict__.update(attributes)
    return val


stubs = {
    "requests": module("requests", RequestException=OSError, get=Mock(), post=Mock(), put=Mock(), delete=Mock()),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module(
        "fastapi",
        **{
            name: Framework
            for name in ("FastAPI", "HTTPException", "Request", "Query", "Form")
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
    "fastapi.templating": module("fastapi.templating", Jinja2Templates=Framework),
    "db": module(
        "db",
        **{
            name: Mock()
            for name in (
                "store_shopify_tokens",
                "get_shopify_tokens",
                "delete_shopify_tokens",
                "store_default_store",
                "get_default_store",
                "get_user_settings",
            )
        },
    ),
    "models": module(
        "models",
        **{
            name: Response
            for name in (
                "ChatToolResponse",
                "ShopifyOrder",
                "ShopifyCustomer",
                "ShopifyLineItem",
                "ShopifyAnalytics",
                "ShopifyShop",
            )
        },
    ),
}

spec = importlib.util.spec_from_file_location(
    "shopify_main_tested", Path(__file__).with_name("main.py")
)
shopify = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shopify)


def _run(coro):
    return asyncio.run(coro)


def mock_request(json_data):
    req = Mock()
    req.json = AsyncMock(return_value=json_data)
    return req


class ShopifyErrorSanitizationTests(unittest.TestCase):
    def setUp(self):
        self.print_patcher = patch("builtins.print")
        self.print_patcher.start()

    def tearDown(self):
        self.print_patcher.stop()

    def test_shopify_api_request_exception_sanitization(self):
        sensitive_msg = "ConnectTimeout to https://mystore.myshopify.com/admin/api/2024-01/orders.json?token=shpat_secret_999"
        err = shopify.requests.RequestException(sensitive_msg)

        tokens = {"access_token": "valid_token", "shop_domain": "mystore.myshopify.com"}
        with patch.object(shopify, "get_shopify_tokens", return_value=tokens), \
             patch.object(shopify.requests, "get", side_effect=err):
            result = shopify.shopify_api_request("user1", "GET", "/orders.json")

        self.assertIn("error", result)
        self.assertEqual(result["error"], "Request failed")
        self.assertNotIn("shpat_secret_999", result["error"])
        self.assertNotIn("mystore.myshopify.com", result["error"])

    def test_tool_get_analytics_unexpected_exception_sanitization(self):
        sensitive_msg = "RuntimeError: Database pool exhausted at postgres://user:pass@10.0.1.55:5432"
        req = mock_request({"uid": "user1"})

        with patch.object(shopify, "get_shopify_tokens", side_effect=RuntimeError(sensitive_msg)):
            resp = _run(shopify.tool_get_analytics(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to get analytics")
        self.assertNotIn("10.0.1.55", resp.error)
        self.assertNotIn("pass", resp.error)

    def test_tool_get_orders_unexpected_exception_sanitization(self):
        sensitive_msg = "KeyError: /var/secrets/shopify_token.json: 'private_key'"
        req = mock_request({"uid": "user1"})

        with patch.object(shopify, "get_shopify_tokens", side_effect=KeyError(sensitive_msg)):
            resp = _run(shopify.tool_get_orders(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to get orders")
        self.assertNotIn("/var/secrets", resp.error)

    def test_tool_get_order_details_unexpected_exception_sanitization(self):
        sensitive_msg = "Timeout accessing proxy http://gateway.corp:3128 with auth=secret_shopify"
        req = mock_request({"uid": "user1", "order_id": "1001"})

        with patch.object(shopify, "get_shopify_tokens", side_effect=TimeoutError(sensitive_msg)):
            resp = _run(shopify.tool_get_order_details(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to get order details")
        self.assertNotIn("gateway.corp", resp.error)
        self.assertNotIn("secret_shopify", resp.error)

    def test_tool_create_order_auth_exception_sanitization(self):
        sensitive_msg = "OAuthTokenExpired: token shpat_leaked_321 failed validation"
        req = mock_request({
            "uid": "user1",
            "line_items": [{"product_name": "T-Shirt", "quantity": 1}],
        })

        with patch.object(shopify, "get_shopify_tokens", side_effect=Exception(sensitive_msg)):
            resp = _run(shopify.tool_create_order(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Authentication error")
        self.assertNotIn("shpat_leaked_321", resp.error)

    def test_tool_create_order_unexpected_exception_sanitization(self):
        sensitive_msg = "ConnectionResetError: peer closed socket at 192.168.1.200"
        req = mock_request({
            "uid": "user1",
            "customer_email": "jane@example.com",
            "line_items": [{"product_name": "T-Shirt", "quantity": 1}],
        })

        tokens = {"access_token": "valid_token", "shop_domain": "mystore.myshopify.com"}
        with patch.object(shopify, "get_shopify_tokens", return_value=tokens), \
             patch.object(shopify, "shopify_fetch_all_pages", side_effect=ConnectionResetError(sensitive_msg)):
            resp = _run(shopify.tool_create_order(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to create order")
        self.assertNotIn("192.168.1.200", resp.error)

    def test_tool_get_customers_unexpected_exception_sanitization(self):
        sensitive_msg = "ValueError: Bad internal state at /etc/ssl/certs/internal.crt"
        req = mock_request({"uid": "user1"})

        with patch.object(shopify, "get_shopify_tokens", side_effect=ValueError(sensitive_msg)):
            resp = _run(shopify.tool_get_customers(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to get customers")
        self.assertNotIn("/etc/ssl", resp.error)

    def test_tool_create_customer_unexpected_exception_sanitization(self):
        sensitive_msg = "Exception: Internal token shpat_bearer_888 leaked in stack"
        req = mock_request({
            "uid": "user1",
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
        })

        with patch.object(shopify, "get_shopify_tokens", side_effect=Exception(sensitive_msg)):
            resp = _run(shopify.tool_create_customer(req))

        self.assertIsNone(resp.result)
        self.assertEqual(resp.error, "Failed to create customer")
        self.assertNotIn("shpat_bearer_888", resp.error)


if __name__ == "__main__":
    unittest.main()
