"""Hermetic regression: create_order must sell exactly the product the user named.

The title lookup took the first product at each fuzzy tier: the request
contained in a title, a title contained in the request, then any shared
word. With "Omi DevKit 2" listed before "Omi Necklace" and "Omi Case", a
line item titled "omi units" matches nothing exactly, so the word tier fired
and the first product containing "omi" won: an order for DevKits, receipt
emailed to the customer, reported as success. A product with several variants always sold
variants[0] whatever the customer asked for.

Now the first tier with a hit must have exactly one hit, and a product with
several variants needs a SKU or the tool asks. No live Shopify, no
framework.

Run: python3 plugins/omi-shopify-app/test_create_order_product_match.py
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
    "requests": module("requests", RequestException=OSError),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module(
        "fastapi", **{name: Framework for name in ("FastAPI", "HTTPException", "Request", "Query", "Form")}
    ),
    "fastapi.responses": module(
        "fastapi.responses", **{name: Framework for name in ("HTMLResponse", "RedirectResponse", "JSONResponse")}
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
spec = importlib.util.spec_from_file_location("shopify_under_test", Path(__file__).with_name("main.py"))
shopify = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shopify)

PRODUCTS = [
    {"id": 1, "title": "Omi DevKit 2", "variants": [{"id": 101, "price": "69.99", "sku": "DK2"}]},
    {"id": 2, "title": "Omi Necklace", "variants": [{"id": 102, "price": "89.00", "sku": "NECK"}]},
    {
        "id": 3,
        "title": "Omi Case",
        "variants": [
            {"id": 103, "price": "19.00", "sku": "CASE-BLK", "title": "Black"},
            {"id": 104, "price": "19.00", "sku": "CASE-WHT", "title": "White"},
        ],
    },
]


def api_for(posted):
    def api(uid, method, endpoint, params=None, json_data=None):
        if endpoint == "/customers/42.json":
            return {"customer": {"id": 42, "email": "buyer@example.com", "first_name": "Ada", "last_name": "Buyer"}}
        if endpoint == "/products.json":
            return {"products": PRODUCTS}
        if method == "POST" and endpoint == "/orders.json":
            posted.append(json_data)
            items = json_data["order"]["line_items"]
            return {
                "order": {
                    "id": 9,
                    "name": "#1009",
                    "order_number": 1009,
                    "total_price": "0",
                    "currency": "USD",
                    "line_items": [
                        {"quantity": i["quantity"], "title": "x", "price": "0", "variant_id": i["variant_id"]}
                        for i in items
                    ],
                }
            }
        return {"error": f"unexpected {method} {endpoint}"}

    return api


class CreateOrderSellsTheNamedProduct(unittest.TestCase):
    def order(self, item):
        posted = []
        request = Mock(json=AsyncMock(return_value={"uid": "u", "customer_id": 42, "line_items": [item]}))
        with patch.object(
            shopify, "get_shopify_tokens", return_value={"connected": True, "shop_domain": "example.myshopify.com"}
        ), patch.object(shopify, "shopify_api_request", side_effect=api_for(posted)):
            result = asyncio.run(shopify.tool_create_order(request))
        return result, posted

    def test_word_tier_with_several_hits_asks_instead_of_selling_the_first(self):
        result, posted = self.order({"title": "omi units", "quantity": 3})
        self.assertEqual(posted, [])
        self.assertIn("Which product did you mean", result.result)
        self.assertIn("Omi Necklace", result.result)
        self.assertIn("Omi DevKit 2", result.result)

    def test_exact_title_sells_that_product(self):
        result, posted = self.order({"title": "omi necklace", "quantity": 3})
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted[0]["order"]["line_items"], [{"variant_id": 102, "quantity": 3}])
        self.assertIn("Order Created Successfully", result.result)

    def test_unique_contains_match_sells_it(self):
        result, posted = self.order({"title": "necklace", "quantity": 1})
        self.assertEqual(posted[0]["order"]["line_items"][0]["variant_id"], 102)

    def test_title_contained_in_a_longer_request_still_resolves(self):
        result, posted = self.order({"title": "3 omi necklaces please", "quantity": 3})
        self.assertEqual(posted[0]["order"]["line_items"][0]["variant_id"], 102)

    def test_multi_variant_product_needs_a_sku(self):
        result, posted = self.order({"title": "Omi Case", "quantity": 2})
        self.assertEqual(posted, [])
        self.assertIn("comes in 2 variants", result.result)
        self.assertIn("CASE-WHT", result.result)
        result, posted = self.order({"title": "Omi Case", "quantity": 2, "sku": "case-wht"})
        self.assertEqual(posted[0]["order"]["line_items"], [{"variant_id": 104, "quantity": 2}])

    def test_explicit_variant_id_is_untouched(self):
        result, posted = self.order({"title": "anything", "quantity": 1, "variant_id": 101})
        self.assertEqual(posted[0]["order"]["line_items"], [{"variant_id": 101, "quantity": 1}])


if __name__ == "__main__":
    unittest.main()
