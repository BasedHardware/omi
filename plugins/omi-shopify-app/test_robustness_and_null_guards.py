"""Hermetic unit tests for Shopify plugin null guards, error resilience, and numerical coercion.

Ensures that:
- Orders with JSON null numeric fields (subtotal_price, total_discounts,
  total_price, total_tax, total_shipping_price_set, refund transactions)
  do not crash get_analytics or get_order_details with TypeError or AttributeError.
- Discount code lookups in create_order safely handle null codes, null price_rule
  values, and non-dict entries without AttributeError.
- Complete draft order retry loop handles list error messages from Shopify
  API without crashing on .lower().
- Shipping address and discount code inputs tolerate non-dict / non-string shapes.

Runs under standard library unittest without third-party dependencies.
Run: python plugins/omi-shopify-app/test_robustness_and_null_guards.py
"""

import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, Mock, patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# Load test harness from test_limit_inputs
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_limit_inputs import mock_request, shopify


class TestSafeFloat(unittest.TestCase):
    def test_default_on_none_and_bool(self):
        self.assertEqual(shopify._safe_float(None), 0.0)
        self.assertEqual(shopify._safe_float(True), 0.0)
        self.assertEqual(shopify._safe_float(False), 0.0)

    def test_default_on_invalid_and_empty_strings(self):
        self.assertEqual(shopify._safe_float(""), 0.0)
        self.assertEqual(shopify._safe_float("abc"), 0.0)
        self.assertEqual(shopify._safe_float("   "), 0.0)

    def test_default_on_containers(self):
        self.assertEqual(shopify._safe_float({}), 0.0)
        self.assertEqual(shopify._safe_float([]), 0.0)

    def test_parses_numeric_types(self):
        self.assertEqual(shopify._safe_float(10), 10.0)
        self.assertEqual(shopify._safe_float(12.5), 12.5)
        self.assertEqual(shopify._safe_float("42.75"), 42.75)
        self.assertEqual(shopify._safe_float("-3.5"), -3.5)

    def test_custom_default(self):
        self.assertEqual(shopify._safe_float(None, default=5.0), 5.0)
        self.assertEqual(shopify._safe_float("bad", default=-1.0), -1.0)


class TestShopifyRobustnessAndNullGuards(unittest.TestCase):
    def setUp(self):
        self.tokens_patcher = patch.object(shopify, "get_shopify_tokens")
        self.mock_tokens = self.tokens_patcher.start()
        self.mock_tokens.return_value = {
            "access_token": "token123",
            "shop_domain": "test-store.myshopify.com",
        }

    def tearDown(self):
        self.tokens_patcher.stop()

    def test_analytics_with_null_numeric_fields(self):
        orders_data = [
            {
                "id": 1,
                "subtotal_price": None,
                "total_discounts": None,
                "total_price": None,
                "total_tax": None,
                "total_shipping_price_set": None,
                "currency": "USD",
                "line_items": [],
                "refunds": [{"transactions": [{"amount": None}]}],
            },
            {
                "id": 2,
                "subtotal_price": "50.00",
                "total_discounts": "5.00",
                "total_price": "55.00",
                "total_tax": "5.00",
                "total_shipping_price_set": {
                    "shop_money": {"amount": "5.00"}
                },
                "currency": "USD",
                "line_items": [{"variant_id": 101, "quantity": 1}],
                "refunds": [],
            },
        ]
        with patch.object(shopify, "shopify_api_request", return_value={"orders": orders_data}):
            req = mock_request({"uid": "user-1", "period": "today"})
            res = asyncio.run(shopify.tool_get_analytics(req))
            self.assertIsNone(res.error)
            self.assertIn("Gross Sales", res.result)
            self.assertIn("Net Sales", res.result)

    def test_order_details_with_null_shipping_price_set(self):
        order_data = {
            "id": 123,
            "name": "#1123",
            "subtotal_price": "25.00",
            "total_shipping_price_set": None,
            "total_tax": "2.50",
            "total_price": "27.50",
            "currency": "USD",
            "created_at": "2026-01-20T10:00:00Z",
            "line_items": [{"quantity": 1, "title": "DevKit", "price": "25.00"}],
        }
        with patch.object(shopify, "shopify_api_request", return_value={"order": order_data}):
            req = mock_request({"uid": "user-1", "order_id": 123})
            res = asyncio.run(shopify.tool_get_order_details(req))
            self.assertIsNone(res.error)
            self.assertIn("Order #1123", res.result)
            self.assertIn("Shipping:", res.result)

    def test_create_order_with_null_discount_code_in_price_rule(self):
        def mock_api(uid, method, endpoint, params=None, json_data=None):
            if "/price_rules.json" in endpoint:
                return {
                    "price_rules": [
                        {"id": 999, "value_type": "percentage", "value": None},
                        {"id": None},  # Missing ID
                        "not-a-dict",  # Corrupted entry
                    ]
                }
            if "/price_rules/999/discount_codes.json" in endpoint:
                return {
                    "discount_codes": [
                        {"code": None},
                        "not-a-dict",
                    ]
                }
            if "/products.json" in endpoint:
                return {
                    "products": [
                        {"id": 1, "title": "Widget", "variants": [{"id": 101, "price": "10.00"}]}
                    ]
                }
            if "/draft_orders.json" in endpoint:
                return {"draft_order": {"id": 888}}
            if "/draft_orders/888/complete.json" in endpoint:
                return {
                    "draft_order": {
                        "id": 888,
                        "order": {
                            "id": 777,
                            "name": "#1777",
                            "total_price": "10.00",
                            "total_discounts": None,
                            "line_items": [],
                        }
                    }
                }
            return {}

        with patch.object(shopify, "shopify_api_request", side_effect=mock_api), \
             patch.object(shopify, "shopify_fetch_all_pages", side_effect=lambda uid, ep, k, **kwargs: mock_api(uid, "GET", ep)):
            req = mock_request({
                "uid": "user-1",
                "customer_email": "buyer@example.com",
                "line_items": [{"title": "Widget", "quantity": 1}],
                "discount_code": "SAVE10"
            })
            res = asyncio.run(shopify.tool_create_order(req))
            self.assertIsNone(res.error)
            self.assertIn("Order Created Successfully", res.result)

    def test_create_order_draft_complete_list_error_retry(self):
        call_count = 0

        def mock_api(uid, method, endpoint, params=None, json_data=None):
            nonlocal call_count
            if "/products.json" in endpoint:
                return {
                    "products": [
                        {"id": 1, "title": "Widget", "variants": [{"id": 101, "price": "10.00"}]}
                    ]
                }
            if "/draft_orders.json" in endpoint:
                return {"draft_order": {"id": 888}}
            if "/draft_orders/888/complete.json" in endpoint:
                call_count += 1
                if call_count < 2:
                    return {"error": ["Order is not finished calculating. Please wait."]}
                return {
                    "draft_order": {
                        "id": 888,
                        "order": {
                            "id": 777,
                            "name": "#1777",
                            "total_price": "10.00",
                            "total_discounts": "0.00",
                            "line_items": [],
                        }
                    }
                }
            return {}

        with patch.object(shopify, "shopify_api_request", side_effect=mock_api), \
             patch.object(shopify, "shopify_fetch_all_pages", side_effect=lambda uid, ep, k, **kwargs: mock_api(uid, "GET", ep)), \
             patch("time.sleep"):
            req = mock_request({
                "uid": "user-1",
                "customer_email": "buyer@example.com",
                "line_items": [{"title": "Widget", "quantity": 1}],
                "shipping_address": {"country": "US"}
            })
            res = asyncio.run(shopify.tool_create_order(req))
            self.assertIsNone(res.error)
            self.assertEqual(call_count, 2)
            self.assertIn("Order Created Successfully", res.result)

    def test_create_order_with_non_dict_shipping_address(self):
        def mock_api(uid, method, endpoint, params=None, json_data=None):
            if "/products.json" in endpoint:
                return {
                    "products": [
                        {"id": 1, "title": "Widget", "variants": [{"id": 101, "price": "10.00"}]}
                    ]
                }
            if "/orders.json" in endpoint:
                return {
                    "order": {
                        "id": 555,
                        "name": "#1555",
                        "total_price": "10.00",
                        "line_items": [],
                    }
                }
            return {}

        with patch.object(shopify, "shopify_api_request", side_effect=mock_api), \
             patch.object(shopify, "shopify_fetch_all_pages", side_effect=lambda uid, ep, k, **kwargs: mock_api(uid, "GET", ep)):
            req = mock_request({
                "uid": "user-1",
                "customer_email": "buyer@example.com",
                "line_items": [{"title": "Widget", "quantity": 1}],
                "shipping_address": "123 Random St (invalid non-dict)",
            })
            res = asyncio.run(shopify.tool_create_order(req))
            self.assertIsNone(res.error)
            self.assertIn("Order Created Successfully", res.result)

    def test_create_order_with_numeric_discount_code(self):
        def mock_api(uid, method, endpoint, params=None, json_data=None):
            if "/products.json" in endpoint:
                return {
                    "products": [
                        {"id": 1, "title": "Widget", "variants": [{"id": 101, "price": "10.00"}]}
                    ]
                }
            if "/price_rules.json" in endpoint:
                return {"price_rules": []}
            if "/draft_orders.json" in endpoint:
                return {"draft_order": {"id": 888}}
            if "/draft_orders/888/complete.json" in endpoint:
                return {
                    "draft_order": {
                        "id": 888,
                        "order": {
                            "id": 999,
                            "name": "#1999",
                            "total_price": "10.00",
                            "total_discounts": None,
                            "line_items": [],
                        }
                    }
                }
            return {}

        with patch.object(shopify, "shopify_api_request", side_effect=mock_api), \
             patch.object(shopify, "shopify_fetch_all_pages", side_effect=lambda uid, ep, k, **kwargs: mock_api(uid, "GET", ep)):
            req = mock_request({
                "uid": "user-1",
                "customer_email": "buyer@example.com",
                "line_items": [{"title": "Widget", "quantity": 1}],
                "discount_code": 100,  # numeric integer discount code
            })
            res = asyncio.run(shopify.tool_create_order(req))
            self.assertIsNone(res.error)
            self.assertIn("Order Created Successfully", res.result)

    def test_shopify_api_request_stringifies_list_errors(self):
        mock_resp = Mock()
        mock_resp.status_code = 422
        mock_resp.content = b'{"errors": ["Draft order calculating", "Inventory unavailable"]}'
        mock_resp.json.return_value = {"errors": ["Draft order calculating", "Inventory unavailable"]}

        with patch.object(shopify.requests, "get", return_value=mock_resp, create=True):
            res = shopify.shopify_api_request("user-1", "GET", "/test.json")
            self.assertIn("error", res)
            self.assertIsInstance(res["error"], str)
            self.assertEqual(res["error"], "Draft order calculating, Inventory unavailable")


if __name__ == "__main__":
    unittest.main(verbosity=2)
