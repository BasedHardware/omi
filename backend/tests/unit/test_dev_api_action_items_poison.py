"""GET /v1/dev/user/action-items must skip a malformed record instead of 500ing the page.

The endpoint declared response_model=List[ActionItemResponse] and returned raw Firestore dicts, so one
malformed record made FastAPI raise ResponseValidationError -> HTTP 500 for the whole page.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

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

import database.action_items as action_items_db  # noqa: E402  (the stub)
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from routers.developer import router as developer_router  # noqa: E402
import routers.developer as developer_module  # noqa: E402
from dependencies import get_uid_with_action_items_read  # noqa: E402


def _build():
    app = FastAPI()
    app.include_router(developer_router)
    app.dependency_overrides[get_uid_with_action_items_read] = lambda: 'uid1'
    return TestClient(app, raise_server_exceptions=False)


def _valid(aid):
    return {'id': aid, 'description': 'do a thing', 'completed': False}


def test_malformed_action_item_skipped_not_500():
    page = [_valid('a1'), {'id': 'bad', 'description': 'missing completed'}, _valid('a2')]
    with patch.object(action_items_db, 'get_action_items', return_value=page):
        resp = _build().get('/v1/dev/user/action-items')
    assert resp.status_code == 200
    assert [i['id'] for i in resp.json()] == ['a1', 'a2']


def test_pagination_is_clamped_before_firestore():
    # Out-of-range pagination is clamped before the query: a negative limit/offset would raise
    # (HTTP 500) and limit=0 hit the falsy `if limit:` guard and streamed the whole collection.
    # Call the handler directly; get_action_items passes limit/offset as keyword args.
    with patch.object(action_items_db, 'get_action_items', return_value=[]) as m:
        developer_module.get_action_items(uid='uid1', limit=99999, offset=-1)
        developer_module.get_action_items(uid='uid1', limit=0, offset=5)
    high = m.call_args_list[0].kwargs
    assert high['limit'] == 1000 and high['offset'] == 0  # 99999 -> 1000, -1 -> 0
    assert m.call_args_list[1].kwargs['limit'] == 1  # 0 -> 1


def _update_fixture():
    due = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
    existing = {
        'id': 'a1',
        'description': 'Original task',
        'completed': False,
        'due_at': due,
    }
    return existing, due


def test_developer_patch_explicit_null_clears_due_date_and_reminder():
    existing, _ = _update_fixture()
    updated = {**existing, 'due_at': None}
    request = developer_module.UpdateActionItemRequest(due_at=None)

    with (
        patch.object(action_items_db, 'get_action_item', side_effect=[existing, updated]),
        patch.object(action_items_db, 'update_action_item', return_value=True) as update,
        patch.object(developer_module, 'sync_action_item_reminder') as sync,
    ):
        result = developer_module.update_action_item('a1', request, uid='uid1')

    assert request.model_fields_set == {'due_at'}
    assert update.call_args.args[2] == {'due_at': None}
    sync.assert_called_once_with(
        user_id='uid1',
        action_item_id='a1',
        description='Original task',
        completed=False,
        due_at=None,
    )
    assert result['due_at'] is None


def test_developer_patch_omitted_due_date_preserves_existing_value():
    existing, due = _update_fixture()
    updated = {**existing, 'description': 'Updated task'}
    request = developer_module.UpdateActionItemRequest(description='Updated task')

    with (
        patch.object(action_items_db, 'get_action_item', side_effect=[existing, updated]),
        patch.object(action_items_db, 'update_action_item', return_value=True) as update,
        patch.object(developer_module, 'sync_action_item_reminder') as sync,
    ):
        result = developer_module.update_action_item('a1', request, uid='uid1')

    assert 'due_at' not in request.model_fields_set
    assert update.call_args.args[2] == {'description': 'Updated task'}
    sync.assert_not_called()
    assert result['due_at'] == due


def test_developer_patch_replaces_due_date_when_supplied():
    existing, _ = _update_fixture()
    replacement = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
    updated = {**existing, 'due_at': replacement}
    request = developer_module.UpdateActionItemRequest(due_at=replacement)

    with (
        patch.object(action_items_db, 'get_action_item', side_effect=[existing, updated]),
        patch.object(action_items_db, 'update_action_item', return_value=True) as update,
        patch.object(developer_module, 'sync_action_item_reminder') as sync,
    ):
        result = developer_module.update_action_item('a1', request, uid='uid1')

    assert update.call_args.args[2] == {'due_at': replacement}
    sync.assert_called_once()
    assert sync.call_args.kwargs['due_at'] == replacement
    assert result['due_at'] == replacement


def test_developer_patch_rejects_empty_payload():
    existing, _ = _update_fixture()
    request = developer_module.UpdateActionItemRequest()

    with patch.object(action_items_db, 'get_action_item', return_value=existing):
        with pytest.raises(HTTPException) as exc:
            developer_module.update_action_item('a1', request, uid='uid1')

    assert exc.value.status_code == 422
    assert exc.value.detail == 'At least one field must be provided'
