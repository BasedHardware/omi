"""Regression test for POST /v1/conversations/search date validation.

SearchRequest.start_date / end_date are free-form ISO strings. Before the fix, a malformed
value made `datetime.fromisoformat(...)` raise an unhandled ValueError, returning HTTP 500.
The handler now catches it and returns HTTP 400. These tests mount the conversations router
(heavy deps stubbed, same pattern as the other router unit tests) and exercise the HTTP layer.
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
for _mod_name in _stubs:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _AutoMockModule(_mod_name)

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
sys.modules['utils.other.endpoints'] = _endpoints

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from routers import conversations as conv  # noqa: E402


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
    conv.search_conversations = MagicMock(return_value={'conversations': []})
    client = _client()
    resp = client.post(
        '/v1/conversations/search',
        json={'query': 'hi', 'start_date': '2026-01-01T00:00:00', 'end_date': '2026-02-01T00:00:00'},
    )
    assert resp.status_code == 200
    assert conv.search_conversations.called
