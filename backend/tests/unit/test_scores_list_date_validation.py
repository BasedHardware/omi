"""Regression test for GET /v1/scores date validation.

The `date` query param is constrained to the YYYY-MM-DD shape by a regex, but a
calendrically-invalid value that still matches that shape (e.g. 2026-02-30) slips
through. The database layer then calls datetime.strptime(date, '%Y-%m-%d'), which
raises an unhandled ValueError, returning HTTP 500. The handler now catches it and
returns HTTP 400. This test mounts the scores router (heavy deps stubbed, same
pattern as the other router unit tests) and exercises the HTTP layer.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from unittest.mock import MagicMock, patch

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


_stubs = [
    'database',
    'database.action_items',
    'firebase_admin',
    'firebase_admin.auth',
    'utils.other.endpoints',
]

_MISSING = object()
_saved_modules = {}
_saved_parent_attrs = {}


def _save_module_for_restore(name):
    if name not in _saved_modules:
        _saved_modules[name] = sys.modules.get(name, _MISSING)
    if '.' in name:
        parent_name, attr = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        key = (parent_name, attr)
        if key not in _saved_parent_attrs:
            previous_attr = parent.__dict__.get(attr, _MISSING) if parent is not None else _MISSING
            _saved_parent_attrs[key] = (parent, previous_attr)


def _register_module(name, module):
    _save_module_for_restore(name)
    sys.modules[name] = module
    if '.' in name:
        parent_name, attr = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if not isinstance(parent, _AutoMockModule):
            parent = _AutoMockModule(parent_name)
            _register_module(parent_name, parent)
        setattr(parent, attr, module)
    return module


def _remove_module_for_fresh_import(name):
    _save_module_for_restore(name)
    sys.modules.pop(name, None)
    if '.' in name:
        parent_name, attr = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            parent.__dict__.pop(attr, None)


def _restore_stubbed_modules():
    for name in sorted(_saved_modules, key=lambda item: item.count('.'), reverse=True):
        previous = _saved_modules[name]
        if previous is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    for (_parent_name, attr), (parent, previous_attr) in _saved_parent_attrs.items():
        if parent is None:
            continue
        if previous_attr is _MISSING:
            parent.__dict__.pop(attr, None)
        else:
            setattr(parent, attr, previous_attr)
    _saved_modules.clear()
    _saved_parent_attrs.clear()


for _mod_name in _stubs:
    _register_module(_mod_name, _AutoMockModule(_mod_name))

sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})


# database.action_items.get_scores is what the endpoint calls. Mirror the real
# implementation's date handling: it does datetime.strptime(date, '%Y-%m-%d'),
# which raises ValueError for a calendrically-invalid date BEFORE any Firestore
# access. Reproduce exactly that so the test exercises the genuine failure mode.
def _real_strptime_get_scores(uid, date=None):
    if date:
        datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
    return {'daily': 0, 'weekly': 0, 'overall': 0}


_action_items_db = sys.modules['database.action_items']
_action_items_db.get_scores = _real_strptime_get_scores

# utils.other.endpoints exposes the auth dependencies used in route signatures; FastAPI needs
# real callables to build the dependants, so provide small stand-ins.
_endpoints = ModuleType('utils.other.endpoints')


def _fake_get_current_user_uid():  # pragma: no cover - dependency stand-in
    return 'test-uid'


def _fake_with_rate_limit(dependency, _policy):  # pragma: no cover - returns wrapped dependency
    return dependency


_endpoints.get_current_user_uid = _fake_get_current_user_uid
_endpoints.with_rate_limit = _fake_with_rate_limit
_endpoints.get_user = MagicMock()
_register_module('utils.other.endpoints', _endpoints)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_remove_module_for_fresh_import('routers.scores')
_remove_module_for_fresh_import('routers')
try:
    from routers import scores as scores_mod  # noqa: E402
finally:
    _restore_stubbed_modules()


def _client():
    app = FastAPI()
    app.include_router(scores_mod.router)
    app.dependency_overrides[scores_mod.auth.get_current_user_uid] = lambda: 'test-uid'
    return TestClient(app, raise_server_exceptions=False)


def test_invalid_calendar_date_returns_400_not_500():
    # 2026-02-30 matches the YYYY-MM-DD regex but is not a real date -> strptime ValueError.
    client = _client()
    resp = client.get('/v1/scores', params={'date': '2026-02-30'})
    assert resp.status_code == 400
    assert 'date' in resp.json().get('detail', '').lower()


def test_valid_date_is_accepted_and_calls_db():
    captured = {}

    def _ok(uid, date=None):
        captured['date'] = date
        return {'daily': 100.0, 'weekly': 50.0, 'overall': 25.0}

    with patch.object(scores_mod.action_items_db, 'get_scores', side_effect=_ok):
        client = _client()
        resp = client.get('/v1/scores', params={'date': '2026-02-28'})
        assert resp.status_code == 200
        assert resp.json() == {'daily': 100.0, 'weekly': 50.0, 'overall': 25.0}
        assert captured['date'] == '2026-02-28'
