"""Only per-100g nutriments may be labeled nutrition_per_100g (#13272).

Hermetic stdlib-only regression runnable via ``python3 test_nutrient_basis.py``;
the broader crash-path coverage lives in test_main.py.
"""

import unittest

from test_main import load_app

app = load_app()


class NutrientBasisTests(unittest.TestCase):
    def test_per_100g_key_wins_over_serving_key(self):
        product = {
            "code": "1",
            "product_name": "Oat milk",
            "nutriments": {
                # serving-only, plus the authoritative _100g key
                "fat": 1.5,
                "fat_100g": 0.2,
            },
        }
        self.assertEqual(app._nutrient(product, "fat"), 0.2)

    def test_serving_only_nutrient_is_not_reported_as_per_100g(self):
        product = {"code": "2", "product_name": "X", "nutriments": {"fat": 1.5}}
        summary = app._summarize_product(product)
        self.assertIsNone(summary["nutrition_per_100g"]["fat_g"])


if __name__ == "__main__":
    unittest.main()
