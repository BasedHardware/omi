"""Hermetic regression for create_order product disambiguation (#13999).

tool_create_order must never sell a product the customer did not name:
the fuzzy title lookup walks four tiers (exact, request-inside-title,
title-inside-request, shared word) and takes the first product at
whichever tier fires, then always orders variants[0]. With "Omi DevKit 2"
listed before "Omi Necklace" and "Omi Case", a line item titled
"omi units" matches nothing closer, the word tier fires on "omi", the
DevKit is sold, send_receipt (default true) mails the customer a receipt
for it, and the tool answers "Order Created Successfully".

Required behavior after the fix:
- every hit at the first matching tier is collected; one hit sells,
  several ask which product and post nothing;
- a multi-variant product without an explicit variant_id/sku lists its
  variants and asks instead of selling variants[0];
- explicit variant_id is untouched.

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
    "shopify_under_test", Path(__file__).with_name("main.py")
)
shopify = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shopify)


CATALOG = [
    {
        "id": 1,
        "title": "Omi DevKit 2",
        "variants": [{"id": 101, "price": "199.00", "title": "Default"}],
    },
    {
        "id": 2,
        "title": "Omi Necklace",
        "variants": [{"id": 102, "price": "49.00", "title": "Default"}],
    },
    {
        "id": 3,
        "title": "Omi Case",
        "variants": [
            {"id": 103, "price": "29.00", "title": "Black"},
            {"id": 104, "price": "35.00", "title": "White"},
        ],
    },
]


def make_api(posted):
    def api(uid, method, endpoint, params=None, json_data=None):
        if endpoint == "/customers/42.json":
            return {
                "customer": {
                    "id": 42,
                    "email": "buyer@example.com",
                    "first_name": "Ada",
                    "last_name": "Buyer",
                }
            }
        if endpoint == "/products.json":
            return {"products": CATALOG}
        if method == "POST" and endpoint == "/orders.json":
            posted.append(json_data)
            return {
                "order": {
                    "id": 9,
                    "name": "#1009",
                    "order_number": 1009,
                    "total_price": "199.00",
                    "currency": "USD",
                    "line_items": [
                        {
                            "quantity": 1,
                            "title": "Omi DevKit 2",
                            "price": "199.00",
                            "variant_id": 101,
                        }
                    ],
                }
            }
        return {"error": f"unexpected {method} {endpoint}"}

    return api


class CreateOrderDisambiguationTests(unittest.TestCase):
    def invoke(self, body):
        posted = []
        request = Mock(json=AsyncMock(return_value=body))
        with (
            patch.object(
                shopify,
                "get_shopify_tokens",
                return_value={
                    "connected": True,
                    "shop_domain": "example.myshopify.com",
                },
            ),
            patch.object(
                shopify, "get_user_shop", return_value="example.myshopify.com"
            ),
            patch.object(shopify, "shopify_api_request", side_effect=make_api(posted)),
        ):
            result = asyncio.run(shopify.tool_create_order(request))
        return result, posted

    def base_body(self, **overrides):
        body = {
            "uid": "test-user",
            "customer_id": 42,
            "line_items": [{"title": "omi units", "quantity": 1}],
        }
        body.update(overrides)
        return body

    def test_shared_word_does_not_sell_first_product(self):
        result, posted = self.invoke(self.base_body())
        self.assertEqual(posted, [], "ambiguous 'omi units' must not post any order")
        self.assertIsNone(result.error)
        text = (result.result or "").lower()
        self.assertIn("omi devkit 2", text)
        self.assertIn("omi necklace", text)
        self.assertIn("omi case", text)
        self.assertNotIn("order created successfully", text)

    def test_multi_variant_without_sku_asks_for_variant(self):
        result, posted = self.invoke(
            self.base_body(line_items=[{"title": "Omi Case", "quantity": 1}])
        )
        self.assertEqual(
            posted, [], "multi-variant 'Omi Case' must not sell variants[0]"
        )
        self.assertIsNone(result.error)
        text = (result.result or "").lower()
        self.assertIn("black", text)
        self.assertIn("white", text)
        self.assertNotIn("order created successfully", text)

    def test_exact_single_variant_still_sells(self):
        result, posted = self.invoke(
            self.base_body(line_items=[{"title": "Omi Necklace", "quantity": 1}])
        )
        self.assertEqual(len(posted), 1)
        variant = posted[0]["order"]["line_items"][0]["variant_id"]
        self.assertEqual(variant, 102)
        self.assertIsNone(result.error)
        self.assertIn("Order Created Successfully", result.result or "")

    def test_explicit_variant_id_is_untouched(self):
        result, posted = self.invoke(
            self.base_body(
                line_items=[{"title": "omi units", "quantity": 1, "variant_id": 104}]
            )
        )
        self.assertEqual(len(posted), 1)
        variant = posted[0]["order"]["line_items"][0]["variant_id"]
        self.assertEqual(variant, 104)

    def test_sku_selects_matching_variant(self):
        catalog = [
            dict(
                p,
                variants=[
                    dict(v, sku="CASE-BLK")
                    if v["id"] == 103
                    else dict(v, sku="CASE-WHT")
                    for v in p["variants"]
                ],
            )
            for p in CATALOG
        ]

        def api(uid, method, endpoint, params=None, json_data=None):
            if endpoint == "/customers/42.json":
                return {
                    "customer": {
                        "id": 42,
                        "email": "buyer@example.com",
                        "first_name": "Ada",
                        "last_name": "Buyer",
                    }
                }
            if endpoint == "/products.json":
                return {"products": catalog}
            if method == "POST" and endpoint == "/orders.json":
                posted.append(json_data)
                return {
                    "order": {
                        "id": 9,
                        "name": "#1009",
                        "order_number": 1009,
                        "total_price": "35.00",
                        "currency": "USD",
                        "line_items": [
                            {
                                "quantity": 1,
                                "title": "Omi Case",
                                "price": "35.00",
                                "variant_id": 104,
                            }
                        ],
                    }
                }
            return {"error": f"unexpected {method} {endpoint}"}

        posted = []
        request = Mock(
            json=AsyncMock(
                return_value=self.base_body(
                    line_items=[{"title": "Omi Case", "quantity": 1, "sku": "case-wht"}]
                )
            )
        )
        with (
            patch.object(
                shopify,
                "get_shopify_tokens",
                return_value={
                    "connected": True,
                    "shop_domain": "example.myshopify.com",
                },
            ),
            patch.object(
                shopify, "get_user_shop", return_value="example.myshopify.com"
            ),
            patch.object(shopify, "shopify_api_request", side_effect=api),
        ):
            result = asyncio.run(shopify.tool_create_order(request))
        self.assertIsNone(result.error)
        self.assertIn("Order Created Successfully", result.result or "")
        self.assertEqual(len(posted), 1)
        self.assertEqual(posted[0]["order"]["line_items"][0]["variant_id"], 104)

    def test_unknown_product_still_lists_catalog(self):
        result, posted = self.invoke(
            self.base_body(line_items=[{"title": "Zebra Unicorn", "quantity": 1}])
        )
        self.assertEqual(posted, [])
        self.assertIsNone(result.error)
        self.assertIn("not found", (result.result or "").lower())

    def test_shared_word_with_all_products_asks(self):
        # "Omi Spaceship" shares "omi" with every product: ambiguous,
        # so the tool must ask instead of selling the first listing.
        result, posted = self.invoke(
            self.base_body(line_items=[{"title": "Omi Spaceship", "quantity": 1}])
        )
        self.assertEqual(posted, [])
        self.assertIsNone(result.error)
        text = (result.result or "").lower()
        self.assertIn("omi devkit 2", text)
        self.assertNotIn("order created successfully", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
