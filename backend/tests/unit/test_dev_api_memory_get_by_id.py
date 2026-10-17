"""Regression tests for GET /v1/dev/user/memories/{memory_id}.

Covers the direct single-memory read: the validated memory shape is returned,
the existing memory-read authorization/policy gates the route, missing or
malformed records fail closed with 404 (never a 500), and the literal
/memories/vector/search route still matches before the {memory_id} route.
"""

import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _ensure_package_path(name: str, path: Path) -> ModuleType:
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


def _drop_stale_module(name: str, expected_file: Path) -> None:
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

# utils.other.endpoints must expose real callables (used in route signatures); provide stand-ins
# without replacing an existing stub that another test may inspect later.
_endpoints = sys.modules.get('utils.other.endpoints')
if _endpoints is None:
    _endpoints = ModuleType('utils.other.endpoints')
    sys.modules['utils.other.endpoints'] = _endpoints


def _fake_get_current_user_uid():  # pragma: no cover - dependency stand-in
    return 'uid1'


def _fake_with_rate_limit(dependency, _policy):  # pragma: no cover - returns wrapped dependency
    return dependency


if not hasattr(_endpoints, 'get_current_user_uid'):
    _endpoints.get_current_user_uid = _fake_get_current_user_uid
if not hasattr(_endpoints, 'with_rate_limit'):
    _endpoints.with_rate_limit = _fake_with_rate_limit
if not hasattr(_endpoints, 'with_rate_limit_context'):
    setattr(_endpoints, 'with_rate_limit_context', _fake_with_rate_limit)
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

from datetime import datetime, timezone  # noqa: E402

from models.memories import MemoryCategory  # noqa: E402  (real model; stubs prevent google init)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from routers.developer import router as developer_router  # noqa: E402
import routers.developer as developer_module  # noqa: E402
from dependencies import get_developer_memory_default_memory_read_context  # noqa: E402
from utils.memory.product_authorization import ProductAuthorizationDecision  # noqa: E402
from utils.memory.default_read_rollout import MemoryReadDecision  # noqa: E402

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


def _grant(allowed, status_code=200, reason='universal_memory'):
    auth_context = developer_module.ProductAuthorizationContext(
        uid='uid1', consumer='developer_api', surface='developer_api', app_id='test-app', key_id='test-key'
    )
    return auth_context, ProductAuthorizationDecision(
        allowed=allowed,
        context=auth_context,
        db_client=None,
        read_decision=MemoryReadDecision.USE_MEMORY,
        reason=reason,
        observability={'enabled': allowed},
        status_code=status_code,
    )


def _build(fetch_result=None, fetch_error=None, grant_allowed=True, monkeypatch=None):
    from fastapi import HTTPException  # noqa: E402

    auth_context, decision = _grant(grant_allowed, status_code=200 if grant_allowed else 403)
    developer_module.authorize_memory_external_default_memory_read = MagicMock(return_value=decision)
    fetch_mock = MagicMock()
    if fetch_error is not None:
        fetch_mock.side_effect = fetch_error
    else:
        fetch_mock.return_value = fetch_result
    monkeypatch.setattr(developer_module, 'fetch_memory_dict', fetch_mock)
    app = FastAPI()
    app.include_router(developer_router)
    app.dependency_overrides[get_developer_memory_default_memory_read_context] = lambda: auth_context
    return TestClient(app, raise_server_exceptions=False), fetch_mock


def test_get_by_id_returns_validated_memory(monkeypatch):
    client, fetch_mock = _build(fetch_result=_valid_memory('m1'), monkeypatch=monkeypatch)
    resp = client.get('/v1/dev/user/memories/m1')
    assert resp.status_code == 200
    body = resp.json()
    assert body['id'] == 'm1'
    assert body['content'] == 'a memory'
    assert body['visibility'] == 'private'
    assert fetch_mock.call_args.args[0] == 'uid1'
    assert fetch_mock.call_args.args[1] == 'm1'


def test_get_by_id_missing_returns_404(monkeypatch):
    from fastapi import HTTPException  # noqa: E402

    client, _ = _build(fetch_error=HTTPException(status_code=404, detail='Memory not found'), monkeypatch=monkeypatch)
    resp = client.get('/v1/dev/user/memories/does-not-exist')
    assert resp.status_code == 404


def test_get_by_id_malformed_record_returns_404_not_500(monkeypatch):
    # A record that cannot be represented in the current validated shape must
    # fail closed like the list endpoint's malformed-record hardening — 404,
    # never a 500 from response validation.
    bad = _valid_memory('bad1')
    del bad['id']
    client, _ = _build(fetch_result=bad, monkeypatch=monkeypatch)
    resp = client.get('/v1/dev/user/memories/bad1')
    assert resp.status_code == 404


def test_get_by_id_denied_grant_fails_closed_before_read(monkeypatch):
    client, fetch_mock = _build(fetch_result=_valid_memory('m1'), grant_allowed=False, monkeypatch=monkeypatch)
    resp = client.get('/v1/dev/user/memories/m1')
    assert resp.status_code == 403
    fetch_mock.assert_not_called()


def test_vector_search_route_still_matches_before_get_by_id():  # FastAPI matches routes in registration order: /memories/vector/search
    # must stay ahead of the GET /memories/{memory_id} route or the literal
    # "vector/search" path would be swallowed by the id parameter.
    routes = list(developer_router.routes)

    def _is_get(route, path):
        return getattr(route, 'path', None) == path and 'GET' in getattr(route, 'methods', set())

    search = [r for r in routes if _is_get(r, '/v1/dev/user/memories/vector/search')]
    get_by_id = [r for r in routes if _is_get(r, '/v1/dev/user/memories/{memory_id}')]
    assert len(search) == 1, 'expected exactly one GET /memories/vector/search route'
    assert len(get_by_id) == 1, 'expected exactly one GET /memories/{memory_id} route'
    assert routes.index(search[0]) < routes.index(get_by_id[0])


def test_get_memory_operation_id_is_unique():
    # OpenAPI operation_ids must be unique across the developer router.
    from collections import Counter  # noqa: E402

    op_ids = [r.operation_id for r in developer_router.routes if getattr(r, 'operation_id', None)]
    dupes = [op for op, count in Counter(op_ids).items() if count > 1]
    assert dupes == []
    assert 'getMemory' in op_ids
