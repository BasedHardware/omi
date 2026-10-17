"""A paid plan whose stored period passed must heal from Stripe like a Basic one.

A Neo subscriber paid every month through Sept 17, yet read as Free in October:
`get_user_valid_subscription` treats a lapsed stored period as Basic, but the
read-time Stripe heal only ran for records stored as `basic`, so a missed
renewal webhook never repaired.
"""

from datetime import datetime, timezone

from models.users import PlanType, Subscription, SubscriptionStatus
from utils import subscription as subscription_utils

NOW = int(datetime.now(timezone.utc).timestamp())


def _stored(plan: PlanType, period_end: int | None) -> Subscription:
    return Subscription(
        plan=plan,
        status=SubscriptionStatus.active,
        current_period_end=period_end,
        stripe_subscription_id='sub_neo',
    )


def _heal(monkeypatch, stored: Subscription, stripe_active: Subscription | None):
    writes = []
    lookups = []
    monkeypatch.setattr(
        subscription_utils,
        'find_active_paid_subscription_for_user',
        lambda uid: lookups.append(uid) or stripe_active,
    )
    monkeypatch.setattr(
        subscription_utils.users_db, 'update_user_subscription', lambda uid, data: writes.append((uid, data))
    )
    monkeypatch.setattr(subscription_utils.stripe.Subscription, 'retrieve', lambda sub_id: None)
    result = subscription_utils.reconcile_basic_plan_with_stripe('uid-1', stored)
    return result, writes, lookups


def test_lapsed_paid_period_heals_from_the_active_stripe_subscription(monkeypatch):
    renewed = _stored(PlanType.unlimited, NOW + 30 * 86400)
    result, writes, _ = _heal(monkeypatch, _stored(PlanType.unlimited, NOW - 86400), renewed)

    assert result is renewed
    assert writes == [('uid-1', renewed.model_dump())]


def test_current_paid_period_never_calls_stripe(monkeypatch):
    stored = _stored(PlanType.unlimited, NOW + 86400)
    result, writes, lookups = _heal(monkeypatch, stored, _stored(PlanType.unlimited, NOW + 30 * 86400))

    assert result is stored
    assert writes == [] and lookups == []


def test_lapsed_paid_with_nothing_active_in_stripe_is_left_alone(monkeypatch):
    stored = _stored(PlanType.unlimited, NOW - 86400)
    result, writes, lookups = _heal(monkeypatch, stored, None)

    assert result is stored
    assert writes == [] and lookups == ['uid-1']
