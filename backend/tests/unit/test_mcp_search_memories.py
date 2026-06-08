"""Unit tests for the search_memories MCP endpoint.

Tests the endpoint logic with mocked database calls,
following the pattern in test_lock_bypass_fixes.py.
"""

from unittest.mock import patch, MagicMock
import os
import pytest
import sys
from types import ModuleType

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


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
]
for mod_name in _stubs:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = _AutoMockModule(mod_name)

sys.modules['firebase_admin.auth'].InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].ExpiredIdTokenError = type('ExpiredIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].RevokedIdTokenError = type('RevokedIdTokenError', (Exception,), {})
sys.modules['firebase_admin.auth'].CertificateFetchError = type('CertificateFetchError', (Exception,), {})
sys.modules['firebase_admin.auth'].UserNotFoundError = type('UserNotFoundError', (Exception,), {})

from routers.mcp import search_memories, delete_memory, edit_memory


class TestSearchMemoriesEndpoint:

    def _make_memory(self, memory_id='mem-1', content='Test memory content', category='other', locked=False):
        return {
            'id': memory_id,
            'content': content,
            'category': category,
            'is_locked': locked,
        }

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_returns_empty_when_no_matches(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = []
        result = search_memories(query="test", limit=10, uid="user-1")
        assert result == []
        # limit=10 → fetch_limit = min(10*3, 60) = 30
        mock_vector_db.find_similar_memories.assert_called_once_with("user-1", "test", threshold=0.0, limit=30)

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_returns_ranked_results(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'category': 'work', 'score': 0.95},
            {'memory_id': 'mem-2', 'category': 'hobbies', 'score': 0.80},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            self._make_memory('mem-1', 'Work memory', 'work'),
            self._make_memory('mem-2', 'Hobby memory', 'hobbies'),
        ]
        result = search_memories(query="work stuff", limit=10, uid="user-1")
        assert len(result) == 2
        assert result[0]['id'] == 'mem-1'
        assert result[0]['relevance_score'] == 0.95
        assert result[1]['id'] == 'mem-2'
        assert result[1]['relevance_score'] == 0.80

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
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
        result = search_memories(query="test", limit=10, uid="user-1")
        assert len(result) == 1
        assert result[0]['id'] == 'mem-2'

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_limit_capped_at_20_fetches_60_candidates(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = []
        search_memories(query="test", limit=100, uid="user-1")
        # limit clamps to 20, fetch_limit = min(20*3, 60) = 60
        mock_vector_db.find_similar_memories.assert_called_once_with("user-1", "test", threshold=0.0, limit=60)

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_limit_zero_clamped_to_1_fetches_3_candidates(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = []
        search_memories(query="test", limit=0, uid="user-1")
        # limit clamps to 1, fetch_limit = min(1*3, 60) = 3
        mock_vector_db.find_similar_memories.assert_called_once_with("user-1", "test", threshold=0.0, limit=3)

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_negative_limit_clamped_to_1_fetches_3_candidates(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = []
        search_memories(query="test", limit=-5, uid="user-1")
        # limit clamps to 1, fetch_limit = min(1*3, 60) = 3
        mock_vector_db.find_similar_memories.assert_called_once_with("user-1", "test", threshold=0.0, limit=3)

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
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
        result = search_memories(query="test", limit=10, uid="user-1")
        assert [r['relevance_score'] for r in result] == [0.99, 0.75, 0.5]

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_skips_matches_with_no_memory_id(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.9},
            {'category': 'other', 'score': 0.5},
            {'memory_id': None, 'score': 0.3},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            self._make_memory('mem-1', 'Valid memory'),
        ]
        result = search_memories(query="test", limit=10, uid="user-1")
        assert len(result) == 1
        assert result[0]['id'] == 'mem-1'
        mock_memories_db.get_memories_by_ids.assert_called_once_with("user-1", ['mem-1'])

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_returns_empty_when_all_ids_filtered(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'category': 'other', 'score': 0.5},
        ]
        result = search_memories(query="test", limit=10, uid="user-1")
        assert result == []
        mock_memories_db.get_memories_by_ids.assert_not_called()

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_default_limit_fetches_3x_candidates(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = []
        search_memories(query="test", uid="user-1")
        # default limit=10, fetch_limit = min(10*3, 60) = 30
        mock_vector_db.find_similar_memories.assert_called_once_with("user-1", "test", threshold=0.0, limit=30)

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
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
        result = search_memories(query="test", limit=1, uid="user-1")
        assert len(result) == 1
        assert result[0]['id'] == 'mem-ok'


class TestSearchMemoriesUserReview:
    """search_memories must not surface memories the user explicitly rejected."""

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_rejected_memory_excluded(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.9},
            {'memory_id': 'mem-2', 'score': 0.8},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            {'id': 'mem-1', 'content': 'accepted', 'category': 'other', 'is_locked': False, 'user_review': True},
            {'id': 'mem-2', 'content': 'rejected', 'category': 'other', 'is_locked': False, 'user_review': False},
        ]
        result = search_memories(query="test", limit=10, uid="user-1")
        assert len(result) == 1
        assert result[0]['id'] == 'mem-1'

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_unreviewed_memory_included(self, mock_vector_db, mock_memories_db):
        # user_review=None means not yet reviewed — should still appear
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.9},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            {'id': 'mem-1', 'content': 'pending review', 'category': 'other', 'is_locked': False},
        ]
        result = search_memories(query="test", limit=10, uid="user-1")
        assert len(result) == 1

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_all_rejected_returns_empty(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.9},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            {'id': 'mem-1', 'content': 'rejected', 'category': 'other', 'is_locked': False, 'user_review': False},
        ]
        result = search_memories(query="test", limit=10, uid="user-1")
        assert result == []


class TestSearchMemoriesInvalidated:
    """search_memories must not surface superseded/invalidated memories — the brain
    only returns facts that are currently true."""

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
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
        result = search_memories(query="ice cream", limit=10, uid="user-1")
        assert len(result) == 1
        assert result[0]['id'] == 'mem-new'

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_active_memory_with_null_invalid_at_included(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'score': 0.9},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            {'id': 'mem-1', 'content': 'active', 'category': 'system', 'is_locked': False, 'invalid_at': None},
        ]
        result = search_memories(query="test", limit=10, uid="user-1")
        assert len(result) == 1
        assert result[0]['id'] == 'mem-1'


class TestEditMemoryVectorSync:
    """edit_memory must re-embed the new content so search finds the edited text."""

    @patch('routers.mcp.upsert_memory_vector')
    @patch('routers.mcp.memories_db')
    def test_edit_upserts_vector_with_new_content(self, mock_memories_db, mock_upsert_vector):
        mock_memories_db.get_memory.return_value = {
            'id': 'mem-1',
            'content': 'old text',
            'category': 'hobbies',
            'is_locked': False,
        }
        result = edit_memory(memory_id="mem-1", value="new text", uid="user-1")
        assert result == {"status": "ok"}
        mock_memories_db.edit_memory.assert_called_once_with("user-1", "mem-1", "new text")
        mock_upsert_vector.assert_called_once_with("user-1", "mem-1", "new text", "hobbies")

    @patch('routers.mcp.upsert_memory_vector')
    @patch('routers.mcp.memories_db')
    def test_edit_succeeds_when_vector_upsert_fails(self, mock_memories_db, mock_upsert_vector):
        mock_memories_db.get_memory.return_value = {
            'id': 'mem-1',
            'content': 'old text',
            'category': 'other',
            'is_locked': False,
        }
        mock_upsert_vector.side_effect = Exception("pinecone down")
        result = edit_memory(memory_id="mem-1", value="new text", uid="user-1")
        assert result == {"status": "ok"}
        mock_memories_db.edit_memory.assert_called_once_with("user-1", "mem-1", "new text")


class TestDeleteMemoryVectorSync:
    """delete_memory must also remove the Pinecone vector so search_memories
    does not return stale top-K slots for deleted memories."""

    @patch('routers.mcp.delete_memory_vector')
    @patch('routers.mcp.memories_db')
    def test_delete_removes_vector(self, mock_memories_db, mock_delete_vector):
        mock_memories_db.get_memory.return_value = {'id': 'mem-1', 'content': 'x', 'is_locked': False}
        result = delete_memory(memory_id="mem-1", uid="user-1")
        assert result == {"status": "ok"}
        mock_memories_db.delete_memory.assert_called_once_with("user-1", "mem-1")
        mock_delete_vector.assert_called_once_with("user-1", "mem-1")

    @patch('routers.mcp.delete_memory_vector')
    @patch('routers.mcp.memories_db')
    def test_delete_succeeds_when_vector_delete_fails(self, mock_memories_db, mock_delete_vector):
        mock_memories_db.get_memory.return_value = {'id': 'mem-1', 'content': 'x', 'is_locked': False}
        mock_delete_vector.side_effect = Exception("pinecone down")
        result = delete_memory(memory_id="mem-1", uid="user-1")
        assert result == {"status": "ok"}
        mock_memories_db.delete_memory.assert_called_once_with("user-1", "mem-1")
