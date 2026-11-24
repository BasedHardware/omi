"""No-card code redemption on a Google Play build: open to every Play client whatever the redemption switch,
with every live-plan refusal kept, and byte-identical responses to main for every other client and setting."""

import hashlib
import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from config import play_billing as config  # noqa: E402
from config import prepaid_code_redeem as switch  # noqa: E402
from database import play_subscriptions as play_db  # noqa: E402
from models.users import PlanType, Subscription, SubscriptionStatus  # noqa: E402
from config.prepaid_code_redeem import SUBSCRIPTION_MARKER as prepaid_marker  # noqa: E402
from tests.unit.test_play_billing import (  # noqa: E402,F401
    DAY,
    NOW,
    TEST_ACCOUNT_KEY,
    TOKEN,
    OTHER,
    UID,
    _notify,
    _row,
    env,
    resource,
    subscribed,
)
from tests.unit.test_prepaid_code_redemption import world  # noqa: E402,F401
from utils import play_billing, play_publisher  # noqa: E402
from utils import prepaid_code_redemption as redemption  # noqa: E402

SUBSCRIPTION = '/v1/users/me/subscription'
REDEEM = '/v1/payments/prepaid-code/redeem'
CODE = {'code': 'OMI-TRYBE-ABCD1234'}
REDEEMED = {'status': 'redeemed', 'plan': 'Omi Pro', 'ends_at': 1, 'months': 12}

# Production today: Stripe for every Android build, empty Play cohort, redemption cohort empty.
PROD = {
    'ANDROID_BILLING': 'stripe',
    'ANDROID_PLAY_BILLING_MIN_BUILD': '1617',
    'PLAY_ACCOUNT_ID_HMAC_KEY': TEST_ACCOUNT_KEY,
    switch.ENV: 'cohort',
}
PLAY_ON = {**PROD, 'ANDROID_BILLING': 'play', 'ANDROID_PLAY_BILLING_MIN_BUILD': '1624'}
ANDROID_PLAY = {'X-App-Platform': 'android', 'X-App-Build': '1624'}
CLIENTS = {
    'ios': {'X-App-Platform': 'ios', 'X-App-Build': '1624'},
    'web': {'X-App-Platform': 'web'},
    'macos': {'X-App-Platform': 'macos', 'X-App-Build': '9999'},
    'windows': {'X-App-Platform': 'windows', 'X-App-Build': '9999'},
    'android_old': {'X-App-Platform': 'android', 'X-App-Build': '1616', 'X-App-Version': '1.0.573'},
    'android_low': {'X-App-Platform': 'android', 'X-App-Build': '1623'},
    'android_play_build': ANDROID_PLAY,
    'none': {},
}
NON_PLAY_CLIENTS = [name for name in CLIENTS if name != 'android_play_build']

# sha256 of (status, content-type, body) pinned from origin/main 120dfa4c91 running this exact harness
# with main's routers/users.py and routers/redeem_code.py checked out (see test_pin_main_responses).
BASE_FILE = os.path.join(os.path.dirname(__file__), 'fixtures', 'play_prepaid_code_entry_base.json')
BASE = json.loads(open(BASE_FILE).read()) if os.path.exists(BASE_FILE) else {}


@pytest.fixture
def client(monkeypatch):
    """The real subscription and redeem routes; the code lookup itself is a stub unless a test swaps it."""
    from routers import redeem_code, users

    for name in list(os.environ):
        if name.startswith(('ANDROID_', 'PLAY_')) or name == switch.ENV:
            monkeypatch.delenv(name)
    monkeypatch.setattr(config.rollout_cohorts, 'in_rollout_cohort', lambda uid, name: False)  # empty cohorts
    monkeypatch.setattr(users.users_db, 'is_byok_active', lambda _uid: True)
    monkeypatch.setattr(users, 'request_has_llm_byok_key', lambda: True)
    monkeypatch.setattr(users.users_db, 'get_user_valid_subscription', lambda *a, **k: None)
    monkeypatch.setattr(users.play_subscriptions_db, 'remember_account_once', lambda *a: None)
    calls = []
    monkeypatch.setattr(redeem_code.auth, 'check_rate_limit_inline', lambda key, policy: calls.append(policy))
    monkeypatch.setattr(redeem_code, 'redeem_prepaid_code', lambda uid, code: calls.append('lookup') or REDEEMED)
    app = FastAPI()
    app.include_router(users.router)
    app.include_router(redeem_code.router)
    app.dependency_overrides[users.auth.get_current_user_uid_no_byok_validation] = lambda: UID
    app.dependency_overrides[redeem_code.auth.get_current_user_uid] = lambda: UID
    state = SimpleNamespace(
        http=TestClient(app, raise_server_exceptions=False), calls=calls, module=redeem_code, mp=monkeypatch
    )

    def settings(values):
        for key, value in values.items():
            monkeypatch.setenv(key, value)

    state.settings = settings
    return state


def _digest(response):
    raw = f'{response.status_code}|{response.headers.get("content-type")}|'.encode() + response.content
    return hashlib.sha256(raw).hexdigest()


def _get(client, headers):
    return client.http.get(SUBSCRIPTION, headers=headers)


def _redeem(client, headers):
    return client.http.post(REDEEM, json=CODE, headers=headers)


SETTINGS = {
    'prod': PROD,
    'prod_switch_off': {**PROD, switch.ENV: 'off'},
    'prod_switch_on': {**PROD, switch.ENV: 'on'},
    'play_on_switch_off': {**PLAY_ON, switch.ENV: 'off'},
}


# ---- byte identity with main -----------------------------------------------------------------


@pytest.mark.parametrize('setting', ['prod', 'prod_switch_off', 'prod_switch_on'])
@pytest.mark.parametrize('name', list(CLIENTS))
def test_today_every_client_gets_main_bytes(client, setting, name):
    client.settings(SETTINGS[setting])
    assert _digest(_get(client, CLIENTS[name])) == BASE[f'{setting}|{name}|subscription']
    assert _digest(_redeem(client, CLIENTS[name])) == BASE[f'{setting}|{name}|redeem']


@pytest.mark.parametrize('name', NON_PLAY_CLIENTS)
def test_with_play_on_every_other_client_gets_main_bytes(client, name):
    client.settings(SETTINGS['play_on_switch_off'])
    assert _digest(_get(client, CLIENTS[name])) == BASE[f'play_on_switch_off|{name}|subscription']
    redeemed = _redeem(client, CLIENTS[name])
    assert _digest(redeemed) == BASE[f'play_on_switch_off|{name}|redeem']
    assert redeemed.status_code == 404 and 'lookup' not in client.calls


# ---- a Play build can redeem whatever the switch ---------------------------------------------


def test_a_play_client_with_the_switch_off_is_offered_and_can_redeem(client):
    client.settings(SETTINGS['play_on_switch_off'])
    body = _get(client, ANDROID_PLAY).json()
    assert body['prepaid_code_redeem'] is True and body['play_billing']['product_id'] == 'omi_pro'
    # Main gave this client no entry: the only addition is the flag.
    main = BASE['play_on_switch_off|android_play_build|subscription_body']
    body.pop('prepaid_code_redeem')
    assert body == main
    response = _redeem(client, ANDROID_PLAY)
    assert response.status_code == 200 and response.json() == REDEEMED
    assert client.calls == ['payments:prepaid_code', 'lookup']  # same rate limit, same lookup


@pytest.mark.parametrize('name', NON_PLAY_CLIENTS)
def test_a_non_play_client_with_the_switch_off_is_refused_before_any_lookup(client, name):
    client.settings(SETTINGS['play_on_switch_off'])
    assert 'prepaid_code_redeem' not in _get(client, CLIENTS[name]).json()
    response = _redeem(client, CLIENTS[name])
    assert (response.status_code, response.json()) == (404, {'detail': 'Not Found'})
    assert client.calls == []


def test_a_play_cohort_member_on_a_stripe_server_can_redeem(client):
    client.settings(
        {**PROD, switch.ENV: 'off', config.COHORT_ENV: f'uid:{UID}', 'ANDROID_PLAY_BILLING_MIN_BUILD': '1624'}
    )
    assert _get(client, ANDROID_PLAY).json()['prepaid_code_redeem'] is True
    assert _redeem(client, ANDROID_PLAY).status_code == 200


# ---- every refusal stays, through the real redemption -----------------------------------------


@pytest.fixture
def real_redeem(client, world):
    client.mp.setattr(client.module, 'redeem_prepaid_code', redemption.redeem_prepaid_code)
    client.settings(SETTINGS['play_on_switch_off'])
    return SimpleNamespace(client=client, world=world)


def test_a_play_client_redeems_a_no_card_plan_that_ends_with_the_term(real_redeem):
    response = _redeem(real_redeem.client, ANDROID_PLAY)
    assert response.status_code == 200 and response.json()['months'] == 12
    (sub,) = real_redeem.world.stripe.created
    assert sub['payment_behavior'] == 'error_if_incomplete' and sub['metadata'][prepaid_marker] == '1'
    assert sub['cancel_at'] == response.json()['ends_at']
    # Same reader again: the same redemption, nothing new. Another account: the code is used.
    assert _redeem(real_redeem.client, ANDROID_PLAY).json() == response.json()
    overrides = real_redeem.client.http.app.dependency_overrides
    overrides[real_redeem.client.module.auth.get_current_user_uid] = lambda: OTHER
    assert (_redeem(real_redeem.client, ANDROID_PLAY).json()) == {'detail': 'code_used'}
    assert len(real_redeem.world.stripe.created) == 1


def test_a_play_client_with_a_live_stripe_plan_is_refused(real_redeem):
    real_redeem.world.customer_id = 'cus_old'
    real_redeem.world.stripe.existing = [{'id': 'sub_live', 'status': 'active', 'metadata': {'uid': UID}}]
    response = _redeem(real_redeem.client, ANDROID_PLAY)
    assert (response.status_code, response.json()) == (409, {'detail': 'has_plan'})
    assert real_redeem.world.stripe.created == [] and real_redeem.world.ledger.docs == {}


def test_a_play_client_with_a_live_play_row_is_refused(real_redeem):
    real_redeem.world.row = Subscription(plan=PlanType.unlimited_v2, current_period_end=NOW + DAY, provider='play')
    response = _redeem(real_redeem.client, ANDROID_PLAY)
    assert (response.status_code, response.json()) == (409, {'detail': 'has_plan'})
    assert real_redeem.world.stripe.created == []


@pytest.fixture
def play_history(real_redeem, subscribed, monkeypatch):
    """A Play purchase bound to this reader, read back from fake Google through the real admission."""
    for name in ('get_user_fields', 'get_purchase', 'purchase_keys_for_uid', 'update_purchase'):
        monkeypatch.setattr(play_db, name, getattr(subscribed.store, name))
    monkeypatch.setattr(play_publisher, '_default', subscribed.publisher)
    real_redeem.client.settings(SETTINGS['play_on_switch_off'])  # the Play fixture reset the env
    monkeypatch.setattr(
        redemption.users_db,
        'get_existing_user_subscription_and_fields',
        lambda uid, fields: (_row(subscribed), {name: subscribed.store.users[UID].get(name) for name in fields}),
    )
    return SimpleNamespace(env=subscribed, real=real_redeem)


@pytest.mark.parametrize(
    'state,kind',
    [('SUBSCRIPTION_STATE_ACTIVE', None), ('SUBSCRIPTION_STATE_ON_HOLD', 5), ('SUBSCRIPTION_STATE_PAUSED', 10)],
)
def test_a_play_client_with_a_live_or_recoverable_play_purchase_is_refused(play_history, state, kind):
    play_history.env.publisher.resources[TOKEN] = resource(state, expiry=NOW + DAY if kind is None else NOW - DAY)
    if kind:
        _notify(kind)
    response = _redeem(play_history.real.client, ANDROID_PLAY)
    assert (response.status_code, response.json()) == (409, {'detail': 'has_plan'})
    assert play_history.real.world.stripe.created == [] and play_history.real.world.ledger.docs == {}


def test_a_play_client_is_asked_to_retry_when_google_cannot_be_read(play_history):
    play_history.env.publisher.resources[TOKEN] = resource('SUBSCRIPTION_STATE_ON_HOLD')
    _notify(5)
    play_history.env.publisher.fail = RuntimeError('timeout')
    response = _redeem(play_history.real.client, ANDROID_PLAY)
    assert (response.status_code, response.json()) == (503, {'detail': 'try_again'})
    assert play_history.real.world.stripe.created == [] and play_history.real.world.ledger.docs == {}


# ---- the reverse: no Google Play purchase on top of a live prepaid plan -------------------------


def _prepaid_sub(status='active'):
    return {
        'id': 'sub_prepaid',
        'status': status,
        'cancel_at': NOW + 300 * DAY,
        'metadata': {'uid': UID, prepaid_marker: '1', 'redeemed_promotion_code_id': 'promo_1'},
    }


def test_a_play_purchase_is_refused_next_to_a_live_prepaid_plan(env):
    env.users.customers[UID] = 'cus_1'
    env.stripe_subs.append(_prepaid_sub())
    env.publisher.resources[TOKEN] = resource()
    with pytest.raises(play_billing.PlayBillingError) as error:
        play_billing.verify_and_bind(UID, TOKEN, 'omi_pro')
    assert (error.value.http_status, error.value.code) == (409, 'stripe_subscription_active')
    assert _row(env).plan == PlanType.basic  # nothing granted, nothing acknowledged


def test_a_play_purchase_is_refused_while_the_webhook_row_says_prepaid(env):
    env.users.rows[UID] = Subscription(
        plan=PlanType.unlimited_v2,
        status=SubscriptionStatus.active,
        current_period_end=NOW + 300 * DAY,
        stripe_subscription_id='sub_prepaid',
        prepaid=True,
    ).model_dump()
    assert play_billing._live_stripe_subscription(UID) is True


def test_an_ended_prepaid_plan_lets_the_reader_subscribe_on_play(env):
    env.users.customers[UID] = 'cus_1'
    env.stripe_subs.append(_prepaid_sub(status='canceled'))
    assert play_billing._live_stripe_subscription(UID) is False


@pytest.mark.skipif(not os.environ.get('PIN_PLAY_PREPAID_BASE'), reason='regenerates the main pins')
def test_pin_main_responses(client):
    """Run with PIN_PLAY_PREPAID_BASE=1 and main's routers/users.py + routers/redeem_code.py checked out."""
    pins = {}
    for setting, values in SETTINGS.items():
        client.settings(values)
        for name, headers in CLIENTS.items():
            got = _get(client, headers)
            pins[f'{setting}|{name}|subscription'] = _digest(got)
            if setting == 'play_on_switch_off' and name == 'android_play_build':
                pins[f'{setting}|{name}|subscription_body'] = got.json()
            pins[f'{setting}|{name}|redeem'] = _digest(_redeem(client, headers))
    with open(BASE_FILE, 'w') as handle:
        json.dump(pins, handle, indent=2, sort_keys=True)
        handle.write('\n')
