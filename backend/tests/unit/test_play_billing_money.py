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
    """Reads Google's state from the shared fake; cancel can fail and can change the state it leaves."""

    def __init__(self, reads, fail=None, read_fail=None, state_after_failure=None):
        self.reads = reads
        self.cancelled = []
        self.fail = fail
        self.read_fail = read_fail
        self.state_after_failure = state_after_failure

    def get_subscription(self, package_name, token):
        if self.read_fail:
            raise self.read_fail
        if token not in self.reads.resources:
            raise play_publisher.PurchaseNotFound()
        return self.reads.resources[token]

    def cancel(self, package_name, token):
        if self.fail:
            if self.state_after_failure:
                self.reads.resources[token] = resource(self.state_after_failure)
            raise self.fail
        self.cancelled.append((package_name, token))
        self.reads.resources[token] = resource('SUBSCRIPTION_STATE_CANCELED', renew=False)


@pytest.fixture
def deletion_store(env, monkeypatch):
    monkeypatch.setattr(play_publisher, 'play_db', env.store)
    return env


def test_account_deletion_cancels_the_live_play_subscription(subscribed, deletion_store):
    publisher = CancelPublisher(subscribed.publisher)
    assert play_publisher.cancel_for_account_deletion(UID, publisher) == 1
    assert publisher.cancelled == [('com.friend.ios', TOKEN)]
    doc = subscribed.store.docs[play_db.token_key(TOKEN)]
    assert doc['account_deletion_cancelled'] is True and doc['auto_renewing'] is False
    # Idempotent on retry: no second call.
    assert play_publisher.cancel_for_account_deletion(UID, publisher) == 0


def test_account_deletion_cancels_a_pending_purchase_too(env, deletion_store):
    env.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_PENDING')
    _verify()
    assert play_publisher.cancel_for_account_deletion(UID, CancelPublisher(env.publisher)) == 1


@pytest.mark.parametrize(
    'google_state',
    ['SUBSCRIPTION_STATE_EXPIRED', 'SUBSCRIPTION_STATE_CANCELED', 'SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED', None],
)
def test_account_deletion_reads_google_first_and_accepts_what_can_no_longer_charge(
    subscribed, deletion_store, google_state
):
    # Our record still says ACTIVE (notification not processed), Google already ended it.
    if google_state is None:
        del subscribed.publisher.resources[TOKEN]
    else:
        subscribed.publisher.resources[TOKEN] = resource(google_state, renew=False)
    publisher = CancelPublisher(subscribed.publisher, fail=play_publisher.PublisherHTTPError(400, 'cancel'))
    assert play_publisher.cancel_for_account_deletion(UID, publisher) == 0
    assert subscribed.store.docs[play_db.token_key(TOKEN)]['account_deletion_cancelled'] is True


def test_a_failed_cancel_is_accepted_when_google_now_shows_no_future_charge(subscribed, deletion_store):
    publisher = CancelPublisher(
        subscribed.publisher,
        fail=play_publisher.PublisherHTTPError(400, 'cancel'),
        state_after_failure='SUBSCRIPTION_STATE_CANCELED',
    )
    assert play_publisher.cancel_for_account_deletion(UID, publisher) == 0
    assert subscribed.store.docs[play_db.token_key(TOKEN)]['account_deletion_cancelled'] is True


@pytest.mark.parametrize('status', [400, 403, 503])
def test_a_cancel_google_refuses_is_retryable_and_never_carries_the_token(subscribed, deletion_store, status):
    publisher = CancelPublisher(subscribed.publisher, fail=play_publisher.PublisherHTTPError(status, 'cancel'))
    with pytest.raises(play_publisher.PlayCancelPending) as error:
        play_publisher.cancel_for_account_deletion(UID, publisher)
    assert error.value.status_code == status
    assert TOKEN not in str(error.value)
    assert play_db.token_key(TOKEN)[:12] in str(error.value)
    assert 'account_deletion_cancelled' not in subscribed.store.docs[play_db.token_key(TOKEN)]
    # A long outage on the first read is retryable too.
    reading_down = CancelPublisher(subscribed.publisher, read_fail=play_publisher.PublisherHTTPError(503, 'read'))
    with pytest.raises(play_publisher.PlayCancelPending):
        play_publisher.cancel_for_account_deletion(UID, reading_down)


def test_account_deletion_skips_other_users_purchases(subscribed, deletion_store):
    publisher = CancelPublisher(subscribed.publisher)
    assert play_publisher.cancel_for_account_deletion(OTHER, publisher) == 0
    assert publisher.cancelled == []


def test_play_cancel_failure_is_retried_by_the_wipe_not_parked_as_billing_failed(monkeypatch):
    from database.account_deletion_policy import deletion_billing_error_is_already_gone
    from services.users import account_deletion

    monkeypatch.setattr(account_deletion.users_db, 'get_existing_user_subscription', lambda uid: None)
    monkeypatch.setattr(account_deletion.stripe_utils, 'find_billable_app_subscription_ids', lambda uid: [])

    def pending(uid):
        raise play_publisher.PlayCancelPending(503, 'a' * 64)

    monkeypatch.setattr(account_deletion.play_publisher, 'cancel_for_account_deletion', pending)
    with pytest.raises(play_publisher.PlayCancelPending) as error:
        account_deletion._cancel_subscription_for_account_deletion(UID)
    # Not a DeletionBillingError: the wipe marks it `failed`, which the reconciler retries with backoff.
    assert not isinstance(error.value, account_deletion.DeletionBillingError)
    # Admission fails on it like a Stripe failure, so grace actions are never marked complete over it.
    monkeypatch.setattr(account_deletion.firebase_auth, 'revoke_refresh_tokens', lambda uid: None)
    monkeypatch.setattr(account_deletion, 'go_queue_erase_required', lambda: True)
    with pytest.raises(play_publisher.PlayCancelPending):
        account_deletion._run_immediate_deletion_steps(UID)
    # Failures parked by the first Play release are re-claimed by the reconciler.
    assert deletion_billing_error_is_already_gone(
        '400 Client Error: Bad Request for url: https://androidpublisher.googleapis.com/x'
    )


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


@pytest.fixture(scope='module', autouse=True)
def _warm_imports():
    """Heavy router imports belong to setup, not to a test's CPU budget."""
    import routers.payment  # noqa: F401
    import routers.play_billing  # noqa: F401
    import routers.users  # noqa: F401
    from services.users import account_deletion  # noqa: F401


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
    monkeypatch.setattr(payment.play_stripe_guard.play_subscriptions_db, 'get_user_pointer', lambda uid: 'a' * 64)
    monkeypatch.setattr(
        payment.play_stripe_guard.stripe_utils,
        'cancel_and_refund_checkout_subscription',
        lambda sub_id: state.refused.append(sub_id) or {'subscription_id': sub_id, 'refund_id': 're_1'},
    )

    async def notice(intent):
        state.notices.append(intent.body)

    monkeypatch.setattr(payment.play_stripe_guard, 'dispatch_notification_async', notice)
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


def test_refund_only_then_a_paid_renewal_grants_again(subscribed):
    # Play Console "refund" without revoke: Google keeps the subscription and bills next period.
    assert _notify(voided=True) == 'revoked'
    assert _row(subscribed).plan == PlanType.basic
    subscribed.publisher.resources[TOKEN] = resource(expiry=NOW + 60 * DAY)  # renewed and paid
    assert _notify(2) == 'active'
    row = _row(subscribed)
    assert row.plan == PlanType.unlimited_v2 and row.current_period_end == NOW + 60 * DAY


def test_refund_and_revoke_never_grants_again(subscribed):
    assert _notify(12) == 'revoked'
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_EXPIRED')  # ended at Google
    assert _notify(13) in ('revoked', 'inactive')
    with pytest.raises(play_billing.PlayBillingError) as error:
        _verify()
    assert error.value.code == 'purchase_refunded'
    assert _row(subscribed).plan == PlanType.basic


def test_refund_only_then_a_reposted_token_before_any_renewal_never_grants(subscribed):
    assert _notify(voided=True) == 'revoked'
    # Google still reads the same refunded period ACTIVE; Restore or a stored-token retry re-posts it.
    with pytest.raises(play_billing.PlayBillingError) as error:
        _verify()
    assert error.value.code == 'purchase_refunded'
    assert _notify(2) in ('revoked', 'inactive')  # a notification for the same period
    assert _row(subscribed).plan == PlanType.basic


def test_a_grace_read_after_a_refund_never_grants(subscribed):
    _notify(voided=True)
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_IN_GRACE_PERIOD', expiry=NOW + 40 * DAY)
    assert _notify(6) in ('revoked', 'inactive')
    assert _row(subscribed).plan == PlanType.basic


def test_refund_of_an_earlier_order_keeps_the_current_paid_period(subscribed):
    subscribed.publisher.resources[TOKEN]['latestOrderId'] = 'GPA.current'
    assert _notify(voided=True, order='GPA.earlier') == 'active'
    assert _row(subscribed).plan == PlanType.unlimited_v2


# ---- fix 3: account ids are server secrets ------------------------------------------------


def test_a_forged_account_id_binds_nothing_and_the_victims_own_purchase_still_grants(env):
    import hashlib

    # The attacker computes the victim's id the old, unkeyed way and buys with it.
    forged = hashlib.sha256(f'omi-play-account:{UID}'.encode()).hexdigest()
    env.store.remember_account(play_billing.obfuscated_account_id(UID), UID)  # issued to the victim
    env.publisher.resources['attacker-token'] = resource(account=forged)
    assert _notify(4, token='attacker-token') == 'unbound'
    assert env.users.writes == [] and env.store.users.get(UID, {}).get(play_db.PENDING_FIELD) is None
    # The victim's real purchase is acknowledged and granted.
    env.publisher.resources[TOKEN] = resource()
    assert _verify().status == 'active'
    assert TOKEN in env.publisher.acks


def test_an_account_map_entry_that_is_not_the_issued_id_is_refused(env):
    env.store.accounts['tampered-id'] = UID  # a row the server never issued for this uid
    env.publisher.resources[TOKEN] = resource(account='tampered-id')
    assert _notify(4) == 'unbound'
    assert env.users.writes == []


def test_verify_is_refused_while_the_account_key_is_missing(env, monkeypatch):
    monkeypatch.delenv('PLAY_ACCOUNT_ID_HMAC_KEY')
    env.publisher.resources[TOKEN] = resource(account='x' * 64)
    with pytest.raises(play_billing.PlayBillingError) as error:
        _verify()
    assert (error.value.http_status, error.value.code) == (503, 'play_not_configured')


def test_the_account_map_is_written_once_and_never_moves():
    from google.api_core.exceptions import AlreadyExists

    stored = {}

    class Doc:
        def __init__(self, key):
            self.key = key

        def create(self, data):
            if self.key in stored:
                raise AlreadyExists('exists')
            stored[self.key] = dict(data)

    client = SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda key: Doc((name, key))))
    play_db.remember_account('id-1', UID, firestore_client=client)
    play_db.remember_account('id-1', OTHER, firestore_client=client)
    assert stored[(play_db.ACCOUNTS, 'id-1')] == {'uid': UID}


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


# ---- round 2 ---------------------------------------------------------------------------------


def test_deleting_a_user_without_play_needs_no_google_credentials(env, deletion_store, monkeypatch):
    import google.auth

    def no_credentials(*args, **kwargs):
        raise google.auth.exceptions.DefaultCredentialsError('no ADC')

    monkeypatch.setattr(google.auth, 'default', no_credentials)
    monkeypatch.setattr(play_publisher, '_default', None)
    assert play_publisher.cancel_for_account_deletion(OTHER) == 0  # a Stripe or iOS user: no Play fields


def test_grace_admission_does_not_complete_over_a_failed_play_cancel_and_the_reconciler_retries(
    subscribed, deletion_store, monkeypatch
):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import MagicMock

    from services.users import account_deletion

    publisher = CancelPublisher(subscribed.publisher, fail=play_publisher.PublisherHTTPError(503, 'cancel'))
    monkeypatch.setattr(play_publisher, '_default', publisher)
    monkeypatch.setattr(account_deletion.users_db, 'get_existing_user_subscription', lambda uid: None)
    monkeypatch.setattr(account_deletion.stripe_utils, 'find_billable_app_subscription_ids', lambda uid: [])
    monkeypatch.setattr(account_deletion.firebase_auth, 'revoke_refresh_tokens', lambda uid: None)
    monkeypatch.setattr(account_deletion, 'go_queue_erase_required', lambda: True)
    monkeypatch.setattr(account_deletion, 'assert_account_deletion_permitted', lambda uid: None)
    monkeypatch.setattr(account_deletion, 'account_deletion_grace_enabled', lambda: True)
    monkeypatch.setattr(account_deletion, 'account_deletion_grace_window', lambda: timedelta(days=14))
    due = datetime.now(timezone.utc) + timedelta(days=14)
    monkeypatch.setattr(
        account_deletion.deletion_grace_db,
        'mark_user_deletion_grace_intent',
        lambda uid, when: {'wipe_job_id': 'grace-job', 'mode': 'created', 'wipe_status': 'pending_deletion'},
    )
    complete = MagicMock(return_value=True)
    monkeypatch.setattr(account_deletion.deletion_grace_db, 'mark_user_deletion_grace_actions_complete', complete)

    # Google answers 503 at admission: the request fails and grace actions stay incomplete.
    with pytest.raises(play_publisher.PlayCancelPending):
        account_deletion.start_account_deletion(UID, grace=True)
    complete.assert_not_called()

    # The next reconciler cycle re-runs the cancel; Google is back, so it completes.
    publisher.fail = None
    record = {
        'uid': UID,
        'wipe_status': 'pending_deletion',
        'wipe_job_id': 'grace-job',
        'wipe_due_at': due,
        'grace_actions_complete': False,
    }
    monkeypatch.setattr(account_deletion.users_db, 'get_pending_deletion_wipes', lambda **_kw: [record])
    account_deletion.reconcile_pending_deletion_wipes()
    assert publisher.cancelled == [('com.friend.ios', TOKEN)]
    complete.assert_called_once_with(UID, 'grace-job')
    assert subscribed.store.docs[play_db.token_key(TOKEN)]['account_deletion_cancelled'] is True


def test_a_transport_error_on_a_notification_never_carries_the_token(subscribed):
    import traceback

    class LeakyTransportError(Exception):
        pass

    url = f'https://androidpublisher.googleapis.com/x/subscriptionsv2/tokens/{TOKEN}'
    subscribed.publisher.fail = LeakyTransportError(f'Max retries exceeded with url: {url}')
    with pytest.raises(play_billing.PlayBillingError) as error:
        _notify(2)
    assert error.value.http_status == 503
    assert TOKEN not in str(error.value)
    assert TOKEN not in ''.join(traceback.format_exception(error.value))


def test_deletion_cancels_a_user_cancelled_subscription_with_time_left(subscribed, deletion_store):
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_CANCELED', renew=False)
    publisher = CancelPublisher(subscribed.publisher)
    assert play_publisher.cancel_for_account_deletion(UID, publisher) == 1
    assert publisher.cancelled == [('com.friend.ios', TOKEN)]


def test_a_failed_cancel_of_a_user_cancelled_subscription_does_not_park_the_wipe(subscribed, deletion_store):
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_CANCELED', renew=False)
    publisher = CancelPublisher(subscribed.publisher, fail=play_publisher.PublisherHTTPError(503, 'cancel'))
    assert play_publisher.cancel_for_account_deletion(UID, publisher) == 0
    assert subscribed.store.docs[play_db.token_key(TOKEN)]['account_deletion_cancelled'] is True


def test_an_ended_cancelled_subscription_needs_no_cancel(subscribed, deletion_store):
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_CANCELED', renew=False, expiry=NOW - DAY)
    publisher = CancelPublisher(subscribed.publisher)
    assert play_publisher.cancel_for_account_deletion(UID, publisher) == 0
    assert publisher.cancelled == []


def test_a_voided_notification_without_googles_order_ids_revokes(subscribed):
    # Neither latestOrderId nor latestSuccessfulOrderId: the voided order cannot be shown to be an old one.
    assert _notify(voided=True, order='GPA.unknown') == 'revoked'
    assert _row(subscribed).plan == PlanType.basic


def test_the_wipe_drops_play_purchase_records_and_account_map_entries():
    class Doc:
        def __init__(self, store, collection, key):
            self.reference = SimpleNamespace(delete=lambda: store[collection].pop(key))

    class Query:
        def __init__(self, store, collection, uid):
            self.store, self.collection, self.uid = store, collection, uid

        def stream(self):
            rows = self.store[self.collection]
            return [Doc(self.store, self.collection, k) for k, v in list(rows.items()) if v.get('uid') == self.uid]

    class Client:
        def __init__(self):
            self.store = {
                play_db.COLLECTION: {
                    'a' * 64: {'uid': UID, 'purchase_token': TOKEN},
                    'b' * 64: {'uid': UID, 'purchase_token': 'older-token'},
                    'c' * 64: {'uid': OTHER, 'purchase_token': 'other-token'},
                },
                play_db.ACCOUNTS: {'issued-id': {'uid': UID}, 'other-id': {'uid': OTHER}},
            }

        def collection(self, name):
            store = self.store
            return SimpleNamespace(where=lambda field, op, value: Query(store, name, value))

    client = Client()
    assert play_db.purge_account_records(UID, firestore_client=client) == 3
    assert list(client.store[play_db.COLLECTION]) == ['c' * 64]
    assert list(client.store[play_db.ACCOUNTS]) == ['other-id']


def test_the_firestore_wipe_purges_play_records(monkeypatch):
    import inspect

    from database import user_data_deletion

    assert 'play_subscriptions.purge_account_records(uid)' in inspect.getsource(user_data_deletion.purge_user_subtree)
