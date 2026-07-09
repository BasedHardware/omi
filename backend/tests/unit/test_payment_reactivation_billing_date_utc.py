"""The subscription-reactivation billing date must be formatted timezone-aware (#4643).

_try_reactivate_subscription rendered Stripe's current_period_end (a Unix epoch) with a naive
datetime.fromtimestamp(...).strftime(...), so the user-facing "your plan will automatically renew
on <date>" message used the server's local timezone instead of UTC. The rest of the codebase formats
this same Stripe current_period_end field with tz=timezone.utc (utils/subscription.py,
database/users.py), so on a non-UTC host the reactivation message could show the wrong day. The
reactivation path now matches. These are source-level structural checks, matching the other payment
endpoint tests (routers/payment.py has a heavy import graph).
"""

from pathlib import Path

PAYMENT_SOURCE = Path(__file__).resolve().parents[2] / "routers" / "payment.py"


def _source() -> str:
    return PAYMENT_SOURCE.read_text(encoding="utf-8")


def test_timezone_is_imported_in_payment():
    assert "from datetime import datetime, timezone" in _source()


def test_reactivation_billing_date_is_timezone_aware():
    source = _source()
    start = source.index("def _try_reactivate_subscription")
    end = source.index("\ndef ", start + 1)
    func = source[start:end]

    # The billing-date formatting must pass tz=timezone.utc, matching how the same Stripe
    # current_period_end field is rendered elsewhere (utils/subscription.py, database/users.py).
    assert "current_period_end" in func
    assert "tz=timezone.utc" in func

    # The naive single-line form (fromtimestamp on current_period_end with no tz) must be gone.
    assert "datetime.fromtimestamp(stripe_sub_dict['current_period_end']).strftime" not in func
