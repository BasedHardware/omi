"""
Tests for POST /v3/memories error handling and rate limit wiring.

Regression goal (#6940): POST /v3/memories must
  (a) have memories:create rate limit applied,
  (b) return 503 on Firestore failure (not unhandled 500),
  (c) survive vector upsert failure without 500 (memory still returned),
  (d) not attempt vector upsert when Firestore write fails,
  (e) run blocking work off the event loop via run_blocking.

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
    with open(ROUTER_PATH, encoding='utf-8') as f:
        return f.read()


def _grep_router(pattern: str) -> list[str]:
    """Return lines matching pattern in the memories router."""
    matches = []
    with open(ROUTER_PATH, encoding='utf-8') as f:
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

    def test_memories_review_policy_exists(self):
        assert "memories:review" in RATE_POLICIES
        max_req, window = RATE_POLICIES["memories:review"]
        assert max_req == 120
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

    def test_delete_batch_endpoint_has_rate_limit(self):
        matches = _grep_router(r"with_rate_limit.*memories:delete_batch")
        assert len(matches) == 1, f"DELETE /v3/memories/batch must have memories:delete_batch, found: {matches}"

    def test_review_endpoint_has_rate_limit(self):
        matches = _grep_router(r"with_rate_limit.*memories:review")
        assert len(matches) == 3, f"Review queue endpoints must have memories:review, found: {matches}"

    def test_modify_endpoints_have_rate_limit(self):
        matches = _grep_router(r"with_rate_limit.*memories:modify")
        assert len(matches) == 5, f"Edit/visibility/review/baseline/read must have memories:modify, found: {matches}"

    def test_all_write_endpoints_rate_limited(self):
        """Every write endpoint in memories.py must use with_rate_limit."""
        matches = _grep_router(r"with_rate_limit.*memories:")
        # extract, create, batch, review queue list/get/resolve, delete, delete_all, delete_batch,
        # modify(review), modify(edit), modify(visibility), modify(baseline), modify(read) = 14
        assert len(matches) == 14, f"Expected 14 rate-limited endpoints, got {len(matches)}: {matches}"


# ---------------------------------------------------------------------------
# Error handling tests (source-level verification)
# ---------------------------------------------------------------------------


class TestCreateMemoryErrorHandling:
    """Verify error handling structure in create_memory source code."""

    def test_single_and_batch_create_stamp_request_device_provenance(self):
        source = _read_router()
        create_body = source.split("async def create_memory(", 1)[1].split("\n@router.", 1)[0]
        batch_body = source.split("async def create_memories_batch(", 1)[1].split("\n@router.", 1)[0]

        assert "resolve_client_device_from_request(request)" in create_body
        assert "client_device_id=device_context.client_device_id" in create_body
        assert "resolve_client_device_from_request(request_context)" in batch_body
        assert "client_device_id=device_context.client_device_id" in batch_body

    def test_create_memory_is_async(self):
        """create_memory must be async def (prevents threadpool exhaustion)."""
        source = _read_router()
        assert re.search(r'async def create_memory\(', source), "create_memory must be async def"

    def test_create_memory_offloads_universal_service_write(self):
        """The canonical service write must stay off the async event loop."""
        source = _read_router()
        match = re.search(r'(async def create_memory\(.+?)(?=\n@router\.)', source, re.DOTALL)
        assert match, "create_memory function not found"
        fn_body = match.group(1)
        assert 'run_blocking' in fn_body
        assert 'MemoryService' in fn_body
        assert '.create_external_memory' in fn_body
        assert 'memories_db.create_memory' not in fn_body

    def test_create_memory_has_no_direct_vector_projection(self):
        """Canonical outbox projection, not the HTTP route, owns vectors."""
        source = _read_router()
        match = re.search(r'(async def create_memory\(.+?)(?=\n@router\.)', source, re.DOTALL)
        assert match, "create_memory function not found"
        fn_body = match.group(1)
        assert 'upsert_memory_vector' not in fn_body
        assert 'upsert_vector=False' in fn_body

    def test_firestore_write_has_error_handling(self):
        """Firestore write in create_memory must be wrapped in try/except."""
        source = _read_router()
        # The pattern: try + run_blocking(_persist) + except -> 503
        assert 'HTTPException(status_code=503' in source, "Firestore failure must return 503"

    def test_projection_failure_is_not_a_route_side_effect(self):
        """The route never performs a best-effort provider write."""
        source = _read_router()
        assert 'Vector upsert failed' not in source

    def test_batch_create_uses_one_universal_service_call(self):
        source = _read_router()
        match = re.search(r'(async def create_memories_batch\(.+?)(?=\n@router\.)', source, re.DOTALL)
        assert match, "create_memories_batch function not found"
        fn_body = match.group(1)
        assert 'MemoryService' in fn_body
        assert '.create_external_memory_batch' in fn_body
        assert 'memories_db.save_memories' not in fn_body
        assert 'upsert_memory_vectors_batch' not in fn_body

    def test_delete_has_no_direct_vector_side_effect(self):
        """Canonical tombstone/outbox authority owns provider deletion."""
        source = _read_router()
        delete_body = source.split("def delete_memory(", 1)[1].split("\n@router.", 1)[0]
        assert 'MemoryService' in delete_body
        assert 'delete_memory_vector' not in delete_body

    def test_service_failure_returns_503_without_wrong_store_fallback(self):
        source = _read_router()
        create_body = source.split("async def create_memory(", 1)[1].split("\n@router.", 1)[0]
        assert 'HTTPException(status_code=503' in create_body
        assert 'memories_db.' not in create_body


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
        assert modify_max > create_max, f"modify ({modify_max}) should be higher than create ({create_max})"

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
        assert delete_all_max < delete_max / 10, f"delete_all ({delete_all_max}) should be <<< delete ({delete_max})"

    def test_all_memory_policies_use_1h_window(self):
        """All memory policies should use consistent 1-hour windows."""
        for name in [
            "memories:create",
            "memories:batch",
            "memories:modify",
            "memories:review",
            "memories:delete",
            "memories:delete_all",
        ]:
            _, window = RATE_POLICIES[name]
            assert window == 3600, f"{name} window is {window}, expected 3600"


# ---------------------------------------------------------------------------
# Integration memory lifecycle contract
# ---------------------------------------------------------------------------

CONVERSATIONS_MEMORIES_PATH = os.path.join(
    os.path.dirname(__file__), '..', '..', 'utils', 'conversations', 'memories.py'
)


def _read_conversations_memories():
    with open(CONVERSATIONS_MEMORIES_PATH, encoding='utf-8') as f:
        return f.read()


class TestIntegrationMemoryLifecycle:
    """Integration and twitter memory paths must go through the canonical
    required-processing workflow, not a raw write_batch that bypasses
    tier/promotion/processor tracking."""

    def test_integration_path_uses_create_external_memory_batch(self):
        source = _read_conversations_memories()
        # process_external_integration_memory must call create_external_memory_batch
        match = re.search(r'(def process_external_integration_memory\(.+?)(?=\ndef )', source, re.DOTALL)
        assert match, "process_external_integration_memory not found"
        fn_body = match.group(1)
        assert (
            '.create_external_memory_batch(' in fn_body
        ), "integration memory path must use create_external_memory_batch for required-processing lifecycle"
        assert (
            '.write_batch(' not in fn_body
        ), "integration memory path must not use raw write_batch (skips required_processing_payload)"

    def test_twitter_path_uses_create_external_memory_batch(self):
        source = _read_conversations_memories()
        match = re.search(r'(def process_twitter_memories\(.+?)(?=\ndef |\Z)', source, re.DOTALL)
        assert match, "process_twitter_memories not found"
        fn_body = match.group(1)
        assert (
            '.create_external_memory_batch(' in fn_body
        ), "twitter memory path must use create_external_memory_batch for required-processing lifecycle"
        assert (
            '.write_batch(' not in fn_body
        ), "twitter memory path must not use raw write_batch (skips required_processing_payload)"
