"""Hermetic regression tests for Shopify analytics money coercion.

Shopify sends money fields as strings, but several (``total_tax``,
``subtotal_price``, a refund ``amount``, a line-item ``price``) can be ``null``
or absent on some order states. ``float(o.get("total_price", 0))`` does not
survive that: ``dict.get`` returns the present-but-null value, and
``float(None)`` raises TypeError. Because ``tool_get_analytics`` sums these
inside one broad ``try``, a single null-bearing order discarded the entire
financial report and surfaced a Python ``TypeError`` to the user.

Runs under standard library unittest without third-party dependencies.
"""

import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


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


fastapi_responses = module(
    "fastapi.responses",
    HTMLResponse=Framework,
    RedirectResponse=Framework,
    JSONResponse=Framework,
)
stubs = {
    "requests": module("requests", RequestException=OSError),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module(
        "fastapi",
        **{name: Framework for name in ("FastAPI", "HTTPException", "Request", "Query", "Form")},
    ),
    "fastapi.responses": fastapi_responses,
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
    "shopify_main_money_tested", Path(__file__).with_name("main.py")
)
shopify = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(shopify)


class MoneyCoercion(unittest.TestCase):
    def test_parses_the_string_shopify_actually_sends(self):
        self.assertEqual(shopify._money("12.50"), 12.50)
        self.assertEqual(shopify._money("0.00"), 0.0)

    def test_accepts_real_numbers(self):
        self.assertEqual(shopify._money(7), 7.0)
        self.assertEqual(shopify._money(3.5), 3.5)

    def test_null_takes_the_default_instead_of_raising(self):
        # The crash: float(None) -> TypeError.
        self.assertEqual(shopify._money(None), 0.0)
        self.assertEqual(shopify._money(None, default=1.0), 1.0)

    def test_blank_and_non_numeric_take_the_default(self):
        for value in ("", "  ", "N/A", "free", [], {}):
            with self.subTest(value=value):
                self.assertEqual(shopify._money(value), 0.0)

    def test_booleans_do_not_count_as_amounts(self):
        # float(True) is 1.0; a money field is never a bool.
        self.assertEqual(shopify._money(True), 0.0)
        self.assertEqual(shopify._money(False), 0.0)


class OldPatternCrashed(unittest.TestCase):
    """Document the exact expression this fix replaces, independent of _money."""

    def test_float_get_default_zero_raises_on_a_present_null(self):
        # This is verbatim what the analytics handler used to compute per order.
        order = {"total_price": None}
        with self.assertRaises(TypeError):
            float(order.get("total_price", 0))

    def test_the_default_never_applied_to_a_present_null_key(self):
        # dict.get returns None (not 0) when the key exists with a null value.
        self.assertIsNone({"total_tax": None}.get("total_tax", 0))


class SumSurvivesANullOrder(unittest.TestCase):
    """Mirror the real summation pattern in tool_get_analytics."""

    def test_one_null_field_does_not_discard_the_whole_total(self):
        orders = [
            {"total_price": "10.00"},
            {"total_price": None},   # the poison order
            {"total_price": "5.50"},
        ]
        # Before the fix this raised TypeError on the middle order.
        total = sum(shopify._money(o.get("total_price")) for o in orders)
        self.assertEqual(total, 15.50)

    def test_missing_and_null_are_both_tolerated(self):
        orders = [{"total_tax": "1.00"}, {}, {"total_tax": None}, {"total_tax": "2.00"}]
        self.assertEqual(sum(shopify._money(o.get("total_tax")) for o in orders), 3.00)

    def test_nested_shipping_money_null_is_tolerated(self):
        orders = [
            {"total_shipping_price_set": {"shop_money": {"amount": "4.99"}}},
            {"total_shipping_price_set": {"shop_money": {"amount": None}}},
            {"total_shipping_price_set": {}},
        ]
        total = sum(
            shopify._money(
                o.get("total_shipping_price_set", {}).get("shop_money", {}).get("amount")
            )
            for o in orders
        )
        self.assertEqual(total, 4.99)


if __name__ == "__main__":
    unittest.main()
