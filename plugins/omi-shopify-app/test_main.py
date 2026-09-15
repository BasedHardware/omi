"""Hermetic regression for null/omitted optional tool params (#13946).

The Omi backend forwards every optional tool parameter the LLM did not
supply as an explicit JSON null, so ``body.get(key, default)`` sees the
key present and returns None instead of the default. ``min(None, 50)``
crashed get_orders/get_customers, and nulls for status, period,
send_receipt, financial_status, country, and line-item fields silently
changed behavior or crashed.

These tests run the real tool handlers through the ``shopify_api_request``
seam. No live Shopify, FastAPI routing, or third-party packages.
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


TOKENS = {"access_token": "tok", "shop_domain": "example.myshopify.com"}


def invoke(handler, body, api):
    """Run a tool handler with stubbed auth and a scripted Shopify API."""
    request = Mock(json=AsyncMock(return_value=body))
    with patch.object(shopify, "get_shopify_tokens", return_value=TOKENS), \
         patch.object(shopify, "shopify_api_request", side_effect=api) as api_mock:
        result = asyncio.run(handler(request))
    return result, api_mock


def last_params(api_mock):
    call = api_mock.call_args_list[-1]
    return call.kwargs.get("params") or {}


def last_endpoint(api_mock):
    return api_mock.call_args_list[-1][0][2]


def post_json(api_mock, endpoint):
    """Return the json_data of the first POST to endpoint."""
    for call in api_mock.call_args_list:
        if len(call[0]) >= 3 and call[0][1] == "POST" and call[0][2] == endpoint:
            return call.kwargs.get("json_data") or {}
    return {}


def orders_api(uid, method, endpoint, params=None, json_data=None):
    if endpoint == "/orders.json":
        return {"orders": [{
            "name": "#1001",
            "total_price": "9.00",
            "currency": "USD",
            "financial_status": "paid",
            "fulfillment_status": "fulfilled",
            "created_at": "2024-01-02T03:04:05Z",
            "customer": None,
            "line_items": [],
        }]}
    return {"error": f"unexpected {method} {endpoint}"}


def customers_api(uid, method, endpoint, params=None, json_data=None):
    if endpoint in ("/customers.json", "/customers/search.json"):
        return {"customers": [{
            "id": 1,
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@example.com",
            "orders_count": 3,
            "total_spent": "42.00",
            "currency": "USD",
        }]}
    return {"error": f"unexpected {method} {endpoint}"}


def create_order_api(uid, method, endpoint, params=None, json_data=None):
    if endpoint == "/customers/42.json":
        return {"customer": {
            "id": 42,
            "email": "ada@example.com",
            "first_name": "Ada",
            "last_name": "Lovelace",
        }}
    if endpoint == "/products.json":
        return {"products": [{
            "id": 1,
            "title": "Custom Item",
            "variants": [{"id": 5, "price": "9.00"}],
        }]}
    if method == "POST" and endpoint == "/orders.json":
        return {"order": {
            "id": 9,
            "name": "#1009",
            "order_number": 1009,
            "total_price": "9.00",
            "currency": "USD",
            "line_items": [{
                "quantity": 1,
                "title": "Custom Item",
                "price": "9.00",
                "variant_id": 5,
            }],
        }}
    return {"error": f"unexpected {method} {endpoint}"}


def create_customer_api(uid, method, endpoint, params=None, json_data=None):
    if endpoint == "/customers/search.json":
        return {"customers": []}
    if method == "POST" and endpoint == "/customers.json":
        return {"customer": {"id": 7}}
    return {"error": f"unexpected {method} {endpoint}"}


class CoerceIntTests(unittest.TestCase):
    def test_null_bool_and_unparseable_fall_back_to_default(self):
        for bad in (None, True, False, "abc", "", [], {}, float("inf"), 1e309):
            with self.subTest(value=bad):
                self.assertEqual(
                    shopify._coerce_int(bad, default=10, minimum=1, maximum=50), 10
                )

    def test_accepts_ints_and_numeric_strings(self):
        self.assertEqual(shopify._coerce_int(7, 10, 1, 50), 7)
        self.assertEqual(shopify._coerce_int("7", 10, 1, 50), 7)
        self.assertEqual(shopify._coerce_int(50, 10, 1, 50), 50)

    def test_clamps_into_range(self):
        self.assertEqual(shopify._coerce_int(0, 10, 1, 50), 1)
        self.assertEqual(shopify._coerce_int(-3, 10, 1, 50), 1)
        self.assertEqual(shopify._coerce_int(500, 10, 1, 50), 50)
        self.assertEqual(shopify._coerce_int("999", 10, 1, 50), 50)


class GetOrdersLimitTests(unittest.TestCase):
    def run_orders(self, body):
        body.setdefault("uid", "test-user")
        return invoke(shopify.tool_get_orders, body, orders_api)

    def test_null_limit_uses_default(self):
        result, api = self.run_orders({"limit": None})
        self.assertIsNone(result.error)
        self.assertIn("#1001", result.result)
        self.assertEqual(last_params(api)["limit"], 10)

    def test_absent_limit_uses_default(self):
        result, api = self.run_orders({})
        self.assertIsNone(result.error)
        self.assertEqual(last_params(api)["limit"], 10)

    def test_valid_limit_passes_through(self):
        result, api = self.run_orders({"limit": 25})
        self.assertIsNone(result.error)
        self.assertEqual(last_params(api)["limit"], 25)

    def test_limit_over_cap_is_capped(self):
        result, api = self.run_orders({"limit": 500})
        self.assertIsNone(result.error)
        self.assertEqual(last_params(api)["limit"], 50)

    def test_zero_and_negative_limit_clamp_to_one(self):
        for bad in (0, -3):
            with self.subTest(limit=bad):
                result, api = self.run_orders({"limit": bad})
                self.assertIsNone(result.error)
                self.assertEqual(last_params(api)["limit"], 1)

    def test_numeric_string_limit_is_coerced(self):
        result, api = self.run_orders({"limit": "7"})
        self.assertIsNone(result.error)
        self.assertEqual(last_params(api)["limit"], 7)

    def test_unparseable_limit_uses_default(self):
        result, api = self.run_orders({"limit": "lots"})
        self.assertIsNone(result.error)
        self.assertEqual(last_params(api)["limit"], 10)

    def test_null_status_uses_any(self):
        # A null status must not reach Shopify as a dropped param: the API
        # would then default to status=open and silently hide closed orders.
        result, api = self.run_orders({"status": None})
        self.assertIsNone(result.error)
        self.assertEqual(last_params(api)["status"], "any")


class GetCustomersLimitTests(unittest.TestCase):
    def run_customers(self, body):
        body.setdefault("uid", "test-user")
        return invoke(shopify.tool_get_customers, body, customers_api)

    def test_null_limit_listing_uses_default(self):
        result, api = self.run_customers({"limit": None})
        self.assertIsNone(result.error)
        self.assertIn("Ada", result.result)
        self.assertEqual(last_endpoint(api), "/customers.json")
        self.assertEqual(last_params(api)["limit"], 10)

    def test_null_limit_search_uses_default(self):
        result, api = self.run_customers({"query": "Ada", "limit": None})
        self.assertIsNone(result.error)
        self.assertEqual(last_endpoint(api), "/customers/search.json")
        self.assertEqual(last_params(api)["limit"], 10)
        self.assertEqual(last_params(api)["query"], "Ada")

    def test_null_query_takes_listing_path(self):
        result, api = self.run_customers({"query": None, "limit": 5})
        self.assertIsNone(result.error)
        self.assertEqual(last_endpoint(api), "/customers.json")
        self.assertEqual(last_params(api)["limit"], 5)

    def test_absent_limit_uses_default(self):
        result, api = self.run_customers({})
        self.assertIsNone(result.error)
        self.assertEqual(last_params(api)["limit"], 10)

    def test_limit_over_cap_is_capped(self):
        result, api = self.run_customers({"limit": 500})
        self.assertIsNone(result.error)
        self.assertEqual(last_params(api)["limit"], 50)

    def test_zero_limit_clamps_to_one(self):
        result, api = self.run_customers({"limit": 0})
        self.assertIsNone(result.error)
        self.assertEqual(last_params(api)["limit"], 1)


class GetAnalyticsPeriodTests(unittest.TestCase):
    def test_null_period_falls_back_to_today(self):
        def api(uid, method, endpoint, params=None, json_data=None):
            if endpoint == "/orders.json":
                return {"orders": []}
            return {"error": f"unexpected {method} {endpoint}"}

        result, _ = invoke(
            shopify.tool_get_analytics, {"uid": "u", "period": None}, api
        )
        self.assertIsNone(result.error)
        self.assertIn("Store Analytics - Today", result.result)


class CreateOrderNullParamTests(unittest.TestCase):
    def run_create_order(self, body):
        body.setdefault("uid", "test-user")
        return invoke(shopify.tool_create_order, body, create_order_api)

    def test_null_item_fields_use_defaults(self):
        # A null line-item title crashed on title.lower(); a null quantity was
        # forwarded to Shopify verbatim.
        result, api = self.run_create_order({
            "customer_id": 42,
            "line_items": [{"title": None, "quantity": None}],
            "send_receipt": False,
        })
        self.assertIsNone(result.error)
        self.assertIn("Order Created Successfully", result.result)
        line_item = post_json(api, "/orders.json")["order"]["line_items"][0]
        self.assertEqual(line_item["quantity"], 1)
        self.assertEqual(line_item["variant_id"], 5)

    def test_null_send_receipt_and_financial_status_use_defaults(self):
        result, api = self.run_create_order({
            "customer_id": 42,
            "line_items": [{"title": "Custom Item", "quantity": 2}],
            "send_receipt": None,
            "financial_status": None,
            "note": None,
            "tags": None,
            "discount_code": None,
        })
        self.assertIsNone(result.error)
        # send_receipt defaults to true: a receipt line must be rendered.
        self.assertIn("Receipt sent to ada@example.com", result.result)
        order = post_json(api, "/orders.json")["order"]
        self.assertEqual(order["financial_status"], "pending")

    def test_explicit_false_send_receipt_is_preserved(self):
        result, api = self.run_create_order({
            "customer_id": 42,
            "line_items": [{"title": "Custom Item", "quantity": 1}],
            "send_receipt": False,
        })
        self.assertIsNone(result.error)
        self.assertNotIn("Receipt sent", result.result)


class CreateCustomerNullParamTests(unittest.TestCase):
    def test_null_name_fields_fall_back_to_generic_name(self):
        result, _ = invoke(shopify.tool_create_customer, {
            "uid": "test-user",
            "email": "new@example.com",
            "first_name": None,
            "last_name": None,
            "phone": None,
            "tags": None,
            "note": None,
            "accepts_marketing": None,
        }, create_customer_api)
        self.assertIsNone(result.error)
        self.assertIn("New Customer", result.result)
        self.assertNotIn("None", result.result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
