"""Tests for payment router error sanitization to prevent sensitive Stripe details from leaking to clients."""

import ast
from pathlib import Path
import unittest

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"


def _read_payment_source() -> str:
    return PAYMENT_SOURCE.read_text(encoding="utf-8")


def _get_sanitize_helper():
    """Extract and execute _sanitize_payment_error definition independently of heavy imports."""
    source = _read_payment_source()
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_sanitize_payment_error":
            code = compile(ast.Module(body=[node], type_ignores=[]), filename="<ast>", mode="exec")
            namespace = {}
            exec(code, namespace)
            return namespace["_sanitize_payment_error"]
    raise NameError("_sanitize_payment_error function not found in payment.py")


class TestPaymentErrorSanitization(unittest.TestCase):
    def setUp(self):
        self.sanitize_error = _get_sanitize_helper()

    def test_sanitize_returns_user_message_when_available(self):
        class MockStripeCardError(Exception):
            user_message = "Your card was declined. Please try another card."

        err = MockStripeCardError("Internal decline code: generic_decline; req_id: req_12345")
        result = self.sanitize_error(err, "stripe_card_failed")
        self.assertEqual(result, "Your card was declined. Please try another card.")

    def test_sanitize_suppresses_raw_error_when_no_user_message(self):
        class MockStripeInvalidRequest(Exception):
            pass

        err = MockStripeInvalidRequest("No such account: 'acct_12345secret'; param: account")
        result = self.sanitize_error(err, "stripe_account_link_refresh_failed")
        self.assertEqual(result, "stripe_account_link_refresh_failed")
        self.assertNotIn("acct_12345secret", result)

    def test_sanitize_handles_empty_user_message(self):
        class MockStripeError(Exception):
            user_message = "   "

        err = MockStripeError("API connection error with api.stripe.com")
        result = self.sanitize_error(err, "stripe_connection_failed")
        self.assertEqual(result, "stripe_connection_failed")

    def test_sanitize_handles_generic_exception(self):
        err = RuntimeError("Database connection string leaked: secret_pwd@db")
        result = self.sanitize_error(err, "stripe_operation_failed")
        self.assertEqual(result, "stripe_operation_failed")
        self.assertNotIn("secret_pwd", result)


class TestPaymentSourceStructuralGuards(unittest.TestCase):
    def setUp(self):
        self.source = _read_payment_source()

    def test_no_raw_str_e_raised_in_detail(self):
        """Ensure no HTTPException in payment.py uses raw detail=str(e)."""
        self.assertNotIn("detail=str(e)", self.source)
        self.assertNotIn("detail=f\"Could not cancel subscription: {str(e)}\"", self.source)

    def test_create_connect_account_sanitizes_error(self):
        start = self.source.index("def create_connect_account_endpoint")
        end = self.source.index("\ndef ", start + 1)
        endpoint_code = self.source[start:end]

        self.assertIn("stripe.error.StripeError", endpoint_code)
        self.assertIn("_sanitize_payment_error", endpoint_code)
        self.assertIn("stripe_connect_account_creation_failed", endpoint_code)
        self.assertNotIn("detail=str(e)", endpoint_code)

    def test_check_onboarding_status_sanitizes_error(self):
        start = self.source.index("def check_onboarding_status")
        end = self.source.index("\ndef ", start + 1)
        endpoint_code = self.source[start:end]

        self.assertIn("stripe.error.StripeError", endpoint_code)
        self.assertIn("_sanitize_payment_error", endpoint_code)
        self.assertIn("stripe_onboarding_status_check_failed", endpoint_code)
        self.assertNotIn("detail=str(e)", endpoint_code)

    def test_refresh_account_link_sanitizes_error(self):
        start = self.source.index("def refresh_account_link_endpoint")
        end = self.source.index("\ndef ", start + 1)
        endpoint_code = self.source[start:end]

        self.assertIn("stripe.error.StripeError", endpoint_code)
        self.assertIn("_sanitize_payment_error", endpoint_code)
        self.assertIn("stripe_account_link_refresh_failed", endpoint_code)
        self.assertNotIn("detail=str(e)", endpoint_code)

    def test_cancel_subscription_sanitizes_error(self):
        start = self.source.index("def cancel_subscription_endpoint")
        end = self.source.index("\ndef ", start + 1)
        endpoint_code = self.source[start:end]

        self.assertIn("stripe.error.StripeError", endpoint_code)
        self.assertIn("_sanitize_payment_error", endpoint_code)
        self.assertIn("stripe_subscription_cancellation_failed", endpoint_code)
        self.assertNotIn("{str(e)}", endpoint_code)

    def test_cancel_app_subscription_sanitizes_error(self):
        start = self.source.index("def cancel_app_subscription")
        endpoint_code = self.source[start:]

        self.assertIn("stripe.error.StripeError", endpoint_code)
        self.assertIn("_sanitize_payment_error", endpoint_code)
        self.assertIn("stripe_app_subscription_cancellation_failed", endpoint_code)
        self.assertNotIn("detail=str(e)", endpoint_code)


if __name__ == "__main__":
    unittest.main()
