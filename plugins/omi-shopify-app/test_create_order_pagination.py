"""Hermetic regression for create_order catalog pagination.

A single /products.json or /price_rules.json page is at most 250 records.
create_order must walk since_id pages or it silently misses later items.
No live Shopify, FastAPI routing, or Pydantic serialization is tested.
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


def product_page(start, count, title_prefix="Filler"):
    items = []
    for n in range(start, start + count):
        items.append({
            "id": n,
            "title": f"{title_prefix} {n}",
            "variants": [{"id": 10000 + n, "price": "10.00"}],
        })
    return {"products": items}


def rule_page(start, count):
    return {"price_rules": [{"id": n, "value_type": "percentage", "value": "-10.0"}
                            for n in range(start, start + count)]}


class FetchAllPagesTests(unittest.TestCase):
    def test_walks_since_id_until_short_page(self):
        pages = [product_page(1, 250), product_page(251, 1, title_prefix="Hidden Widget")]
        with patch.object(shopify, "shopify_api_request", side_effect=pages) as api:
            result = shopify.shopify_fetch_all_pages(
                "u", "/products.json", "products", params={"status": "active"}
            )
        self.assertNotIn("error", result)
        self.assertEqual(len(result["products"]), 251)
        self.assertEqual(result["products"][-1]["title"], "Hidden Widget 251")
        self.assertEqual(api.call_count, 2)
        first_params = api.call_args_list[0].kwargs.get("params") or api.call_args_list[0][1].get("params")
        second_params = api.call_args_list[1].kwargs.get("params") or api.call_args_list[1][1].get("params")
        self.assertEqual(first_params.get("status"), "active")
        self.assertNotIn("since_id", first_params)
        self.assertEqual(second_params.get("since_id"), 250)

    def test_first_page_error_is_returned(self):
        with patch.object(shopify, "shopify_api_request", return_value={"error": "nope"}):
            result = shopify.shopify_fetch_all_pages("u", "/products.json", "products")
        self.assertEqual(result, {"error": "nope"})

    def test_later_page_error_keeps_collected_items(self):
        pages = [product_page(1, 250), {"error": "rate limited"}]
        with patch.object(shopify, "shopify_api_request", side_effect=pages):
            result = shopify.shopify_fetch_all_pages("u", "/products.json", "products")
        self.assertNotIn("error", result)
        self.assertEqual(len(result["products"]), 250)

    def test_price_rules_pagination(self):
        pages = [rule_page(1, 250), rule_page(251, 3)]
        with patch.object(shopify, "shopify_api_request", side_effect=pages):
            result = shopify.shopify_fetch_all_pages("u", "/price_rules.json", "price_rules")
        self.assertEqual(len(result["price_rules"]), 253)

    def test_page_cap_stops_after_max_full_pages(self):
        full = [product_page(1 + i * 250, 250) for i in range(12)]
        with patch.object(shopify, "shopify_api_request", side_effect=full) as api:
            result = shopify.shopify_fetch_all_pages(
                "u", "/products.json", "products", max_pages=10
            )
        self.assertEqual(len(result["products"]), 2500)
        self.assertEqual(api.call_count, 10)


class CreateOrderCatalogTests(unittest.TestCase):
    def invoke(self, api_side_effect, body):
        request = Mock(json=AsyncMock(return_value=body))
        with patch.object(shopify, "get_shopify_tokens", return_value={
            "connected": True, "shop_domain": "example.myshopify.com",
        }), \
             patch.object(shopify, "shopify_api_request", side_effect=api_side_effect) as api:
            result = asyncio.run(shopify.tool_create_order(request))
        return result, api

    def test_create_order_matches_product_past_first_page(self):
        hidden = {
            "id": 251,
            "title": "Hidden Widget",
            "variants": [{"id": 777, "price": "12.00"}],
        }

        def api(uid, method, endpoint, params=None, json_data=None):
            if endpoint == "/customers/42.json":
                return {"customer": {
                    "id": 42, "email": "buyer@example.com",
                    "first_name": "Ada", "last_name": "Buyer",
                }}
            if endpoint == "/products.json":
                since = (params or {}).get("since_id")
                if since is None:
                    return product_page(1, 250)
                return {"products": [hidden]}
            if method == "POST" and endpoint == "/orders.json":
                return {"order": {
                    "id": 9,
                    "name": "#1009",
                    "order_number": 1009,
                    "total_price": "12.00",
                    "currency": "USD",
                    "line_items": [{
                        "quantity": 1,
                        "title": "Hidden Widget",
                        "price": "12.00",
                        "variant_id": 777,
                    }],
                }}
            return {"error": f"unexpected {method} {endpoint}"}

        result, api_mock = self.invoke(api, {
            "uid": "test-user",
            "customer_id": 42,
            "line_items": [{"title": "Hidden Widget", "quantity": 1}],
        })
        self.assertIsNone(result.error)
        self.assertIn("Order Created Successfully", result.result)
        self.assertIn("Hidden Widget", result.result)
        self.assertIn("https://example.myshopify.com/admin/orders/9", result.result)
        product_gets = [
            call for call in api_mock.call_args_list
            if call[0][2] == "/products.json"
        ]
        self.assertGreaterEqual(len(product_gets), 2)

    def test_single_page_still_reports_unknown_product(self):
        def api(uid, method, endpoint, params=None, json_data=None):
            if endpoint == "/customers/42.json":
                return {"customer": {
                    "id": 42, "email": "buyer@example.com",
                    "first_name": "Ada", "last_name": "Buyer",
                }}
            if endpoint == "/products.json":
                return product_page(1, 2)
            return {"error": f"unexpected {method} {endpoint}"}

        result, _api = self.invoke(api, {
            "uid": "test-user",
            "customer_id": 42,
            "line_items": [{"title": "Hidden Widget", "quantity": 1}],
        })
        self.assertIsNone(result.error)
        self.assertIn("not found", result.result.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
