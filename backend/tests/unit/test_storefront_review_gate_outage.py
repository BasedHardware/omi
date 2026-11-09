"""A storage outage behind the App Store review gate must stay server-side.

`should_hide_subscription_ui` fails closed to an empty config when Firestore
raises, so the storefront route keeps serving. This pins the route-level
contract: the internal error text is logged for operators, never reflected to
the client.
"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import app_review_config
from models.storefront import StorefrontUsage
from models.users import Subscription
from routers import storefront as route


class _MemoryCache:
    def __init__(self):
        self._store = {}

    def get_or_fetch(self, key, fetch, ttl=None):
        if key not in self._store:
            self._store[key] = fetch()
        return self._store[key]


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.auth.get_current_user_uid_no_byok_validation] = lambda: 'fixture-user'
    monkeypatch.setattr(route.auth, 'check_rate_limit', lambda *args: (True, 12, 0))
    monkeypatch.setattr(route.auth, 'RATE_LIMIT_SHADOW', False)
    monkeypatch.setenv('STOREFRONT_LADDER_V1_ENABLED', 'true')
    monkeypatch.setattr(route.users_db, 'get_user_valid_subscription', lambda uid, **kwargs: Subscription())
    monkeypatch.setattr(route, '_usage', lambda *args: StorefrontUsage())
    return TestClient(app)


def test_firestore_outage_is_logged_not_reflected_in_the_storefront_response(client, monkeypatch, caplog):
    sentinel = 'firestore://internal-db:5432 connection refused'

    class _ExplodingFirestore:
        def collection(self, name):
            raise RuntimeError(sentinel)

    monkeypatch.setattr(route, 'should_hide_subscription_ui', app_review_config.should_hide_subscription_ui)
    monkeypatch.setattr(app_review_config, 'get_firestore_client', lambda: _ExplodingFirestore())
    monkeypatch.setattr(app_review_config, 'get_memory_cache', lambda: _MemoryCache())

    with caplog.at_level(logging.WARNING, logger=app_review_config.__name__):
        response = client.get('/v2/payments/plans', headers={'X-App-Platform': 'ios', 'X-App-Version': '1.0.531'})

    assert response.status_code == 200
    assert response.json()['show_subscription_ui'] is True
    assert sentinel not in response.text
    assert sentinel in caplog.text
