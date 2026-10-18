import unittest
from pydantic import ValidationError

from models.storefront import (
    StorefrontCurrent,
    StorefrontPrice,
    StorefrontResponse,
    StorefrontTier,
    StorefrontUsage,
)


class TestStorefrontValidation(unittest.TestCase):
    def test_storefront_price_valid(self):
        price = StorefrontPrice(
            price_id="price_123",
            interval="month",
            amount_minor=1999,
            currency="USD",
            headline="$19.99 / month",
        )
        self.assertEqual(price.amount_minor, 1999)
        self.assertEqual(price.currency, "USD")

    def test_storefront_price_zero_amount_allowed(self):
        price = StorefrontPrice(
            interval="month",
            amount_minor=0,
            currency="USD",
            headline="Free",
        )
        self.assertEqual(price.amount_minor, 0)

    def test_storefront_price_negative_amount_rejected(self):
        with self.assertRaises(ValidationError):
            StorefrontPrice(
                interval="month",
                amount_minor=-100,
                currency="USD",
                headline="Invalid",
            )

    def test_storefront_price_negative_months_free_rejected(self):
        with self.assertRaises(ValidationError):
            StorefrontPrice(
                interval="year",
                amount_minor=12000,
                currency="USD",
                headline="$120 / year",
                months_free=-1,
            )

    def test_storefront_usage_valid_percent(self):
        usage = StorefrontUsage(percent=75)
        self.assertEqual(usage.percent, 75)

    def test_storefront_usage_boundary_percent(self):
        u0 = StorefrontUsage(percent=0)
        self.assertEqual(u0.percent, 0)

        u100 = StorefrontUsage(percent=100)
        self.assertEqual(u100.percent, 100)

        u140 = StorefrontUsage(percent=140)
        self.assertEqual(u140.percent, 140)

    def test_storefront_usage_negative_percent_rejected(self):
        with self.assertRaises(ValidationError):
            StorefrontUsage(percent=-1)

    def test_storefront_response_valid(self):
        response = StorefrontResponse(catalog_revision=1)
        self.assertEqual(response.catalog_revision, 1)

    def test_storefront_response_negative_catalog_revision_rejected(self):
        with self.assertRaises(ValidationError):
            StorefrontResponse(catalog_revision=-1)


if __name__ == "__main__":
    unittest.main()
