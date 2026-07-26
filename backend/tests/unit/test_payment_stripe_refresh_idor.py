"""POST /v1/stripe/refresh/{account_id} must verify account_id belongs to the caller.

account_id is a client-supplied path param. Before this fix, refresh_account_link_endpoint
passed it straight to refresh_connect_account_link() with no check that it was the caller's
own Stripe Connect account, so any authenticated user could obtain a fresh onboarding
AccountLink for another user's Connect account (IDOR / payout-hijack vector). The endpoint
now compares account_id against get_stripe_connect_account_id(uid) and 403s on mismatch,
matching the guard already used by check_onboarding_status in the same file.

Source-level structural check: routers/payment.py has a heavy import graph (stripe SDK,
Firestore clients), matching the approach in test_payment_connect_account_user_guard.py.
"""

from pathlib import Path

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"


def _source() -> str:
    return PAYMENT_SOURCE.read_text(encoding="utf-8")


def _endpoint_body(source: str, def_line: str) -> str:
    start = source.index(def_line)
    end = source.index("\ndef ", start + 1)
    return source[start:end]


def test_refresh_account_link_checks_ownership_before_stripe_call():
    source = _source()
    endpoint = _endpoint_body(source, "def refresh_account_link_endpoint")

    assert "get_stripe_connect_account_id(uid)" in endpoint
    assert "403" in endpoint

    guard_pos = endpoint.index("get_stripe_connect_account_id(uid)")
    call_pos = endpoint.index("refresh_connect_account_link(account_id)")
    assert guard_pos < call_pos, "ownership guard must run before the Stripe account-link call"
