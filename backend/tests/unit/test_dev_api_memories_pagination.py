"""Regression test for GET /v1/dev/user/memories resilience (issue #7492).

The endpoint declares response_model=List[CleanerMemory] and returned raw Firestore dicts, so a
single malformed/legacy record (missing a required field or an out-of-enum category) made FastAPI
raise ResponseValidationError -> HTTP 500 for the whole page (only the offsets containing that record
failed). The handler now validates each record and skips+logs invalid ones, mirroring GET /v3/memories.
"""

import os
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

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


def _invalid_memory(mid):
    # Legacy/malformed record missing a required CleanerMemory field ('edited').
    m = _valid_memory(mid)
    del m['edited']
    return m


def _build():
    app = FastAPI()
    app.include_router(developer_router)
    app.dependency_overrides[get_uid_with_memories_read] = lambda: 'uid1'
    return TestClient(app, raise_server_exceptions=False)


def test_invalid_record_is_skipped_not_500():
    page = [_valid_memory('good1'), _invalid_memory('bad1'), _valid_memory('good2')]
    with patch.object(memories_db, 'get_memories', return_value=page):
        client = _build()
        resp = client.get('/v1/dev/user/memories')
    assert resp.status_code == 200
    assert [m['id'] for m in resp.json()] == ['good1', 'good2']


def test_all_valid_records_returned():
    page = [_valid_memory('a'), _valid_memory('b')]
    with patch.object(memories_db, 'get_memories', return_value=page):
        client = _build()
        resp = client.get('/v1/dev/user/memories')
    assert resp.status_code == 200
    assert len(resp.json()) == 2
