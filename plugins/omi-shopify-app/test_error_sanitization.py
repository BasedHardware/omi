"""Hermetic regression tests verifying error sanitization in plugins/omi-shopify-app.
Ensures internal exception details, network errors, and sensitive tokens are not leaked to users.
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


class RequestException(Exception):
    pass


stubs = {
    "requests": module("requests", RequestException=RequestException, post=Mock(), get=Mock(), put=Mock()),
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
    "shopify_err_test", Path(__file__).with_name("main.py")
)
shopify = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shopify)


def mock_request(body):
    req = Mock()
    req.json = AsyncMock(return_value=body)
    return req


class ShopifyErrorSanitizationTests(unittest.TestCase):
    """Verify that network exceptions and unexpected tool errors return sanitized messages."""

    def test_shopify_api_request_exception_sanitized(self):
        with patch.object(shopify, "get_shopify_tokens", return_value={"shop_domain": "test.myshopify.com", "access_token": "shpat_xxx"}):
            with patch.object(shopify.requests, "get", side_effect=shopify.requests.RequestException("connection reset by peer: 192.168.1.1")):
                res = shopify.shopify_api_request("u1", "GET", "/orders.json")
                self.assertEqual(res, {"error": "Request failed"})
                self.assertNotIn("192.168.1.1", str(res))

    def test_tool_get_analytics_exception_sanitized(self):
        req = mock_request({"uid": "u1"})
        with patch.object(shopify, "get_shopify_tokens", return_value={"shop_domain": "test.myshopify.com", "access_token": "tok"}):
            with patch.object(shopify, "shopify_api_request", side_effect=RuntimeError("internal crash in analytics math")):
                res = asyncio.run(shopify.tool_get_analytics(req))
                self.assertIsNone(res.result)
                self.assertEqual(res.error, "Failed to get analytics")
                self.assertNotIn("internal crash", res.error)

    def test_tool_get_orders_exception_sanitized(self):
        req = mock_request({"uid": "u1"})
        with patch.object(shopify, "get_shopify_tokens", return_value={"shop_domain": "test.myshopify.com", "access_token": "tok"}):
            with patch.object(shopify, "shopify_api_request", side_effect=RuntimeError("internal crash in orders parser")):
                res = asyncio.run(shopify.tool_get_orders(req))
                self.assertIsNone(res.result)
                self.assertEqual(res.error, "Failed to get orders")
                self.assertNotIn("internal crash", res.error)

    def test_tool_get_order_details_exception_sanitized(self):
        req = mock_request({"uid": "u1", "order_id": "123"})
        with patch.object(shopify, "get_shopify_tokens", return_value={"shop_domain": "test.myshopify.com", "access_token": "tok"}):
            with patch.object(shopify, "shopify_api_request", side_effect=RuntimeError("internal crash in details formatter")):
                res = asyncio.run(shopify.tool_get_order_details(req))
                self.assertIsNone(res.result)
                self.assertEqual(res.error, "Failed to get order details")
                self.assertNotIn("internal crash", res.error)

    def test_tool_create_order_auth_exception_sanitized(self):
        req = mock_request({"uid": "u1", "customer_name": "Test", "line_items": [{"title": "Shirt"}]})
        with patch.object(shopify, "get_shopify_tokens", side_effect=RuntimeError("redis pool down at 10.0.0.9")):
            res = asyncio.run(shopify.tool_create_order(req))
            self.assertIsNone(res.result)
            self.assertEqual(res.error, "Authentication error")
            self.assertNotIn("10.0.0.9", res.error)

    def test_tool_create_order_general_exception_sanitized(self):
        req = mock_request({"uid": "u1", "customer_name": "Test", "line_items": [{"title": "Shirt"}]})
        with patch.object(shopify, "get_shopify_tokens", return_value={"shop_domain": "test.myshopify.com", "access_token": "tok"}):
            with patch.object(shopify, "shopify_fetch_all_pages", side_effect=RuntimeError("crash in product resolution")):
                res = asyncio.run(shopify.tool_create_order(req))
                self.assertIsNone(res.result)
                self.assertEqual(res.error, "Failed to create order")
                self.assertNotIn("crash in product", res.error)

    def test_tool_get_customers_exception_sanitized(self):
        req = mock_request({"uid": "u1"})
        with patch.object(shopify, "get_shopify_tokens", return_value={"shop_domain": "test.myshopify.com", "access_token": "tok"}):
            with patch.object(shopify, "shopify_api_request", side_effect=RuntimeError("internal crash in customer query")):
                res = asyncio.run(shopify.tool_get_customers(req))
                self.assertIsNone(res.result)
                self.assertEqual(res.error, "Failed to get customers")
                self.assertNotIn("internal crash", res.error)

    def test_tool_create_customer_exception_sanitized(self):
        req = mock_request({"uid": "u1", "first_name": "Test", "email": "test@example.com"})
        with patch.object(shopify, "get_shopify_tokens", return_value={"shop_domain": "test.myshopify.com", "access_token": "tok"}):
            with patch.object(shopify, "shopify_api_request", side_effect=RuntimeError("internal crash in customer creation")):
                res = asyncio.run(shopify.tool_create_customer(req))
                self.assertIsNone(res.result)
                self.assertEqual(res.error, "Failed to create customer")
                self.assertNotIn("internal crash", res.error)


if __name__ == "__main__":
    unittest.main(verbosity=2)
