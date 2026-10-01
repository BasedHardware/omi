"""Stripe error details returned to API clients must not leak raw Stripe internals (#18608, #20055).

Several endpoints in routers/payment.py caught `stripe.error.StripeError` and put
`str(e)` directly into the HTTPException `detail`, which FastAPI serializes straight
into the JSON response body. Stripe's raw exception text can include internal error
messages and object IDs (customer/account/subscription IDs) that should never reach
an API client. These are source-level structural checks, matching the other payment
endpoint tests (routers/payment.py has a heavy import graph).
"""

import re
from pathlib import Path

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"


def _source() -> str:
    return PAYMENT_SOURCE.read_text(encoding="utf-8")


def test_stripe_client_error_detail_helper_is_defined():
    source = _source()
    assert "def _stripe_client_error_detail(" in source


def test_stripe_error_status_code_helper_maps_expected_statuses():
    source = _source()
    assert "def _stripe_error_status_code(" in source
    assert "isinstance(e, stripe.error.RateLimitError)" in source
    assert "429" in source
    assert "isinstance(e, (stripe.error.APIConnectionError, stripe.error.APIError))" in source
    assert "502" in source


def test_no_raw_stripe_error_leaked_into_response_detail():
    source = _source()
    # `detail=str(e)` or an f-string interpolating `str(e)` or `else str(e)` puts the raw Stripe
    # exception text straight into the HTTP response body.
    assert "detail=str(e)" not in source
    assert '{str(e)}"' not in source
    assert "else str(e)" not in source


def test_stripe_error_handlers_use_the_safe_detail_helper():
    source = _source()
    idx = 0
    found = 0
    while True:
        idx = source.find("except stripe.error.StripeError as e:", idx)
        if idx == -1:
            break
        # Scan until the start of the next top-level statement or handler
        next_except = source.find("\n    except ", idx + 10)
        next_fn = source.find("\ndef ", idx)
        next_router = source.find("\n@router.", idx)
        candidates = [p for p in (next_except, next_fn, next_router) if p != -1]
        block_end = min(candidates) if candidates else len(source)
        block = source[idx:block_end]
        assert (
            "_stripe_client_error_detail(e," in block or "e.user_message" in block
        ), f"StripeError handler at offset {idx} raises detail without sanitizing it:\n{block}"
        found += 1
        idx = idx + 35
    # Handlers must include checkout, upgrade, and customer portal endpoints
    assert found >= 7


def test_customer_portal_shields_stripe_errors():
    source = _source()
    start = source.find("def create_customer_portal_endpoint(")
    assert start != -1
    next_endpoint = source.find("\n@router.", start)
    end = next_endpoint if next_endpoint != -1 else len(source)
    portal_block = source[start:end]
    assert "except stripe.error.StripeError as e:" in portal_block
    assert "_stripe_client_error_detail(e," in portal_block
    assert "_stripe_error_status_code(e" in portal_block


def test_checkout_and_upgrade_catch_base_stripe_error():
    source = _source()
    for endpoint in ("def create_checkout_session_endpoint(", "def upgrade_subscription_endpoint("):
        start = source.find(endpoint)
        assert start != -1
        next_fn = source.find("\n@router.", start)
        next_def = source.find("\ndef ", start + len(endpoint))
        candidates = [pos for pos in (next_fn, next_def) if pos != -1]
        end = min(candidates) if candidates else len(source)
        block = source[start:end]
        assert "except stripe.error.StripeError as e:" in block
        assert "_stripe_client_error_detail(e," in block
        assert "_stripe_error_status_code(e" in block
        assert "except stripe.error.InvalidRequestError" not in block


def test_no_unsanitized_exception_logging():
    source = _source()
    # Assert that all logger calls do not log raw `{e}` without sanitize(), handling multi-line calls
    unsanitized_matches = re.findall(r'logger\.\w+\([^)]*\{e\}[^)]*\)', source, re.DOTALL)
    assert not unsanitized_matches, f"Found unsanitized exception logs: {unsanitized_matches}"
