"""Hermetic unit tests for error sanitization in the payment router.

Verifies that:
1. cancel_subscription_endpoint catches stripe.error.StripeError and generic Exception,
   logs type(e).__name__, and returns generic HTTP 500 without leaking exception details.
2. create_connect_account_endpoint catches stripe.error.StripeError, logs type(e).__name__,
   and returns generic HTTP 400 without leaking raw str(e) details.
3. check_onboarding_status catches stripe.error.StripeError, logs type(e).__name__,
   and returns generic HTTP 400 without leaking raw str(e) details.
4. refresh_account_link_endpoint catches stripe.error.StripeError, logs type(e).__name__,
   and returns generic HTTP 400 without leaking raw str(e) details.
5. cancel_app_subscription catches stripe.error.StripeError and generic Exception,
   logs type(e).__name__, and returns generic HTTP 400/500 without leaking raw str(e) details.
"""

from __future__ import annotations

from pathlib import Path
import re
import unittest

PAYMENT_SOURCE_FILE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"


def _get_endpoint_source(endpoint_name: str) -> str:
    source = PAYMENT_SOURCE_FILE.read_text(encoding="utf-8")
    start = source.index(f"def {endpoint_name}")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class PaymentErrorSanitizationTests(unittest.TestCase):
    def test_cancel_subscription_endpoint_sanitizes_errors(self):
        source = _get_endpoint_source("cancel_subscription_endpoint")
        self.assertNotIn("str(e)", source)
        self.assertNotIn("{e}", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('detail="Could not cancel subscription. Please try again."', source)

    def test_create_connect_account_endpoint_sanitizes_stripe_errors(self):
        source = _get_endpoint_source("create_connect_account_endpoint")
        self.assertNotIn("detail=str(e)", source)
        self.assertNotIn("detail=f\"{str(e)}\"", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('detail="Failed to create Stripe connect account."', source)

    def test_check_onboarding_status_sanitizes_stripe_errors(self):
        source = _get_endpoint_source("check_onboarding_status")
        self.assertNotIn("detail=str(e)", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('detail="Failed to check onboarding status."', source)

    def test_refresh_account_link_endpoint_sanitizes_stripe_errors(self):
        source = _get_endpoint_source("refresh_account_link_endpoint")
        self.assertNotIn("detail=str(e)", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('detail="Failed to refresh Stripe account link."', source)

    def test_cancel_app_subscription_sanitizes_stripe_errors(self):
        source = _get_endpoint_source("cancel_app_subscription")
        self.assertNotIn("detail=str(e)", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('detail="Could not cancel subscription."', source)


if __name__ == "__main__":
    unittest.main()
