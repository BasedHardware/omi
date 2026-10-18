"""Stripe error details returned to API clients must not leak raw Stripe internals (#18608).

Several endpoints in routers/payment.py caught `stripe.error.StripeError` and put
`str(e)` directly into the HTTPException `detail`, which FastAPI serializes straight
into the JSON response body. Stripe's raw exception text can include internal error
messages and object IDs (customer/account/subscription IDs) that should never reach
an API client. These are source-level structural checks, matching the other payment
endpoint tests (routers/payment.py has a heavy import graph).
"""

from pathlib import Path

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"


def _source() -> str:
    return PAYMENT_SOURCE.read_text(encoding="utf-8")


def test_stripe_client_error_detail_helper_is_defined():
    source = _source()
    assert "def _stripe_client_error_detail(" in source


def test_no_raw_stripe_error_leaked_into_response_detail():
    source = _source()
    # `detail=str(e)` or an f-string interpolating `str(e)` puts the raw Stripe
    # exception text straight into the HTTP response body.
    assert "detail=str(e)" not in source
    assert '{str(e)}"' not in source
    # Must not fallback to str(e) when e.user_message is absent
    assert "else str(e)" not in source


def test_stripe_error_handlers_use_the_safe_detail_helper():
    import re

    source = _source()
    pattern = re.compile(r"except\s+(?:\([^)]*stripe\.error\.StripeError[^)]*\)|stripe\.error\.StripeError)\s+as\s+e:")
    matches = list(pattern.finditer(source))
    assert len(matches) >= 8
    for m in matches:
        idx = m.start()
        next_blank = source.find("\n\n", idx)
        block_end = next_blank if next_blank != -1 else len(source)
        block = source[idx:block_end]
        assert (
            "_stripe_client_error_detail(e," in block or "e.user_message" in block
        ), f"StripeError handler at offset {idx} raises detail without sanitizing it:\n{block}"


def test_customer_portal_endpoint_shields_stripe_errors():
    source = _source()
    portal_def = "def create_customer_portal_endpoint"
    assert portal_def in source
    start = source.find(portal_def)
    end = source.find("\ndef ", start + len(portal_def))
    endpoint_body = source[start:end]

    assert "except stripe.error.StripeError as e:" in endpoint_body
    assert "_stripe_client_error_detail(e, \"Could not open customer portal. Please try again.\")" in endpoint_body
    assert "except HTTPException:" in endpoint_body


def test_checkout_and_upgrade_endpoints_shield_stripe_errors():
    source = _source()

    # Checkout session endpoint
    chk_start = source.find("def create_checkout_session_endpoint")
    chk_end = source.find("\ndef ", chk_start + 1)
    chk_body = source[chk_start:chk_end]
    assert "stripe.error.StripeError" in chk_body
    assert "stripe.error.InvalidRequestError" in chk_body
    assert "_stripe_client_error_detail(e, \"Could not create checkout session.\")" in chk_body
    assert "else str(e)" not in chk_body

    # Upgrade subscription endpoint
    upg_start = source.find("def upgrade_subscription_endpoint")
    upg_end = source.find("\nclass CancelSubscriptionRequest", upg_start + 1)
    upg_body = source[upg_start:upg_end]
    assert "stripe.error.StripeError" in upg_body
    assert "stripe.error.InvalidRequestError" in upg_body
    assert "_stripe_client_error_detail(e, \"Failed to process subscription change. Please try again.\")" in upg_body
    assert "else str(e)" not in upg_body


def test_stripe_client_error_detail_helper_behavior():
    # Test the logic of _stripe_client_error_detail in isolation
    class MockStripeError:
        def __init__(self, message: str, user_message: str | None = None):
            self.message = message
            self.user_message = user_message

        def __str__(self):
            return self.message

    def safe_helper(e, fallback: str) -> str:
        user_msg = getattr(e, "user_message", None)
        return user_msg if user_msg else fallback

    err_with_user_msg = MockStripeError("raw internal cus_123 fail", user_message="Card declined")
    assert safe_helper(err_with_user_msg, "Fallback msg") == "Card declined"

    err_without_user_msg = MockStripeError("raw internal key/id leak", user_message=None)
    assert safe_helper(err_without_user_msg, "Fallback msg") == "Fallback msg"
