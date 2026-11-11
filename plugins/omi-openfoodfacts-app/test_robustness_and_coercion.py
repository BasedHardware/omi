import asyncio
import os
import sys
import types
import unittest


# Pre-emptively stub non-stdlib dependencies so this suite can run hermetically
# in minimal Python CI runners without external pip packages.
class _Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda f: f

    post = get

    def __call__(self, *args, **kwargs):
        return self


class _BaseModelStub:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _stub_module(name, **attributes):
    val = types.ModuleType(name)
    val.__dict__.update(attributes)
    return val


_stubs = {
    "requests": _stub_module("requests", RequestException=OSError),
    "fastapi": _stub_module(
        "fastapi",
        FastAPI=_Framework,
        Request=_Framework,
        Body=lambda default=None, **kw: default,
    ),
    "pydantic": _stub_module("pydantic", BaseModel=_BaseModelStub),
    "starlette.concurrency": _stub_module(
        "starlette.concurrency",
        run_in_threadpool=lambda f, *args, **kwargs: f(*args, **kwargs),
    ),
}
for _name, _mod in _stubs.items():
    if _name not in sys.modules:
        try:
            __import__(_name)
        except Exception:
            sys.modules[_name] = _mod

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import (
    _collect_foods_from_body,
    _ingredient_mentions_term,
    _normalize_string_list,
    _nutrient,
    _safe_grade,
    _safe_int,
    _summarize_product,
)


class TestOpenFoodFactsRobustnessAndCoercion(unittest.TestCase):
    def test_nutrient_empty_list_and_non_dict_nutriments(self):
        # When Open Food Facts returns nutriments as [] instead of {}, must return None without TypeError
        product_empty_list = {"nutriments": []}
        self.assertIsNone(_nutrient(product_empty_list, "fat"))

        product_none = {"nutriments": None}
        self.assertIsNone(_nutrient(product_none, "fat"))

        self.assertIsNone(_nutrient("not-a-dict", "fat"))

        product_valid = {"nutriments": {"fat_100g": 3.5}}
        self.assertEqual(_nutrient(product_valid, "fat"), 3.5)

    def test_safe_grade_non_string_protection(self):
        # Calling .upper() on numeric or boolean or dict grades must not raise AttributeError
        self.assertIsNone(_safe_grade(None))
        self.assertIsNone(_safe_grade(1))
        self.assertIsNone(_safe_grade(True))
        self.assertIsNone(_safe_grade({}))
        self.assertEqual(_safe_grade("a"), "A")
        self.assertEqual(_safe_grade("  b  "), "B")

    def test_safe_int_booleans_and_bounds(self):
        self.assertEqual(_safe_int(True, default=5), 5)
        self.assertEqual(_safe_int(False, default=5), 5)
        self.assertEqual(_safe_int("7", default=5), 7)
        self.assertEqual(_safe_int(25, default=5, maximum=10), 10)
        self.assertEqual(_safe_int(-5, default=5, minimum=1), 1)
        self.assertEqual(_safe_int("bad", default=5), 5)

    def test_normalize_string_list_delimited_and_collections(self):
        self.assertEqual(_normalize_string_list(None), [])
        self.assertEqual(_normalize_string_list(True), [])
        self.assertEqual(
            _normalize_string_list("peanuts, milk; soy"),
            ["peanuts", "milk", "soy"],
        )
        self.assertEqual(
            _normalize_string_list(["peanuts", "gluten"]), ["peanuts", "gluten"]
        )
        self.assertEqual(
            _normalize_string_list("single_barcode"), ["single_barcode"]
        )

    def test_summarize_product_non_string_grades(self):
        product = {
            "code": "12345",
            "product_name": "Nutty Bar",
            "nutriscore_grade": 4,  # numeric grade
            "ecoscore_grade": False,  # boolean grade
            "nova_group": True,  # boolean nova group
            "nutriments": [],  # empty list nutriments
        }
        summary = _summarize_product(product)
        self.assertEqual(summary["barcode"], "12345")
        self.assertEqual(summary["name"], "Nutty Bar")
        self.assertIsNone(summary["nutri_score"])
        self.assertIsNone(summary["eco_score"])
        self.assertIsNone(summary["nova_group"])
        self.assertIsNone(summary["nutrition_per_100g"]["fat_g"])

    def test_ingredient_mentions_term_none_safety(self):
        # Must not raise AttributeError when ingredients is None
        self.assertFalse(_ingredient_mentions_term(None, "peanuts"))
        self.assertFalse(_ingredient_mentions_term("", "peanuts"))
        self.assertTrue(
            _ingredient_mentions_term("Ingredients: oats, peanuts, sugar", "peanuts")
        )
        self.assertFalse(
            _ingredient_mentions_term("Ingredients: peanut-free chocolate", "peanut")
        )

    def test_collect_foods_from_body_string_barcodes(self):
        # Accepts comma-separated barcodes string
        body = {"barcodes": "111, 222"}

        async def run_collect():
            # Mock lookup
            import main

            original = main._lookup_barcode

            async def fake_lookup(barcode):
                return {"product": {"name": f"Product {barcode}"}}

            main._lookup_barcode = fake_lookup
            try:
                return await _collect_foods_from_body(body)
            finally:
                main._lookup_barcode = original

        res = asyncio.run(run_collect())
        self.assertIn("products", res)
        self.assertEqual(len(res["products"]), 2)


if __name__ == "__main__":
    unittest.main()
