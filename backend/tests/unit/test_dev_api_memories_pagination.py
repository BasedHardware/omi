"""Regression tests for GET /v1/dev/user/memories resilience (issue #7492).

The endpoint declares response_model=List[CleanerMemory] and returned raw Firestore dicts, so a
single malformed/legacy record could make FastAPI raise ResponseValidationError -> HTTP 500 for the
whole page. The handler now validates each record individually, skips records without required
identity fields, and coerces legacy optional fields to safe defaults.
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
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'database._client',
    'database.redis_db',
    'database.conversations',
    'database.memories',
    'database.action_items',
    'database.folders',
    'database.users',
    'database.user_usage',
    'database.vector_db',
    'database.chat',
    'database.apps',
    'database.goals',
    'database.notifications',
    'database.mem_db',
    'database.mcp_api_key',
    'database.daily_summaries',
    'database.fair_use',
    'database.auth',
    'database.knowledge_graph',
    'database.dev_api_key',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'firebase_admin.credentials',
    'firebase_admin.firestore',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'utils.other.storage',
    'utils.stt.pre_recorded',
    'utils.stt.vad',
    'utils.fair_use',
    'utils.subscription',
    'utils.conversations.process_conversation',
    'utils.conversations.location',
    'utils.notifications',
    'utils.apps',
    'utils.llm.memories',
    'utils.llm.chat',
    'utils.llm.knowledge_graph',
]
for _mod_name in _stubs:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _AutoMockModule(_mod_name)

sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
sys.modules['utils.apps'].update_personas_async = MagicMock()

# utils.other.endpoints must expose real callables (used in route signatures); provide stand-ins.
_endpoints = ModuleType('utils.other.endpoints')


def _fake_get_current_user_uid():  # pragma: no cover - dependency stand-in
    return 'uid1'


def _fake_with_rate_limit(dependency, _policy):  # pragma: no cover - returns wrapped dependency
    return dependency


_endpoints.get_current_user_uid = _fake_get_current_user_uid
_endpoints.with_rate_limit = _fake_with_rate_limit
_endpoints.get_user = MagicMock()
sys.modules['utils.other.endpoints'] = _endpoints

from datetime import datetime, timezone  # noqa: E402

import database.memories as memories_db  # noqa: E402  (the stub)
from models.memories import MemoryCategory  # noqa: E402  (real model; stubs prevent google init)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from routers.developer import router as developer_router  # noqa: E402
from dependencies import get_uid_with_memories_read  # noqa: E402

_VALID_CATEGORY = next(iter(MemoryCategory)).value


def _valid_memory(mid):
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return {
        'id': mid,
        'content': 'a memory',
        'category': _VALID_CATEGORY,
        'visibility': 'private',
        'tags': [],
        'created_at': now,
        'updated_at': now,
        'manually_added': False,
        'scoring': None,
        'reviewed': False,
        'user_review': None,
        'edited': False,
    }


def _missing_id_memory(mid):
    # Malformed record missing the required identity field.
    m = _valid_memory(mid)
    del m['id']
    return m


def _legacy_memory(mid):
    # Legacy record with missing/invalid optional fields that should be coerced.
    m = _valid_memory(mid)
    m['category'] = 'old-category'
    m['visibility'] = None
    m['tags'] = None
    m['created_at'] = 'not-a-date'
    m['updated_at'] = {'bad': 'date'}
    m['manually_added'] = ''
    m['reviewed'] = None
    m['user_review'] = 'yes'
    del m['edited']
    return m


def _build():
    app = FastAPI()
    app.include_router(developer_router)
    app.dependency_overrides[get_uid_with_memories_read] = lambda: 'uid1'
    return TestClient(app, raise_server_exceptions=False)


def test_invalid_record_is_skipped_not_500():
    page = [_valid_memory('good1'), _missing_id_memory('bad1'), _valid_memory('good2')]
    with patch.object(memories_db, 'get_memories', return_value=page):
        client = _build()
        resp = client.get('/v1/dev/user/memories')
    assert resp.status_code == 200
    assert [m['id'] for m in resp.json()] == ['good1', 'good2']


def test_legacy_optional_fields_are_defaulted_not_500():
    page = [_legacy_memory('legacy1')]
    with patch.object(memories_db, 'get_memories', return_value=page):
        client = _build()
        resp = client.get('/v1/dev/user/memories')
    assert resp.status_code == 200
    [memory] = resp.json()
    assert memory['id'] == 'legacy1'
    assert memory['category'] == 'interesting'
    assert memory['visibility'] == 'private'
    assert memory['tags'] == []
    assert memory['created_at'] is None
    assert memory['updated_at'] is None
    assert memory['manually_added'] is False
    assert memory['reviewed'] is False
    assert memory['user_review'] is True
    assert memory['edited'] is False


def test_all_valid_records_returned():
    page = [_valid_memory('a'), _valid_memory('b')]
    with patch.object(memories_db, 'get_memories', return_value=page):
        client = _build()
        resp = client.get('/v1/dev/user/memories')
    assert resp.status_code == 200
    assert len(resp.json()) == 2
