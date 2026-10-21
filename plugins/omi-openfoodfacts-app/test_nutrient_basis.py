"""Only per-100g nutriments may be labeled nutrition_per_100g (#13272)."""

from main import _nutrient, _summarize_product


def test_serving_only_nutrient_is_not_reported_as_per_100g():
    product = {
        "code": "1",
        "product_name": "Oat milk",
        "nutriments": {
            # serving-only, no _100g key
            "fat": 1.5,
            "fat_100g": 0.2,
        },
    }
    assert _nutrient(product, "fat") == 0.2
    # Serving-only key must not leak into nutrition_per_100g.
    product2 = {"code": "2", "product_name": "X", "nutriments": {"fat": 1.5}}
    summary = _summarize_product(product2)
    assert summary["nutrition_per_100g"]["fat_g"] is None
