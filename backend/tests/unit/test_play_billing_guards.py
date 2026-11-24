"""Play Billing money guards: one billing agreement per user while the other can still recover, an
existing Stripe + Play conflict converges on Stripe, Play builds never start a new Stripe charge, and a
malformed build header routes to Stripe. With the switch off every response is byte-identical."""

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
from utils import play_billing  # noqa: E402

ON_HOLD = 'SUBSCRIPTION_STATE_ON_HOLD'


@pytest.fixture(scope='module', autouse=True)
def _warm_imports():
    import routers.monthly_switch  # noqa: F401
    import routers.payment  # noqa: F401
    import routers.retention_offer  # noqa: F401
    import routers.yearly_switch  # noqa: F401
    import utils.prepaid_code_redemption  # noqa: F401


@pytest.fixture
def real_play_reads(env, monkeypatch):
    """The real play_subscriptions readers over the fake store."""
    monkeypatch.setattr(play_db, 'get_user_fields', env.store.get_user_fields)
    monkeypatch.setattr(play_db, 'get_purchase', env.store.get_purchase)
    return env


def _stripe_row(sub_id='sub_card'):
    return Subscription(
        plan=PlanType.unlimited_v2, current_period_end=NOW + 20 * DAY, stripe_subscription_id=sub_id
    ).model_dump()


# ---- 1. no second agreement while Play can still recover ----------------------------------


@pytest.mark.parametrize('state', [ON_HOLD, 'SUBSCRIPTION_STATE_PAUSED'])
def test_stripe_checkout_is_refused_while_play_is_on_hold(subscribed, real_play_reads, monkeypatch, state):
    from routers import payment
    from utils import subscription as subscription_utils

    subscribed.publisher.resources[TOKEN] = resource(state)
    assert _notify(5) == 'revoked'
    assert _row(subscribed).plan == PlanType.basic  # access gone, pointer and token kept
    monkeypatch.setattr(subscription_utils.users_db, 'get_user_valid_subscription', lambda *a, **k: _row(subscribed))
    allowed, reason = subscription_utils.can_user_make_payment(UID, 'price_any')
    assert allowed is False and reason == 'You have a Google Play subscription on hold. Fix the payment in Google Play.'

    monkeypatch.setattr(payment, '_validate_price_id', lambda price: None)
    monkeypatch.setattr(payment, 'management_binding', lambda price: None)
    app = FastAPI()
    app.include_router(payment.router)
    app.dependency_overrides[payment.auth.get_current_user_uid] = lambda: UID
    response = TestClient(app).post('/v1/payments/checkout-session', json={'price_id': 'price_any'})
    assert response.status_code == 400
    # Old clients read ``detail`` as a string and show it.
    assert response.json() == {'detail': reason, 'code': 'play_subscription_on_hold'}


def test_prepaid_redemption_is_refused_while_play_is_on_hold(subscribed, real_play_reads, monkeypatch):
    from utils import prepaid_code_redemption as redemption

    subscribed.publisher.resources[TOKEN] = resource(ON_HOLD)
    _notify(5)
    monkeypatch.setattr(redemption.users_db, 'get_existing_user_subscription', lambda uid: _row(subscribed))
    monkeypatch.setattr(redemption, '_open_stripe_subscriptions', lambda *a: pytest.fail('Play hold decides first'))
    assert redemption._has_live_plan(UID, NOW) is True


def test_an_expired_play_purchase_does_not_block_stripe(subscribed, real_play_reads):
    subscribed.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_EXPIRED', expiry=NOW - DAY)
    _notify(13)
    assert play_db.chargeable_play_state(UID) is None


def _stripe_list(env, subs):
    env.users.customers[UID] = 'cus_1'
    env.stripe_subs.extend(subs)


@pytest.mark.parametrize('status', ['unpaid', 'incomplete', 'paused', 'past_due', 'trialing', 'active'])
def test_every_non_terminal_stripe_state_counts_as_live(env, status):
    _stripe_list(env, [{'status': status, 'metadata': {'uid': UID}}])
    assert play_billing._live_stripe_subscription(UID) is True


@pytest.mark.parametrize('status', ['canceled', 'incomplete_expired'])
def test_ended_stripe_subscriptions_do_not_count(env, status):
    _stripe_list(env, [{'status': status, 'metadata': {'uid': UID}}])
    assert play_billing._live_stripe_subscription(UID) is False


def test_a_live_stripe_subscription_past_the_first_page_is_found(env):
    marketplace = [{'status': 'active', 'metadata': {'app_id': f'app_{i}'}} for i in range(10)]
    _stripe_list(env, marketplace + [{'status': 'active', 'metadata': {'uid': UID}}])
    assert play_billing._live_stripe_subscription(UID) is True


# ---- 2. an existing conflict converges on Stripe -------------------------------------------


class CancellingPublisher:
    def __init__(self, base, fail=None):
        self.base = base
        self.cancelled = []
        self.fail = fail

    def get_subscription(self, package_name, token):
        return self.base.get_subscription(package_name, token)

    def acknowledge(self, package_name, product_id, token):
        return self.base.acknowledge(package_name, product_id, token)

    def cancel(self, package_name, token):
        if self.fail:
            raise self.fail
        self.cancelled.append((package_name, token))
        acked = self.base.resources[token]['acknowledgementState']
        self.base.resources[token] = resource('SUBSCRIPTION_STATE_CANCELED', renew=False, acknowledgementState=acked)


@pytest.fixture
def conflict(subscribed, monkeypatch):
    """Play on hold, the user then bought Stripe on the web, then Google recovers the Play payment."""
    subscribed.publisher.resources[TOKEN] = resource(ON_HOLD)
    assert _notify(5) == 'revoked'
    subscribed.users.rows[UID] = _stripe_row()
    subscribed.users.writes.clear()
    recovered = resource(expiry=NOW + 30 * DAY, acknowledgementState='ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED')
    subscribed.publisher.resources[TOKEN] = recovered
    publisher = CancellingPublisher(subscribed.publisher)
    monkeypatch.setattr(play_billing, '_publisher', publisher)
    notices = []
    monkeypatch.setattr(play_billing, 'dispatch_notification', lambda intent: notices.append(intent))
    for name in ('cancel', 'modify', 'delete'):
        monkeypatch.setattr(
            play_billing.stripe.Subscription, name, lambda *a, **k: pytest.fail('Stripe is never touched')
        )
    return SimpleNamespace(env=subscribed, publisher=publisher, notices=notices)


def test_play_recovery_next_to_stripe_cancels_play_once_and_keeps_stripe(conflict, caplog):
    assert _notify(1) == 'stripe_conflict'  # SUBSCRIPTION_RECOVERED
    assert conflict.publisher.cancelled == [('com.friend.ios', TOKEN)]
    doc = conflict.env.store.docs[play_db.token_key(TOKEN)]
    assert doc[play_billing.CONFLICT_FIELD] and doc['auto_renewing'] is False
    assert _row(conflict.env).stripe_subscription_id == 'sub_card' and conflict.env.users.writes == []
    lines = [r.getMessage() for r in caplog.records if 'play_billing_double_charge' in r.getMessage()]
    assert lines == [
        f'play_billing_double_charge uid={UID} purchase={play_db.token_key(TOKEN)[:12]} '
        'state=SUBSCRIPTION_STATE_ACTIVE auto_renewing=True action=cancel_play'
    ]
    assert TOKEN not in caplog.text
    assert [n.source for n in conflict.notices] == ['play_billing_double_billing']

    # The cancel's own notification and later reconciles converge: no second cancel, log or notice.
    assert _notify(3) == 'stripe_conflict'
    assert play_billing.reconcile_due() in ({}, {'stripe_conflict': 1})
    assert len(conflict.publisher.cancelled) == 1 and len(conflict.notices) == 1
    assert sum('play_billing_double_charge' in r.getMessage() for r in caplog.records) == 1
    assert _row(conflict.env).stripe_subscription_id == 'sub_card'


def test_a_failed_conflict_cancel_is_recorded_and_retried(conflict):
    conflict.publisher.fail = RuntimeError('timeout')
    with pytest.raises(play_billing.PlayBillingError) as error:
        _notify(1)
    assert error.value.http_status == 503  # Pub/Sub redelivers
    assert conflict.env.store.docs[play_db.token_key(TOKEN)][play_billing.CONFLICT_FIELD]
    conflict.publisher.fail = None
    assert _notify(1) == 'stripe_conflict'
    assert len(conflict.publisher.cancelled) == 1


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


ALL_CALLS = CHARGE_CALLS + [
    ('get', '/v1/payments/yearly-switch', None),
    ('post', '/v1/payments/customer-portal', None),
]


@pytest.mark.parametrize('build', ['1617', '1624', '9999'])
def test_switch_off_responses_are_byte_identical(routes, build):
    from routers import monthly_switch, payment

    headers = {'X-App-Platform': 'android', 'X-App-Build': build}
    _env(routes, PROD_OFF)
    today = [_call(routes, m, p, b, headers).content for m, p, b in ALL_CALLS]
    # Today's code: the guard does not exist.
    routes.monkeypatch.setattr(payment, 'play_client_refusal', lambda request, uid: None)
    routes.monkeypatch.setattr(monthly_switch, 'play_client_refusal', lambda request, uid: None)
    routes.monkeypatch.setattr(config, 'client_uses_play', lambda *a, **k: False)
    before = [_call(routes, m, p, b, headers).content for m, p, b in ALL_CALLS]
    assert today == before


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
