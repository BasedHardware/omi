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
    for name in ('get_user_fields', 'get_purchase', 'purchase_keys_for_uid', 'update_purchase'):
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
    # Admission never writes: the stored state stays for notifications and reconcile to update.
    assert subscribed.store.docs[play_db.token_key(TOKEN)]['state'] == ON_HOLD


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
    monkeypatch.setattr(
        redemption.users_db,
        'get_existing_user_subscription_and_fields',
        lambda uid, fields: (_row(subscribed), {name: subscribed.store.users[UID].get(name) for name in fields}),
    )
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


def _dispatched(delivered=1):
    return NotificationDispatchOutcome(status=NotificationDispatchStatus.DISPATCHED, delivered=delivered)


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
    monkeypatch.setattr(play_db, 'purchase_keys_for_uid', _boom)
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


# ---- Round 2: history marker, no admission writes, typed failures, atomic stamps, all link routes ----

import ast  # noqa: E402
import json  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from pathlib import Path  # noqa: E402

from google.api_core.exceptions import FailedPrecondition  # noqa: E402

_BASE = json.loads((Path(__file__).parent / 'fixtures' / 'play_guards_base_functions.json').read_text())


def _base_function(key, namespace):
    """Main's exact function source (pinned fixture), executed against the current module's globals."""
    node = ast.parse(_BASE['functions'][key]).body[0]
    node.decorator_list = [d for d in node.decorator_list if not isinstance(d, ast.Call)]
    scope = dict(namespace)
    exec(compile(ast.Module(body=[node], type_ignores=[]), key, 'exec'), scope)
    return scope[node.name]


def test_the_pinned_base_functions_match_main():
    commit = _BASE['commit']
    if subprocess.run(['git', 'cat-file', '-e', commit], capture_output=True).returncode:
        pytest.skip('base commit not in this checkout')
    for key, source in _BASE['functions'].items():
        path, name = key.split('::')
        text = subprocess.check_output(['git', 'show', f'{commit}:{path}'], text=True)
        assert source in text, key


# 1. history marker before the bind, repaired on retries, backfill.


def test_a_failed_marker_write_never_leaves_a_bound_purchase_unprotected(env, real_play_reads, monkeypatch):
    env.store.remember_account(play_billing.obfuscated_account_id(UID), UID)
    env.publisher.resources[TOKEN] = resource(ON_HOLD)
    original = env.store.set_user_fields
    monkeypatch.setattr(env.store, 'set_user_fields', lambda *a: (_ for _ in ()).throw(RuntimeError('user write')))
    with pytest.raises(RuntimeError):
        _notify(5)
    # Marker first: the failed write left no bound purchase behind, so nothing is hidden from checkout.
    assert 'uid' not in env.store.docs.get(play_db.token_key(TOKEN), {})
    monkeypatch.setattr(env.store, 'set_user_fields', original)
    _notify(5)  # Pub/Sub retry
    assert env.store.docs[play_db.token_key(TOKEN)]['uid'] == UID
    assert env.store.users[UID][play_db.BOUND_FIELD] is True
    assert _admission(env, monkeypatch)() == (False, HOLD_REASON)


@pytest.mark.parametrize('path', ['rtdn', 'verify', 'reconcile'])
def test_a_missing_marker_is_repaired_on_every_retry_path(subscribed, real_play_reads, monkeypatch, path):
    subscribed.publisher.resources[TOKEN] = resource(ON_HOLD)
    _notify(5)
    subscribed.store.users[UID] = {}  # a purchase bound before the marker existed
    key = play_db.token_key(TOKEN)
    subscribed.store.docs[key]['next_check_at'] = NOW - 1
    if path == 'rtdn':
        _notify(5)
    elif path == 'verify':
        play_billing.verify_and_bind(UID, TOKEN, 'omi_pro')
    else:
        play_billing.reconcile_due()
    assert subscribed.store.users[UID].get(play_db.BOUND_FIELD) is True
    assert _admission(subscribed, monkeypatch)() == (False, HOLD_REASON)


class _Doc:
    def __init__(self, data, exists=True):
        self._data, self.exists = data, exists

    def to_dict(self):
        return dict(self._data)


class _BackfillClient:
    def __init__(self, purchases, users):
        self.purchases, self.users, self.updates = purchases, users, []

    def collection(self, name):
        client = self

        class Collection:
            def select(self, fields):
                return self

            def stream(self):
                return [_Doc(p) for p in client.purchases]

            def document(self, uid):
                class Ref:
                    def get(self, fields=None):
                        return _Doc(client.users.get(uid, {}), exists=uid in client.users)

                    def update(self, data):
                        client.updates.append(uid)
                        client.users[uid].update(data)

                return Ref()

        return Collection()


def test_the_backfill_marks_every_owner_once_and_prints_counts_only(capsys):
    from scripts import backfill_play_purchase_bound as backfill

    client = _BackfillClient(
        [{'uid': 'a'}, {'uid': 'a'}, {'uid': 'b'}, {'uid': 'gone'}, {}],
        {'a': {}, 'b': {play_db.BOUND_FIELD: True}},
    )
    dry = backfill.backfill(client, apply=False)
    assert dry == {'purchases': 5, 'owners': 3, 'already_marked': 1, 'missing_user': 1, 'to_mark': 1, 'marked': 0}
    assert client.updates == []
    assert backfill.backfill(client, apply=True)['marked'] == 1 and client.updates == ['a']
    assert backfill.backfill(client, apply=True)['marked'] == 0  # idempotent


# 2. admission never writes and never trusts a stored terminal state that could be stale.


def test_old_terminal_snapshot_cannot_hide_live_google(env, real_play_reads, monkeypatch):
    key = play_db.token_key(TOKEN)
    env.store.docs[key] = {'uid': UID, 'purchase_token': TOKEN, 'state': ON_HOLD}

    def raced_read(package, token):
        env.store.docs[key]['state'] = 'SUBSCRIPTION_STATE_ACTIVE'  # a newer notification landed meanwhile
        return resource('SUBSCRIPTION_STATE_EXPIRED', expiry=NOW - DAY)

    monkeypatch.setattr(env.publisher, 'get_subscription', raced_read)
    assert play_publisher.recoverable_play_purchase(UID) is None
    assert env.store.docs[key]['state'] == 'SUBSCRIPTION_STATE_ACTIVE'  # never overwritten by admission
    reads = []
    monkeypatch.setattr(env.publisher, 'get_subscription', lambda p, t: reads.append(t) or resource())
    assert play_publisher.recoverable_play_purchase(UID) == 'SUBSCRIPTION_STATE_ACTIVE'
    assert reads == [TOKEN]


@pytest.mark.parametrize(
    'stored',
    [
        {'state': 'SUBSCRIPTION_STATE_EXPIRED', 'expiry_time': NOW + DAY},  # "ended" but its period is not over
        {'state': 'SUBSCRIPTION_STATE_EXPIRED'},  # no expiry on record
        {'state': 'NOT_FOUND'},
        {'state': 'SUBSCRIPTION_STATE_PENDING_PURCHASE_CANCELED'},
    ],
)
def test_a_stored_end_is_trusted_only_when_its_expiry_has_passed(env, real_play_reads, stored):
    key = play_db.token_key(TOKEN)
    env.store.docs[key] = {'uid': UID, 'purchase_token': TOKEN, **stored}
    env.publisher.resources[TOKEN] = resource(ON_HOLD)
    assert play_publisher.recoverable_play_purchase(UID) == ON_HOLD


def test_a_truly_ended_purchase_is_not_read_again(env, real_play_reads, monkeypatch):
    key = play_db.token_key(TOKEN)
    env.store.docs[key] = {
        'uid': UID,
        'purchase_token': TOKEN,
        'state': 'SUBSCRIPTION_STATE_EXPIRED',
        'expiry_time': NOW - DAY,
    }
    monkeypatch.setattr(env.publisher, 'get_subscription', lambda *a: pytest.fail('no read for an ended purchase'))
    assert play_publisher.recoverable_play_purchase(UID) is None


def test_admission_writes_nothing(env, real_play_reads, monkeypatch):
    key = play_db.token_key(TOKEN)
    env.store.docs[key] = {'uid': UID, 'purchase_token': TOKEN, 'state': ON_HOLD}
    for name in ('update_purchase', 'record_unbound', 'set_user_fields', 'bind_purchase'):
        monkeypatch.setattr(play_db, name, lambda *a, **k: pytest.fail('admission must not write'))
    env.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_EXPIRED', expiry=NOW - DAY)
    assert play_publisher.recoverable_play_purchase(UID) is None
    del env.publisher.resources[TOKEN]  # not found at Google
    assert play_publisher.recoverable_play_purchase(UID) is None


# 3. pending is re-read; storage failures are the typed retry; prepaid adds nothing for no-history buyers.


def test_a_stored_pending_purchase_google_ended_does_not_block(env, real_play_reads, monkeypatch):
    key = play_db.token_key(TOKEN)
    env.store.docs[key] = {'uid': UID, 'purchase_token': TOKEN, 'state': 'SUBSCRIPTION_STATE_PENDING'}
    env.store.users[UID] = {play_db.PENDING_FIELD: key, play_db.BOUND_FIELD: True}
    env.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_EXPIRED', expiry=NOW - DAY)
    assert _admission(env, monkeypatch)()[0] is True
    env.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_PENDING')
    assert _admission(env, monkeypatch)() == (
        False,
        'Your Google Play purchase is still being processed. Try again once it completes.',
    )


@pytest.mark.parametrize('failing', ['purchase_keys_for_uid', 'get_purchase'])
def test_a_storage_failure_for_a_play_history_buyer_is_the_typed_retry(real_checkout, monkeypatch, failing):
    from utils import subscription as sub

    _env(real_checkout, PROD_OFF)
    monkeypatch.setattr(sub.play_subscriptions_db, 'get_user_fields', lambda uid: {play_db.BOUND_FIELD: True})
    monkeypatch.setattr(play_db, 'purchase_keys_for_uid', lambda uid: ['k'])
    monkeypatch.setattr(play_db, 'get_purchase', lambda key: {'uid': UID, 'purchase_token': 't', 'state': ON_HOLD})
    monkeypatch.setattr(play_db, failing, _boom)
    response = _call(
        real_checkout, 'post', '/v1/payments/checkout-session', {'price_id': 'price_pro'}, {'X-App-Platform': 'ios'}
    )
    assert response.status_code == 400
    assert response.json() == {'detail': UNAVAILABLE_REASON, 'code': 'play_check_unavailable'}


@pytest.fixture
def prepaid_route(monkeypatch):
    """POST /v1/payments/prepaid-code/redeem over the prepaid suite's fake Stripe and ledger."""
    from routers import redeem_code
    from tests.unit import test_prepaid_code_redemption as prepaid_suite
    from utils import prepaid_code_redemption as redemption

    state = SimpleNamespace(
        stripe=prepaid_suite.FakeStripe([prepaid_suite.promo(prepaid_suite.BUNDLE)]), ledger=prepaid_suite.FakeLedger()
    )
    monkeypatch.setattr(redemption, 'stripe', state.stripe)
    for name in ('claim', 'get', 'release', 'set_subscription'):
        monkeypatch.setattr(redemption.redemptions_db, name, getattr(state.ledger, name))
    monkeypatch.setattr(redemption.users_db, 'get_stripe_customer_id', lambda uid: None)
    monkeypatch.setattr(redemption.users_db, 'set_stripe_customer_id', lambda uid, customer_id: None)
    monkeypatch.setattr(redemption, '_pro_prices', lambda: (prepaid_suite.MONTHLY['id'], prepaid_suite.YEARLY['id']))
    monkeypatch.setattr(redeem_code.prepaid_code_config, 'enabled_for', lambda uid: True)
    monkeypatch.setattr(redeem_code.auth, 'check_rate_limit_inline', lambda key, policy: None)
    monkeypatch.setattr(redemption.time, 'time', lambda: prepaid_suite.NOW)
    reads = []
    # The single user-document read main makes (subscription), and the same read now also returning Play fields.
    monkeypatch.setattr(redemption.users_db, 'get_existing_user_subscription', lambda uid: reads.append('user') or None)
    monkeypatch.setattr(
        redemption.users_db,
        'get_existing_user_subscription_and_fields',
        lambda uid, fields: reads.append('user') or (None, {}),
    )
    app = FastAPI()
    app.include_router(redeem_code.router)
    app.dependency_overrides[redeem_code.auth.get_current_user_uid] = lambda: prepaid_suite.UID
    state.client = TestClient(app, raise_server_exceptions=False)
    state.reads = reads
    state.redemption = redemption
    state.code = 'OMI-TRYBE-ABCD1234'
    return state


def _redeem(route):
    response = route.client.post('/v1/payments/prepaid-code/redeem', json={'code': route.code})
    return response.status_code, dict(response.headers), response.content


def test_prepaid_redemption_for_a_no_history_buyer_matches_main_with_added_reads_failing(prepaid_route, monkeypatch):
    for name in ('get_user_fields', 'purchase_keys_for_uid', 'get_purchase'):
        monkeypatch.setattr(play_db, name, _boom)
    monkeypatch.setattr(play_publisher, 'default_publisher', _boom)
    head = _redeem(prepaid_route)
    head_reads = list(prepaid_route.reads)
    # Main's _has_live_plan on a fresh ledger and Stripe.
    from tests.unit import test_prepaid_code_redemption as prepaid_suite

    monkeypatch.setattr(
        prepaid_route.redemption, 'stripe', prepaid_suite.FakeStripe([prepaid_suite.promo(prepaid_suite.BUNDLE)])
    )
    prepaid_route.ledger.docs.clear()
    prepaid_route.reads.clear()
    base = _base_function('backend/utils/prepaid_code_redemption.py::_has_live_plan', prepaid_route.redemption.__dict__)
    monkeypatch.setattr(prepaid_route.redemption, '_has_live_plan', base)
    assert _redeem(prepaid_route) == head
    assert head[0] == 200
    # The second read is the Play re-check right before the Stripe create (same document, no Google call here).
    assert head_reads == prepaid_route.reads == ['user', 'user']


def test_prepaid_redemption_for_a_play_history_buyer_on_hold_or_unreadable(prepaid_route, monkeypatch):
    monkeypatch.setattr(
        prepaid_route.redemption.users_db,
        'get_existing_user_subscription_and_fields',
        lambda uid, fields: (None, {play_db.BOUND_FIELD: True}),
    )
    monkeypatch.setattr(play_publisher, 'recoverable_play_purchase', lambda uid: ON_HOLD)
    status, _, body = _redeem(prepaid_route)
    assert (status, json.loads(body)['detail']) == (409, 'has_plan')
    monkeypatch.setattr(play_publisher, 'recoverable_play_purchase', _boom_unavailable)
    status, _, body = _redeem(prepaid_route)
    assert (status, json.loads(body)['detail']) == (503, 'try_again')


def _boom_unavailable(*args, **kwargs):
    raise play_publisher.PlayStateUnavailable('test')


# 4. atomic stamp and notice, tested on the real helper with interleaved callers.


class CasFirestore:
    """In-memory Firestore for one collection with update-time preconditions, like the real service."""

    def __init__(self, docs, barrier=None, barrier_on_read=1):
        self.docs, self.versions, self.barrier, self.lock = docs, {}, barrier, threading.Lock()
        self.barrier_on_read = barrier_on_read  # each caller meets the barrier on this read of its own only
        self.local = threading.local()

    def write_option(self, last_update_time):
        return last_update_time

    def collection(self, name):
        store = self

        class Ref:
            def __init__(self, key):
                self.key = key

            def get(self):
                with store.lock:
                    data, version = dict(store.docs.get(self.key, {})), store.versions.get(self.key, 0)
                    exists = self.key in store.docs
                store.local.reads = getattr(store.local, 'reads', 0) + 1
                if store.barrier and store.local.reads == store.barrier_on_read:
                    store.barrier.wait(timeout=3)
                return SimpleNamespace(exists=exists, to_dict=lambda: data, update_time=version)

            def update(self, fields, option=None):
                with store.lock:
                    if option is not None and option != store.versions.get(self.key, 0):
                        raise FailedPrecondition('changed')
                    store.docs[self.key].update(fields)
                    store.versions[self.key] = store.versions.get(self.key, 0) + 1

        return SimpleNamespace(document=Ref)


def test_two_concurrent_stamps_keep_the_first_written_value():
    docs = {'k': {}}
    client = CasFirestore(docs, barrier=threading.Barrier(2))
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(lambda v: play_db.mark_once('k', 'stripe_conflict_at', v, firestore_client=client), [100, 200])
        )
    assert sorted(results) == [False, True]
    assert docs['k']['stripe_conflict_at'] == (100 if results[0] else 200)
    client.barrier = None
    assert play_db.mark_once('k', 'stripe_conflict_at', 300, firestore_client=client) is False
    assert docs['k']['stripe_conflict_at'] in (100, 200)


@pytest.fixture
def real_conflict_store(conflict, monkeypatch):
    """The conflict fixture with the real compare-and-set helpers over an interleaving in-memory Firestore."""
    client = CasFirestore(conflict.env.store.docs)
    for name in ('compare_and_set', 'mark_once'):
        real = getattr(play_db, name)
        monkeypatch.setattr(
            conflict.env.store, name, lambda *a, real=real, **k: real(*a, firestore_client=client, **k), raising=False
        )
    conflict.client = client
    return conflict


def test_two_concurrent_observers_send_one_notice(real_conflict_store, monkeypatch):
    key = play_db.token_key(TOKEN)
    _notify(1)  # first observation
    real_conflict_store.env.store.docs[key].pop(play_billing.CONFLICT_NOTIFIED_FIELD)
    real_conflict_store.env.store.docs[key].pop(play_billing.CONFLICT_NOTICE_CLAIM_FIELD)
    real_conflict_store.notices.clear()
    state = play_billing.read_state(real_conflict_store.env.publisher.resources[TOKEN])
    # Read 1 is the conflict stamp, read 2 the notice claim: both observers read the claim before either writes.
    real_conflict_store.client.barrier = threading.Barrier(2)
    real_conflict_store.client.barrier_on_read = 2
    real_conflict_store.client.local = threading.local()
    monkeypatch.setattr(play_db, 'get_purchase', real_conflict_store.env.store.get_purchase)

    def observe(_):
        play_billing._record_stripe_conflict(UID, key, state)

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(observe, range(2)))
    real_conflict_store.client.barrier = None
    assert len(real_conflict_store.notices) == 1


def test_a_notice_dispatched_to_no_device_is_retried(conflict, monkeypatch):
    from utils.notification_dispatch import NotificationDispatcher

    key = play_db.token_key(TOKEN)
    nobody = NotificationDispatcher(sync_delivery=lambda *a: 0, deletion_blocks=lambda uid: False)
    monkeypatch.setattr(play_billing, 'dispatch_notification', nobody.dispatch)
    assert _notify(1) == 'stripe_conflict'
    assert not conflict.env.store.docs[key].get(play_billing.CONFLICT_NOTIFIED_FIELD)
    assert not conflict.env.store.docs[key].get(play_billing.CONFLICT_NOTICE_CLAIM_FIELD)  # released
    delivered = NotificationDispatcher(sync_delivery=lambda *a: 1, deletion_blocks=lambda uid: False)
    monkeypatch.setattr(play_billing, 'dispatch_notification', delivered.dispatch)
    assert _notify(2) == 'stripe_conflict'
    assert conflict.env.store.docs[key][play_billing.CONFLICT_NOTIFIED_FIELD]


def test_an_abandoned_notice_claim_expires(conflict, monkeypatch):
    key = play_db.token_key(TOKEN)
    conflict.env.store.docs[key][play_billing.CONFLICT_NOTICE_CLAIM_FIELD] = NOW - 3600  # a worker died mid-send
    assert _notify(1) == 'stripe_conflict'
    assert len(conflict.notices) == 1 and conflict.env.store.docs[key][play_billing.CONFLICT_NOTIFIED_FIELD]


# 5. no Stripe payment link in any app response for a Play build; today's bytes for every other client.

PAID_APP = {
    'id': 'paid-app',
    'name': 'Paid',
    'category': 'other',
    'author': 'dev',
    'uid': 'dev',
    'description': '',
    'image': '',
    'capabilities': [],
    'approved': True,
    'private': False,
    'is_paid': True,
    'payment_link': 'https://buy.stripe.com/x',
}
LINK_ROUTES = [
    ('backend/routers/apps.py::get_apps', '/v1/apps'),
    ('backend/routers/apps.py::get_approved_apps', '/v1/approved-apps'),
    ('backend/routers/apps.py::get_popular_apps_endpoint', '/v1/apps/popular'),
    ('backend/routers/apps.py::get_app_details', '/v1/apps/paid-app'),
    ('backend/routers/conversations.py::get_conversation_suggested_apps', '/v1/conversations/c1/suggested-apps'),
]


@pytest.fixture
def link_routes(monkeypatch):
    from models.app import App
    from routers import apps, conversations

    for name in list(os.environ):
        if name.startswith(('ANDROID_', 'PLAY_')):
            monkeypatch.delenv(name)
    monkeypatch.setattr(config.rollout_cohorts, 'in_rollout_cohort', lambda uid, name: False)
    monkeypatch.setattr(apps, 'get_available_apps', lambda uid, include_reviews=True: [App(**PAID_APP)])
    monkeypatch.setattr(apps, 'get_approved_available_apps', lambda include_reviews=False: [App(**PAID_APP)])
    monkeypatch.setattr(apps, 'get_popular_apps', lambda: [App(**PAID_APP)])
    monkeypatch.setattr(apps, 'get_available_app_by_id_with_reviews', lambda app_id, uid: dict(PAID_APP))
    monkeypatch.setattr(apps, 'get_is_user_paid_app', lambda app_id, uid: False)
    monkeypatch.setattr(apps, 'authorize_app_setup', lambda app, uid: app)
    monkeypatch.setattr(conversations, '_get_valid_conversation_by_id', lambda uid, cid: {'id': cid})
    monkeypatch.setattr(
        conversations,
        'deserialize_conversation',
        lambda data: SimpleNamespace(suggested_summarization_apps=['paid-app']),
    )

    def hydrate(app_id, uid):
        app = App(**PAID_APP)
        app.payment_link = f'{app.payment_link}?client_reference_id=uid_{uid}'
        return app

    monkeypatch.setattr(conversations, '_hydrate_suggested_app', hydrate)

    def client(base=False):
        app = FastAPI()
        if base:
            for key, path in LINK_ROUTES:
                module = apps if 'apps.py' in key else conversations
                route = next(
                    r
                    for r in module.router.routes
                    if getattr(r, 'path', None) and r.endpoint.__name__ == key.split('::')[1]
                )
                app.add_api_route(
                    route.path,
                    _base_function(key, module.__dict__),
                    methods=list(route.methods),
                    response_model=route.response_model,
                )
        else:
            app.include_router(apps.router)
            app.include_router(conversations.router)
        for module in (apps, conversations):
            app.dependency_overrides[module.auth.get_current_user_uid] = lambda: UID
        return TestClient(app, raise_server_exceptions=False)

    return SimpleNamespace(client=client, monkeypatch=monkeypatch)


def _links(response):
    body = response.json()
    items = body if isinstance(body, list) else body.get('suggested_apps', [body])
    return [item.get('payment_link') for item in items]


@pytest.mark.parametrize('key,path', LINK_ROUTES)
def test_a_play_build_gets_no_stripe_link_from_any_app_route(link_routes, key, path):
    for name, value in PLAY.items():
        link_routes.monkeypatch.setenv(name, value)
    response = link_routes.client().get(path, headers=ANDROID_PLAY)
    assert response.status_code == 200, response.text
    assert _links(response) == [None]
    assert 'buy.stripe.com' not in response.text


@pytest.mark.parametrize('key,path', LINK_ROUTES)
@pytest.mark.parametrize(
    'headers',
    [
        {'X-App-Platform': 'ios', 'X-App-Build': '1624'},
        {'X-App-Platform': 'android', 'X-App-Build': '1623'},
        {'X-App-Platform': 'macos', 'X-App-Build': '9999'},
        {'X-App-Platform': 'web'},
        {},
    ],
)
def test_every_other_client_gets_mains_bytes_from_every_app_route(link_routes, key, path, headers):
    for name, value in PLAY.items():
        link_routes.monkeypatch.setenv(name, value)
    head = link_routes.client().get(path, headers=headers)
    base = link_routes.client(base=True).get(path, headers=headers)
    assert (head.status_code, dict(head.headers), head.content) == (base.status_code, dict(base.headers), base.content)
    assert head.status_code == 200 and 'buy.stripe.com/x' in head.text


from utils.subscription import can_user_make_payment as REAL_CAN_PAY  # noqa: E402
