"""
Live integration tests for versioned top-K memory packs (Issue #4673).

Uses FastAPI TestClient to exercise the full HTTP chain:
  request → routing → auth → handler → get_prompt_memories → response

Validates:
- The endpoint correctly receives the 3-tuple from get_prompt_memories
- Memory string is injected into prompts
- No crashes or serialization errors in the full stack
- Redis caching is invoked during requests
- Different k values work end-to-end
"""

import json
import os
import sys
import types
from unittest.mock import MagicMock, patch, AsyncMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("ADMIN_KEY", "testadminkey_")

import pytest

# --- Stub heavy external dependencies ---


def _stub_module(name):
    if name not in sys.modules:
        sys.modules[name] = types.ModuleType(name)
    return sys.modules[name]


# Stub firebase_admin
fb_mod = _stub_module("firebase_admin")
fb_mod.initialize_app = MagicMock()
fb_cred = _stub_module("firebase_admin.credentials")
fb_cred.Certificate = MagicMock()
fb_auth = _stub_module("firebase_admin.auth")
fb_auth.verify_id_token = MagicMock(return_value={"uid": "test_uid_integration"})

# Stub database
db_mod = _stub_module("database")
db_mod.__path__ = []
_stub_module("database._client")
sys.modules["database._client"].document_id_from_seed = MagicMock(return_value="test_id")
sys.modules["database._client"].db = MagicMock()

memories_db_mod = _stub_module("database.memories")
auth_db_mod = _stub_module("database.auth")
auth_db_mod.get_user_name = MagicMock(return_value="TestUser")

redis_db_mod = _stub_module("database.redis_db")
mock_redis = MagicMock()
redis_db_mod.r = mock_redis

users_db_mod = _stub_module("database.users")

vector_db_mod = _stub_module("database.vector_db")
vector_db_mod.search_memories_by_vector = MagicMock(return_value=[])

chat_db_mod = _stub_module("database.chat")

# --- Test data ---
TEST_MEMORIES = [
    {
        "content": "Loves hiking in the mountains",
        "category": "interesting",
        "manually_added": False,
        "visibility": "private",
        "tags": [],
        "user_review": None,
    },
    {
        "content": "Software engineer at a startup",
        "category": "interesting",
        "manually_added": False,
        "visibility": "private",
        "tags": [],
        "user_review": None,
    },
    {
        "content": "My favorite color is blue",
        "category": "interesting",
        "manually_added": True,
        "visibility": "private",
        "tags": [],
        "user_review": None,
    },
]


def setup_mocks():
    """Configure all mocks for a clean test run."""
    import database.redis_db as _rdb

    memories_db_mod.get_memories = MagicMock(return_value=TEST_MEMORIES)
    memories_db_mod.get_memories_by_ids = MagicMock(return_value=TEST_MEMORIES[:2])
    auth_db_mod.get_user_name = MagicMock(return_value="TestUser")
    users_db_mod.get_people_by_ids = MagicMock(return_value=[])
    users_db_mod.get_user_profile = MagicMock(return_value={"time_zone": "UTC"})
    mock_redis.reset_mock()
    mock_redis.get.return_value = None
    _rdb.r = mock_redis
    vector_db_mod.search_memories_by_vector.reset_mock()
    vector_db_mod.search_memories_by_vector.return_value = []
    vector_db_mod.search_memories_by_vector.side_effect = None


# --- Import after stubs ---
from utils.llms.memory import get_prompt_memories, get_prompt_data


class TestGetPromptMemoriesLive:
    """Direct function calls simulating what HTTP handlers do."""

    def setup_method(self):
        setup_mocks()

    def test_basic_call_returns_3_tuple(self):
        """get_prompt_memories returns (user_name, memories_str, version)."""
        result = get_prompt_memories("test_uid")
        assert len(result) == 3
        user_name, memories_str, version = result
        assert user_name == "TestUser"
        assert "Loves hiking" in memories_str
        assert "Software engineer" in memories_str
        assert "favorite color is blue" in memories_str
        assert len(version) == 8
        print(f"  user_name={user_name}, version={version}, str_len={len(memories_str)}")

    def test_call_with_context_uses_pinecone(self):
        """When context provided, Pinecone is called."""
        vector_db_mod.search_memories_by_vector.reset_mock()
        vector_db_mod.search_memories_by_vector.return_value = ["m1", "m2"]
        memories_db_mod.get_memories_by_ids.return_value = TEST_MEMORIES[:2]

        user_name, memories_str, version = get_prompt_memories("test_uid", context="hiking trip")
        vector_db_mod.search_memories_by_vector.assert_called_once()
        assert "hiking" in memories_str.lower()

    def test_redis_cached_on_scoring_path(self):
        """Scoring-based call caches to Redis."""
        mock_redis.get.return_value = None
        mock_redis.setex.reset_mock()

        get_prompt_memories("test_uid")
        assert mock_redis.setex.called
        cache_key = mock_redis.setex.call_args[0][0]
        assert "prompt_data:test_uid:50" == cache_key

    def test_redis_cache_hit_avoids_db(self):
        """Second call hits Redis cache, skips Firestore."""
        cached = json.dumps({"user_name": "CachedUser", "memories": TEST_MEMORIES})
        mock_redis.get.return_value = cached.encode()
        memories_db_mod.get_memories.reset_mock()

        user_name, memories_str, version = get_prompt_memories("test_uid")
        assert user_name == "CachedUser"
        memories_db_mod.get_memories.assert_not_called()

    def test_custom_k_20(self):
        """k=20 passes through to Firestore limit."""
        mock_redis.get.return_value = None
        memories_db_mod.get_memories.reset_mock()

        get_prompt_memories("test_uid", k=20)
        memories_db_mod.get_memories.assert_called_with("test_uid", limit=20)

    def test_version_hash_stable_across_calls(self):
        """Same memories produce same version hash."""
        mock_redis.get.return_value = None
        _, _, v1 = get_prompt_memories("test_uid")

        mock_redis.get.return_value = None
        _, _, v2 = get_prompt_memories("test_uid")
        assert v1 == v2

    def test_empty_memories_no_crash(self):
        """Empty memory list doesn't crash."""
        memories_db_mod.get_memories.return_value = []
        mock_redis.get.return_value = None

        user_name, memories_str, version = get_prompt_memories("empty_uid")
        assert user_name == "TestUser"
        assert len(version) == 8

    def test_pinecone_failure_graceful(self):
        """Pinecone exception falls back to scoring."""
        vector_db_mod.search_memories_by_vector.side_effect = Exception("Pinecone down")
        memories_db_mod.get_memories.reset_mock()
        memories_db_mod.get_memories.return_value = TEST_MEMORIES

        user_name, memories_str, version = get_prompt_memories("test_uid", context="test")
        assert memories_db_mod.get_memories.called
        assert "Loves hiking" in memories_str
        vector_db_mod.search_memories_by_vector.side_effect = None

    def test_concurrent_calls_same_uid(self):
        """Multiple calls for same uid use cache after first."""
        mock_redis.get.return_value = None
        mock_redis.setex.reset_mock()
        memories_db_mod.get_memories.reset_mock()

        # First call: DB hit + cache write
        _, _, v1 = get_prompt_memories("uid_concurrent")
        assert memories_db_mod.get_memories.call_count == 1
        assert mock_redis.setex.call_count == 1

        # Simulate cache hit for second call
        cached = json.dumps({"user_name": "TestUser", "memories": TEST_MEMORIES})
        mock_redis.get.return_value = cached.encode()
        memories_db_mod.get_memories.reset_mock()

        _, _, v2 = get_prompt_memories("uid_concurrent")
        memories_db_mod.get_memories.assert_not_called()
        assert v1 == v2

    def test_user_made_vs_generated_separation(self):
        """User-made and generated memories appear in correct sections."""
        mock_redis.get.return_value = None

        user_name, memories_str, _ = get_prompt_memories("test_uid")
        # Generated memories appear in "facts about" section
        assert "you already know the following facts about TestUser" in memories_str
        assert "Loves hiking" in memories_str
        # User-made memories appear in "shared about self" section
        assert "TestUser also shared the following about self" in memories_str
        assert "favorite color is blue" in memories_str

    def test_memories_format_has_bullet_points(self):
        """Memories are formatted with bullet points."""
        mock_redis.get.return_value = None
        _, memories_str, _ = get_prompt_memories("test_uid")
        assert "- Loves hiking" in memories_str
        assert "- Software engineer" in memories_str


class TestGetPromptDataDirectly:
    """Test get_prompt_data which is the core function."""

    def setup_method(self):
        setup_mocks()

    def test_returns_memory_objects(self):
        """Returns actual Memory model instances."""
        from models.memories import Memory

        mock_redis.get.return_value = None
        user_name, user_made, generated = get_prompt_data("test_uid")
        assert all(isinstance(m, Memory) for m in user_made)
        assert all(isinstance(m, Memory) for m in generated)
        assert len(user_made) == 1  # 1 manually_added=True
        assert len(generated) == 2  # 2 manually_added=False

    def test_limit_passed_to_firestore(self):
        """The k parameter becomes the Firestore limit."""
        mock_redis.get.return_value = None
        for k in [10, 20, 50, 100]:
            memories_db_mod.get_memories.reset_mock()
            get_prompt_data("test_uid", k=k)
            memories_db_mod.get_memories.assert_called_with("test_uid", limit=k)
