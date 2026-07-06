"""Unit tests for Phase 3 per-person on-demand retrieval:

- ``person_service.search_person_memories`` — person-scoped semantic search that
  hydrates vector hits and filters out invalidated memories.
- ``person_service.get_person_context(query=...)`` — semantic ranking of the facts
  block while the default (no-query) path stays byte-for-byte unchanged.
- ``routers/mcp.py`` ``GET /v1/mcp/people/context`` handler — auth fail-closed +
  delegation to the service.

Follows the heavy-dependency stubbing pattern in test_mcp_data_endpoints.py so
``routers.mcp`` (and its new person_service import) load without real GCP creds.
"""

import os
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _ensure_package_path(name, path):
    module = sys.modules.get(name)
    if not isinstance(module, ModuleType):
        module = ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [path]
    if '.' in name:
        parent_name, child_name = name.rsplit('.', 1)
        parent = sys.modules.setdefault(parent_name, ModuleType(parent_name))
        setattr(parent, child_name, module)
    return module


_ensure_package_path('utils', os.path.join(_BACKEND_DIR, 'utils'))
_ensure_package_path('utils.retrieval', os.path.join(_BACKEND_DIR, 'utils', 'retrieval'))
_ensure_package_path('utils.retrieval.tool_services', os.path.join(_BACKEND_DIR, 'utils', 'retrieval', 'tool_services'))
_ensure_package_path('models', os.path.join(_BACKEND_DIR, 'models'))

_stubs = [
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
    'database.mcp_oauth',
    'database.daily_summaries',
    'database.screen_activity',
    'database.x_posts',
    'database.fair_use',
    'database.auth',
    'database.dev_api_key',
    'database.entities',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google',
    'google.cloud',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'utils.other.storage',
    'utils.other.endpoints',
    'utils.stt.pre_recorded',
    'utils.stt.vad',
    'utils.fair_use',
    'utils.subscription',
    'utils.conversations.process_conversation',
    'utils.conversations.render',
    'utils.notifications',
    'utils.apps',
    'utils.llm.memories',
    'utils.llm.chat',
    'utils.log_sanitizer',
    'utils.executors',
    'dependencies',
]
for _mod_name in _stubs:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = _AutoMockModule(_mod_name)

# person_service imports these names at module top; make the stubs provide them.
sys.modules['database.entities'].person_entity_id = lambda pid: f"person:{pid}"
sys.modules['utils.log_sanitizer'].sanitize_pii = lambda v: v
sys.modules['dependencies'].get_uid_from_mcp_api_key = MagicMock(return_value='user-1')
sys.modules['dependencies'].get_current_user_id = MagicMock(return_value='user-1')
sys.modules['utils.other.endpoints'].with_rate_limit = MagicMock(side_effect=lambda dependency, _policy: dependency)
sys.modules['utils.other.endpoints'].with_rate_limit_context = MagicMock(
    side_effect=lambda dependency, _policy: dependency
)
for _exc in (
    'InvalidIdTokenError',
    'ExpiredIdTokenError',
    'RevokedIdTokenError',
    'CertificateFetchError',
    'UserNotFoundError',
):
    setattr(sys.modules['firebase_admin.auth'], _exc, type(_exc, (Exception,), {}))

# models.transcript_segment / models.other are real modules used by person_service;
# leave them un-stubbed so Person / TranscriptSegment behave normally.

import utils.retrieval.tool_services.person_service as ps  # noqa: E402
from routers import mcp as rest  # noqa: E402

UID = 'user-1'
PID = 'p1'


# ---------------------------------------------------------------------------
# search_person_memories
# ---------------------------------------------------------------------------


def test_search_returns_person_scoped_hydrated_active_hits():
    # vector search returns two hits; one hydrates to an invalidated memory (dropped),
    # one to an active memory (kept). Ordering follows the vector ranking.
    hits = [{'memory_id': 'm_active', 'score': 0.9}, {'memory_id': 'm_invalid', 'score': 0.8}]

    def _get_memory(uid, memory_id, **kwargs):
        if memory_id == 'm_active':
            return {'id': 'm_active', 'content': 'Loves rock climbing', 'invalid_at': None}
        return {'id': 'm_invalid', 'content': 'Old stale fact', 'invalid_at': 'yesterday'}

    with patch.object(ps.vector_db, 'find_similar_memories', return_value=hits) as vsearch, patch.object(
        ps.memories_db, 'get_memory', side_effect=_get_memory
    ):
        out = ps.search_person_memories(UID, PID, 'hobbies', limit=10)

    # Scoped to this person's subject entity, low threshold.
    _, kwargs = vsearch.call_args
    assert kwargs['subject_entity_id'] == 'person:p1'
    assert kwargs['threshold'] <= 0.3
    assert kwargs['limit'] == 10

    assert [m['content'] for m in out] == ['Loves rock climbing']


def test_search_guards_return_empty():
    assert ps.search_person_memories(UID, '', 'q') == []
    assert ps.search_person_memories(UID, PID, '') == []
    with patch.object(ps.vector_db, 'find_similar_memories', side_effect=RuntimeError('boom')):
        assert ps.search_person_memories(UID, PID, 'q') == []


# ---------------------------------------------------------------------------
# get_person_context — query vs no-query
# ---------------------------------------------------------------------------

_PERSON = {'id': PID, 'name': 'Alice', 'relationship': 'friend'}
_FLAT_FACTS = [{'content': 'Alice lives in NYC'}, {'content': 'Alice is a designer'}]


def _resolve_patches():
    return (
        patch.object(ps.users_db, 'get_person', return_value=_PERSON),
        patch.object(ps.users_db, 'get_person_by_handle', return_value=None),
        patch.object(ps.users_db, 'get_people_by_name', return_value=[]),
        patch.object(ps.conversations_db, 'get_conversations_by_person_id', return_value=[]),
    )


def test_no_query_path_is_unchanged():
    # The default path must not call the vector search at all, and must emit the flat
    # recency-ordered facts exactly as before.
    p1, p2, p3, p4 = _resolve_patches()
    with p1, p2, p3, p4, patch.object(
        ps.memories_db, 'get_memories_by_subject_entity', return_value=_FLAT_FACTS
    ), patch.object(ps.vector_db, 'find_similar_memories') as vsearch:
        out = ps.get_person_context(UID, 'Alice')

    vsearch.assert_not_called()
    assert isinstance(out, str)
    assert '- Alice lives in NYC' in out
    assert '- Alice is a designer' in out
    # Untrusted fencing preserved.
    assert '<untrusted_facts>' in out
    # Flat recency order preserved (NYC before designer).
    assert out.index('Alice lives in NYC') < out.index('Alice is a designer')


def test_query_path_prioritizes_semantic_hits_and_dedupes():
    # Semantic search surfaces the "designer" fact first; the flat list then tops up
    # without duplicating it.
    semantic = [{'content': 'Alice is a designer', 'invalid_at': None}]
    p1, p2, p3, p4 = _resolve_patches()
    with p1, p2, p3, p4, patch.object(
        ps.memories_db, 'get_memories_by_subject_entity', return_value=_FLAT_FACTS
    ), patch.object(ps, 'search_person_memories', return_value=semantic):
        out = ps.get_person_context(UID, 'Alice', query='what does she do')

    assert isinstance(out, str)
    # Semantic hit ranked ahead of the flat NYC fact.
    assert out.index('Alice is a designer') < out.index('Alice lives in NYC')
    # No duplicate of the semantic fact.
    assert out.count('- Alice is a designer') == 1


def test_query_path_falls_back_when_search_empty():
    p1, p2, p3, p4 = _resolve_patches()
    with p1, p2, p3, p4, patch.object(
        ps.memories_db, 'get_memories_by_subject_entity', return_value=_FLAT_FACTS
    ), patch.object(ps, 'search_person_memories', return_value=[]):
        out = ps.get_person_context(UID, 'Alice', query='anything')

    assert '- Alice lives in NYC' in out
    assert '- Alice is a designer' in out


# ---------------------------------------------------------------------------
# MCP route handler
# ---------------------------------------------------------------------------


class _Grant:
    def __init__(self, allowed, status_code=403):
        self.allowed = allowed
        self.status_code = status_code
        self.observability = {'reason': 'denied'}


class _AuthCtx:
    uid = UID


def test_route_delegates_to_service_when_authorized():
    with patch.object(rest, 'authorize_memory_external_default_memory_read', return_value=_Grant(True)), patch.object(
        rest, 'get_person_context', return_value='CTX'
    ) as svc:
        res = rest.get_person_context_route(ref='Alice', query='plans', auth_context=_AuthCtx())

    assert res == {'context': 'CTX'}
    svc.assert_called_once_with(UID, 'Alice', query='plans')


def test_route_fails_closed_when_unauthorized():
    with patch.object(
        rest, 'authorize_memory_external_default_memory_read', return_value=_Grant(False, status_code=403)
    ), patch.object(rest, 'get_person_context') as svc:
        with pytest.raises(rest.HTTPException) as exc:
            rest.get_person_context_route(ref='Alice', query=None, auth_context=_AuthCtx())

    assert exc.value.status_code == 403
    svc.assert_not_called()
