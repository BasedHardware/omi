"""Play Billing money guards: no new Stripe agreement while a Google Play one can still charge or recover, a
Stripe + Play overlap is logged and recorded for a person (never cancelled automatically), Play builds never
start a new Stripe charge or get a Marketplace payment link, and malformed build headers route to Stripe.
A buyer with no Play history gets exactly today's checkout, with no new read or failure mode."""

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from config import play_billing as config  # noqa: E402
from database import play_subscriptions as play_db  # noqa: E402
from models.users import PlanType, Subscription  # noqa: E402
from tests.unit.test_play_billing import (  # noqa: E402,F401
    DAY,
    NOW,
    TEST_ACCOUNT_KEY,
    TOKEN,
    UID,
    _notify,
    _row,
    env,
    resource,
    subscribed,
)
from utils import play_billing, play_publisher  # noqa: E402
from utils.notification_dispatch import NotificationDispatchOutcome, NotificationDispatchStatus  # noqa: E402

ON_HOLD = 'SUBSCRIPTION_STATE_ON_HOLD'
HOLD_REASON = 'You have a Google Play subscription on hold. Fix the payment in Google Play.'
UNAVAILABLE_REASON = 'We could not check your Google Play subscription. Try again in a minute.'


@pytest.fixture(scope='module', autouse=True)
def _warm_imports():
    import routers.apps  # noqa: F401
    import routers.monthly_switch  # noqa: F401
    import routers.payment  # noqa: F401
    import routers.retention_offer  # noqa: F401
    import routers.yearly_switch  # noqa: F401
    import utils.prepaid_code_redemption  # noqa: F401


@pytest.fixture
def real_play_reads(env, monkeypatch):
    """The real play_subscriptions readers and Google re-read over the fake store and fake Google."""
    for name in ('get_user_fields', 'get_purchase', 'purchases_for_uid', 'update_purchase'):
        monkeypatch.setattr(play_db, name, getattr(env.store, name))
    monkeypatch.setattr(play_publisher, '_default', env.publisher)
    return env


def _stripe_row(sub_id='sub_card'):
    return Subscription(
        plan=PlanType.unlimited_v2, current_period_end=NOW + 20 * DAY, stripe_subscription_id=sub_id
    ).model_dump()


def _admission(world, monkeypatch):
    """The real checkout admission, with today's Stripe-side reads answered as for a Free reader."""
    from utils import subscription as sub

    monkeypatch.setattr(sub.users_db, 'get_user_valid_subscription', world.users.get_user_valid_subscription)
    monkeypatch.setattr(sub, '_has_active_stripe_subscription', lambda uid: False)
    monkeypatch.setattr(sub, 'find_active_paid_subscription_for_user', lambda uid: None)
    monkeypatch.setattr(sub, 'configured_ladder_prices', lambda: set())
    return lambda: sub.can_user_make_payment(UID, 'price_pro')


# ---- B. no second agreement while any owned Play purchase can still charge or recover --------


@pytest.mark.parametrize(
    'state,expiry,allowed',
    [
        ('SUBSCRIPTION_STATE_ACTIVE', NOW + DAY, False),
        ('SUBSCRIPTION_STATE_IN_GRACE_PERIOD', NOW + DAY, False),
        (ON_HOLD, NOW - DAY, False),
        ('SUBSCRIPTION_STATE_PAUSED', NOW - DAY, False),
        ('SUBSCRIPTION_STATE_CANCELED', NOW + DAY, False),
        ('SUBSCRIPTION_STATE_PENDING', NOW + DAY, False),
        ('SUBSCRIPTION_STATE_EXPIRED', NOW - DAY, True),
    ],
)
def test_checkout_admission_follows_google(subscribed, real_play_reads, monkeypatch, state, expiry, allowed):
    subscribed.publisher.resources[TOKEN] = resource(state, expiry=expiry)
    _notify(2)
    assert _admission(subscribed, monkeypatch)()[0] is allowed


@pytest.mark.parametrize('state', [ON_HOLD, 'SUBSCRIPTION_STATE_PAUSED'])
def test_stripe_checkout_is_refused_while_play_is_on_hold(subscribed, real_play_reads, monkeypatch, state):
    from routers import payment

    subscribed.publisher.resources[TOKEN] = resource(state)
    assert _notify(5) == 'revoked'
    assert _row(subscribed).plan == PlanType.basic  # access gone, Google can still recover it
    _admission(subscribed, monkeypatch)
    monkeypatch.setattr(payment, '_validate_price_id', lambda price: None)
    monkeypatch.setattr(payment, 'management_binding', lambda price: None)
    app = FastAPI()
    app.include_router(payment.router)
    app.dependency_overrides[payment.auth.get_current_user_uid] = lambda: UID
    response = TestClient(app).post('/v1/payments/checkout-session', json={'price_id': 'price_any'})
    assert response.status_code == 400
    # Old clients read ``detail`` as a string and show it.
    assert response.json() == {'detail': HOLD_REASON, 'code': 'play_subscription_on_hold'}


def test_a_noncurrent_purchase_on_hold_blocks_checkout(subscribed, real_play_reads, monkeypatch):
    subscribed.publisher.resources[TOKEN] = resource(ON_HOLD)
    _notify(5)
    old = play_db.token_key('expired-current')
    subscribed.store.docs[old] = {'uid': UID, 'state': 'SUBSCRIPTION_STATE_EXPIRED'}
    subscribed.store.users[UID][play_db.USER_POINTER_FIELD] = old
    assert _admission(subscribed, monkeypatch)() == (False, HOLD_REASON)


def test_a_purchase_first_bound_on_hold_by_a_notification_blocks_checkout(env, real_play_reads, monkeypatch):
    env.store.remember_account(play_billing.obfuscated_account_id(UID), UID)
    env.publisher.resources[TOKEN] = resource(ON_HOLD)
    assert _notify(5) == 'inactive'
    assert play_db.USER_POINTER_FIELD not in env.store.users[UID]  # never granted
    assert _admission(env, monkeypatch)() == (False, HOLD_REASON)


def test_a_stale_canceled_record_is_rechecked_and_blocks_when_google_restored_it(
    subscribed, real_play_reads, monkeypatch
):
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_CANCELED', expiry=NOW + DAY, renew=False)
    _notify(12)
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_ACTIVE')
    assert _admission(subscribed, monkeypatch)()[0] is False


def test_a_stale_hold_is_refreshed_and_never_blocks_once_google_ended_it(subscribed, real_play_reads, monkeypatch):
    subscribed.publisher.resources[TOKEN] = resource(ON_HOLD, expiry=NOW - DAY)
    _notify(5)
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_EXPIRED', expiry=NOW - DAY)
    assert _admission(subscribed, monkeypatch)() == (True, 'User can make payment')
    assert subscribed.store.docs[play_db.token_key(TOKEN)]['state'] == 'SUBSCRIPTION_STATE_EXPIRED'


def test_a_purchase_stopped_by_account_deletion_never_blocks(subscribed, real_play_reads, monkeypatch):
    subscribed.publisher.resources[TOKEN] = resource(ON_HOLD, expiry=NOW - DAY)
    _notify(5)
    subscribed.store.docs[play_db.token_key(TOKEN)].update(
        {'auto_renewing': False, 'account_deletion_confirmed_at': NOW}
    )
    subscribed.publisher.resources[TOKEN] = resource(
        'SUBSCRIPTION_STATE_CANCELED',
        renew=False,
        expiry=NOW - DAY,
        canceledStateContext={'developerInitiatedCancellation': {}},
    )
    assert _admission(subscribed, monkeypatch)()[0] is True


def test_refund_only_with_a_future_renewal_still_blocks(subscribed, real_play_reads, monkeypatch):
    _notify(12)
    assert _row(subscribed).plan == PlanType.basic
    assert _admission(subscribed, monkeypatch)()[0] is False


def test_google_unreadable_for_a_chargeable_purchase_refuses_with_a_retry(subscribed, real_play_reads, monkeypatch):
    from routers import payment

    subscribed.publisher.resources[TOKEN] = resource(ON_HOLD)
    _notify(5)
    subscribed.publisher.fail = RuntimeError('timeout')
    assert _admission(subscribed, monkeypatch)() == (False, UNAVAILABLE_REASON)
    monkeypatch.setattr(payment, '_validate_price_id', lambda price: None)
    monkeypatch.setattr(payment, 'management_binding', lambda price: None)
    app = FastAPI()
    app.include_router(payment.router)
    app.dependency_overrides[payment.auth.get_current_user_uid] = lambda: UID
    response = TestClient(app, raise_server_exceptions=False).post(
        '/v1/payments/checkout-session', json={'price_id': 'price_any'}
    )
    assert response.status_code == 400
    assert response.json() == {'detail': UNAVAILABLE_REASON, 'code': 'play_check_unavailable'}


def test_the_guard_holds_after_a_rollback_to_stripe(subscribed, real_play_reads, monkeypatch):
    monkeypatch.setenv('ANDROID_BILLING', 'stripe')
    monkeypatch.delenv('ANDROID_PLAY_BILLING_MIN_BUILD', raising=False)
    subscribed.publisher.resources[TOKEN] = resource(ON_HOLD)
    _notify(5)
    assert _admission(subscribed, monkeypatch)() == (False, HOLD_REASON)


def test_prepaid_redemption_follows_the_same_admission(subscribed, real_play_reads, monkeypatch):
    from utils import prepaid_code_redemption as redemption

    subscribed.publisher.resources[TOKEN] = resource(ON_HOLD)
    _notify(5)
    monkeypatch.setattr(redemption.users_db, 'get_existing_user_subscription', lambda uid: _row(subscribed))
    monkeypatch.setattr(redemption, '_open_stripe_subscriptions', lambda *a: pytest.fail('Play hold decides first'))
    assert redemption._has_live_plan(UID, NOW) is True
    subscribed.publisher.fail = RuntimeError('timeout')
    with pytest.raises(redemption.PrepaidCodeError) as error:
        redemption._has_live_plan(UID, NOW)
    assert error.value.status_code == 503


def _stripe_list(env, subs):
    env.users.customers[UID] = 'cus_1'
    env.stripe_subs.extend(subs)


@pytest.mark.parametrize('status', ['unpaid', 'incomplete', 'paused', 'past_due', 'trialing', 'active'])
def test_every_non_terminal_stripe_state_refuses_a_new_play_purchase(env, status):
    _stripe_list(env, [{'status': status, 'metadata': {'uid': UID}}])
    assert play_billing._live_stripe_subscription(UID) is True


@pytest.mark.parametrize('status', ['canceled', 'incomplete_expired'])
def test_ended_stripe_subscriptions_do_not_count(env, status):
    _stripe_list(env, [{'status': status, 'metadata': {'uid': UID}}])
    assert play_billing._live_stripe_subscription(UID) is False


def test_a_live_stripe_subscription_past_the_first_page_is_found(env):
    # 101 records: a page of 100 marketplace subscriptions, then the user's own.
    marketplace = [{'status': 'active', 'metadata': {'app_id': f'app_{i}'}} for i in range(100)]
    _stripe_list(env, marketplace + [{'status': 'active', 'metadata': {'uid': UID}}])
    assert play_billing._live_stripe_subscription(UID) is True


# ---- A. an existing overlap is logged and recorded, never cancelled -------------------------


class NoCancelPublisher:
    def __init__(self, base):
        self.base = base

    def get_subscription(self, package_name, token):
        return self.base.get_subscription(package_name, token)

    def acknowledge(self, package_name, product_id, token):
        return self.base.acknowledge(package_name, product_id, token)

    def cancel(self, package_name, token):
        pytest.fail('Google is never cancelled automatically')


def _dispatched():
    return NotificationDispatchOutcome(status=NotificationDispatchStatus.DISPATCHED)


@pytest.fixture
def conflict(subscribed, monkeypatch):
    """Play on hold, the user then bought Stripe on the web, then Google recovers the Play payment."""
    subscribed.publisher.resources[TOKEN] = resource(ON_HOLD)
    assert _notify(5) == 'revoked'
    subscribed.users.rows[UID] = _stripe_row()
    _stripe_list(subscribed, [{'id': 'sub_card', 'status': 'active', 'metadata': {'uid': UID}}])
    subscribed.users.writes.clear()
    recovered = resource(expiry=NOW + 30 * DAY, acknowledgementState='ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED')
    subscribed.publisher.resources[TOKEN] = recovered
    monkeypatch.setattr(play_billing, '_publisher', NoCancelPublisher(subscribed.publisher))
    state = SimpleNamespace(env=subscribed, notices=[], outcomes=[])

    def dispatch(intent):
        state.notices.append(intent)
        outcome = state.outcomes.pop(0) if state.outcomes else _dispatched()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(play_billing, 'dispatch_notification', dispatch)
    for name in ('cancel', 'modify', 'delete'):
        monkeypatch.setattr(
            play_billing.stripe.Subscription, name, lambda *a, **k: pytest.fail('Stripe is never touched')
        )
    return state


def _double_charge_lines(caplog):
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith('play_billing_double_charge ')]


def test_play_recovery_next_to_stripe_keeps_both_and_records_it_once(conflict, caplog, monkeypatch):
    key = play_db.token_key(TOKEN)
    assert _notify(1) == 'stripe_conflict'  # SUBSCRIPTION_RECOVERED
    first_seen = conflict.env.store.docs[key][play_billing.CONFLICT_FIELD]
    assert _row(conflict.env).stripe_subscription_id == 'sub_card' and conflict.env.users.writes == []
    assert _double_charge_lines(caplog) == [
        f'play_billing_double_charge uid={UID} purchase={key[:12]} state=SUBSCRIPTION_STATE_ACTIVE'
    ]
    assert TOKEN not in caplog.text
    assert [n.source for n in conflict.notices] == ['play_billing_double_billing']

    # Every later observation logs again (an alert watches the line); the stamp and the notice stay single.
    monkeypatch.setattr(play_billing.time, 'time', lambda: NOW + 3600)
    assert _notify(2) == 'stripe_conflict'
    assert play_billing.reconcile_due() in ({}, {'stripe_conflict': 1})
    assert len(_double_charge_lines(caplog)) >= 2
    assert conflict.env.store.docs[key][play_billing.CONFLICT_FIELD] == first_seen
    assert len(conflict.notices) == 1
    assert _row(conflict.env).stripe_subscription_id == 'sub_card'


@pytest.mark.parametrize('failure', [RuntimeError('fcm down'), 'failed'])
def test_a_failed_notice_is_sent_on_the_next_observation(conflict, failure):
    if failure == 'failed':
        failure = NotificationDispatchOutcome(status=NotificationDispatchStatus.FAILED)
    conflict.outcomes.append(failure)
    key = play_db.token_key(TOKEN)
    assert _notify(1) == 'stripe_conflict'
    assert conflict.env.store.docs[key][play_billing.CONFLICT_FIELD]
    assert not conflict.env.store.docs[key].get(play_billing.CONFLICT_NOTIFIED_FIELD)
    assert _notify(2) == 'stripe_conflict'
    assert conflict.env.store.docs[key][play_billing.CONFLICT_NOTIFIED_FIELD]
    assert _notify(2) == 'stripe_conflict'
    assert len(conflict.notices) == 2


def test_a_stale_play_snapshot_never_clears_the_conflict_stamp(conflict):
    key = play_db.token_key(TOKEN)
    _notify(1)
    stamp = conflict.env.store.docs[key][play_billing.CONFLICT_FIELD]
    snapshot = play_billing.read_state(conflict.env.publisher.resources[TOKEN])
    conflict.env.store.update_purchase(key, play_billing._record(snapshot, TOKEN, NOW))
    assert conflict.env.store.docs[key][play_billing.CONFLICT_FIELD] == stamp


@pytest.mark.parametrize('kind', ['one_time_org', 'stale_canceled_stripe', 'incomplete_stripe'])
def test_no_double_charge_is_reported_without_a_paid_recurring_stripe_subscription(
    subscribed, caplog, monkeypatch, kind
):
    if kind == 'one_time_org':
        subscribed.users.rows[UID] = Subscription(
            plan=PlanType.unlimited_v2, current_period_end=NOW + DAY, stripe_subscription_id='pi_org_payment'
        ).model_dump()
    elif kind == 'stale_canceled_stripe':
        subscribed.users.rows[UID] = _stripe_row()
        _stripe_list(subscribed, [{'id': 'sub_card', 'status': 'canceled', 'metadata': {'uid': UID}}])
    else:
        _stripe_list(subscribed, [{'id': 'sub_new', 'status': 'incomplete', 'metadata': {'uid': UID}}])
    subscribed.publisher.resources[TOKEN]['acknowledgementState'] = 'ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED'
    monkeypatch.setattr(play_billing, '_publisher', NoCancelPublisher(subscribed.publisher))
    monkeypatch.setattr(play_billing, 'dispatch_notification', lambda intent: pytest.fail('no notice'))
    assert _notify(2) == 'stripe_conflict'  # still never granted over the other row
    assert _double_charge_lines(caplog) == []
    assert play_billing.CONFLICT_FIELD not in subscribed.store.docs[play_db.token_key(TOKEN)]


# ---- 3. Play builds never start a new Stripe charge ----------------------------------------

PLAY = {
    'ANDROID_BILLING': 'play',
    'ANDROID_PLAY_BILLING_MIN_BUILD': '1624',
    'PLAY_ACCOUNT_ID_HMAC_KEY': TEST_ACCOUNT_KEY,
}
PROD_OFF = {
    'ANDROID_BILLING': 'stripe',
    'ANDROID_PLAY_BILLING_MIN_BUILD': '1617',
    'PLAY_ACCOUNT_ID_HMAC_KEY': TEST_ACCOUNT_KEY,
}
ANDROID_PLAY = {'X-App-Platform': 'android', 'X-App-Build': '1624'}
REFUSED = {'detail': 'Subscribe with Google Play in the app.', 'code': 'use_google_play'}


class _Offer:
    def __init__(self):
        self.eligible = False
        self.reason = 'no_subscription'


@pytest.fixture
def routes(monkeypatch):
    """Payment routes over fakes: each reaches its own first answer without Stripe or Firestore."""
    from routers import monthly_switch, payment, retention_offer, yearly_switch

    for name in list(os.environ):
        if name.startswith(('ANDROID_', 'PLAY_')):
            monkeypatch.delenv(name)
    monkeypatch.setattr(config.rollout_cohorts, 'in_rollout_cohort', lambda uid, name: False)  # empty cohort
    basic = Subscription()
    stripe_row = Subscription.model_validate(_stripe_row())
    state = SimpleNamespace(reactivate=None, created=[])
    monkeypatch.setattr(payment, '_validate_price_id', lambda price: None)
    monkeypatch.setattr(payment, 'management_binding', lambda price: None)
    monkeypatch.setattr(payment.subscription_utils, 'can_user_make_payment', lambda uid, price: (True, 'ok'))
    monkeypatch.setattr(payment, '_try_reactivate_subscription', lambda uid, price: state.reactivate)
    monkeypatch.setattr(payment.subscription_utils, 'new_buyer_single_plan_violation', lambda uid, price: None)
    monkeypatch.setattr(payment.users_db, 'get_stripe_customer_id', lambda uid: 'cus_1')
    monkeypatch.setattr(payment.play_subscriptions_db, 'is_play_customer', lambda uid: False)

    def create_session(uid, price, key, **options):
        state.created.append(price)
        return SimpleNamespace(url='https://checkout.stripe.com/c/pay/cs_1', id='cs_1')

    monkeypatch.setattr(payment.stripe_utils, 'create_subscription_checkout_session', create_session)
    monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid, **k: stripe_row)
    pending_cancel = {'cancel_at_period_end': True, 'current_period_end': NOW + DAY, 'metadata': {}}
    monkeypatch.setattr(
        payment.stripe.Subscription, 'retrieve', lambda sid, **k: SimpleNamespace(to_dict=lambda: pending_cancel)
    )
    monkeypatch.setattr(monthly_switch.users_db, 'get_user_subscription', lambda uid: basic)
    monkeypatch.setattr(yearly_switch.users_db, 'get_user_subscription', lambda uid: basic)
    monkeypatch.setattr(yearly_switch.yearly_switch, 'get_offer', lambda sub_id, preview=False: _Offer())
    monkeypatch.setattr(retention_offer.users_db, 'get_user_subscription', lambda uid: basic)
    monkeypatch.setattr(
        payment.stripe.billing_portal.Session,
        'create',
        lambda **k: SimpleNamespace(url='https://billing.stripe.com/p/session/1'),
    )
    monkeypatch.setattr(payment.prepaid_code_config, 'mode', lambda: 'off')
    app = FastAPI()
    for module in (payment, monthly_switch, yearly_switch, retention_offer):
        app.include_router(module.router)
    for module in (payment, monthly_switch, yearly_switch, retention_offer):
        app.dependency_overrides[module.auth.get_current_user_uid] = lambda: UID
    state.client = TestClient(app)
    state.monkeypatch = monkeypatch
    return state


def _env(routes, values):
    for key, value in values.items():
        routes.monkeypatch.setenv(key, value)


CHARGE_CALLS = [
    ('post', '/v1/payments/checkout-session', {'price_id': 'price_pro'}),
    ('post', '/v1/payments/upgrade-subscription', {'price_id': 'price_pro_year', 'switch_now': True}),
    ('post', '/v1/payments/payment-issue/monthly-switch', {'price_id': 'price_pro', 'expected_amount': 2999}),
]


def _call(routes, method, path, body=None, headers=None):
    return routes.client.request(method.upper(), path, json=body, headers=headers or {})


@pytest.mark.parametrize('method,path,body', CHARGE_CALLS)
def test_a_play_build_cannot_start_a_new_stripe_charge(routes, method, path, body):
    _env(routes, PLAY)
    response = _call(routes, method, path, body, ANDROID_PLAY)
    assert response.status_code == 409 and response.json() == REFUSED
    assert routes.created == []


def test_a_play_build_sees_no_yearly_switch_offer(routes):
    _env(routes, PLAY)
    response = _call(routes, 'get', '/v1/payments/yearly-switch', headers=ANDROID_PLAY)
    assert response.json()['eligible'] is False and response.json()['reason'] == 'use_google_play'


@pytest.mark.parametrize(
    'headers',
    [
        {'X-App-Platform': 'ios', 'X-App-Build': '1624'},
        {'X-App-Platform': 'web'},
        {'X-App-Platform': 'macos', 'X-App-Build': '9999'},
        {'X-App-Platform': 'windows', 'X-App-Build': '9999'},
        {'X-App-Platform': 'android', 'X-App-Build': '1623'},
        {'X-App-Platform': 'android'},
        {},
    ],
)
def test_other_clients_still_reach_stripe_checkout(routes, headers):
    _env(routes, PLAY)
    response = _call(routes, 'post', '/v1/payments/checkout-session', {'price_id': 'price_pro'}, headers)
    assert response.status_code == 200 and response.json()['session_id'] == 'cs_1'
    for method, path, body in CHARGE_CALLS[1:]:
        assert _call(routes, method, path, body, headers).json() != REFUSED


def test_a_play_build_keeps_stripe_management(routes):
    _env(routes, PLAY)
    # Resubscribe of a cancel-pending subscription at the same price.
    routes.reactivate = {'status': 'reactivated', 'message': 'Back on.', 'next_billing_date': NOW + DAY}
    response = _call(routes, 'post', '/v1/payments/checkout-session', {'price_id': 'price_pro'}, ANDROID_PLAY)
    assert response.status_code == 200 and response.json()['status'] == 'reactivated'
    # Customer portal.
    portal = _call(routes, 'post', '/v1/payments/customer-portal', headers=ANDROID_PLAY)
    assert portal.status_code == 200 and portal.json()['url'].startswith('https://billing.stripe.com/')
    # Cancel and the stay offer answer from their own logic, not the Play refusal.
    from routers import payment

    routes.monkeypatch.setattr(payment.users_db, 'get_user_subscription', lambda uid, **k: Subscription())
    cancel = _call(routes, 'delete', '/v1/payments/subscription', headers=ANDROID_PLAY)
    assert cancel.status_code == 400 and cancel.json() != REFUSED
    stay = _call(routes, 'post', '/v1/payments/retention-offer', headers=ANDROID_PLAY)
    assert stay.status_code == 400 and stay.json() != REFUSED


# ---- C. a buyer with no Play history gets today's checkout, with no new dependency ----------

# Pinned from origin/main (670cfef604) running this exact harness: the response every no-history buyer gets.
BASE_CHECKOUT = (200, 'application/json', b'{"url":"https://checkout.stripe.com/c/pay/cs_1","session_id":"cs_1"}')
NO_HISTORY_CLIENTS = [
    {'X-App-Platform': 'ios', 'X-App-Build': '1624'},
    {'X-App-Platform': 'web'},
    {'X-App-Platform': 'macos', 'X-App-Build': '9999'},
    {'X-App-Platform': 'windows', 'X-App-Build': '9999'},
    {'X-App-Platform': 'android', 'X-App-Build': '1616', 'X-App-Version': '1.0.573'},
    {'X-App-Platform': 'android', 'X-App-Build': '1624'},  # qualifies for the Play build gate, switch off
]


@pytest.fixture
def real_checkout(routes, monkeypatch):
    """The checkout route through the REAL can_user_make_payment for a Free reader with no Play history."""
    from routers import payment
    from utils import subscription as sub

    monkeypatch.setattr(payment.subscription_utils, 'can_user_make_payment', REAL_CAN_PAY)
    monkeypatch.setattr(sub.users_db, 'get_user_valid_subscription', lambda *a, **k: Subscription())
    monkeypatch.setattr(sub, '_has_active_stripe_subscription', lambda uid: False)
    monkeypatch.setattr(sub, 'find_active_paid_subscription_for_user', lambda uid: None)
    monkeypatch.setattr(sub, 'configured_ladder_prices', lambda: set())
    reads = []
    monkeypatch.setattr(sub.play_subscriptions_db, 'get_user_fields', lambda uid: reads.append(uid) or {})
    routes.reads = reads
    routes.client = TestClient(routes.client.app, raise_server_exceptions=False)
    return routes


def _response(response):
    return response.status_code, response.headers.get('content-type'), response.content


@pytest.mark.parametrize('headers', NO_HISTORY_CLIENTS)
def test_no_history_checkout_matches_main(real_checkout, headers):
    _env(real_checkout, PROD_OFF)
    response = _call(real_checkout, 'post', '/v1/payments/checkout-session', {'price_id': 'price_pro'}, headers)
    assert _response(response) == BASE_CHECKOUT
    assert real_checkout.reads == [UID]  # the one Play-fields read main already made


def _boom(*args, **kwargs):
    raise RuntimeError('added dependency down')


@pytest.mark.parametrize('headers', NO_HISTORY_CLIENTS)
def test_no_history_checkout_survives_every_added_dependency_failing(real_checkout, monkeypatch, headers):
    _env(real_checkout, PROD_OFF)
    monkeypatch.setattr(play_db, 'purchases_for_uid', _boom)
    monkeypatch.setattr(play_db, 'get_purchase', _boom)
    monkeypatch.setattr(play_publisher, 'default_publisher', _boom)
    monkeypatch.setattr(play_publisher, 'recoverable_play_purchase', _boom)
    monkeypatch.setattr(config.rollout_cohorts, 'in_rollout_cohort', _boom)
    monkeypatch.setattr(config.rollout_cohorts, 'cohort_admits', _boom)
    response = _call(real_checkout, 'post', '/v1/payments/checkout-session', {'price_id': 'price_pro'}, headers)
    assert _response(response) == BASE_CHECKOUT


def test_a_play_history_buyer_is_checked_against_google(real_checkout, monkeypatch):
    from utils import subscription as sub

    _env(real_checkout, PROD_OFF)
    monkeypatch.setattr(sub.play_subscriptions_db, 'get_user_fields', lambda uid: {play_db.BOUND_FIELD: True})
    monkeypatch.setattr(play_publisher, 'recoverable_play_purchase', lambda uid: ON_HOLD)
    response = _call(
        real_checkout, 'post', '/v1/payments/checkout-session', {'price_id': 'price_pro'}, {'X-App-Platform': 'ios'}
    )
    assert response.status_code == 400 and response.json()['code'] == 'play_subscription_on_hold'
    monkeypatch.setattr(play_publisher, 'recoverable_play_purchase', lambda uid: None)  # ended at Google
    response = _call(
        real_checkout, 'post', '/v1/payments/checkout-session', {'price_id': 'price_pro'}, {'X-App-Platform': 'ios'}
    )
    assert _response(response) == BASE_CHECKOUT


def test_a_failing_cohort_lookup_never_fails_a_qualifying_android_checkout(real_checkout, monkeypatch):
    _env(real_checkout, PROD_OFF)
    monkeypatch.setattr(config.rollout_cohorts, 'valid_uid', _boom)
    response = _call(real_checkout, 'post', '/v1/payments/checkout-session', {'price_id': 'price_pro'}, ANDROID_PLAY)
    assert _response(response) == BASE_CHECKOUT


# ---- E. Marketplace: no Stripe payment link for a Play build ---------------------------------


@pytest.fixture
def app_detail(monkeypatch):
    from models.app import App
    from routers import apps

    for name in list(os.environ):
        if name.startswith(('ANDROID_', 'PLAY_')):
            monkeypatch.delenv(name)
    monkeypatch.setattr(config.rollout_cohorts, 'in_rollout_cohort', lambda uid, name: False)
    stored = {'id': 'paid-app', 'uid': 'dev', 'name': 'Paid', 'approved': True, 'private': False}
    monkeypatch.setattr(apps, 'get_available_app_by_id_with_reviews', lambda app_id, uid: dict(stored))
    monkeypatch.setattr(
        apps,
        '_safe_app_from_dict',
        lambda data: App.model_construct(
            **data, payment_link='https://buy.stripe.com/x', is_paid=True, thumbnails=[], is_user_paid=False
        ),
    )
    monkeypatch.setattr(apps, 'get_is_user_paid_app', lambda app_id, uid: False)
    monkeypatch.setattr(apps, 'authorize_app_setup', lambda app, uid: {'payment_link': app.payment_link})
    return lambda headers=None: apps.get_app_details(
        'paid-app', uid=UID, http_request=SimpleNamespace(headers=headers or {})
    )


def test_a_play_build_gets_no_marketplace_payment_link(app_detail, monkeypatch):
    for key, value in PLAY.items():
        monkeypatch.setenv(key, value)
    assert app_detail(ANDROID_PLAY)['payment_link'] is None


@pytest.mark.parametrize(
    'headers',
    [
        {'X-App-Platform': 'ios', 'X-App-Build': '1624'},
        {'X-App-Platform': 'android', 'X-App-Build': '1623'},
        {'X-App-Platform': 'macos'},
        {},
    ],
)
def test_other_clients_keep_the_marketplace_payment_link(app_detail, monkeypatch, headers):
    for key, value in PLAY.items():
        monkeypatch.setenv(key, value)
    assert app_detail(headers)['payment_link'] == f'https://buy.stripe.com/x?client_reference_id=uid_{UID}'


def test_switch_off_keeps_the_marketplace_payment_link(app_detail, monkeypatch):
    for key, value in PROD_OFF.items():
        monkeypatch.setenv(key, value)
    assert app_detail(ANDROID_PLAY)['payment_link'] == f'https://buy.stripe.com/x?client_reference_id=uid_{UID}'


# ---- 4. a malformed build header routes to Stripe ------------------------------------------


@pytest.mark.parametrize('build', ['¹⁶²⁴', '١٦٢٤', '1624²', ' ', '1_624', '+1624'])
def test_malformed_build_routes_to_stripe_without_an_error(build):
    assert config.client_uses_play('android', build, UID, environ=PLAY) is False


def test_malformed_minimum_admits_nobody():
    for minimum in ('¹⁶²⁴', '0', '', 'abc'):
        assert (
            config.client_uses_play('android', '9999', UID, environ={**PLAY, 'ANDROID_PLAY_BILLING_MIN_BUILD': minimum})
            is False
        )
    assert config.client_uses_play('android', ' 1624 ', UID, environ=PLAY) is True


def test_malformed_build_header_on_checkout_is_not_a_500(routes):
    _env(routes, PLAY)
    response = _call(
        routes,
        'post',
        '/v1/payments/checkout-session',
        {'price_id': 'price_pro'},
        {'X-App-Platform': 'android', 'X-App-Build': b'\xb9\xb2\xb3'},  # latin-1 superscripts: isdigit, not int
    )
    assert response.status_code == 200


@pytest.mark.parametrize('build', ['9' * 10, '9' * 5000])
def test_an_oversized_build_header_routes_to_stripe(build):
    assert config.client_uses_play('android', build, UID, environ=PLAY) is False


def test_an_oversized_minimum_admits_nobody():
    environ = {**PLAY, 'ANDROID_PLAY_BILLING_MIN_BUILD': '9' * 5000}
    assert config.min_play_build(environ) is None
    assert config.client_uses_play('android', '1624', UID, environ=environ) is False


def test_an_oversized_build_header_on_checkout_is_not_a_500(routes):
    _env(routes, PLAY)
    routes.client = TestClient(routes.client.app, raise_server_exceptions=False)
    response = _call(
        routes,
        'post',
        '/v1/payments/checkout-session',
        {'price_id': 'price_pro'},
        {'X-App-Platform': 'android', 'X-App-Build': '9' * 5000},
    )
    assert response.status_code == 200


from utils.subscription import can_user_make_payment as REAL_CAN_PAY  # noqa: E402
