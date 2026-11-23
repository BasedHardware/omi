"""Money-safety review fixes for Google Play Billing: account deletion stops Google billing,
pending and notification-only purchases are bound and acknowledged, Stripe and Play never both
bill, a refunded token never grants again, verify is rate limited, trials are shared across
providers, and the grace period keeps access."""

import asyncio
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from database import play_subscriptions as play_db  # noqa: E402
from models.users import PlanType, Subscription  # noqa: E402
from tests.unit.test_play_billing import (  # noqa: E402,F401
    DAY,
    NOW,
    OTHER,
    TOKEN,
    UID,
    _notify,
    _row,
    _verify,
    env,
    resource,
    subscribed,
)
from utils import play_billing, play_publisher  # noqa: E402

# ---- 1. account deletion cancels Google billing --------------------------------------------


class CancelPublisher:
    def __init__(self, fail=None):
        self.cancelled = []
        self.fail = fail

    def cancel(self, package_name, token):
        if self.fail:
            raise self.fail
        self.cancelled.append((package_name, token))


@pytest.fixture
def deletion_store(env, monkeypatch):
    monkeypatch.setattr(play_publisher, 'play_db', env.store)
    return env


def test_account_deletion_cancels_the_live_play_subscription(subscribed, deletion_store):
    publisher = CancelPublisher()
    assert play_publisher.cancel_for_account_deletion(UID, publisher) == 1
    assert publisher.cancelled == [('com.friend.ios', TOKEN)]
    doc = subscribed.store.docs[play_db.token_key(TOKEN)]
    assert doc['account_deletion_cancelled'] is True and doc['auto_renewing'] is False
    # Idempotent on retry: no second call.
    assert play_publisher.cancel_for_account_deletion(UID, publisher) == 0


def test_account_deletion_cancels_a_pending_purchase_too(env, deletion_store):
    env.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_PENDING')
    _verify()
    publisher = CancelPublisher()
    assert play_publisher.cancel_for_account_deletion(UID, publisher) == 1


def test_account_deletion_fails_loudly_when_google_cannot_cancel(subscribed, deletion_store):
    with pytest.raises(RuntimeError):
        play_publisher.cancel_for_account_deletion(UID, CancelPublisher(fail=RuntimeError('google 503')))
    assert 'account_deletion_cancelled' not in subscribed.store.docs[play_db.token_key(TOKEN)]


def test_account_deletion_skips_ended_and_other_users_purchases(subscribed, deletion_store):
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_EXPIRED')
    _notify(13)
    publisher = CancelPublisher()
    assert play_publisher.cancel_for_account_deletion(UID, publisher) == 0
    assert play_publisher.cancel_for_account_deletion(OTHER, publisher) == 0
    assert publisher.cancelled == []


def test_deletion_billing_step_raises_when_play_cancel_fails(monkeypatch):
    from services.users import account_deletion

    monkeypatch.setattr(account_deletion.users_db, 'get_existing_user_subscription', lambda uid: None)
    monkeypatch.setattr(account_deletion.stripe_utils, 'find_billable_app_subscription_ids', lambda uid: [])

    def boom(uid):
        raise RuntimeError('google unavailable')

    monkeypatch.setattr(account_deletion.play_publisher, 'cancel_for_account_deletion', boom)
    with pytest.raises(account_deletion.DeletionBillingError) as error:
        account_deletion._cancel_subscription_for_account_deletion(UID)
    assert error.value.subscription_id == 'google_play'

    called = []
    monkeypatch.setattr(account_deletion.play_publisher, 'cancel_for_account_deletion', lambda uid: called.append(uid))
    account_deletion._cancel_subscription_for_account_deletion(UID)
    assert called == [UID]


def test_publisher_cancel_uses_subscriptionsv2_with_developer_stop_payments():
    from urllib.parse import quote

    calls = []

    class Session:
        def post(self, url, json, timeout):
            calls.append((url, json))
            return SimpleNamespace(status_code=200, raise_for_status=lambda: None)

    client = object.__new__(play_publisher.GooglePublisher)
    client._session = Session()
    client._quote = lambda value: quote(value, safe='')
    client.cancel('com.friend.ios', 'tok')
    assert calls == [
        (
            'https://androidpublisher.googleapis.com/androidpublisher/v3/applications/com.friend.ios'
            '/purchases/subscriptionsv2/tokens/tok:cancel',
            {'cancellationContext': {'cancellationType': 'DEVELOPER_REQUESTED_STOP_PAYMENTS'}},
        )
    ]


# ---- 2. pending and notification-only purchases --------------------------------------------


def test_pending_purchase_is_recorded_then_granted_and_acknowledged_by_notification(env):
    env.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_PENDING')
    assert _verify().status == 'pending'
    assert env.store.users[UID][play_db.PENDING_FIELD] == play_db.token_key(TOKEN)
    assert env.users.writes == [] and env.publisher.acks == []
    env.publisher.resources[TOKEN] = resource()  # Google cleared the payment
    assert _notify(4) == 'active'
    assert env.publisher.acks == [TOKEN]
    assert _row(env).plan == PlanType.unlimited_v2
    assert env.store.users[UID][play_db.PENDING_FIELD] is None


def test_unbound_resubscribe_token_binds_through_its_linked_token(subscribed):
    subscribed.publisher.resources['play-token-2'] = resource(linkedPurchaseToken=TOKEN, account=None)
    subscribed.publisher.resources['play-token-2']['externalAccountIdentifiers'] = {}
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_EXPIRED')
    _notify(13)
    assert _notify(4, token='play-token-2') == 'active'
    doc = subscribed.store.docs[play_db.token_key('play-token-2')]
    assert doc['uid'] == UID
    assert 'play-token-2' in subscribed.publisher.acks
    assert subscribed.store.pointers[UID] == play_db.token_key('play-token-2')


def test_unbound_token_binds_through_the_obfuscated_account_id(env):
    env.store.remember_account(play_billing.obfuscated_account_id(UID), UID)
    env.publisher.resources[TOKEN] = resource()
    assert _notify(4) == 'active'
    assert env.store.docs[play_db.token_key(TOKEN)]['uid'] == UID
    assert env.publisher.acks == [TOKEN]


def test_unbound_token_with_no_owner_is_logged_and_never_granted(env, caplog):
    env.publisher.resources[TOKEN] = resource()
    env.publisher.resources[TOKEN]['externalAccountIdentifiers'] = {}
    assert _notify(4) == 'unbound'
    assert env.users.writes == [] and env.publisher.acks == []
    assert 'no known owner' in caplog.text


def test_linked_and_account_owners_that_disagree_never_bind(env):
    env.store.remember_account(play_billing.obfuscated_account_id(UID), UID)
    env.store.docs[play_db.token_key('old')] = {'uid': OTHER}
    env.publisher.resources[TOKEN] = resource(linkedPurchaseToken='old')
    assert _notify(4) == 'unbound'
    assert env.users.writes == []


# ---- 3. Stripe and Play never both bill ----------------------------------------------------


def test_play_renewal_never_overwrites_a_live_stripe_row(subscribed, caplog):
    stripe_row = Subscription(
        plan=PlanType.unlimited_v2, current_period_end=NOW + 20 * DAY, stripe_subscription_id='sub_9'
    ).model_dump()
    subscribed.users.rows[UID] = stripe_row
    subscribed.publisher.resources[TOKEN] = resource(expiry=NOW + 60 * DAY)
    subscribed.publisher.resources[TOKEN]['acknowledgementState'] = 'ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED'
    assert _notify(2) == 'stripe_conflict'
    assert _row(subscribed).stripe_subscription_id == 'sub_9'
    assert 'double billing' in caplog.text


def test_new_play_token_for_a_live_stripe_user_is_never_acknowledged(env):
    env.users.rows[UID] = Subscription(
        plan=PlanType.unlimited_v2, current_period_end=NOW + 20 * DAY, stripe_subscription_id='sub_9'
    ).model_dump()
    env.store.remember_account(play_billing.obfuscated_account_id(UID), UID)
    env.publisher.resources[TOKEN] = resource()
    with pytest.raises(play_billing.PlayBillingError) as error:
        _notify(4)
    assert error.value.code == 'stripe_subscription_active'
    assert env.publisher.acks == []  # Google refunds it on day 3


@pytest.fixture
def webhook(monkeypatch):
    import routers.payment as payment

    play_row = Subscription(plan=PlanType.unlimited_v2, current_period_end=NOW + 20 * DAY, provider='play')
    state = SimpleNamespace(refused=[], writes=[], notices=[], row=play_row)

    async def no_fence(uid, sub_id):
        return False

    monkeypatch.setattr(payment, '_deletion_webhook_blocks_entitlement', no_fence)
    monkeypatch.setattr(payment.users_db, 'get_user_profile', lambda uid: {'uid': uid})
    monkeypatch.setattr(payment.users_db, 'get_user_valid_subscription', lambda uid: state.row)
    monkeypatch.setattr(payment.users_db, 'get_existing_user_subscription', lambda uid: state.row)
    monkeypatch.setattr(payment.users_db, 'update_user_subscription', lambda uid, data: state.writes.append(data))
    monkeypatch.setattr(payment.play_subscriptions_db, 'get_user_pointer', lambda uid: 'a' * 64)
    monkeypatch.setattr(
        payment.stripe_utils,
        'cancel_and_refund_checkout_subscription',
        lambda sub_id: state.refused.append(sub_id) or {'subscription_id': sub_id, 'refund_id': 're_1'},
    )
    monkeypatch.setattr(payment, 'send_notification', lambda uid, title, body: state.notices.append(body))
    monkeypatch.setattr(payment, 'record_subscription_event', lambda **kw: None)
    monkeypatch.setattr(
        payment,
        '_build_subscription_from_stripe_object',
        lambda obj, **kw: Subscription(plan=PlanType.unlimited_v2, current_period_end=NOW + 30 * DAY),
    )
    return SimpleNamespace(payment=payment, state=state)


def test_stripe_checkout_after_play_is_cancelled_refunded_and_never_written(webhook):
    event = {
        'type': 'checkout.session.completed',
        'data': {'object': {'id': 'cs_1', 'client_reference_id': UID, 'subscription': 'sub_new', 'metadata': {}}},
    }
    result = asyncio.run(webhook.payment._handle_stripe_event(event, None))
    assert 'Google Play' in result['message']
    assert webhook.state.refused == ['sub_new'] and webhook.state.writes == []
    assert 'refunded' in webhook.state.notices[0]


def test_stripe_subscription_created_after_play_is_refused_too(webhook):
    event = {
        'type': 'customer.subscription.created',
        'data': {'object': {'id': 'sub_new', 'status': 'active', 'customer': 'cus_1', 'metadata': {'uid': UID}}},
    }
    asyncio.run(webhook.payment._handle_stripe_event(event, None))
    assert webhook.state.refused == ['sub_new'] and webhook.state.writes == []


def test_cancel_and_refund_refunds_the_paid_first_invoice(monkeypatch):
    from utils import stripe as stripe_utils

    calls = []
    monkeypatch.setattr(
        stripe_utils.stripe.Subscription,
        'retrieve',
        staticmethod(
            lambda sid, expand=None: {
                'status': 'active',
                'latest_invoice': {'amount_paid': 2999, 'payment_intent': 'pi_1'},
            }
        ),
    )
    monkeypatch.setattr(
        stripe_utils.stripe.Refund, 'create', staticmethod(lambda **kw: calls.append(('refund', kw)) or {'id': 're_1'})
    )
    monkeypatch.setattr(
        stripe_utils.stripe.Subscription, 'cancel', staticmethod(lambda sid: calls.append(('cancel', sid)))
    )
    result = stripe_utils.cancel_and_refund_checkout_subscription('sub_new')
    assert result['refund_id'] == 're_1'
    assert calls[0] == ('refund', {'payment_intent': 'pi_1', 'idempotency_key': 'play-conflict-refund-sub_new'})
    assert calls[1] == ('cancel', 'sub_new')


def test_stripe_checkout_is_refused_while_a_play_purchase_is_pending(monkeypatch):
    from utils import subscription as subscription_utils

    monkeypatch.setattr(subscription_utils.users_db, 'get_user_valid_subscription', lambda *a, **k: Subscription())
    monkeypatch.setattr(subscription_utils.play_subscriptions_db, 'pending_play_purchase', lambda uid: True)
    allowed, reason = subscription_utils.can_user_make_payment(UID, 'price_any')
    assert allowed is False and 'Google Play purchase' in reason


def test_play_subscriber_gets_typed_play_answers_from_stripe_portal_and_cancel(monkeypatch):
    from fastapi import HTTPException

    import routers.payment as payment

    row = Subscription(plan=PlanType.unlimited_v2, current_period_end=NOW + DAY, provider='play')
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid: row)
    portal = payment.create_customer_portal_endpoint(uid=UID)
    assert portal['url'].startswith('https://play.google.com/store/account/subscriptions?sku=omi_pro')
    with pytest.raises(HTTPException) as cancel:
        payment.cancel_subscription_endpoint(uid=UID)
    assert cancel.value.status_code == 409 and 'Google Play' in cancel.value.detail


# ---- 4. a refunded token never grants again ------------------------------------------------


def test_refunded_token_is_never_granted_again(subscribed):
    assert _notify(voided=True) == 'revoked'
    # Google still reads it ACTIVE (refund without revoke); the client re-posts it.
    with pytest.raises(play_billing.PlayBillingError) as error:
        _verify()
    assert error.value.code == 'purchase_refunded'
    assert _notify(2) in ('revoked', 'inactive')  # a later renewal notification
    assert _row(subscribed).plan == PlanType.basic
    assert subscribed.store.docs[play_db.token_key(TOKEN)]['revoked'] is True


# ---- 5. rate limit and trials --------------------------------------------------------------


def test_verify_route_is_rate_limited_per_uid():
    from utils.rate_limit_config import RATE_POLICIES

    from routers import play_billing as routes

    assert 'payments:play_verify' in RATE_POLICIES
    route = next(r for r in routes.router.routes if r.path == '/v1/payments/play/purchases')
    names = {getattr(dep.call, '__qualname__', '') for dep in route.dependant.dependencies}
    assert any('rate_limit' in name for name in names)


def test_a_play_purchase_marks_the_user_as_a_former_subscriber(env):
    env.publisher.resources[TOKEN] = resource()
    _verify()
    assert env.store.users[UID][play_db.CUSTOMER_FIELD] is True


def test_former_play_subscriber_is_not_trial_eligible_for_stripe(monkeypatch):
    from fastapi import HTTPException

    import routers.payment as payment

    monkeypatch.setattr(payment, 'management_binding', lambda price: None)
    monkeypatch.setattr(payment, '_validate_price_id', lambda price: None)
    monkeypatch.setattr(payment.subscription_utils, 'can_user_make_payment', lambda uid, price: (True, ''))
    monkeypatch.setattr(payment, '_try_reactivate_subscription', lambda uid, price: None)
    monkeypatch.setattr(payment.subscription_utils, 'new_buyer_single_plan_violation', lambda uid, price: None)
    monkeypatch.setattr(payment.users_db, 'get_stripe_customer_id', lambda uid: None)
    monkeypatch.setattr(payment.play_subscriptions_db, 'is_play_customer', lambda uid: True)
    request = payment.CreateCheckoutRequest(price_id='price_x', trial_days=7)
    with pytest.raises(HTTPException) as error:
        payment.create_checkout_session_endpoint(request, uid=UID, x_app_platform='ios')
    assert error.value.detail == 'trial_unavailable'


def test_trial_eligibility_counts_play_history_in_both_directions(monkeypatch):
    import routers.users as users

    customers = {'stripe': None, 'play': False}
    monkeypatch.setattr(users.users_db, 'get_stripe_customer_id', lambda uid: customers['stripe'])
    monkeypatch.setattr(users.play_subscriptions_db, 'is_play_customer', lambda uid: customers['play'])
    assert users._never_subscribed(UID) is True
    customers['play'] = True  # had a Play trial or subscription: no Stripe trial later
    assert users._never_subscribed(UID) is False
    customers.update(play=False, stripe='cus_1')  # had Stripe: the app then buys Play without the trial offer
    assert users._never_subscribed(UID) is False

    def down(uid):
        raise RuntimeError('firestore')

    monkeypatch.setattr(users.play_subscriptions_db, 'is_play_customer', down)
    customers['stripe'] = None
    assert users._never_subscribed(UID) is False


# ---- grace period --------------------------------------------------------------------------


def test_grace_keeps_access_with_googles_extended_expiry(subscribed):
    # Realistic: renewal failed an hour ago; Google extends expiryTime through the 7-day grace.
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_IN_GRACE_PERIOD', expiry=NOW + 6 * DAY)
    assert _notify(6) == 'active'
    assert _row(subscribed).current_period_end == NOW + 6 * DAY


def test_grace_keeps_access_even_before_google_extends_expiry(subscribed):
    # The notification can race Google's extension: expiryTime still at the missed renewal.
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_IN_GRACE_PERIOD', expiry=NOW - 3600)
    assert _notify(6) == 'active'
    row = _row(subscribed)
    assert row.plan == PlanType.unlimited_v2
    assert row.current_period_end >= NOW + 23 * 3600
    assert subscribed.store.docs[play_db.token_key(TOKEN)]['next_check_at'] <= NOW + 7 * 3600
    # Grace ends without payment: Google moves it to on hold and access goes.
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_ON_HOLD', expiry=NOW - 3600)
    assert _notify(5) == 'revoked'
