"""Hermetic unit tests for Open Food Facts app.

Runs purely on Python standard library without third-party runtime dependencies.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch


def load_app():
    class DummyFastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, path, **kwargs):
            return lambda func: func

        post = get

    class DummyBaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    fastapi.Request = object

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel

    starlette_concurrency = types.ModuleType("starlette.concurrency")

    async def dummy_run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    starlette_concurrency.run_in_threadpool = dummy_run_in_threadpool

    requests_module = types.ModuleType("requests")
    class DummyRequestException(Exception):
        pass
    class DummyHTTPError(DummyRequestException):
        pass
    requests_module.RequestException = DummyRequestException
    requests_module.HTTPError = DummyHTTPError
    requests_module.get = Mock()

    spec = importlib.util.spec_from_file_location(
        "openfoodfacts_app_hermetic", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "fastapi": fastapi,
            "pydantic": pydantic,
            "starlette.concurrency": starlette_concurrency,
            "requests": requests_module,
        },
    ):
        spec.loader.exec_module(module)
    return module


off = load_app()


class SafeIntTests(unittest.TestCase):
    def test_safe_int_valid_values(self):
        self.assertEqual(off._safe_int(5, default=3), 5)
        self.assertEqual(off._safe_int("7", default=3), 7)
        self.assertEqual(off._safe_int("5.0", default=3), 5)

    def test_safe_int_clamping(self):
        self.assertEqual(off._safe_int(0, default=5, minimum=1, maximum=10), 1)
        self.assertEqual(off._safe_int(99, default=5, minimum=1, maximum=10), 10)
        self.assertEqual(off._safe_int("-10", default=5, minimum=1, maximum=10), 1)

    def test_safe_int_rejects_dirty_types(self):
        self.assertEqual(off._safe_int(None, default=5), 5)
        self.assertEqual(off._safe_int(True, default=5), 5)
        self.assertEqual(off._safe_int(False, default=5), 5)
        self.assertEqual(off._safe_int("not_a_number", default=5), 5)
        self.assertEqual(off._safe_int(["list"], default=5), 5)

    def test_safe_int_overflow_and_infinity(self):
        self.assertEqual(off._safe_int("inf", default=5), 5)
        self.assertEqual(off._safe_int("-infinity", default=5), 5)
        self.assertEqual(off._safe_int("1e1000", default=5), 5)
        self.assertEqual(off._safe_int(float("inf"), default=5), 5)
        self.assertEqual(off._safe_int(float("nan"), default=5), 5)


class BarcodeSanitizationTests(unittest.TestCase):
    def test_standard_digits(self):
        self.assertEqual(off.sanitize_barcode("3017666510800"), "3017666510800")
        self.assertEqual(off.sanitize_barcode("012345678905"), "012345678905")
        self.assertEqual(off.sanitize_barcode(3017666510800), "3017666510800")

    def test_prefixes_and_wrapping_stripped(self):
        self.assertEqual(off.sanitize_barcode("barcode: 3017666510800"), "3017666510800")
        self.assertEqual(off.sanitize_barcode("EAN: 3017666510800"), "3017666510800")
        self.assertEqual(off.sanitize_barcode("#012345678905"), "012345678905")
        self.assertEqual(off.sanitize_barcode("`3017666510800`"), "3017666510800")

    def test_url_extraction(self):
        url = "https://world.openfoodfacts.org/product/3017666510800"
        self.assertEqual(off.sanitize_barcode(url), "3017666510800")

        url_with_slug = "https://world.openfoodfacts.org/product/3017666510800-nutella"
        self.assertEqual(off.sanitize_barcode(url_with_slug), "3017666510800")

    def test_rejects_alphanumeric_mixed_text(self):
        self.assertIsNone(off.sanitize_barcode("coca cola 1000ml"))
        self.assertIsNone(off.sanitize_barcode("iphone 15 pro max 256gb"))
        self.assertIsNone(off.sanitize_barcode("sku-abc-12345-xyz"))

    def test_invalid_types_and_lengths_rejected(self):
        self.assertIsNone(off.sanitize_barcode(None))
        self.assertIsNone(off.sanitize_barcode(True))
        self.assertIsNone(off.sanitize_barcode(False))
        self.assertIsNone(off.sanitize_barcode(""))
        self.assertIsNone(off.sanitize_barcode("abc"))
        self.assertIsNone(off.sanitize_barcode("12"))
        self.assertIsNone(off.sanitize_barcode("123456789012345678901234567890"))


class UnicodeNormalizationAndAllergenTests(unittest.TestCase):
    def test_unicode_normalization(self):
        nfd_word = "ble\u0301"  # blé in NFD
        normalized = off._normalize_term(nfd_word)
        self.assertEqual(normalized, "blé")

        zero_width = "pea\u200bnut"
        self.assertEqual(off._normalize_term(zero_width), "pea nut")

    def test_ingredient_mentions_english(self):
        text = "Water, sugar, roasted peanuts, salt, natural flavor."
        self.assertTrue(off._ingredient_mentions_term(text, "peanuts"))
        self.assertTrue(off._ingredient_mentions_term(text, "peanut"))
        self.assertFalse(off._ingredient_mentions_term(text, "hazelnut"))

    def test_ingredient_negative_mention_english(self):
        free_text = "Organic oat beverage, peanut-free, gluten free, free from milk, non-dairy."
        self.assertFalse(off._ingredient_mentions_term(free_text, "peanut"))
        self.assertFalse(off._ingredient_mentions_term(free_text, "gluten"))
        self.assertFalse(off._ingredient_mentions_term(free_text, "milk"))

    def test_ingredient_latin_plural_stems(self):
        # -es on 'e' ending stems should match singular (apple/grape) and normal -es (peach)
        apple_text = "Ingredients: fresh apple slices, cane sugar."
        self.assertTrue(off._ingredient_mentions_term(apple_text, "apples"))
        grape_text = "Ingredients: red grape juice concentrate."
        self.assertTrue(off._ingredient_mentions_term(grape_text, "grapes"))
        peach_text = "Ingredients: organic peach puree."
        self.assertTrue(off._ingredient_mentions_term(peach_text, "peaches"))

    def test_ingredient_mentions_accents(self):
        french_ingredients = "Farine de blé, sucre, huile de palme, cacao maigre, lait écrémé."
        self.assertTrue(off._ingredient_mentions_term(french_ingredients, "blé"))
        self.assertTrue(off._ingredient_mentions_term(french_ingredients, "lait"))
        self.assertFalse(off._ingredient_mentions_term(french_ingredients, "arachide"))

    def test_ingredient_mentions_cjk(self):
        cjk_ingredients = "配料：小麦粉，白砂糖，花生碎，食用植物油，食品添加剂。"
        self.assertTrue(off._ingredient_mentions_term(cjk_ingredients, "花生"))
        self.assertTrue(off._ingredient_mentions_term(cjk_ingredients, "小麦"))
        self.assertFalse(off._ingredient_mentions_term(cjk_ingredients, "大豆"))

        cjk_free = "本产品无花生，不含糖。"
        self.assertFalse(off._ingredient_mentions_term(cjk_free, "花生"))
        self.assertFalse(off._ingredient_mentions_term(cjk_free, "糖"))

    def test_cjk_partial_negation_safeguard(self):
        # If product says "无花生油，含花生碎", peanut must NOT be falsely silenced
        cjk_mixed = "本产品无花生油，配料含有花生碎和榛子。"
        self.assertTrue(off._ingredient_mentions_term(cjk_mixed, "花生"))
        self.assertTrue(off._ingredient_mentions_term(cjk_mixed, "榛子"))

    def test_summarize_product_polluted_types_does_not_crash(self):
        polluted_product = {
            "code": 12345678,
            "product_name": None,
            "generic_name": None,
            "nutriscore_grade": True,  # dirty boolean
            "ecoscore_grade": 100,     # dirty integer
            "nutriments": False,       # dirty boolean
            "allergens_tags": None,
            "traces_tags": None,
        }
        summary = off._summarize_product(polluted_product)
        self.assertEqual(summary["name"], "Unknown product")
        self.assertIsNone(summary["nutri_score"])
        self.assertIsNone(summary["eco_score"])
        self.assertIsNone(summary["nutrition_per_100g"]["fat_g"])
        self.assertEqual(summary["allergens"], [])


class ToolEndpointsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.mock_product = {
            "code": "3017666510800",
            "product_name": "Nutella",
            "brands": "Ferrero",
            "quantity": "400g",
            "nutriscore_grade": "e",
            "nova_group": 4,
            "ecoscore_grade": "d",
            "allergens_tags": ["en:milk", "en:nuts", "en:soybeans"],
            "traces_tags": [],
            "labels_tags": ["en:green-dot"],
            "categories_tags": ["en:breakfasts", "en:spreads"],
            "ingredients_text": "Sugar, palm oil, hazelnuts (13%), skimmed milk powder (8.7%), fat-reduced cocoa (7.4%), emulsifier: lecithins (soya), vanillin.",
            "nutriments": {
                "energy-kcal_100g": 539,
                "fat_100g": 30.9,
                "saturated-fat_100g": 10.6,
                "carbohydrates_100g": 57.5,
                "sugars_100g": 56.3,
                "proteins_100g": 6.3,
                "salt_100g": 0.107,
            },
            "image_front_small_url": "https://images.openfoodfacts.org/images/products/301/766/651/0800/front_en.jpg",
        }

    def _mock_request(self, body):
        request = Mock()
        request.json = AsyncMock(return_value=body)
        return request

    def test_lookup_barcode_success(self):
        api_response = {"status": 1, "product": self.mock_product}
        with patch.object(off, "_openfoodfacts_get", return_value=api_response):
            request = self._mock_request({"barcode": "3017666510800"})
            response = asyncio.run(off.tool_lookup_barcode(request))

        self.assertTrue(response.success)
        self.assertIn("Nutella found in Open Food Facts.", response.message)
        self.assertEqual(response.data["product"]["name"], "Nutella")
        self.assertEqual(response.data["product"]["nutri_score"], "E")
        self.assertEqual(response.data["product"]["nova_group"], 4)

    def test_lookup_barcode_via_url(self):
        url = "https://world.openfoodfacts.org/product/3017666510800"
        api_response = {"status": 1, "product": self.mock_product}
        with patch.object(off, "_openfoodfacts_get", return_value=api_response):
            request = self._mock_request({"barcode": url})
            response = asyncio.run(off.tool_lookup_barcode(request))

        self.assertTrue(response.success)
        self.assertEqual(response.data["product"]["barcode"], "3017666510800")

    def test_lookup_barcode_not_found_clean_error(self):
        with patch.object(off, "_openfoodfacts_get", return_value={"not_found": True, "status_code": 404}):
            request = self._mock_request({"barcode": "9999999999999"})
            response = asyncio.run(off.tool_lookup_barcode(request))

        self.assertFalse(response.success)
        self.assertIn("no product found for barcode 9999999999999", response.message)

    def test_lookup_barcode_invalid_input(self):
        request = self._mock_request({"barcode": "not-a-code"})
        response = asyncio.run(off.tool_lookup_barcode(request))
        self.assertFalse(response.success)
        self.assertIn("valid barcode is required", response.message)

    def test_search_foods_success(self):
        api_response = {"count": 1, "products": [self.mock_product]}
        with patch.object(off, "_openfoodfacts_get", return_value=api_response):
            request = self._mock_request({"query": "nutella", "page_size": 3})
            response = asyncio.run(off.tool_search_foods(request))

        self.assertTrue(response.success)
        self.assertIn("Found 1 product(s)", response.message)
        self.assertEqual(len(response.data["products"]), 1)

    def test_search_foods_empty_query(self):
        request = self._mock_request({"query": "   "})
        response = asyncio.run(off.tool_search_foods(request))
        self.assertFalse(response.success)
        self.assertIn("query is required", response.message)

    def test_compare_foods_success(self):
        api_response = {"status": 1, "product": self.mock_product}
        with patch.object(off, "_openfoodfacts_get", return_value=api_response):
            request = self._mock_request({"barcodes": ["3017666510800", "012345678905"]})
            response = asyncio.run(off.tool_compare_foods(request))

        self.assertTrue(response.success)
        self.assertIn("Compared 2 product(s)", response.message)

    def test_compare_foods_invalid_barcodes_type(self):
        request = self._mock_request({"barcodes": "not_a_list"})
        response = asyncio.run(off.tool_compare_foods(request))
        self.assertFalse(response.success)
        self.assertIn("barcodes must be a list", response.message)

    def test_check_allergens_detected(self):
        api_response = {"status": 1, "product": self.mock_product}
        with patch.object(off, "_openfoodfacts_get", return_value=api_response):
            request = self._mock_request({
                "barcode": "3017666510800",
                "avoid": ["milk", "hazelnuts", "gluten"]
            })
            response = asyncio.run(off.tool_check_allergens(request))

        self.assertTrue(response.success)
        self.assertIn("Nutella may include: hazelnuts, milk", response.message)
        self.assertIn("milk", response.data["matches"])
        self.assertIn("hazelnuts", response.data["matches"])

    def test_check_allergens_empty_avoid_rejected(self):
        request = self._mock_request({
            "barcode": "3017666510800",
            "avoid": []
        })
        response = asyncio.run(off.tool_check_allergens(request))
        self.assertFalse(response.success)
        self.assertIn("avoid must be a non-empty list", response.message)

    def test_check_allergens_tag_matching_singular_plural(self):
        # Even when ingredients text is empty, avoid: ["soybean"] must match allergens_tags: ["en:soybeans"]
        product_no_ingredients = dict(self.mock_product)
        product_no_ingredients["ingredients_text"] = ""
        api_response = {"status": 1, "product": product_no_ingredients}
        with patch.object(off, "_openfoodfacts_get", return_value=api_response):
            request = self._mock_request({
                "barcode": "3017666510800",
                "avoid": ["soybean"]  # singular against plural tag 'soybeans'
            })
            response = asyncio.run(off.tool_check_allergens(request))

        self.assertTrue(response.success)
        self.assertIn("soybean", response.data["matches"])

    def test_lookup_barcode_api_error_not_masked(self):
        # Network/server error must return the error, not "no product found"
        api_response = {"error": "Open Food Facts request failed"}
        with patch.object(off, "_openfoodfacts_get", return_value=api_response):
            request = self._mock_request({"barcode": "3017666510800"})
            response = asyncio.run(off.tool_lookup_barcode(request))

        self.assertFalse(response.success)
        self.assertIn("Open Food Facts request failed", response.message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
