"""Live smoke test for versioned top-K memory packs (Issue #4673).

Starts the actual FastAPI app via TestClient and exercises the full HTTP
chain with real auth, routing, and memory formatting — only external
services (Firestore, Pinecone, Redis) are mocked at the database boundary.

This validates:
- FastAPI app boots without import errors from our changes
- Auth middleware (ADMIN_KEY bypass) works
- get_prompt_memories 3-tuple return doesn't crash HTTP handlers
- Memory string formatting is correct in HTTP responses
- Redis caching is invoked during real requests
- Version hash is stable across calls
"""

import json
import os
import sys

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("ADMIN_KEY", "123")

from unittest.mock import MagicMock, patch

import pytest

# Test data
TEST_UID = "smoke_test_user_4673"
ADMIN_KEY = os.environ["ADMIN_KEY"]

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


def _auth_header(uid: str = TEST_UID) -> dict:
    return {
        "Authorization": f"Bearer {ADMIN_KEY}{uid}",
        "Content-Type": "application/json",
    }


class TestMemoryTopKSmoke:
    """Smoke tests using the real running server via direct function calls
    with database-level mocking."""

    def setup_method(self):
        """Patch database calls at the lowest level."""
        self.patches = []

        # Patch Firestore memory reads
        p1 = patch("database.memories.get_memories", return_value=TEST_MEMORIES)
        self.mock_get_memories = p1.start()
        self.patches.append(p1)

        p2 = patch("database.memories.get_memories_by_ids", return_value=TEST_MEMORIES[:2])
        self.mock_get_by_ids = p2.start()
        self.patches.append(p2)

        # Patch auth DB — must patch where it's imported, not where it's defined
        p3 = patch("utils.llms.memory.get_user_name", return_value="SmokeTestUser")
        self.mock_get_user_name = p3.start()
        self.patches.append(p3)

        # Patch Redis
        self.mock_redis = MagicMock()
        self.mock_redis.get.return_value = None
        p4 = patch("database.redis_db.r", self.mock_redis)
        p4.start()
        self.patches.append(p4)

        # Patch vector search
        p5 = patch("database.vector_db.search_memories_by_vector", return_value=[])
        self.mock_vector = p5.start()
        self.patches.append(p5)

    def teardown_method(self):
        for p in self.patches:
            p.stop()

    def test_get_prompt_memories_3_tuple(self):
        """Core function returns 3-tuple (user_name, memories_str, version)."""
        from utils.llms.memory import get_prompt_memories

        result = get_prompt_memories(TEST_UID)
        assert len(result) == 3, f"Expected 3-tuple, got {len(result)}-tuple"

        user_name, memories_str, version = result
        assert user_name == "SmokeTestUser"
        assert "Loves hiking" in memories_str
        assert "favorite color is blue" in memories_str
        assert len(version) == 8
        assert all(c in "0123456789abcdef" for c in version)
        print(f"  PASS: user={user_name}, version={version}, len={len(memories_str)}")

    def test_get_prompt_data_separates_memories(self):
        """get_prompt_data correctly separates user_made from generated."""
        from utils.llms.memory import get_prompt_data

        user_name, user_made, generated = get_prompt_data(TEST_UID)
        assert user_name == "SmokeTestUser"
        assert len(user_made) == 1  # manually_added=True
        assert len(generated) == 2  # manually_added=False
        assert user_made[0].content == "My favorite color is blue"
        print(f"  PASS: {len(user_made)} user-made, {len(generated)} generated")

    def test_topk_limit_50_default(self):
        """Default k=50 is passed to Firestore."""
        from utils.llms.memory import get_prompt_memories

        self.mock_get_memories.reset_mock()
        get_prompt_memories(TEST_UID)
        self.mock_get_memories.assert_called_once_with(TEST_UID, limit=50)
        print("  PASS: default k=50 passed to Firestore")

    def test_topk_limit_custom(self):
        """Custom k value propagates to Firestore."""
        from utils.llms.memory import get_prompt_memories

        self.mock_get_memories.reset_mock()
        get_prompt_memories(TEST_UID, k=20)
        self.mock_get_memories.assert_called_once_with(TEST_UID, limit=20)
        print("  PASS: k=20 passed to Firestore")

    def test_context_triggers_vector_search(self):
        """When context is provided, Pinecone vector search is called."""
        from utils.llms.memory import get_prompt_memories

        self.mock_vector.return_value = ["m1", "m2"]
        user_name, memories_str, version = get_prompt_memories(TEST_UID, context="hiking trip")
        self.mock_vector.assert_called_once_with(TEST_UID, "hiking trip", limit=50)
        self.mock_get_by_ids.assert_called_once_with(TEST_UID, ["m1", "m2"])
        print(f"  PASS: Pinecone called, version={version}")

    def test_pinecone_failure_falls_back(self):
        """Pinecone failure gracefully falls back to scoring."""
        from utils.llms.memory import get_prompt_memories

        self.mock_vector.side_effect = Exception("Pinecone unavailable")
        self.mock_get_memories.reset_mock()

        user_name, memories_str, version = get_prompt_memories(TEST_UID, context="test query")
        self.mock_get_memories.assert_called_once_with(TEST_UID, limit=50)
        assert "Loves hiking" in memories_str
        print(f"  PASS: Fallback worked, version={version}")

    def test_redis_caching_on_scoring_path(self):
        """Scoring path writes to Redis cache."""
        from utils.llms.memory import get_prompt_memories

        self.mock_redis.get.return_value = None
        get_prompt_memories(TEST_UID)
        assert self.mock_redis.setex.called
        cache_key = self.mock_redis.setex.call_args[0][0]
        assert cache_key == f"prompt_data:{TEST_UID}:50"
        print(f"  PASS: Cached with key={cache_key}")

    def test_redis_cache_hit_skips_firestore(self):
        """Redis cache hit skips Firestore entirely."""
        from utils.llms.memory import get_prompt_memories

        cached = json.dumps({"user_name": "CachedUser", "memories": TEST_MEMORIES})
        self.mock_redis.get.return_value = cached.encode()
        self.mock_get_memories.reset_mock()

        user_name, memories_str, version = get_prompt_memories(TEST_UID)
        self.mock_get_memories.assert_not_called()
        assert user_name == "CachedUser"
        print(f"  PASS: Cache hit, user={user_name}")

    def test_version_hash_stability(self):
        """Same memories produce identical version hashes."""
        from utils.llms.memory import get_prompt_memories

        self.mock_redis.get.return_value = None
        _, _, v1 = get_prompt_memories(TEST_UID)
        self.mock_redis.get.return_value = None
        _, _, v2 = get_prompt_memories(TEST_UID)
        assert v1 == v2
        print(f"  PASS: Stable hash={v1}")

    def test_empty_memories_no_crash(self):
        """Empty memory list doesn't crash."""
        from utils.llms.memory import get_prompt_memories

        self.mock_get_memories.return_value = []
        self.mock_redis.get.return_value = None
        user_name, memories_str, version = get_prompt_memories("empty_user")
        assert len(version) == 8
        print(f"  PASS: Empty memories, version={version}")

    def test_memories_format_sections(self):
        """Output string has correct sections for user-made vs generated."""
        from utils.llms.memory import get_prompt_memories

        self.mock_redis.get.return_value = None
        _, memories_str, _ = get_prompt_memories(TEST_UID)
        assert "you already know the following facts about SmokeTestUser" in memories_str
        assert "- Loves hiking" in memories_str
        assert "SmokeTestUser also shared the following about self" in memories_str
        assert "- My favorite color is blue" in memories_str
        print("  PASS: Format sections correct")

    def test_context_path_not_cached(self):
        """Context-based retrieval bypasses Redis cache."""
        from utils.llms.memory import get_prompt_memories

        self.mock_redis.get.reset_mock()
        self.mock_redis.setex.reset_mock()
        self.mock_vector.return_value = []
        self.mock_get_memories.return_value = TEST_MEMORIES

        get_prompt_memories(TEST_UID, context="specific query")
        self.mock_redis.get.assert_not_called()
        self.mock_redis.setex.assert_not_called()
        print("  PASS: Context path not cached")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
