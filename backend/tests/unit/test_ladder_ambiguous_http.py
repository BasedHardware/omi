"""Real quota handlers admit a conservative ambiguous-history snapshot, without 503."""

from datetime import datetime, timezone
from unittest.mock import Mock

from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.unit.fixtures.shadow_usage_firestore import Store


@pytest.fixture
def http_modules():
    from routers import users
    from utils import subscription

    return users, subscription


@pytest.fixture
def ambiguous_snapshot(monkeypatch):
    from database import usage_units
    from utils import ladder_v1 as ladder
    from utils.observability import ladder_v1 as metrics

    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')
    monkeypatch.setattr(
        ladder,
        'account',
        lambda *a, **k: {
            'plan_id': 'plus',
            'entitlement_version': 'ladder_v1',
            'budget': {'kind': 'units', 'value': 100000},
        },
    )
    now = datetime.now(timezone.utc)
    leaf = {'micro_units': 123456, 'legacy_counter_seconds': 600, 'status_counts': {'complete': 5, 'missing': 1}}
    store = Store(
        {
            'users/u/hourly_usage/'
            + now.strftime('%Y-%m-%d-%H'): {
                'year': now.year,
                'month': now.month,
                'transcription_seconds': 600,
                'shadow_v1': {'features': {'transcription': {'funding': {'omi': leaf}}}},
            }
        }
    )
    monkeypatch.setattr(usage_units, 'get_customer_firestore_client', lambda: store)
    observe = Mock()
    monkeypatch.setattr(metrics.AMBIGUOUS_SECONDS, 'observe', observe)
    snapshot = ladder.usage_snapshot('u', firestore_client=store)
    assert (
        snapshot['used_units']
        == max(123456, usage_units.price_transcription(600, accepted=True)['micro_units']) / 1_000_000
    )
    observe.assert_called_once_with(600)
    # Keep the real snapshot and budget/admission functions; freeze just persistence
    # while the router harness installs its separate provider/message fakes.
    monkeypatch.setattr(ladder, 'usage_snapshot', lambda *a, **k: snapshot)
    return snapshot, store


def test_usage_quota_endpoint_admits_ambiguous_history(monkeypatch, ambiguous_snapshot, http_modules):
    from models.users import Subscription, PlanType

    users, subscription = http_modules

    snapshot, store = ambiguous_snapshot
    profile = Subscription(plan=PlanType.plus)
    monkeypatch.setattr(users, 'get_customer_firestore_client', lambda: store)
    monkeypatch.setattr(subscription.users_db, 'get_user_valid_subscription', lambda *a, **k: profile)
    monkeypatch.setattr(
        subscription.user_usage_db,
        'get_monthly_chat_usage',
        lambda *a, **k: {'questions': 0, 'cost_usd': 0, 'reset_at': snapshot['reset_at']},
    )
    app = FastAPI()
    app.include_router(users.router)
    app.dependency_overrides[users.auth.get_current_user_uid] = lambda: 'u'
    with TestClient(app) as client:
        response = client.get('/v1/users/me/usage-quota')
    assert response.status_code == 200, response.text
    assert response.json()['allowed'] is True
    assert response.json()['uses_shared_budget'] is True


def test_chat_endpoint_admits_ambiguous_history(monkeypatch, ambiguous_snapshot, http_modules):
    subscription = http_modules[1]
    from tests.unit.test_chat_quota_counting_router import _make_chat_client, _cleanup

    enforce = subscription.enforce_chat_quota
    client, module, saved = _make_chat_client()
    try:
        monkeypatch.setattr(module, 'enforce_chat_quota', enforce)
        response = client.post(
            '/v2/messages', json={'text': 'hello', 'file_ids': []}, headers={'X-App-Platform': 'ios'}
        )
        assert response.status_code == 200, response.text
    finally:
        client.close()
        _cleanup(saved)
