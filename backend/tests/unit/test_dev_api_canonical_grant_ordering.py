"""Regression tests for Developer API canonical-cohort grant-check ordering.

Verifies that the Developer API default-memory read endpoints enforce the
persisted app/key grant (authorize_memory_external_default_memory_read)
*before* branching to the canonical memory system, so a canonical-cohort
user holding a legacy/read-only Developer key without a stored default-read
grant is denied instead of receiving canonical memories before authorization.

Addresses Codex P1 feedback on PR #8429:
- "Gate canonical Developer API listing with grants"
- "Gate canonical Developer vector search with grants"
"""

import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

os.environ.setdefault('OPENAI_API_KEY', '***')
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
_stub_module_snapshot = {name: sys.modules.get(name) for name in _stubs}
_stub_parent_attr_snapshot = {}
for _stub_name in _stubs:
    if '.' in _stub_name:
        _parent_name, _child_name = _stub_name.rsplit('.', 1)
        _parent = sys.modules.get(_parent_name)
        if isinstance(_parent, ModuleType):
            _stub_parent_attr_snapshot[_stub_name] = getattr(_parent, _child_name, None)
        else:
            _stub_parent_attr_snapshot[_stub_name] = None

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

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import routers.developer as developer_module  # noqa: E402
from routers.developer import router as developer_router  # noqa: E402
from dependencies import get_developer_memory_default_memory_read_context  # noqa: E402
from utils.memory.product_authorization import (  # noqa: E402
    AppKeyScopeGrantDecision,
    MemoryGrantOperation,
    ProductAuthorizationContext,
)

from models.memories import MemoryCategory  # noqa: E402  (real model)

import pytest  # noqa: E402

_VALID_CATEGORY = next(iter(MemoryCategory)).value


@pytest.fixture(scope='module', autouse=True)
def _restore_import_stubs():
    yield
    for name, original in _stub_module_snapshot.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original
        if '.' not in name:
            continue
        parent_name, child_name = name.rsplit('.', 1)
        parent = sys.modules.get(parent_name)
        if not isinstance(parent, ModuleType):
            continue
        original_parent_attr = _stub_parent_attr_snapshot.get(name)
        if original_parent_attr is None:
            try:
                delattr(parent, child_name)
            except AttributeError:
                pass
        else:
            setattr(parent, child_name, original_parent_attr)


# Save originals so tests can mutate the module and restore after.
_ORIG_AUTHORIZE = developer_module.authorize_memory_external_default_memory_read
_ORIG_PIN_MEMORY_SYSTEM = developer_module.pin_memory_system
_ORIG_LIST_WITH_LOCKED_PREVIEW = developer_module.memorydb_list_with_locked_preview
_ORIG_SEARCH_MEMORIES = developer_module.search_memory_default_developer_memories
_ORIG_SEARCH_MEMORIES_VECTOR = getattr(developer_module, 'search_memory_default_developer_memories_vector', None)


@pytest.fixture(autouse=True)
def _restore_developer_module():
    """Restore developer module attributes after each test to prevent cross-test pollution."""
    yield
    developer_module.authorize_memory_external_default_memory_read = _ORIG_AUTHORIZE
    developer_module.pin_memory_system = _ORIG_PIN_MEMORY_SYSTEM
    developer_module.memorydb_list_with_locked_preview = _ORIG_LIST_WITH_LOCKED_PREVIEW
    developer_module.search_memory_default_developer_memories = _ORIG_SEARCH_MEMORIES
    if _ORIG_SEARCH_MEMORIES_VECTOR is not None:
        developer_module.search_memory_default_developer_memories_vector = _ORIG_SEARCH_MEMORIES_VECTOR


def _auth_context():
    return ProductAuthorizationContext(
        uid='uid1',
        consumer='developer_api',
        surface='developer_api',
        app_id='test-app',
        key_id='test-key',
        scopes=('memories.read',),
    )


def _denied_grant():
    return AppKeyScopeGrantDecision(
        allowed=False,
        context=_auth_context(),
        operation=MemoryGrantOperation.DEFAULT_READ,
        reason='no_stored_default_read_grant',
        required_scope='memories.read',
        observability={'enabled': False},
        grant_path='test_denied',
        status_code=403,
    )


def _build(deny_grant=False, canonical=False):
    auth_context = _auth_context()
    if deny_grant:
        developer_module.authorize_memory_external_default_memory_read = MagicMock(return_value=_denied_grant())
    else:
        developer_module.authorize_memory_external_default_memory_read = MagicMock(
            return_value=AppKeyScopeGrantDecision(
                allowed=True,
                context=auth_context,
                operation=MemoryGrantOperation.DEFAULT_READ,
                reason='ok',
                required_scope='memories.read',
                observability={'enabled': True},
                grant_path='test_allowed',
                status_code=200,
            )
        )
    developer_module.pin_memory_system = MagicMock(
        return_value=developer_module.MemorySystem.CANONICAL if canonical else developer_module.MemorySystem.LEGACY
    )
    developer_module.memorydb_list_with_locked_preview = MagicMock(side_effect=lambda x: x)
    developer_module.search_memory_default_developer_memories = MagicMock(
        return_value=type(
            'LegacySafeMemoryResult',
            (),
            {
                'read_decision': developer_module.MemoryReadDecision.USE_LEGACY_SAFE,
                'memories': [],
                'fallback_reason': 'test_legacy_safe',
                'should_use_legacy_fallback': True,
            },
        )()
    )
    developer_module.search_memory_default_developer_memories_vector = MagicMock(
        return_value=type(
            'VectorLegacySafeResult',
            (),
            {
                'read_decision': developer_module.MemoryReadDecision.USE_LEGACY_SAFE,
                'memories': [],
                'fallback_reason': 'test_legacy_safe',
                'should_use_legacy_fallback': True,
            },
        )()
    )

    app = FastAPI()
    app.include_router(developer_router)
    app.dependency_overrides[get_developer_memory_default_memory_read_context] = lambda: auth_context
    return TestClient(app, raise_server_exceptions=False)


# =============================================================================
# GET /v1/dev/user/memories — grant must run before canonical listing
# =============================================================================


def test_get_memories_denied_grant_blocks_canonical_listing():
    """A canonical-cohort user with a denied grant must get 403, not canonical memories.

    This is the core security regression: before the fix, the canonical branch
    returned memories before authorize_memory_external_default_memory_read ran.
    """
    client = _build(deny_grant=True, canonical=True)
    resp = client.get('/v1/dev/user/memories')
    assert resp.status_code == 403
    body = resp.json()
    assert body['detail']['enabled'] is False
    assert body['detail']['reason'] == 'no_stored_default_read_grant'
    assert body['detail']['app_id'] == 'test-app'
    assert body['detail']['key_id'] == 'test-key'
    # The grant check ran and denied; pin_memory_system must NOT have been called
    # because the denial short-circuits before the memory-system branch. This proves
    # the grant check runs ahead of the canonical listing.
    assert developer_module.authorize_memory_external_default_memory_read.called
    assert not developer_module.pin_memory_system.called


def test_get_memories_allowed_grant_canonical_lists():
    """A canonical-cohort user with an allowed grant gets memories normally."""
    from datetime import datetime, timezone

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # MemoryService.read() returns List[MemoryDB]; the router calls .dict() on each
    from models.memories import MemoryDB

    canonical_memory = MemoryDB(
        id='canon-1',
        uid='uid1',
        content='a canonical memory',
        category=_VALID_CATEGORY,
        visibility='private',
        tags=[],
        created_at=now,
        updated_at=now,
        manually_added=False,
        scoring=None,
    )

    client = _build(deny_grant=False, canonical=True)

    # MemoryService is a real class; mock its read method via patching the class
    with __import__('unittest.mock', fromlist=['patch']).patch.object(
        developer_module.MemoryService, 'read', return_value=[canonical_memory]
    ):
        resp = client.get('/v1/dev/user/memories')

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]['id'] == 'canon-1'


def test_get_memories_missing_rollout_state_has_actionable_contract():
    """A valid memory-read key must not look invalid when account rollout is absent."""
    client = _build()

    developer_module.search_memory_default_developer_memories = MagicMock(
        return_value=type(
            'DeniedMemoryResult',
            (),
            {
                'read_decision': developer_module.MemoryReadDecision.DENY_MEMORY,
                'memories': [],
                'fallback_reason': 'missing_rollout_state',
                'should_use_legacy_fallback': False,
            },
        )()
    )

    resp = client.get('/v1/dev/user/memories')

    assert resp.status_code == 403
    detail = resp.json()['detail']
    assert detail['code'] == 'developer_memory_access_not_ready'
    assert detail['reason'] == 'missing_rollout_state'
    assert 'key can be valid and correctly scoped' in detail['message']
    assert developer_module.authorize_memory_external_default_memory_read.called


def test_search_memories_vector_missing_rollout_state_has_actionable_contract():
    """Vector search uses the same account-readiness error after a valid key grant."""
    client = _build()

    developer_module.search_memory_default_developer_memories_vector = MagicMock(
        return_value=type(
            'DeniedVectorMemoryResult',
            (),
            {
                'read_decision': developer_module.MemoryReadDecision.DENY_MEMORY,
                'memories': [],
                'fallback_reason': 'missing_rollout_state',
                'should_use_legacy_fallback': False,
            },
        )()
    )

    resp = client.get('/v1/dev/user/memories/vector/search', params={'query': 'memory'})

    assert resp.status_code == 403
    detail = resp.json()['detail']
    assert detail['code'] == 'developer_memory_access_not_ready'
    assert detail['reason'] == 'missing_rollout_state'
    assert 'key can be valid and correctly scoped' in detail['message']


# =============================================================================
# GET /v1/dev/user/memories/vector/search — grant must run before canonical search
# =============================================================================


def test_search_memories_vector_denied_grant_blocks_canonical_search():
    """A canonical-cohort user with a denied grant must get 403, not canonical search results.

    This is the vector-search counterpart of the listing regression: before the
    fix, the canonical branch returned search results before the grant check.
    """
    client = _build(deny_grant=True, canonical=True)
    resp = client.get('/v1/dev/user/memories/vector/search', params={'query': 'secret'})
    assert resp.status_code == 403
    body = resp.json()
    assert body['detail']['enabled'] is False
    assert body['detail']['reason'] == 'no_stored_default_read_grant'
    assert body['detail']['app_id'] == 'test-app'
    assert body['detail']['key_id'] == 'test-key'
    assert developer_module.authorize_memory_external_default_memory_read.called


def test_search_memories_vector_allowed_grant_canonical_searches():
    """A canonical-cohort user with an allowed grant gets search results normally."""
    from datetime import datetime, timezone

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    from models.memories import MemoryDB
    from utils.memory.memory_service import MemorySearchMatch

    canonical_memory = MemoryDB(
        id='canon-search-1',
        uid='uid1',
        content='a canonical search result',
        category=_VALID_CATEGORY,
        visibility='private',
        tags=[],
        created_at=now,
        updated_at=now,
        manually_added=False,
        scoring=None,
    )
    mock_match = MemorySearchMatch(memory=canonical_memory, score=0.95)

    client = _build(deny_grant=False, canonical=True)

    with __import__('unittest.mock', fromlist=['patch']).patch.object(
        developer_module.MemoryService, 'search', return_value=[mock_match]
    ):
        resp = client.get('/v1/dev/user/memories/vector/search', params={'query': 'test', 'limit': 5})

    assert resp.status_code == 200
    body = resp.json()
    assert body['returned_count'] == 1
    assert body['items'][0]['id'] == 'canon-search-1'
    assert body['items'][0]['relevance_score'] == 0.95
