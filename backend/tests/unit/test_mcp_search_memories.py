"""Unit tests for the search_memories MCP endpoint.

Tests the endpoint logic with mocked database calls,
following the pattern in test_lock_bypass_fixes.py.
"""

from unittest.mock import patch, MagicMock
import os
import pytest
import sys
from types import ModuleType, SimpleNamespace

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

from tests.unit.memory_import_isolation import (
    install_mcp_search_memories_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)

_MCP_STUB_NAMES = [
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
    'database.dev_api_key',
    'firebase_admin',
    'firebase_admin.messaging',
    'firebase_admin.auth',
    'google.cloud.firestore',
    'google.cloud.firestore_v1',
    'google.cloud.firestore_v1.FieldFilter',
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
    'routers.mcp',
    'utils',
    'utils.retrieval',
    'models',
]

mcp_router = None
search_memories = None
delete_memory = None
edit_memory = None


@pytest.fixture(scope='module', autouse=True)
def _mcp_search_import_isolation():
    saved = snapshot_sys_modules(_MCP_STUB_NAMES)
    install_mcp_search_memories_stubs(_BACKEND_DIR)
    import routers.mcp as mcp_router_mod
    from routers.mcp import search_memories as search_memories_fn
    from routers.mcp import delete_memory as delete_memory_fn
    from routers.mcp import edit_memory as edit_memory_fn

    def _allow_memory_auth(_auth_context, db_client=None):
        return SimpleNamespace(allowed=True, status_code=200, observability={})

    def _legacy_safe_vector_result(*_args, **_kwargs):
        return SimpleNamespace(read_decision=mcp_router_mod.MemoryReadDecision.USE_LEGACY_SAFE, memories=[])

    def _allow_legacy_write(*_args, **_kwargs):
        return SimpleNamespace(allowed=True, status_code=200, detail={})

    mcp_router_mod.authorize_memory_external_default_memory_read = _allow_memory_auth
    mcp_router_mod.authorize_memory_external_default_memory_write = _allow_memory_auth
    mcp_router_mod.read_default_read_rollout = MagicMock(
        return_value=SimpleNamespace(read_decision=mcp_router_mod.MemoryReadDecision.USE_LEGACY_SAFE)
    )
    mcp_router_mod.search_default_mcp_memories_vector = MagicMock(side_effect=_legacy_safe_vector_result)
    mcp_router_mod.guard_legacy_memory_write = MagicMock(side_effect=_allow_legacy_write)

    globals()['mcp_router'] = mcp_router_mod
    globals()['search_memories'] = search_memories_fn
    globals()['delete_memory'] = delete_memory_fn
    globals()['edit_memory'] = edit_memory_fn
    yield
    restore_sys_modules(saved)
    sys.modules.pop('routers.mcp', None)
    globals()['mcp_router'] = None
    globals()['search_memories'] = None
    globals()['delete_memory'] = None
    globals()['edit_memory'] = None


def _auth_context(uid: str = "user-1"):
    return mcp_router.ProductAuthorizationContext(
        uid=uid,
        consumer="mcp",
        surface="unit_test",
        app_id="test-app",
        key_id="test-key",
        scopes=("memories.read", "memories.write"),
    )


class TestSearchMemoriesEndpoint:
    def _make_memory(self, memory_id='mem-1', content='Test memory content', category='other', locked=False):
        return {
            'id': memory_id,
            'content': content,
            'category': category,
            'is_locked': locked,
        }

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_returns_empty_when_no_matches(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = []
        result = search_memories(query="test", limit=10, auth_context=_auth_context())
        assert result == []
        # limit=10 → fetch_limit = min(10*3, 60) = 30
        mock_vector_db.find_similar_memories.assert_called_once_with("user-1", "test", threshold=0.0, limit=30)

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_returns_ranked_results(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'category': 'work', 'score': 0.95},
            {'memory_id': 'mem-2', 'category': 'hobbies', 'score': 0.80},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            self._make_memory('mem-1', 'Work memory', 'work'),
            self._make_memory('mem-2', 'Hobby memory', 'hobbies'),
        ]
        result = search_memories(query="work stuff", limit=10, auth_context=_auth_context())
        assert len(result) == 2
        assert result[0]['id'] == 'mem-1'
        assert result[0]['relevance_score'] == 0.95
        assert result[1]['id'] == 'mem-2'
        assert result[1]['relevance_score'] == 0.80

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_locked_memory_excluded_from_search(self, mock_vector_db, mock_memories_db):
        # Search drops locked hits entirely (matches tool_services/memories.py behaviour);
        # even short content must not leak via an MCP API key.
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'category': 'other', 'score': 0.9},
            {'memory_id': 'mem-2', 'category': 'other', 'score': 0.8},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            self._make_memory('mem-1', 'Short locked', 'other', locked=True),
            self._make_memory('mem-2', 'Unlocked memory', 'other', locked=False),
        ]
        result = search_memories(query="test", limit=10, auth_context=_auth_context())
        assert len(result) == 1
        assert result[0]['id'] == 'mem-2'

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_limit_capped_at_20_fetches_60_candidates(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = []
        search_memories(query="test", limit=100, auth_context=_auth_context())
        # limit clamps to 20, fetch_limit = min(20*3, 60) = 60
        mock_vector_db.find_similar_memories.assert_called_once_with("user-1", "test", threshold=0.0, limit=60)

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_limit_zero_clamped_to_1_fetches_3_candidates(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = []
        search_memories(query="test", limit=0, auth_context=_auth_context())
        # limit clamps to 1, fetch_limit = min(1*3, 60) = 3
        mock_vector_db.find_similar_memories.assert_called_once_with("user-1", "test", threshold=0.0, limit=3)

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_negative_limit_clamped_to_1_fetches_3_candidates(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = []
        search_memories(query="test", limit=-5, auth_context=_auth_context())
        # limit clamps to 1, fetch_limit = min(1*3, 60) = 3
        mock_vector_db.find_similar_memories.assert_called_once_with("user-1", "test", threshold=0.0, limit=3)

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_results_sorted_by_relevance_desc(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.5},
            {'memory_id': 'mem-2', 'score': 0.99},
            {'memory_id': 'mem-3', 'score': 0.75},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            self._make_memory('mem-1', 'Low relevance'),
            self._make_memory('mem-2', 'High relevance'),
            self._make_memory('mem-3', 'Mid relevance'),
        ]
        result = search_memories(query="test", limit=10, auth_context=_auth_context())
        assert [r['relevance_score'] for r in result] == [0.99, 0.75, 0.5]

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_skips_matches_with_no_memory_id(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.9},
            {'category': 'other', 'score': 0.5},
            {'memory_id': None, 'score': 0.3},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            self._make_memory('mem-1', 'Valid memory'),
        ]
        result = search_memories(query="test", limit=10, auth_context=_auth_context())
        assert len(result) == 1
        assert result[0]['id'] == 'mem-1'
        mock_memories_db.get_memories_by_ids.assert_called_once_with("user-1", ['mem-1'])

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_returns_empty_when_all_ids_filtered(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'category': 'other', 'score': 0.5},
        ]
        result = search_memories(query="test", limit=10, auth_context=_auth_context())
        assert result == []
        mock_memories_db.get_memories_by_ids.assert_not_called()

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_default_limit_fetches_3x_candidates(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = []
        search_memories(query="test", auth_context=_auth_context())
        # default limit=10, fetch_limit = min(10*3, 60) = 30
        mock_vector_db.find_similar_memories.assert_called_once_with("user-1", "test", threshold=0.0, limit=30)

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_locked_top_hit_does_not_exhaust_budget(self, mock_vector_db, mock_memories_db):
        # Reviewer's exact scenario: best Pinecone hit is locked, second is accessible.
        # With exact-limit fetching this returned [], now returns the accessible memory.
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-locked', 'score': 0.99},
            {'memory_id': 'mem-ok', 'score': 0.80},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            self._make_memory('mem-locked', 'secret', 'other', locked=True),
            self._make_memory('mem-ok', 'visible', 'other', locked=False),
        ]
        result = search_memories(query="test", limit=1, auth_context=_auth_context())
        assert len(result) == 1
        assert result[0]['id'] == 'mem-ok'


class TestSearchMemoriesUserReview:
    """search_memories must not surface memories the user explicitly rejected."""

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_rejected_memory_excluded(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.9},
            {'memory_id': 'mem-2', 'score': 0.8},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            {'id': 'mem-1', 'content': 'accepted', 'category': 'other', 'is_locked': False, 'user_review': True},
            {'id': 'mem-2', 'content': 'rejected', 'category': 'other', 'is_locked': False, 'user_review': False},
        ]
        result = search_memories(query="test", limit=10, auth_context=_auth_context())
        assert len(result) == 1
        assert result[0]['id'] == 'mem-1'

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_unreviewed_memory_included(self, mock_vector_db, mock_memories_db):
        # user_review=None means not yet reviewed — should still appear
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.9},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            {'id': 'mem-1', 'content': 'pending review', 'category': 'other', 'is_locked': False},
        ]
        result = search_memories(query="test", limit=10, auth_context=_auth_context())
        assert len(result) == 1

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_all_rejected_returns_empty(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.9},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            {'id': 'mem-1', 'content': 'rejected', 'category': 'other', 'is_locked': False, 'user_review': False},
        ]
        result = search_memories(query="test", limit=10, auth_context=_auth_context())
        assert result == []


class TestSearchMemoriesInvalidated:
    """search_memories must not surface superseded/invalidated memories — the brain
    only returns facts that are currently true."""

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_invalidated_memory_excluded(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-old', 'score': 0.95},
            {'memory_id': 'mem-new', 'score': 0.80},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            # superseded "loves ice cream" — higher vector score but invalidated
            {
                'id': 'mem-old',
                'content': 'loves ice cream',
                'category': 'system',
                'is_locked': False,
                'invalid_at': '2026-06-01T00:00:00+00:00',
                'superseded_by': 'mem-new',
            },
            {'id': 'mem-new', 'content': 'hates ice cream', 'category': 'system', 'is_locked': False},
        ]
        result = search_memories(query="ice cream", limit=10, auth_context=_auth_context())
        assert len(result) == 1
        assert result[0]['id'] == 'mem-new'

    @patch('utils.memory.memory_service.memories_db')
    @patch('utils.memory.memory_service.vector_db')
    def test_active_memory_with_null_invalid_at_included(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.9},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            {'id': 'mem-1', 'content': 'active', 'category': 'system', 'is_locked': False, 'invalid_at': None},
        ]
        result = search_memories(query="test", limit=10, auth_context=_auth_context())
        assert len(result) == 1
        assert result[0]['id'] == 'mem-1'


_LEGACY = __import__('utils.memory.memory_system', fromlist=['MemorySystem']).MemorySystem.LEGACY


def _allowed_write_guard(*_args, **_kwargs):
    return SimpleNamespace(allowed=True, status_code=200, detail={})


def _legacy_memory_doc(memory_id='mem-1', content='old text', category='hobbies'):
    """Full MemoryDB-valid legacy doc.

    ``MemoryService.update_external_memory_content`` re-reads + ``model_validate``s
    the memory for its return value, so legacy ``get_memory`` stubs must carry the
    required MemoryDB fields (not just the lock-check subset).
    """
    return {
        'id': memory_id,
        'uid': 'user-1',
        'content': content,
        'category': category,
        'is_locked': False,
        'created_at': '2026-06-19T12:00:00+00:00',
        'updated_at': '2026-06-19T12:00:00+00:00',
    }


class TestEditMemoryVectorSync:
    """edit_memory must re-embed the new content so search finds the edited text.

    Legacy mutation now flows through ``MemoryService.update_external_memory_content``,
    so the legacy write/guard/vector side effects are exercised on
    ``utils.memory.memory_service`` rather than on ``routers.mcp``.
    """

    @patch('utils.memory.memory_service.guard_legacy_memory_write', side_effect=_allowed_write_guard)
    @patch('utils.memory.memory_service.upsert_memory_vector')
    @patch('utils.memory.memory_service.memories_db')
    @patch('routers.mcp.fetch_memory_dict')
    @patch('routers.mcp.pin_memory_system')
    def test_edit_upserts_vector_with_new_content(
        self, mock_pin, mock_fetch, mock_service_memories_db, mock_upsert_vector, _mock_guard
    ):
        mock_pin.return_value = _LEGACY
        mock_fetch.return_value = _legacy_memory_doc(category='hobbies')
        mock_service_memories_db.get_memory.return_value = _legacy_memory_doc(category='hobbies')
        result = edit_memory(memory_id="mem-1", value="new text", auth_context=_auth_context())
        assert result == {"status": "ok"}
        mock_service_memories_db.edit_memory.assert_called_once_with("user-1", "mem-1", "new text")
        mock_upsert_vector.assert_called_once_with("user-1", "mem-1", "new text", "hobbies", subject_entity_id=None)

    @patch('utils.memory.memory_service.guard_legacy_memory_write', side_effect=_allowed_write_guard)
    @patch('utils.memory.memory_service.upsert_memory_vector')
    @patch('utils.memory.memory_service.memories_db')
    @patch('routers.mcp.fetch_memory_dict')
    @patch('routers.mcp.pin_memory_system')
    def test_edit_succeeds_when_vector_upsert_fails(
        self, mock_pin, mock_fetch, mock_service_memories_db, mock_upsert_vector, _mock_guard
    ):
        mock_pin.return_value = _LEGACY
        mock_fetch.return_value = _legacy_memory_doc(category='other')
        mock_service_memories_db.get_memory.return_value = _legacy_memory_doc(category='other')
        mock_upsert_vector.side_effect = Exception("pinecone down")
        result = edit_memory(memory_id="mem-1", value="new text", auth_context=_auth_context())
        assert result == {"status": "ok"}
        mock_service_memories_db.edit_memory.assert_called_once_with("user-1", "mem-1", "new text")


class TestDeleteMemoryVectorSync:
    """delete_memory must also remove the Pinecone vector so search_memories
    does not return stale top-K slots for deleted memories.

    Legacy mutation now flows through ``MemoryService.delete_external_memory``,
    so the legacy write/guard/vector side effects are exercised on
    ``utils.memory.memory_service`` rather than on ``routers.mcp``.
    """

    @patch('utils.memory.memory_service.guard_legacy_memory_write', side_effect=_allowed_write_guard)
    @patch('utils.memory.memory_service.delete_memory_vector')
    @patch('utils.memory.memory_service.memories_db')
    @patch('routers.mcp.fetch_memory_dict')
    @patch('routers.mcp.pin_memory_system')
    def test_delete_removes_vector(
        self, mock_pin, mock_fetch, mock_service_memories_db, mock_delete_vector, _mock_guard
    ):
        mock_pin.return_value = _LEGACY
        mock_fetch.return_value = {'id': 'mem-1', 'content': 'x', 'is_locked': False}
        mock_service_memories_db.get_memory.return_value = {'id': 'mem-1', 'content': 'x', 'is_locked': False}
        result = delete_memory(memory_id="mem-1", auth_context=_auth_context())
        assert result == {"status": "ok"}
        mock_service_memories_db.delete_memory.assert_called_once_with("user-1", "mem-1")
        mock_delete_vector.assert_called_once_with("user-1", "mem-1")

    @patch('utils.memory.memory_service.guard_legacy_memory_write', side_effect=_allowed_write_guard)
    @patch('utils.memory.memory_service.delete_memory_vector')
    @patch('utils.memory.memory_service.memories_db')
    @patch('routers.mcp.fetch_memory_dict')
    @patch('routers.mcp.pin_memory_system')
    def test_delete_succeeds_when_vector_delete_fails(
        self, mock_pin, mock_fetch, mock_service_memories_db, mock_delete_vector, _mock_guard
    ):
        mock_pin.return_value = _LEGACY
        mock_fetch.return_value = {'id': 'mem-1', 'content': 'x', 'is_locked': False}
        mock_service_memories_db.get_memory.return_value = {'id': 'mem-1', 'content': 'x', 'is_locked': False}
        mock_delete_vector.side_effect = Exception("pinecone down")
        result = delete_memory(memory_id="mem-1", auth_context=_auth_context())
        assert result == {"status": "ok"}
        mock_service_memories_db.delete_memory.assert_called_once_with("user-1", "mem-1")
