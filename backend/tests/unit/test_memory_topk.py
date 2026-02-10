"""Tests for versioned top-K memory packs (Issue #4673).

Tests:
- Top-K limit reduction (1000 -> configurable K)
- Deterministic version hashing
- Redis caching for get_prompt_data
- Semantic retrieval fallback to scoring
- Version hash stability
"""

import hashlib
import json
import os
import sys
import types
from unittest.mock import MagicMock, patch, PropertyMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import pytest

# --- Stub external dependencies before importing the module under test ---


def _stub_module(name):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
    return sys.modules[name]


# Stub database (external dependency, not in our codebase tests)
db_mod = _stub_module("database")
db_mod.__path__ = []
_stub_module("database._client")
sys.modules["database._client"].document_id_from_seed = MagicMock(return_value="test_id")

memories_db_mod = _stub_module("database.memories")
memories_db_mod.get_memories = MagicMock(return_value=[])
memories_db_mod.get_memories_by_ids = MagicMock(return_value=[])

auth_mod = _stub_module("database.auth")
auth_mod.get_user_name = MagicMock(return_value="TestUser")

redis_db_mod = _stub_module("database.redis_db")
mock_redis = MagicMock()
mock_redis.get = MagicMock(return_value=None)
mock_redis.setex = MagicMock()
redis_db_mod.r = mock_redis


def _reset_mocks():
    """Reset all mocks to clean state — call in setup_method to avoid cross-test contamination."""
    import database.redis_db as _rdb

    mock_redis.reset_mock()
    mock_redis.get.return_value = None
    _rdb.r = mock_redis
    memories_db_mod.get_memories.reset_mock()
    memories_db_mod.get_memories.return_value = []
    memories_db_mod.get_memories_by_ids.reset_mock()
    memories_db_mod.get_memories_by_ids.return_value = []
    vector_db_mod.search_memories_by_vector.reset_mock()
    vector_db_mod.search_memories_by_vector.return_value = []
    vector_db_mod.search_memories_by_vector.side_effect = None
    auth_mod.get_user_name.return_value = "TestUser"


vector_db_mod = _stub_module("database.vector_db")
vector_db_mod.search_memories_by_vector = MagicMock(return_value=[])

# Import the real Memory model (models is a real package, don't stub it)
from models.memories import Memory, MemoryCategory

# Now import the module under test
from utils.llms.memory import (
    get_prompt_memories,
    get_prompt_data,
    safe_create_memory,
    _compute_version_hash,
    _cache_prompt_data,
    _get_cached_prompt_data,
    _fetch_memories_by_context,
    _PROMPT_DATA_CACHE_TTL,
)

# --- Test fixtures ---


def _make_memory_dict(content, manually_added=False, category="interesting"):
    """Create a minimal memory dict as returned by Firestore."""
    return {
        "content": content,
        "category": category,
        "manually_added": manually_added,
        "visibility": "private",
        "tags": [],
    }


def _make_memories(n, manually_added=False):
    """Create n memory dicts."""
    return [_make_memory_dict(f"Memory {i}", manually_added=manually_added) for i in range(n)]


# --- Tests ---


class TestTopKLimit:
    """Part A: Top-K retrieval with configurable limit."""

    def setup_method(self):
        _reset_mocks()

    def test_default_k_is_50(self):
        """get_prompt_data defaults to k=50."""
        memories_db_mod.get_memories.reset_mock()
        mock_redis.get.return_value = None
        memories_db_mod.get_memories.return_value = _make_memories(50)

        get_prompt_data("uid1")
        memories_db_mod.get_memories.assert_called_once_with("uid1", limit=50)

    def test_custom_k(self):
        """get_prompt_data respects custom k value."""
        memories_db_mod.get_memories.reset_mock()
        mock_redis.get.return_value = None
        memories_db_mod.get_memories.return_value = _make_memories(20)

        get_prompt_data("uid1", k=20)
        memories_db_mod.get_memories.assert_called_once_with("uid1", limit=20)

    def test_k_propagates_through_get_prompt_memories(self):
        """get_prompt_memories passes k to get_prompt_data."""
        memories_db_mod.get_memories.reset_mock()
        mock_redis.get.return_value = None
        memories_db_mod.get_memories.return_value = _make_memories(10)

        get_prompt_memories("uid1", k=10)
        memories_db_mod.get_memories.assert_called_once_with("uid1", limit=10)

    def test_separates_user_made_and_generated(self):
        """Memories are correctly split into user_made and generated."""
        mock_redis.get.return_value = None
        memories_db_mod.get_memories.return_value = [
            _make_memory_dict("User memory", manually_added=True),
            _make_memory_dict("Auto memory 1", manually_added=False),
            _make_memory_dict("Auto memory 2", manually_added=False),
        ]

        user_name, user_made, generated = get_prompt_data("uid1")
        assert len(user_made) == 1
        assert len(generated) == 2
        assert user_made[0].content == "User memory"


class TestSemanticRetrieval:
    """Part A: Pinecone semantic search when context is provided."""

    def setup_method(self):
        _reset_mocks()

    def test_context_triggers_pinecone_search(self):
        """When context is provided, Pinecone search is attempted."""
        vector_db_mod.search_memories_by_vector.reset_mock()
        vector_db_mod.search_memories_by_vector.return_value = ["mem1", "mem2"]
        memories_db_mod.get_memories_by_ids.return_value = [
            _make_memory_dict("Relevant memory 1"),
            _make_memory_dict("Relevant memory 2"),
        ]

        user_name, user_made, generated = get_prompt_data("uid1", context="hiking trip")
        vector_db_mod.search_memories_by_vector.assert_called_once_with("uid1", "hiking trip", limit=50)
        memories_db_mod.get_memories_by_ids.assert_called_once_with("uid1", ["mem1", "mem2"])

    def test_no_context_uses_scoring(self):
        """Without context, falls back to Firestore scoring."""
        mock_redis.get.return_value = None
        vector_db_mod.search_memories_by_vector.reset_mock()
        memories_db_mod.get_memories.reset_mock()
        memories_db_mod.get_memories.return_value = []

        get_prompt_data("uid1")
        vector_db_mod.search_memories_by_vector.assert_not_called()
        memories_db_mod.get_memories.assert_called_once()

    def test_pinecone_failure_falls_back_to_scoring(self):
        """If Pinecone fails, falls back to Firestore scoring."""
        vector_db_mod.search_memories_by_vector.side_effect = Exception("Pinecone unavailable")
        memories_db_mod.get_memories.reset_mock()
        memories_db_mod.get_memories.return_value = _make_memories(5)

        user_name, user_made, generated = get_prompt_data("uid1", context="test context")
        memories_db_mod.get_memories.assert_called_once_with("uid1", limit=50)
        # Reset side_effect for other tests
        vector_db_mod.search_memories_by_vector.side_effect = None

    def test_empty_pinecone_results_falls_back(self):
        """If Pinecone returns no results, falls back to scoring."""
        vector_db_mod.search_memories_by_vector.return_value = []
        memories_db_mod.get_memories.reset_mock()
        memories_db_mod.get_memories.return_value = _make_memories(5)

        get_prompt_data("uid1", context="obscure query")
        memories_db_mod.get_memories.assert_called_once_with("uid1", limit=50)


class TestVersionHash:
    """Part B: Deterministic versioned memory packs."""

    def setup_method(self):
        _reset_mocks()

    def test_deterministic_hash(self):
        """Same memories always produce the same hash."""
        m1 = Memory(content="Likes hiking", category="interesting")
        m2 = Memory(content="Works in tech", category="interesting")

        hash1 = _compute_version_hash([m1], [m2])
        hash2 = _compute_version_hash([m1], [m2])
        assert hash1 == hash2

    def test_hash_is_8_chars(self):
        """Version hash is 8 hex characters."""
        m1 = Memory(content="Test memory", category="interesting")
        h = _compute_version_hash([], [m1])
        assert len(h) == 8
        assert all(c in '0123456789abcdef' for c in h)

    def test_order_independent(self):
        """Hash is the same regardless of input order (sorted internally)."""
        m1 = Memory(content="Alpha", category="interesting")
        m2 = Memory(content="Beta", category="interesting")

        hash_ab = _compute_version_hash([m1, m2], [])
        hash_ba = _compute_version_hash([m2, m1], [])
        assert hash_ab == hash_ba

    def test_different_content_different_hash(self):
        """Different memory content produces different hash."""
        m1 = Memory(content="Likes hiking", category="interesting")
        m2 = Memory(content="Likes swimming", category="interesting")

        hash1 = _compute_version_hash([], [m1])
        hash2 = _compute_version_hash([], [m2])
        assert hash1 != hash2

    def test_empty_memories_hash(self):
        """Empty memory list produces a valid hash."""
        h = _compute_version_hash([], [])
        assert len(h) == 8

    def test_version_returned_in_get_prompt_memories(self):
        """get_prompt_memories returns version hash as third element."""
        mock_redis.get.return_value = None
        memories_db_mod.get_memories.return_value = [
            _make_memory_dict("Test memory"),
        ]

        user_name, memories_str, version = get_prompt_memories("uid1")
        assert isinstance(version, str)
        assert len(version) == 8


class TestRedisCache:
    """Part C: Application-level caching."""

    def setup_method(self):
        _reset_mocks()

    def test_cache_miss_fetches_from_db(self):
        """On cache miss, fetches from Firestore."""
        mock_redis.get.return_value = None
        memories_db_mod.get_memories.reset_mock()
        memories_db_mod.get_memories.return_value = _make_memories(3)

        get_prompt_data("uid1", k=50)
        memories_db_mod.get_memories.assert_called_once()

    def test_cache_hit_skips_db(self):
        """On cache hit, does NOT fetch from Firestore."""
        cached_data = json.dumps(
            {
                'user_name': 'CachedUser',
                'memories': [
                    _make_memory_dict("Cached memory 1"),
                    _make_memory_dict("Cached memory 2", manually_added=True),
                ],
            }
        )
        mock_redis.get.return_value = cached_data.encode()
        memories_db_mod.get_memories.reset_mock()

        user_name, user_made, generated = get_prompt_data("uid1", k=50)
        memories_db_mod.get_memories.assert_not_called()
        assert user_name == 'CachedUser'
        assert len(user_made) == 1
        assert len(generated) == 1

    def test_cache_stores_on_miss(self):
        """After DB fetch, results are cached in Redis."""
        mock_redis.get.return_value = None
        mock_redis.setex.reset_mock()
        memories_db_mod.get_memories.return_value = _make_memories(3)

        get_prompt_data("uid1", k=50)
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == 'prompt_data:uid1:50'
        assert call_args[0][1] == _PROMPT_DATA_CACHE_TTL

    def test_cache_key_includes_k(self):
        """Cache key includes k value for isolation."""
        mock_redis.get.return_value = None
        mock_redis.setex.reset_mock()
        memories_db_mod.get_memories.return_value = []

        get_prompt_data("uid1", k=20)
        call_args = mock_redis.setex.call_args
        assert call_args[0][0] == 'prompt_data:uid1:20'

    def test_context_based_retrieval_not_cached(self):
        """Context-specific results are NOT cached (different queries = different results)."""
        mock_redis.get.reset_mock()
        mock_redis.setex.reset_mock()
        vector_db_mod.search_memories_by_vector.return_value = []
        memories_db_mod.get_memories.return_value = []

        get_prompt_data("uid1", context="some context")
        mock_redis.get.assert_not_called()  # No cache check
        mock_redis.setex.assert_not_called()  # No cache store

    def test_cache_ttl_is_5_minutes(self):
        """Cache TTL is 300 seconds (5 minutes)."""
        assert _PROMPT_DATA_CACHE_TTL == 300

    def test_redis_failure_doesnt_crash(self):
        """Redis errors are caught gracefully."""
        mock_redis.get.side_effect = Exception("Redis down")
        memories_db_mod.get_memories.return_value = _make_memories(2)

        # Should not raise, just fall through to DB
        user_name, user_made, generated = get_prompt_data("uid1")
        assert len(generated) == 2

        # Reset
        mock_redis.get.side_effect = None


class TestReturnSignature:
    """Verify the new return signature works with all call patterns."""

    def setup_method(self):
        _reset_mocks()

    def test_three_tuple_return(self):
        """get_prompt_memories returns (user_name, memories_str, version)."""
        mock_redis.get.return_value = None
        memories_db_mod.get_memories.return_value = [
            _make_memory_dict("Test memory"),
        ]

        result = get_prompt_memories("uid1")
        assert len(result) == 3
        user_name, memories_str, version = result
        assert isinstance(user_name, str)
        assert isinstance(memories_str, str)
        assert isinstance(version, str)

    def test_underscore_unpack_works(self):
        """Can unpack with _ for version (backward compat pattern)."""
        mock_redis.get.return_value = None
        memories_db_mod.get_memories.return_value = []

        user_name, memories_str, _ = get_prompt_memories("uid1")
        assert user_name == "TestUser"

    def test_memories_str_format_unchanged(self):
        """Output string format matches original behavior."""
        mock_redis.get.return_value = None
        memories_db_mod.get_memories.return_value = [
            _make_memory_dict("Likes hiking", manually_added=False),
            _make_memory_dict("My hobby is running", manually_added=True),
        ]

        user_name, memories_str, _ = get_prompt_memories("uid1")
        assert "you already know the following facts about TestUser" in memories_str
        assert "Likes hiking" in memories_str
        assert "TestUser also shared the following about self" in memories_str
        assert "My hobby is running" in memories_str
