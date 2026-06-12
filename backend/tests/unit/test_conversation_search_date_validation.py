"""Regression test for POST /v1/conversations/search date validation.

SearchRequest.start_date / end_date are free-form ISO strings. Before the fix, a malformed
value made `datetime.fromisoformat(...)` raise an unhandled ValueError, returning HTTP 500.
The handler now catches it and returns HTTP 400. These tests mount the conversations router
(heavy deps stubbed, same pattern as the other router unit tests) and exercise the HTTP layer.
"""

import os
import sys
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
    'ulid',
    'pinecone',
    'typesense',
    'database._client',
    'database.conversations',
    'database.action_items',
    'database.memories',
    'database.redis_db',
    'database.users',
    'database.vector_db',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'firebase_admin.credentials',
    'firebase_admin.firestore',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'utils.other.endpoints',
    'utils.other.storage',
    'utils.conversations.factory',
    'utils.conversations.render',
    'utils.conversations.process_conversation',
    'utils.conversations.search',
    'utils.conversations.calendar_linking',
    'utils.conversations.calendar_utils',
    'utils.conversations.location',
    'utils.llm.conversation_processing',
    'utils.speaker_identification',
    'utils.app_integrations',
    'utils.retrieval.tools.calendar_tools',
    'utils.retrieval.tools.google_utils',
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

_remove_module_for_fresh_import('routers.conversations')
_remove_module_for_fresh_import('routers')
try:
    from routers import conversations as conv  # noqa: E402
finally:
    _restore_stubbed_modules()


def _client():
    app = FastAPI()
    app.include_router(conv.router)
    app.dependency_overrides[conv.auth.get_current_user_uid] = lambda: 'test-uid'
    return TestClient(app, raise_server_exceptions=False)


def test_bad_start_date_returns_400_not_500():
    client = _client()
    resp = client.post('/v1/conversations/search', json={'query': 'hi', 'start_date': 'not-a-date'})
    assert resp.status_code == 400
    assert 'start_date' in resp.json().get('detail', '')


def test_bad_end_date_returns_400_not_500():
    client = _client()
    resp = client.post('/v1/conversations/search', json={'query': 'hi', 'end_date': 'nope'})
    assert resp.status_code == 400
    assert 'end_date' in resp.json().get('detail', '')


def test_valid_date_is_accepted_and_calls_search():
    with patch.object(conv, 'search_conversations', return_value={'conversations': []}) as mock_search:
        client = _client()
        resp = client.post(
            '/v1/conversations/search',
            json={'query': 'hi', 'start_date': '2026-01-01T00:00:00', 'end_date': '2026-02-01T00:00:00'},
        )
        assert resp.status_code == 200
        assert mock_search.called
