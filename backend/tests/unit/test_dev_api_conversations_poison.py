"""GET /v1/dev/user/conversations must skip a malformed record instead of 500ing the page.

The endpoint declared response_model=List[Conversation] and returned raw Firestore dicts, so one malformed
record made FastAPI raise ResponseValidationError -> HTTP 500 for the whole page.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

BACKEND_DIR = Path(__file__).resolve().parents[2]


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _ensure_package_path(name, path):
    module = sys.modules.get(name)
    if module is None or not hasattr(module, "__path__"):
        module = ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [str(path)]
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, module)
    return module


def _drop_stale_module(name, expected_file):
    module = sys.modules.get(name)
    if module is None:
        return
    module_file = getattr(module, "__file__", None)
    try:
        module_path = Path(module_file).resolve() if module_file else None
    except TypeError:
        module_path = None
    if module_path == expected_file.resolve():
        return
    sys.modules.pop(name, None)
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None and getattr(parent, attr_name, None) is module:
            delattr(parent, attr_name)


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

sys.modules['database._client'].document_id_from_seed = MagicMock(return_value='memory-id')
sys.modules['database.vector_db'].upsert_memory_vectors_batch = MagicMock()
sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
sys.modules['utils.apps'].update_personas_async = MagicMock()

_endpoints = sys.modules.get('utils.other.endpoints')
if _endpoints is None:
    _endpoints = ModuleType('utils.other.endpoints')
    sys.modules['utils.other.endpoints'] = _endpoints
if not hasattr(_endpoints, 'get_current_user_uid'):
    _endpoints.get_current_user_uid = lambda: 'uid1'
if not hasattr(_endpoints, 'with_rate_limit'):
    _endpoints.with_rate_limit = lambda dependency, _policy: dependency
if not hasattr(_endpoints, 'with_rate_limit_context'):
    setattr(_endpoints, 'with_rate_limit_context', lambda dependency, _policy: dependency)
if not hasattr(_endpoints, 'check_api_key_rate_limit'):
    _endpoints.check_api_key_rate_limit = MagicMock()
if not hasattr(_endpoints, 'get_user'):
    _endpoints.get_user = MagicMock()

_ensure_package_path("models", BACKEND_DIR / "models")
_ensure_package_path("routers", BACKEND_DIR / "routers")
_ensure_package_path("utils", BACKEND_DIR / "utils")
_ensure_package_path("utils.conversations", BACKEND_DIR / "utils" / "conversations")
_drop_stale_module("models.conversation", BACKEND_DIR / "models" / "conversation.py")
_drop_stale_module("models.conversation_enums", BACKEND_DIR / "models" / "conversation_enums.py")
_drop_stale_module("models.dev_api_key", BACKEND_DIR / "models" / "dev_api_key.py")
_drop_stale_module("models.folder", BACKEND_DIR / "models" / "folder.py")
_drop_stale_module("models.geolocation", BACKEND_DIR / "models" / "geolocation.py")
_drop_stale_module("models.memories", BACKEND_DIR / "models" / "memories.py")
_drop_stale_module("models.transcript_segment", BACKEND_DIR / "models" / "transcript_segment.py")
_drop_stale_module("routers.developer", BACKEND_DIR / "routers" / "developer.py")
_drop_stale_module("utils.conversations.render", BACKEND_DIR / "utils" / "conversations" / "render.py")

import database.conversations as conversations_db  # noqa: E402  (the stub)
from models.conversation_enums import CategoryEnum  # noqa: E402  (real enum)
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
import routers.developer as developer_module  # noqa: E402
from routers.developer import router as developer_router  # noqa: E402
from dependencies import ApiKeyAuth, get_auth_with_conversations_read  # noqa: E402

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_VALID_CATEGORY = next(iter(CategoryEnum)).value


def _read_auth():
    return ApiKeyAuth(
        uid='uid1',
        scopes=['conversations:read'],
        app_id='test-app',
        key_id='test-key',
    )


def _valid(cid):
    return {
        'id': cid,
        'created_at': _NOW,
        'started_at': _NOW,
        'finished_at': _NOW,
        'structured': {'title': 'A Title', 'overview': 'An overview', 'category': _VALID_CATEGORY},
    }


def _build():
    app = FastAPI()
    app.include_router(developer_router)
    app.dependency_overrides[get_auth_with_conversations_read] = _read_auth
    return TestClient(app, raise_server_exceptions=False)


def test_malformed_conversation_skipped_not_500():
    missing_structured = _valid('bad')
    del missing_structured['structured']
    page = [_valid('c1'), missing_structured, _valid('c2')]
    with patch.object(conversations_db, 'get_conversations', return_value=page), patch.object(
        developer_module, 'populate_folder_names', lambda *a, **k: None
    ), patch.object(developer_module, 'populate_speaker_names', lambda *a, **k: None):
        resp = _build().get('/v1/dev/user/conversations')
    assert resp.status_code == 200
    assert [c['id'] for c in resp.json()] == ['c1', 'c2']


def test_pagination_is_clamped_before_firestore():
    # Out-of-range pagination is clamped before the Firestore query: a negative offset/limit
    # would otherwise raise (HTTP 500) and an oversized/zero limit would stream the whole
    # collection. Call the handler directly (the TestClient async path is flaky on Windows; the
    # clamp is what matters).
    with patch.object(conversations_db, 'get_conversations', return_value=[]) as m, patch.object(
        developer_module, 'populate_folder_names', lambda *a, **k: None
    ), patch.object(developer_module, 'populate_speaker_names', lambda *a, **k: None):
        developer_module.get_conversations(uid=_read_auth(), limit=99999, offset=-1)
        developer_module.get_conversations(uid=_read_auth(), limit=99999, offset=0, include_transcript=True)
        developer_module.get_conversations(uid=_read_auth(), limit=0, offset=5)
    high = m.call_args_list[0].args
    assert high[1] == 100 and high[2] == 0  # limit 99999 -> 100, offset -1 -> 0
    assert m.call_args_list[1].args[1] == 25  # transcript reads cap tighter
    assert m.call_args_list[2].args[1] == 1  # limit 0 -> 1


def test_goals_limit_is_clamped_before_firestore():
    # Sibling of the conversations clamp above: GET /v1/dev/user/goals passed the request `limit`
    # straight to get_user_goals -> Firestore .limit(), so ?limit=-1 raised (HTTP 500) and an
    # oversized limit could stream the whole collection. Reuses this file's developer-router
    # harness (database.goals is already stubbed); call the handler directly.
    with patch.object(developer_module.goals_db, 'get_user_goals', return_value=[]) as m:
        developer_module.get_goals(uid='uid1', limit=-1)
        developer_module.get_goals(uid='uid1', limit=99999)
        developer_module.get_goals(uid='uid1', limit=0)
    assert m.call_args_list[0].kwargs['limit'] == 1  # -1 -> 1
    assert m.call_args_list[1].kwargs['limit'] == 1000  # 99999 -> 1000
    assert m.call_args_list[2].kwargs['limit'] == 1  # 0 -> 1
