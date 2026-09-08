"""The Stripe connect-account endpoint must block creation for a missing user (#8567).

Guarding the database/users.py getters made get_stripe_connect_account_id return None for a missing
user document instead of raising. On its own that let create_connect_account_endpoint fall through
to creating a Stripe Connect account for a UID with no Firestore record, leaving an orphaned billing
account (cubic on #8567). The endpoint now verifies the user exists and returns 404 before any Stripe
side effect. These are source-level structural checks, matching the other payment endpoint tests
(routers/payment.py has a heavy import graph).
"""

from pathlib import Path

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"


def _source() -> str:
    return PAYMENT_SOURCE.read_text(encoding="utf-8")


def test_get_user_profile_is_imported_in_payment():
    assert "get_user_profile" in _source()


def test_connect_account_creation_checks_user_before_creating():
    source = _source()
    start = source.index("def create_connect_account_endpoint")
    end = source.index("\ndef ", start + 1)
    endpoint = source[start:end]

    # The missing-user guard and its 404 must be present in this endpoint.
    assert "get_user_profile(uid)" in endpoint
    assert "User not found" in endpoint

    # The guard must run BEFORE the Stripe account is created, so a non-existent user never produces
    # an orphaned Stripe Connect account.
    guard_pos = endpoint.index("User not found")
    create_pos = endpoint.index("create_connect_account(uid")
    assert guard_pos < create_pos, "user-existence guard must run before Stripe account creation"
