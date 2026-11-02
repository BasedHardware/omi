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


def test_lapsed_paid_heals_from_stripe_subscription_id_directly(monkeypatch):
    stored = _stored(PlanType.unlimited, NOW - 86400)
    writes = []
    saved_customer = []

    class FakeStripeSub:
        def to_dict(self):
            return {
                'status': 'active',
                'current_period_end': NOW + 30 * 86400,
                'current_period_start': NOW - 86400,
                'items': {'data': [{'price': {'id': 'price_1RrxXL1F8wnoWYvwIddzR902'}}]},
                'customer': 'cus_neo_vip',
            }

    monkeypatch.setattr(subscription_utils.stripe.Subscription, 'retrieve', lambda sub_id: FakeStripeSub())
    monkeypatch.setattr(
        subscription_utils.users_db, 'update_user_subscription', lambda uid, data: writes.append((uid, data))
    )
    monkeypatch.setattr(
        subscription_utils.users_db,
        'set_stripe_customer_id',
        lambda uid, cus: saved_customer.append((uid, cus)),
    )
    # Ensure fallback customer listing is never needed
    monkeypatch.setattr(
        subscription_utils,
        'find_active_paid_subscription_for_user',
        lambda uid: None,
    )

    result = subscription_utils.reconcile_basic_plan_with_stripe('uid-neo', stored)
    assert result.current_period_end == NOW + 30 * 86400
    assert result.plan == PlanType.unlimited
    assert result.status == SubscriptionStatus.active
    assert len(writes) == 1
    assert saved_customer == [('uid-neo', 'cus_neo_vip')]


def test_lapsed_paid_stripe_retrieve_fails_falls_back_to_customer_search(monkeypatch):
    stored = _stored(PlanType.unlimited, NOW - 86400)
    renewed = _stored(PlanType.unlimited, NOW + 30 * 86400)
    writes = []
    lookups = []

    def mock_retrieve(sub_id):
        raise RuntimeError("Stripe API down")

    monkeypatch.setattr(subscription_utils.stripe.Subscription, 'retrieve', mock_retrieve)
    monkeypatch.setattr(
        subscription_utils,
        'find_active_paid_subscription_for_user',
        lambda uid: lookups.append(uid) or renewed,
    )
    monkeypatch.setattr(
        subscription_utils.users_db, 'update_user_subscription', lambda uid, data: writes.append((uid, data))
    )

    result = subscription_utils.reconcile_basic_plan_with_stripe('uid-fallback', stored)
    assert result is renewed
    assert lookups == ['uid-fallback']
    assert writes == [('uid-fallback', renewed.model_dump())]


def test_lapsed_paid_canceled_in_stripe_falls_back_to_customer_search(monkeypatch):
    stored = _stored(PlanType.unlimited, NOW - 86400)
    writes = []
    lookups = []

    class FakeCanceledSub:
        def to_dict(self):
            return {
                'status': 'canceled',
                'current_period_end': NOW + 30 * 86400,
                'items': {'data': [{'price': {'id': 'price_1RrxXL1F8wnoWYvwIddzR902'}}]},
                'customer': 'cus_neo_canceled',
            }

    monkeypatch.setattr(subscription_utils.stripe.Subscription, 'retrieve', lambda sub_id: FakeCanceledSub())
    monkeypatch.setattr(
        subscription_utils,
        'find_active_paid_subscription_for_user',
        lambda uid: lookups.append(uid) or None,
    )
    monkeypatch.setattr(
        subscription_utils.users_db, 'update_user_subscription', lambda uid, data: writes.append((uid, data))
    )

    result = subscription_utils.reconcile_basic_plan_with_stripe('uid-canceled', stored)
    assert result is stored
    assert lookups == ['uid-canceled']
    assert writes == []
