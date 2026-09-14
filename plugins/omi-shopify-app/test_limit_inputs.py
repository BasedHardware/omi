"""Regression tests for limit handling in get_orders and get_customers.

The Omi backend models every optional tool parameter as ``Optional[int]``
with a ``None`` default and forwards the model's arguments verbatim, so
``{"limit": null}`` is what an ordinary "show my recent orders" request looks
like on the wire. ``tool_get_orders`` and ``tool_get_customers`` used to do
``min(body.get("limit", 10), 50)`` on the raw value, which raises
``TypeError`` for ``None`` (and for numeric strings), so both tools answered
``... '<' not supported between instances of 'int' and 'NoneType'``. Values of
``0`` or below were forwarded unchanged as Shopify's ``limit`` query
parameter, which the Admin API rejects.

Hermetic production-handler tests in the style of
test_create_order_pagination.py: HTTP, framework and token storage are
doubles, so the suite runs on a stdlib-only interpreter and never touches
the network.
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
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
    "requests": module("requests", RequestException=OSError, get=Mock(), post=Mock()),
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

TOKENS = {"access_token": "test-placeholder", "shop_domain": "example.myshopify.com"}
ORDER = {
    "name": "#1001",
    "total_price": "42.00",
    "currency": "USD",
    "financial_status": "paid",
    "fulfillment_status": None,
    "customer": {"first_name": "Ada", "last_name": "Lovelace"},
    "created_at": "2026-09-14T10:00:00-04:00",
}
CUSTOMER = {
    "first_name": "Ada",
    "last_name": "Lovelace",
    "email": "ada@example.com",
    "orders_count": 3,
    "total_spent": "126.00",
    "currency": "USD",
}

# (handler, extra request fields, expected path suffix, upstream payload)
TOOLS = [
    ("tool_get_orders", {}, "/orders.json", {"orders": [ORDER]}),
    ("tool_get_customers", {}, "/customers.json", {"customers": [CUSTOMER]}),
    ("tool_get_customers", {"query": "ada"}, "/customers/search.json", {"customers": [CUSTOMER]}),
]


class LimitInputTests(unittest.TestCase):
    def call(self, handler, extra, limit, payload):
        response = Mock(status_code=200, content=b"{}")
        response.json.return_value = payload
        request = Mock(json=AsyncMock(return_value={"uid": "test-user", "limit": limit, **extra}))
        with patch.object(shopify, "get_shopify_tokens", return_value=TOKENS), \
                patch.object(shopify.requests, "get", return_value=response) as get:
            result = asyncio.run(getattr(shopify, handler)(request))
        self.assertEqual(get.call_count, 1, f"{handler}: {result.error}")
        return result, get.call_args.args[0], get.call_args.kwargs["params"]

    def assert_limit(self, limit, expected, label):
        for handler, extra, suffix, payload in TOOLS:
            with self.subTest(handler=handler, extra=extra, case=label):
                result, url, params = self.call(handler, extra, limit, payload)
                self.assertIsNone(result.error, result.error)
                self.assertIsNotNone(result.result)
                self.assertTrue(url.endswith(suffix), url)
                self.assertEqual(params["limit"], expected)

    def test_json_null_falls_back_to_default(self):
        self.assert_limit(None, 10, "null")

    def test_numeric_string_is_coerced(self):
        self.assert_limit("5", 5, "string")

    def test_non_positive_is_clamped_to_one(self):
        self.assert_limit(0, 1, "zero")
        self.assert_limit(-3, 1, "negative")

    def test_oversized_is_capped_at_fifty(self):
        self.assert_limit(500, 50, "oversized")

    def test_unparseable_and_overflowing_fall_back_to_default(self):
        self.assert_limit("a few", 10, "text")
        # json.loads turns 1e309 into float('inf'); int(inf) raises OverflowError.
        self.assert_limit(float("inf"), 10, "overflow")

    def test_results_are_rendered_for_the_default_request(self):
        result, _, _ = self.call("tool_get_orders", {}, None, {"orders": [ORDER]})
        self.assertIn("#1001", result.result)
        result, _, _ = self.call("tool_get_customers", {}, None, {"customers": [CUSTOMER]})
        self.assertIn("Ada Lovelace", result.result)


if __name__ == "__main__":
    unittest.main()
