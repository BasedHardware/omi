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


def test_stripe_error_handlers_use_the_safe_detail_helper():
    source = _source()
    idx = 0
    found = 0
    while True:
        idx = source.find("except stripe.error.StripeError as e:", idx)
        if idx == -1:
            break
        next_blank = source.find("\n\n", idx)
        block_end = next_blank if next_blank != -1 else len(source)
        block = source[idx:block_end]
        assert (
            "_stripe_client_error_detail(e," in block or "e.user_message" in block
        ), f"StripeError handler at offset {idx} raises detail without sanitizing it:\n{block}"
        found += 1
        idx = block_end
    # Sanity check that this test is actually exercising handlers, not vacuously passing.
    assert found >= 5
