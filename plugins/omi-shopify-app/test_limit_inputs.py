"""Hermetic regression tests for optional Shopify list limits.

The Omi retrieval layer serializes omitted optional integer arguments as JSON
``null``.  These tests exercise both production handlers through the HTTP
request seam and verify that every value sent to Shopify is in its documented
range.
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
    "requests": module("requests", RequestException=OSError, get=Mock()),
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
    "shopify_limit_under_test", Path(__file__).with_name("main.py")
)
shopify = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shopify)


class LimitInputTests(unittest.TestCase):
    def response_for(self, url):
        response = Mock(status_code=200, content=b"{}")
        if url.endswith("/orders.json"):
            response.json.return_value = {"orders": [{
                "name": "#1001", "total_price": "12.00", "currency": "USD",
                "financial_status": "paid", "fulfillment_status": "fulfilled",
                "created_at": "2026-09-14T00:00:00Z",
            }]}
        else:
            response.json.return_value = {"customers": [{
                "first_name": "Ada", "last_name": "Lovelace",
                "email": "ada@example.com", "orders_count": 1,
                "total_spent": "12.00", "currency": "USD",
            }]}
        return response

    def invoke(self, tool, limit, query=None):
        body = {"uid": "test-user", "limit": limit}
        if query is not None:
            body["query"] = query
        request = Mock(json=AsyncMock(return_value=body))

        def get(url, **kwargs):
            return self.response_for(url)

        with patch.object(shopify, "get_shopify_tokens", return_value={
            "access_token": "test-token", "shop_domain": "example.myshopify.com",
        }), patch.object(shopify.requests, "get", side_effect=get) as api:
            result = asyncio.run(tool(request))
        self.assertIsNone(result.error)
        self.assertTrue(result.result)
        self.assertEqual(api.call_count, 1)
        return api.call_args.kwargs["params"]

    def test_coerce_int_contract(self):
        cases = (
            (None, 10),
            (True, 10),
            (False, 10),
            ("", 10),
            (" 5 ", 5),
            (5, 5),
            (0, 1),
            (-3, 1),
            (999, 50),
            ("not-a-number", 10),
            (float("inf"), 10),
            (float("nan"), 10),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(shopify._coerce_int(value, 10, 1, 50), expected)

    def test_get_orders_normalizes_limit(self):
        for value, expected in ((None, 10), ("5", 5), (0, 1), (-3, 1), (500, 50),
                                 ("1e309", 10), (float("inf"), 10)):
            with self.subTest(value=value):
                params = self.invoke(shopify.tool_get_orders, value)
                self.assertEqual(params["limit"], expected)

    def test_get_customers_listing_normalizes_limit(self):
        for value, expected in ((None, 10), ("5", 5), (0, 1), (-3, 1), (500, 50),
                                 ("1e309", 10), (float("inf"), 10)):
            with self.subTest(value=value):
                params = self.invoke(shopify.tool_get_customers, value)
                self.assertEqual(params["limit"], expected)

    def test_get_customers_search_normalizes_limit(self):
        for value, expected in ((None, 10), ("5", 5), (0, 1), (-3, 1), (500, 50),
                                 ("1e309", 10), (float("inf"), 10)):
            with self.subTest(value=value):
                params = self.invoke(shopify.tool_get_customers, value, query="Ada")
                self.assertEqual(params["limit"], expected)


if __name__ == "__main__":
    unittest.main()
