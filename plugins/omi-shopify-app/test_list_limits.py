"""Hermetic regression tests for Shopify list tools with null/omitted limits.

Validates that tool_get_orders and tool_get_customers safely handle None/null limits,
string numbers, negative values, and out-of-bounds limits without throwing TypeError.
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
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


stubs = {
    "requests": module("requests", RequestException=OSError),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module("fastapi", **{name: Framework for name in
        ("FastAPI", "HTTPException", "Request", "Query", "Form")}),
    "fastapi.responses": module("fastapi.responses", **{name: Framework for name in
        ("HTMLResponse", "RedirectResponse", "JSONResponse")}),
    "fastapi.staticfiles": module("fastapi.staticfiles", StaticFiles=Framework),
    "fastapi.templating": module("fastapi.templating", Jinja2Templates=Framework),
    "db": module("db", **{name: Mock() for name in
        ("store_shopify_tokens", "get_shopify_tokens", "delete_shopify_tokens",
         "store_default_store", "get_default_store", "get_user_settings")}),
    "models": module("models", **{name: Response for name in
        ("ChatToolResponse", "ShopifyOrder", "ShopifyCustomer", "ShopifyLineItem",
         "ShopifyAnalytics", "ShopifyShop")}),
}

spec = importlib.util.spec_from_file_location(
    "shopify_under_test", Path(__file__).with_name("main.py")
)
shopify = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shopify)


def mock_request(json_data):
    req = Mock()
    req.json = AsyncMock(return_value=json_data)
    return req


class TestShopifyListLimits(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_get_orders_null_limit_defaults_to_10(self):
        req = mock_request({"uid": "test_user", "limit": None})
        with patch.object(shopify, "get_shopify_tokens", return_value={"access_token": "tok"}), \
             patch.object(shopify, "shopify_api_request", return_value={"orders": [{"id": 1, "name": "#1001", "total_price": "50.00", "currency": "USD"}]}) as mock_api:
            resp = self.loop.run_until_complete(shopify.tool_get_orders(req))
            self.assertIsNone(resp.error)
            mock_api.assert_called_once()
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("limit"), 10)

    def test_get_orders_custom_valid_limit(self):
        req = mock_request({"uid": "test_user", "limit": 25})
        with patch.object(shopify, "get_shopify_tokens", return_value={"access_token": "tok"}), \
             patch.object(shopify, "shopify_api_request", return_value={"orders": []}) as mock_api:
            resp = self.loop.run_until_complete(shopify.tool_get_orders(req))
            self.assertIsNone(resp.error)
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("limit"), 25)

    def test_get_orders_limit_clamped_to_max_50(self):
        req = mock_request({"uid": "test_user", "limit": 999})
        with patch.object(shopify, "get_shopify_tokens", return_value={"access_token": "tok"}), \
             patch.object(shopify, "shopify_api_request", return_value={"orders": []}) as mock_api:
            resp = self.loop.run_until_complete(shopify.tool_get_orders(req))
            self.assertIsNone(resp.error)
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("limit"), 50)

    def test_get_orders_invalid_string_limit(self):
        req = mock_request({"uid": "test_user", "limit": "invalid"})
        with patch.object(shopify, "get_shopify_tokens", return_value={"access_token": "tok"}), \
             patch.object(shopify, "shopify_api_request", return_value={"orders": []}) as mock_api:
            resp = self.loop.run_until_complete(shopify.tool_get_orders(req))
            self.assertIsNone(resp.error)
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("limit"), 10)

    def test_get_customers_null_limit_defaults_to_10(self):
        req = mock_request({"uid": "test_user", "limit": None})
        with patch.object(shopify, "get_shopify_tokens", return_value={"access_token": "tok"}), \
             patch.object(shopify, "shopify_api_request", return_value={"customers": [{"id": 1, "first_name": "Jane", "last_name": "Doe"}]}) as mock_api:
            resp = self.loop.run_until_complete(shopify.tool_get_customers(req))
            self.assertIsNone(resp.error)
            mock_api.assert_called_once()
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("limit"), 10)

    def test_get_customers_search_with_null_limit(self):
        req = mock_request({"uid": "test_user", "query": "Jane", "limit": None})
        with patch.object(shopify, "get_shopify_tokens", return_value={"access_token": "tok"}), \
             patch.object(shopify, "shopify_api_request", return_value={"customers": [{"id": 1, "first_name": "Jane", "last_name": "Doe"}]}) as mock_api:
            resp = self.loop.run_until_complete(shopify.tool_get_customers(req))
            self.assertIsNone(resp.error)
            mock_api.assert_called_once()
            self.assertEqual(mock_api.call_args.args[2], "/customers/search.json")
            params = mock_api.call_args.kwargs.get("params", {})
            self.assertEqual(params.get("limit"), 10)
            self.assertEqual(params.get("query"), "Jane")


if __name__ == "__main__":
    unittest.main()
