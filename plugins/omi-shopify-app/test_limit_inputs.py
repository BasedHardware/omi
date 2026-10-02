"""Hermetic regression tests for Shopify chat tool input coercion (#13946).

Ensures optional inputs like limit, period, and request bodies are coerced
defensively without TypeErrors, AttributeErrors, or unexpected crashes.
Runs under standard library unittest without third-party dependencies.
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
    "requests": module("requests", RequestException=OSError),
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


def mock_request(json_data):
    req = Mock()
    req.json = AsyncMock(return_value=json_data)
    return req


class TestCoerceInt(unittest.TestCase):
    def test_default_on_none(self):
        self.assertEqual(shopify._coerce_int(None), 10)

    def test_default_on_bool(self):
        self.assertEqual(shopify._coerce_int(True), 10)
        self.assertEqual(shopify._coerce_int(False), 10)

    def test_default_on_invalid_string(self):
        self.assertEqual(shopify._coerce_int("invalid"), 10)
        self.assertEqual(shopify._coerce_int(""), 10)

    def test_default_on_complex_types(self):
        self.assertEqual(shopify._coerce_int({}), 10)
        self.assertEqual(shopify._coerce_int([]), 10)

    def test_parses_numeric_string(self):
        self.assertEqual(shopify._coerce_int("25"), 25)

    def test_parses_int(self):
        self.assertEqual(shopify._coerce_int(20), 20)

    def test_clamps_maximum(self):
        self.assertEqual(shopify._coerce_int(999), 50)
        self.assertEqual(shopify._coerce_int("100"), 50)

    def test_clamps_minimum(self):
        self.assertEqual(shopify._coerce_int(-5), 1)
        self.assertEqual(shopify._coerce_int(0), 1)

    def test_custom_defaults_and_bounds(self):
        self.assertEqual(shopify._coerce_int(None, default=5, minimum=2, maximum=8), 5)
        self.assertEqual(shopify._coerce_int(1, default=5, minimum=2, maximum=8), 2)
        self.assertEqual(shopify._coerce_int(10, default=5, minimum=2, maximum=8), 8)


class TestToolGetOrdersInputs(unittest.TestCase):
    def setUp(self):
        self.api_patcher = patch.object(shopify, "shopify_api_request")
        self.mock_api = self.api_patcher.start()
        self.mock_api.return_value = {"orders": []}

        self.tokens_patcher = patch.object(shopify, "get_shopify_tokens")
        self.mock_tokens = self.tokens_patcher.start()
        self.mock_tokens.return_value = {"access_token": "token123"}

    def tearDown(self):
        self.api_patcher.stop()
        self.tokens_patcher.stop()

    def test_get_orders_omitted_limit(self):
        req = mock_request({"uid": "user-1"})
        res = asyncio.run(shopify.tool_get_orders(req))
        self.assertIsNone(res.error)
        self.mock_api.assert_called_once()
        params = self.mock_api.call_args[1].get("params", {})
        self.assertEqual(params.get("limit"), 10)

    def test_get_orders_null_limit(self):
        req = mock_request({"uid": "user-1", "limit": None})
        res = asyncio.run(shopify.tool_get_orders(req))
        self.assertIsNone(res.error)
        params = self.mock_api.call_args[1].get("params", {})
        self.assertEqual(params.get("limit"), 10)

    def test_get_orders_string_limit(self):
        req = mock_request({"uid": "user-1", "limit": "25"})
        res = asyncio.run(shopify.tool_get_orders(req))
        self.assertIsNone(res.error)
        params = self.mock_api.call_args[1].get("params", {})
        self.assertEqual(params.get("limit"), 25)

    def test_get_orders_clamped_limit(self):
        req = mock_request({"uid": "user-1", "limit": 999})
        res = asyncio.run(shopify.tool_get_orders(req))
        self.assertIsNone(res.error)
        params = self.mock_api.call_args[1].get("params", {})
        self.assertEqual(params.get("limit"), 50)

    def test_get_orders_bool_limit(self):
        req = mock_request({"uid": "user-1", "limit": True})
        res = asyncio.run(shopify.tool_get_orders(req))
        self.assertIsNone(res.error)
        params = self.mock_api.call_args[1].get("params", {})
        self.assertEqual(params.get("limit"), 10)

    def test_get_orders_null_body(self):
        req = mock_request(None)
        res = asyncio.run(shopify.tool_get_orders(req))
        self.assertEqual(res.error, "User ID is required")


class TestToolGetCustomersInputs(unittest.TestCase):
    def setUp(self):
        self.api_patcher = patch.object(shopify, "shopify_api_request")
        self.mock_api = self.api_patcher.start()
        self.mock_api.return_value = {"customers": []}

        self.tokens_patcher = patch.object(shopify, "get_shopify_tokens")
        self.mock_tokens = self.tokens_patcher.start()
        self.mock_tokens.return_value = {"access_token": "token123"}

    def tearDown(self):
        self.api_patcher.stop()
        self.tokens_patcher.stop()

    def test_get_customers_omitted_limit(self):
        req = mock_request({"uid": "user-1"})
        res = asyncio.run(shopify.tool_get_customers(req))
        self.assertIsNone(res.error)
        params = self.mock_api.call_args[1].get("params", {})
        self.assertEqual(params.get("limit"), 10)

    def test_get_customers_null_limit(self):
        req = mock_request({"uid": "user-1", "limit": None})
        res = asyncio.run(shopify.tool_get_customers(req))
        self.assertIsNone(res.error)
        params = self.mock_api.call_args[1].get("params", {})
        self.assertEqual(params.get("limit"), 10)

    def test_get_customers_string_limit(self):
        req = mock_request({"uid": "user-1", "limit": "35"})
        res = asyncio.run(shopify.tool_get_customers(req))
        self.assertIsNone(res.error)
        params = self.mock_api.call_args[1].get("params", {})
        self.assertEqual(params.get("limit"), 35)

    def test_get_customers_clamped_limit(self):
        req = mock_request({"uid": "user-1", "limit": 999})
        res = asyncio.run(shopify.tool_get_customers(req))
        self.assertIsNone(res.error)
        params = self.mock_api.call_args[1].get("params", {})
        self.assertEqual(params.get("limit"), 50)

    def test_get_customers_bool_limit(self):
        req = mock_request({"uid": "user-1", "limit": False})
        res = asyncio.run(shopify.tool_get_customers(req))
        self.assertIsNone(res.error)
        params = self.mock_api.call_args[1].get("params", {})
        self.assertEqual(params.get("limit"), 10)

    def test_get_customers_null_body(self):
        req = mock_request(None)
        res = asyncio.run(shopify.tool_get_customers(req))
        self.assertEqual(res.error, "User ID is required")


class TestToolGetAnalyticsInputs(unittest.TestCase):
    def setUp(self):
        self.tokens_patcher = patch.object(shopify, "get_shopify_tokens")
        self.mock_tokens = self.tokens_patcher.start()
        self.mock_tokens.return_value = {"access_token": "token123"}

        self.api_patcher = patch.object(shopify, "shopify_api_request")
        self.mock_api = self.api_patcher.start()
        self.mock_api.return_value = {"orders": []}

    def tearDown(self):
        self.tokens_patcher.stop()
        self.api_patcher.stop()

    def test_get_analytics_null_period(self):
        req = mock_request({"uid": "user-1", "period": None})
        res = asyncio.run(shopify.tool_get_analytics(req))
        self.assertIsNone(res.error)

    def test_get_analytics_null_body(self):
        req = mock_request(None)
        res = asyncio.run(shopify.tool_get_analytics(req))
        self.assertEqual(res.error, "User ID is required")


if __name__ == "__main__":
    unittest.main()
