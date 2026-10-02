"""
Hermetic unit tests for Omi Open Food Facts Integration App.
Verifies safe integer parsing, null allergen lists, barcode lookup, product summaries,
URL/slug extraction, 4-18 digit length cap, 404 error handling, and tool endpoints.
"""

import asyncio
import os
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# --- Hermetic stubs for environments without FastAPI/Pydantic/Requests installed ---
if "fastapi" not in sys.modules:
    fastapi_mod = ModuleType("fastapi")

    class DummyFastAPI:
        def __init__(self, *args, **kwargs):
            self.state = SimpleNamespace()

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

    class DummyRequest:
        def __init__(self, json_data=None):
            self._json = json_data or {}

        async def json(self):
            return self._json

    fastapi_mod.FastAPI = DummyFastAPI
    fastapi_mod.Request = DummyRequest
    sys.modules["fastapi"] = fastapi_mod

if "pydantic" not in sys.modules:
    pydantic_mod = ModuleType("pydantic")

    class DummyBaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    pydantic_mod.BaseModel = DummyBaseModel
    sys.modules["pydantic"] = pydantic_mod

if "starlette.concurrency" not in sys.modules:
    concurrency_mod = ModuleType("starlette.concurrency")

    async def run_in_threadpool(func, *args, **kwargs):
        return func(*args, **kwargs)

    concurrency_mod.run_in_threadpool = run_in_threadpool
    sys.modules["starlette.concurrency"] = concurrency_mod

if "requests" not in sys.modules:
    requests_mod = ModuleType("requests")
    requests_mod.RequestException = Exception
    requests_mod.get = MagicMock()
    sys.modules["requests"] = requests_mod

import main


class TestOpenFoodFacts(unittest.TestCase):

    def test_safe_int_booleans_and_bounds(self):
        # Booleans must not coerce to 1 or 0
        self.assertEqual(main._safe_int(True, default=5), 5)
        self.assertEqual(main._safe_int(False, default=5), 5)
        self.assertEqual(main._safe_int(None, default=5), 5)
        self.assertEqual(main._safe_int("invalid", default=5), 5)

        # Clamping
        self.assertEqual(main._safe_int(0, default=5, minimum=1), 1)
        self.assertEqual(main._safe_int(-10, default=5, minimum=1), 1)
        self.assertEqual(main._safe_int(99, default=5, maximum=10), 10)
        self.assertEqual(main._safe_int("7", default=5), 7)

    def test_normalize_tags(self):
        self.assertEqual(main._normalize_tag("en:whole-milk"), "whole milk")
        self.assertEqual(main._normalize_tag("gluten-free"), "gluten free")
        self.assertEqual(main._normalize_tag(None), "")
        self.assertEqual(main._normalize_tag(123), "")

        tags = main._normalize_tags(["en:gluten", "en:soy-beans", None, ""])
        self.assertEqual(tags, ["gluten", "soy beans"])
        self.assertEqual(main._normalize_tags(None), [])

    def test_nutrient_per_100g(self):
        product = {
            "nutriments": {
                "fat_100g": 2.5,
                "fat": 5.0,  # serving-only basis
                "sugars_100g": 12.0,
            }
        }
        self.assertEqual(main._nutrient(product, "fat"), 2.5)
        self.assertEqual(main._nutrient(product, "sugars"), 12.0)
        # Should not fall back to serving-only keys
        product_serving_only = {"nutriments": {"fiber": 3.0}}
        self.assertIsNone(main._nutrient(product_serving_only, "fiber"))
        self.assertIsNone(main._nutrient({}, "fat"))

    def test_summarize_product(self):
        product = {
            "code": "737628064502",
            "product_name": "Thai Peanut Noodles",
            "brands": "Thai Kitchen",
            "nutriscore_grade": "d",
            "allergens_tags": ["en:peanuts"],
            "traces_tags": ["en:sesame-seeds"],
            "nutriments": {"energy-kcal_100g": 380, "fat_100g": 12},
        }
        summary = main._summarize_product(product)
        self.assertEqual(summary["barcode"], "737628064502")
        self.assertEqual(summary["name"], "Thai Peanut Noodles")
        self.assertEqual(summary["nutri_score"], "D")
        self.assertIn("peanuts", summary["allergens"])
        self.assertIn("sesame seeds", summary["traces"])
        self.assertEqual(summary["nutrition_per_100g"]["fat_g"], 12)

    def test_ingredient_mentions_term_negations(self):
        # Direct mention
        self.assertTrue(main._ingredient_mentions_term("Organic peanut butter and oats", "peanut"))
        # Negations
        self.assertFalse(main._ingredient_mentions_term("Certified gluten-free rolled oats", "gluten"))
        self.assertFalse(main._ingredient_mentions_term("Made with non-dairy milk", "dairy"))
        self.assertFalse(main._ingredient_mentions_term("Contains no peanuts or tree nuts", "peanuts"))
        self.assertFalse(main._ingredient_mentions_term("", "milk"))

    def test_check_allergens_null_allergens_and_traces(self):
        # Verify that product with null allergens/traces fields does not raise TypeError
        product = {
            "name": "Sparse Product",
            "allergens": None,
            "traces": None,
            "ingredients": "Water, sugar, salt",
        }
        fake_lookup = {"product": product}
        with patch.object(main, "_lookup_barcode", new_callable=AsyncMock) as mock_lookup:
            mock_lookup.return_value = fake_lookup
            fake_req = main.Request({"barcode": "123456", "avoid": ["peanuts"]})
            resp = asyncio.run(main.tool_check_allergens(fake_req))
            self.assertTrue(resp.success)
            self.assertIn("No listed match found", resp.message)

    def test_check_allergens_detects_avoidance(self):
        product = {
            "name": "Nutty Crunch",
            "allergens": ["peanuts", "milk"],
            "traces": [],
            "ingredients": "Peanuts, whole milk powder",
        }
        fake_lookup = {"product": product}
        with patch.object(main, "_lookup_barcode", new_callable=AsyncMock) as mock_lookup:
            mock_lookup.return_value = fake_lookup
            fake_req = main.Request({"barcode": "123456", "avoid": ["peanuts", "soy"]})
            resp = asyncio.run(main.tool_check_allergens(fake_req))
            self.assertTrue(resp.success)
            self.assertIn("may include: peanuts", resp.message)
            self.assertEqual(resp.data["matches"], ["peanuts"])

    def test_check_allergens_invalid_avoid(self):
        fake_req = main.Request({"barcode": "123456", "avoid": []})
        resp = asyncio.run(main.tool_check_allergens(fake_req))
        self.assertFalse(resp.success)
        self.assertEqual(resp.message, "avoid must be a non-empty list")

    def test_lookup_barcode_validation(self):
        # Empty barcode returns error
        res = asyncio.run(main._lookup_barcode(""))
        self.assertIn("error", res)
        self.assertEqual(res["error"], "barcode is required")

        # Non-digits only
        res_letters = asyncio.run(main._lookup_barcode("abcdef"))
        self.assertIn("error", res_letters)
        self.assertIn("4 to 18 digits", res_letters["error"])

    def test_barcode_sanitization_and_url_extraction(self):
        self.assertEqual(main.sanitize_barcode("3017620422003"), "3017620422003")
        self.assertEqual(main.sanitize_barcode(3017620422003), "3017620422003")
        self.assertEqual(main.sanitize_barcode("  301-762-042-2003  "), "3017620422003")

        # Open Food Facts URL & slug extraction
        url = "https://world.openfoodfacts.org/product/3017620422003/nutella"
        self.assertEqual(main.sanitize_barcode(url), "3017620422003")
        url_fr = "https://fr.openfoodfacts.org/produit/0049000006582"
        self.assertEqual(main.sanitize_barcode(url_fr), "0049000006582")
        slug = "/product/5449000000996"
        self.assertEqual(main.sanitize_barcode(slug), "5449000000996")

    def test_barcode_length_bounds_4_to_18(self):
        # Min/max bounds
        self.assertEqual(main.sanitize_barcode("1234"), "1234")
        self.assertEqual(main.sanitize_barcode("123456789012345678"), "123456789012345678")

        # Bounds violations
        self.assertIsNone(main.sanitize_barcode("123"))
        self.assertIsNone(main.sanitize_barcode("1"))
        self.assertIsNone(main.sanitize_barcode("1234567890123456789"))
        self.assertIsNone(main.sanitize_barcode(None))
        self.assertIsNone(main.sanitize_barcode(""))

    def test_openfoodfacts_404_graceful_handling(self):
        with patch("main.requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_get.return_value = mock_resp

            result = main._openfoodfacts_get("/api/v2/product/00000000.json")
            self.assertTrue(result.get("not_found"))
            self.assertEqual(result.get("status"), 0)
            mock_resp.raise_for_status.assert_not_called()

        with patch("main._openfoodfacts_get_async") as mock_async_get:
            mock_async_get.return_value = {"status": 0, "product": None, "not_found": True}
            lookup_res = asyncio.run(main._lookup_barcode("3017620422003"))
            self.assertIn("error", lookup_res)
            self.assertEqual(lookup_res["error"], "no product found for barcode 3017620422003")

    def test_tool_lookup_barcode_endpoints(self):
        with patch.object(main, "_lookup_barcode", new_callable=AsyncMock) as mock_lookup:
            mock_lookup.return_value = {"product": {"name": "Nutella"}}
            resp = asyncio.run(main.tool_lookup_barcode(main.Request({"barcode": "3017620422003"})))
            self.assertTrue(resp.success)
            self.assertIn("Nutella found", resp.message)

            mock_lookup.return_value = {"error": "no product found for barcode 00000000"}
            resp_404 = asyncio.run(main.tool_lookup_barcode(main.Request({"barcode": "00000000"})))
            self.assertFalse(resp_404.success)
            self.assertIn("no product found", resp_404.message)

    def test_health_and_manifest(self):
        h = asyncio.run(main.health())
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["service"], "omi-openfoodfacts-app")

        manifest = asyncio.run(main.get_omi_tools_manifest())
        self.assertIn("tools", manifest)
        self.assertEqual(len(manifest["tools"]), 4)


if __name__ == "__main__":
    unittest.main()
