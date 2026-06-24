"""Regression test for GET /v1/daily-score calendar date validation.

The `date` query param is regex-constrained to YYYY-MM-DD, but a calendrically-invalid value
that still matches the shape (e.g. 2026-02-30) reaches database.action_items.get_daily_score,
whose `datetime.strptime(date, '%Y-%m-%d')` raises ValueError. Before the fix that surfaced as an
unhandled HTTP 500. The endpoint now catches ValueError and returns HTTP 400.

The real database.action_items.get_daily_score runs here (only the Firestore client is stubbed),
so the actual strptime is exercised: an invalid date raises before any Firestore access, while a
valid date proceeds into the (mocked) Firestore call.
"""

import os
import sys
from types import ModuleType
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)


class _AutoMockModule(ModuleType):
    """Module stub that returns a MagicMock for any missing attribute."""

    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


# Stub only the heavy leaf deps that database.action_items / the router pull in. We deliberately
# keep the REAL database.action_items so the real strptime parses the date.
_stubs = [
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'firebase_admin.credentials',
    'firebase_admin.firestore',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'database._client',
]

_MISSING = object()
_saved_modules = {}


def _register_stub(name):
    _saved_modules.setdefault(name, sys.modules.get(name, _MISSING))
    sys.modules[name] = _AutoMockModule(name)


for _mod_name in _stubs:
    _register_stub(_mod_name)

# google.cloud.firestore_v1.FieldFilter must be a real callable for the `from ... import FieldFilter`.
sys.modules['google.cloud.firestore_v1'].FieldFilter = MagicMock()

# utils.other.endpoints exposes the auth dependencies used in the route signatures; FastAPI needs
# real callables to build the dependants, so provide small stand-ins.
_endpoints = ModuleType('utils.other.endpoints')


def _fake_get_current_user_uid():  # pragma: no cover - dependency stand-in
    return 'test-uid'


def _fake_with_rate_limit(dependency, _policy):  # pragma: no cover - returns wrapped dependency
    return dependency


_endpoints.get_current_user_uid = _fake_get_current_user_uid
_endpoints.with_rate_limit = _fake_with_rate_limit
_saved_modules.setdefault('utils.other.endpoints', sys.modules.get('utils.other.endpoints', _MISSING))
sys.modules['utils.other.endpoints'] = _endpoints

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_saved_modules.setdefault('routers.scores', sys.modules.get('routers.scores', _MISSING))
sys.modules.pop('routers.scores', None)
try:
    from routers import scores as scores_mod  # noqa: E402
finally:
    for _name, _prev in _saved_modules.items():
        if _prev is _MISSING:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _prev


def _client():
    app = FastAPI()
    app.include_router(scores_mod.router)
    app.dependency_overrides[scores_mod.auth.get_current_user_uid] = lambda: 'test-uid'
    return TestClient(app, raise_server_exceptions=False)


def test_invalid_calendar_date_returns_400_not_500():
    client = _client()
    resp = client.get('/v1/daily-score', params={'date': '2026-02-30'})
    assert resp.status_code == 400
    assert 'date' in resp.json().get('detail', '').lower()


def test_valid_date_is_accepted():
    client = _client()
    resp = client.get('/v1/daily-score', params={'date': '2026-01-15'})
    # A real calendar date must not 400; the (mocked) Firestore read returns a score payload.
    assert resp.status_code == 200
