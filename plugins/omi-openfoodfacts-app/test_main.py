"""Hermetic tests of full production module/handlers with framework and HTTP doubles.

Fixtures follow OFF's product_nutrition schema, not a claimed live incident.
The doubles do not verify FastAPI routing, Pydantic serialization or threadpool scheduling.
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


class Response:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


async def threadpool(function, *args, **kwargs):
    return function(*args, **kwargs)


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


stubs = {
    "requests": module("requests", get=Mock(), RequestException=OSError),
    "fastapi": module("fastapi", FastAPI=Framework, Request=Framework),
    "pydantic": module("pydantic", BaseModel=Response),
    "starlette.concurrency": module("starlette.concurrency", run_in_threadpool=threadpool),
}
spec = importlib.util.spec_from_file_location("off_under_test", Path(__file__).with_name("main.py"))
off = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(off)


class NutritionTests(unittest.TestCase):
    routes = (
        ("tool_lookup_barcode", {"barcode": "123"}),
        ("tool_search_foods", {"query": "food"}),
        ("tool_compare_foods", {"barcodes": ["123"]}),
        ("tool_check_allergens", {"barcode": "123", "avoid": ["milk"]}),
    )

    def invoke(self, handler, body, product):
        response = Mock()
        response.json.return_value = {"status": 1, "product": product, "products": [product], "count": 1}
        request = Mock(json=AsyncMock(return_value=body))
        with patch.object(off.requests, "get", return_value=response) as get:
            result = asyncio.run(getattr(off, handler)(request))
        self.assertTrue(result.success)
        self.assertEqual(get.call_count, 1)
        self.assertIn("nutriments", get.call_args.kwargs["params"]["fields"])
        return result.data.get("product") or result.data["products"][0]

    def test_serving_values_are_not_reported_per_100g(self):
        # OFF generic nutrients use nutrition_data_per; missing normalized
        # values cannot establish a per-100g amount, even when they are zero.
        for handler, body in self.routes:
            with self.subTest(handler=handler):
                product = self.invoke(handler, body, {
                    "code": "123", "nutrition_data_per": "serving",
                    "nutriments": {"fat": 8, "fat_serving": 8, "fat_unit": "g",
                                   "sugars": 0, "sugars_serving": 0},
                })
                self.assertIsNone(product["nutrition_per_100g"]["fat_g"])
                self.assertIsNone(product["nutrition_per_100g"]["sugars_g"])

    def test_normalized_values_and_zero_survive(self):
        for handler, body in self.routes:
            with self.subTest(handler=handler):
                product = self.invoke(handler, body, {"nutriments": {
                    "fat": 8, "fat_100g": 16, "sugars": 9, "sugars_100g": 0,
                    "energy-kcal_100g": 120, "salt_100g": None, "salt": 3,
                }})
                nutrition = product["nutrition_per_100g"]
                self.assertEqual(nutrition["fat_g"], 16)
                self.assertEqual(nutrition["sugars_g"], 0)
                self.assertEqual(nutrition["energy_kcal"], 120)
                self.assertIsNone(nutrition["salt_g"])
                self.assertIsNone(nutrition["fiber_g"])

    def test_missing_nutrition_remains_unknown(self):
        for nutriments in (None, {}):
            with self.subTest(nutriments=nutriments):
                product = self.invoke(*self.routes[0], {"nutriments": nutriments})
                self.assertTrue(all(value is None for value in product["nutrition_per_100g"].values()))

    def test_provider_failure_remains_an_error(self):
        request = Mock(json=AsyncMock(return_value={"barcode": "123"}))
        with patch.object(off.requests, "get", side_effect=OSError("unavailable")):
            result = asyncio.run(off.tool_lookup_barcode(request))
        self.assertFalse(result.success)
        self.assertIn("Open Food Facts request failed", result.message)


if __name__ == "__main__":
    unittest.main(verbosity=2)
