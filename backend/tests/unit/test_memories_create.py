"""
Tests for POST /v3/memories error handling and rate limit wiring.

Regression goal (#6940): POST /v3/memories must
  (a) have memories:create rate limit applied,
  (b) return 503 on Firestore failure (not unhandled 500),
  (c) survive vector upsert failure without 500 (memory still returned),
  (d) not attempt vector upsert when Firestore write fails,
  (e) run blocking work off the event loop via asyncio.to_thread.

The router import chain (database.memories → encryption → cryptography)
requires production env vars, so behavior tests use source-level verification
matching the repo pattern in test_rate_limiting.py.
"""

import os
import re

import pytest

from utils.rate_limit_config import RATE_POLICIES

ROUTER_PATH = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'memories.py')


def _read_router():
    with open(ROUTER_PATH) as f:
        return f.read()


def _grep_router(pattern: str) -> list[str]:
    """Return lines matching pattern in the memories router."""
    matches = []
    with open(ROUTER_PATH) as f:
        for line in f:
            if re.search(pattern, line):
                matches.append(line.strip())
    return matches


# ---------------------------------------------------------------------------
# Policy existence tests
# ---------------------------------------------------------------------------


class TestMemoriesRateLimitPolicies:
    def test_memories_create_policy_exists(self):
        assert "memories:create" in RATE_POLICIES
        max_req, window = RATE_POLICIES["memories:create"]
        assert max_req == 60
        assert window == 3600

    def test_memories_modify_policy_exists(self):
        assert "memories:modify" in RATE_POLICIES
        max_req, window = RATE_POLICIES["memories:modify"]
        assert max_req == 120
        assert window == 3600

    def test_memories_delete_policy_exists(self):
        assert "memories:delete" in RATE_POLICIES
        max_req, window = RATE_POLICIES["memories:delete"]
        assert max_req == 60
        assert window == 3600

    def test_memories_delete_all_policy_exists(self):
        assert "memories:delete_all" in RATE_POLICIES
        max_req, window = RATE_POLICIES["memories:delete_all"]
        assert max_req == 2
        assert window == 3600


# ---------------------------------------------------------------------------
# Rate limit wiring tests (source-level grep)
# ---------------------------------------------------------------------------


class TestMemoriesRateLimitWiring:
    def test_create_endpoint_has_rate_limit(self):
        matches = _grep_router(r"with_rate_limit.*memories:create")
        assert len(matches) == 1, f"POST /v3/memories must have memories:create, found: {matches}"

    def test_batch_endpoint_has_rate_limit(self):
        matches = _grep_router(r"with_rate_limit.*memories:batch")
        assert len(matches) == 1, f"POST /v3/memories/batch must have memories:batch, found: {matches}"

    def test_delete_endpoint_has_rate_limit(self):
        matches = _grep_router(r"with_rate_limit.*memories:delete[^_]")
        assert len(matches) == 1, f"DELETE /v3/memories/{{id}} must have memories:delete, found: {matches}"

    def test_delete_all_endpoint_has_rate_limit(self):
        matches = _grep_router(r"with_rate_limit.*memories:delete_all")
        assert len(matches) == 1, f"DELETE /v3/memories must have memories:delete_all, found: {matches}"

    def test_review_endpoint_has_rate_limit(self):
        matches = _grep_router(r"with_rate_limit.*memories:modify")
        assert len(matches) >= 1, f"Review/edit/visibility must have memories:modify, found: {matches}"

    def test_all_write_endpoints_rate_limited(self):
        """Every write endpoint in memories.py must use with_rate_limit."""
        matches = _grep_router(r"with_rate_limit.*memories:")
        # create, batch, delete, delete_all, modify(review), modify(edit), modify(visibility) = 7
        assert len(matches) == 7, f"Expected 7 rate-limited endpoints, got {len(matches)}: {matches}"


# ---------------------------------------------------------------------------
# Error handling tests (source-level verification)
# ---------------------------------------------------------------------------


class TestCreateMemoryErrorHandling:
    """Verify error handling structure in create_memory source code."""

    def test_create_memory_is_async(self):
        """create_memory must be async def (prevents threadpool exhaustion)."""
        source = _read_router()
        assert re.search(r'async def create_memory\(', source), "create_memory must be async def"

    def test_create_memory_uses_to_thread_for_firestore(self):
        """Firestore write in create_memory must use asyncio.to_thread."""
        source = _read_router()
        # Extract the create_memory function body (between its def and the next @router)
        match = re.search(
            r'(async def create_memory\(.+?)(?=\n@router\.)', source, re.DOTALL
        )
        assert match, "create_memory function not found"
        fn_body = match.group(1)
        assert 'asyncio.to_thread(memories_db.create_memory' in fn_body, \
            "create_memory must offload Firestore write via asyncio.to_thread"

    def test_create_memory_uses_to_thread_for_vector(self):
        """Vector upsert in create_memory must use asyncio.to_thread."""
        source = _read_router()
        match = re.search(
            r'(async def create_memory\(.+?)(?=\n@router\.)', source, re.DOTALL
        )
        assert match, "create_memory function not found"
        fn_body = match.group(1)
        assert 'asyncio.to_thread' in fn_body and 'upsert_memory_vector' in fn_body, \
            "create_memory must offload vector upsert via asyncio.to_thread"

    def test_firestore_write_has_error_handling(self):
        """Firestore write in create_memory must be wrapped in try/except."""
        source = _read_router()
        # The pattern: try + to_thread(_persist) + except -> 503
        assert 'HTTPException(status_code=503' in source, "Firestore failure must return 503"

    def test_vector_upsert_has_error_handling(self):
        """Vector upsert failure must be caught and logged (not 500)."""
        source = _read_router()
        assert 'Vector upsert failed' in source, "Vector upsert failure must be logged"

    def test_vector_delete_has_error_handling(self):
        """Vector delete in delete_memory must be caught (not 500)."""
        source = _read_router()
        assert 'Vector delete failed' in source, "Vector delete failure must be logged"

    def test_firestore_failure_blocks_vector_upsert(self):
        """If Firestore fails (raises), vector upsert must not execute.

        Verified by structural ordering: Firestore try/except with raise
        appears before vector try/except in the create_memory function.
        """
        source = _read_router()
        # Find positions of both error-handling blocks
        firestore_pos = source.find('HTTPException(status_code=503')
        vector_pos = source.find('Vector upsert failed')
        assert firestore_pos < vector_pos, "Firestore error handling must come before vector upsert"


# ---------------------------------------------------------------------------
# Delete-all safety tests
# ---------------------------------------------------------------------------


class TestPolicyBoundaries:
    """Verify rate limit policy values are safe and reasonable."""

    def test_delete_all_limit_is_tight(self):
        """delete_all is extremely destructive — must have very tight limits."""
        max_req, window = RATE_POLICIES["memories:delete_all"]
        assert max_req <= 5, f"delete_all limit too high: {max_req}"
        assert window >= 3600, f"delete_all window too short: {window}"

    def test_modify_limit_higher_than_create(self):
        """Modify (lightweight Firestore writes) should allow more than create (OpenAI+Pinecone)."""
        create_max, _ = RATE_POLICIES["memories:create"]
        modify_max, _ = RATE_POLICIES["memories:modify"]
        assert modify_max > create_max, \
            f"modify ({modify_max}) should be higher than create ({create_max})"

    def test_delete_limit_matches_create(self):
        """Single delete should match create rate (same Firestore+Pinecone cost)."""
        create_max, create_window = RATE_POLICIES["memories:create"]
        delete_max, delete_window = RATE_POLICIES["memories:delete"]
        assert delete_max == create_max
        assert delete_window == create_window

    def test_delete_all_much_tighter_than_single_delete(self):
        """Bulk delete must be much tighter than single delete."""
        delete_max, _ = RATE_POLICIES["memories:delete"]
        delete_all_max, _ = RATE_POLICIES["memories:delete_all"]
        assert delete_all_max < delete_max / 10, \
            f"delete_all ({delete_all_max}) should be <<< delete ({delete_max})"

    def test_all_memory_policies_use_1h_window(self):
        """All memory policies should use consistent 1-hour windows."""
        for name in ["memories:create", "memories:batch", "memories:modify",
                      "memories:delete", "memories:delete_all"]:
            _, window = RATE_POLICIES[name]
            assert window == 3600, f"{name} window is {window}, expected 3600"
