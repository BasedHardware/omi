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

from routers.mcp import search_memories


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
        mock_vector_db.find_similar_memories.assert_called_once_with("user-1", "test", threshold=0.0, limit=10)

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
    def test_locked_memory_truncates_content(self, mock_vector_db, mock_memories_db):
        long_content = "A" * 200
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'category': 'other', 'score': 0.9},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            self._make_memory('mem-1', long_content, 'other', locked=True),
        ]
        result = search_memories(query="test", limit=10, uid="user-1")
        assert len(result) == 1
        assert result[0]['content'] == "A" * 70 + "..."
        assert result[0]['relevance_score'] == 0.9

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_locked_memory_short_content_not_truncated(self, mock_vector_db, mock_memories_db):
        short_content = "Short memory"
        mock_vector_db.find_similar_memories.return_value = [
            {'memory_id': 'mem-1', 'category': 'other', 'score': 0.9},
        ]
        mock_memories_db.get_memories_by_ids.return_value = [
            self._make_memory('mem-1', short_content, 'other', locked=True),
        ]
        result = search_memories(query="test", limit=10, uid="user-1")
        assert result[0]['content'] == "Short memory"

    @patch('routers.mcp.memories_db')
    @patch('routers.mcp.vector_db')
    def test_limit_capped_at_20(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = []
        search_memories(query="test", limit=100, uid="user-1")
        mock_vector_db.find_similar_memories.assert_called_once_with("user-1", "test", threshold=0.0, limit=20)

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
    def test_default_limit_is_10(self, mock_vector_db, mock_memories_db):
        mock_vector_db.find_similar_memories.return_value = []
        search_memories(query="test", uid="user-1")
        mock_vector_db.find_similar_memories.assert_called_once_with("user-1", "test", threshold=0.0, limit=10)
