"""POST /v1/payments/payment-issue/monthly-switch: status codes, the per-user lock, and what is stored.

Real route and response model; Stripe, Redis and storage are fakes. utils/monthly_switch.py owns
the Stripe sequence (tests/unit/test_monthly_switch.py); this file pins the HTTP boundary.
"""

import os

import pytest
import stripe
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from models.users import PlanType, Subscription, SubscriptionStatus  # noqa: E402
from routers import monthly_switch as route  # noqa: E402
from routers import payment  # noqa: E402
from utils import monthly_switch  # noqa: E402

UID = 'fixture-user'
NEO_MONTHLY = 'price_1RtJPm1F8wnoWYvwhVJ38kLb'
BODY = {'price_id': NEO_MONTHLY, 'expected_amount': 1999}
SWITCHED = {
    'id': 'sub_1',
    'status': 'active',
    'current_period_start': 1_793_000_000,
    'current_period_end': 1_795_600_000,
    'cancel_at_period_end': False,
    'metadata': {'uid': UID},
    'items': {'data': [{'id': 'si_1', 'price': {'id': NEO_MONTHLY}}]},
}


class _Env:
    def __init__(self, monkeypatch, switch=None, lock=True, stored_id='sub_1'):
        self.stored = []
        self.unlocked = []
        self.locks = {}
        self.lock = lock
        self.switch_calls = []
        stored = Subscription(plan=PlanType.basic, status=SubscriptionStatus.active, stripe_subscription_id=stored_id)
        monkeypatch.setattr(route.users_db, 'get_user_subscription', lambda uid: stored.model_copy())
        monkeypatch.setattr(route.users_db, 'update_user_subscription', lambda uid, data: self.stored.append(data))
        monkeypatch.setattr(route.redis_db, 'set_credits_invalidation_signal', lambda uid: None)
        monkeypatch.setattr(route.conversations_db, 'unlock_all_conversations', lambda uid: self.unlocked.append(uid))
        monkeypatch.setattr(route.memories_db, 'unlock_all_memories', lambda uid: None)
        monkeypatch.setattr(route.action_items_db, 'unlock_all_action_items', lambda uid: None)
        monkeypatch.setattr(route, 'clear_fair_use_on_upgrade', lambda uid: None)
        monkeypatch.setattr(route, 'funded_processing_enabled', lambda uid: False)
        monkeypatch.setattr(route, 'try_acquire_lock', self.acquire)
        monkeypatch.setattr(route, 'release_lock', self.release)
        monkeypatch.setattr(route.monthly_switch, 'switch', self.run_switch)
        self.switch = switch or (lambda *args: dict(SWITCHED))

    def acquire(self, uid, token):
        if self.lock is None:
            raise ConnectionError('redis down')
        if not self.lock or uid in self.locks:
            return False
        self.locks[uid] = token
        return True

    def release(self, uid, token):
        if self.locks.get(uid) == token:
            del self.locks[uid]

    def run_switch(self, uid, sub_id, price_id, amount, attempt):
        self.switch_calls.append((uid, sub_id, price_id, amount))
        return self.switch(uid, sub_id, price_id, amount, attempt)

    def post(self, body=BODY):
        app = FastAPI()
        app.include_router(route.router)
        app.dependency_overrides[route.auth.get_current_user_uid] = lambda: UID
        with TestClient(app) as client:
            return client.post('/v1/payments/payment-issue/monthly-switch', json=body)


def test_switch_stores_the_paid_monthly_plan_and_restores_access(monkeypatch):
    env = _Env(monkeypatch)

    response = env.post()

    assert response.status_code == 200
    assert response.json()['status'] == 'switched'
    assert env.switch_calls == [(UID, 'sub_1', NEO_MONTHLY, 1999)]
    assert env.stored[-1]['plan'] == PlanType.unlimited
    assert env.stored[-1]['stripe_subscription_id'] == 'sub_1'
    assert env.unlocked == [UID]
    assert env.locks == {}  # released


def test_declined_card_is_402_and_nothing_is_stored(monkeypatch):
    def declined(*args):
        raise stripe.error.CardError('Your card has insufficient funds.', None, 'card_declined')

    env = _Env(monkeypatch, switch=declined)

    response = env.post()

    assert response.status_code == 402
    assert 'insufficient funds' in response.json()['detail']
    assert env.stored == [] and env.unlocked == []
    assert env.locks == {}


def test_refused_switch_is_409_and_nothing_is_stored(monkeypatch):
    def refused(*args):
        raise monthly_switch.Refused('discounted')

    env = _Env(monkeypatch, switch=refused)

    response = env.post()

    assert response.status_code == 409
    assert env.stored == []


@pytest.mark.parametrize('error', [stripe.error.APIConnectionError('down'), monthly_switch.Incomplete('past_due')])
def test_unconfirmed_switch_is_503_and_nothing_is_stored(monkeypatch, error):
    def unknown(*args):
        raise error

    env = _Env(monkeypatch, switch=unknown)

    response = env.post()

    assert response.status_code == 503
    assert env.stored == []
    assert env.locks == {}


def test_a_switch_already_running_is_409_without_touching_stripe(monkeypatch):
    env = _Env(monkeypatch, lock=False)

    response = env.post()

    assert response.status_code == 409
    assert env.switch_calls == []


def test_no_lock_store_means_no_charge(monkeypatch):
    env = _Env(monkeypatch, lock=None)

    response = env.post()

    assert response.status_code == 503
    assert env.switch_calls == []


@pytest.mark.parametrize('stored_id', [None, 'pi_org_grant'])
def test_no_stripe_subscription_is_409(monkeypatch, stored_id):
    env = _Env(monkeypatch, stored_id=stored_id)

    response = env.post()

    assert response.status_code == 409
    assert env.switch_calls == []


@pytest.mark.parametrize(
    'body', [{'price_id': NEO_MONTHLY}, {'price_id': '', 'expected_amount': 1999}, {**BODY, 'expected_amount': 0}]
)
def test_malformed_request_is_rejected_before_stripe(monkeypatch, body):
    env = _Env(monkeypatch)

    response = env.post(body)

    assert response.status_code == 422
    assert env.switch_calls == []
