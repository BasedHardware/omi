"""DELETE /v3/memories/batch — safe bulk delete with single-delete authorization parity.

Regression goal: the batch route must preserve the EXACT authorization/business semantics
of DELETE /v3/memories/{memory_id}. The earlier bulk-delete attempt (#7006) validated the
batch with get_memories_by_ids and only checked existence, so a caller could slip a locked
(paid-plan) memory into ``memory_ids`` and delete it through the batch route even though the
single-delete route rejects that with 402. These tests pin the guard back in place:

  * a locked memory anywhere in the selection -> 402, nothing deleted
  * a missing / not-owned id -> 404, nothing deleted (get_memories_by_ids is uid-scoped)
  * duplicates are deduped before any DB call
  * a fully valid selection deletes Firestore docs + Pinecone vectors in one batch each
  * the canonical cohort mirrors the single-delete canonical path

Test isolation: routers.memories imports cleanly, so the handler is called directly with
monkeypatched DB/vector helpers (no sys.modules mutation, no TestClient).
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from routers import memories as mem_mod  # noqa: E402


def _force_legacy(monkeypatch):
    """Force the legacy cohort where _validate_memory's locked guard applies."""
    monkeypatch.setattr(mem_mod, '_canonical_write_enabled_or_fail_closed', lambda *a, **k: False)


def _patch_db(monkeypatch, fetched):
    get_mock = MagicMock(return_value=fetched)
    delete_mock = MagicMock()
    monkeypatch.setattr(mem_mod.memories_db, 'get_memories_by_ids', get_mock)
    monkeypatch.setattr(mem_mod.memories_db, 'delete_memories_batch', delete_mock)
    vectors_mock = MagicMock()
    monkeypatch.setattr(mem_mod, 'delete_memory_vectors_batch', vectors_mock)
    return get_mock, delete_mock, vectors_mock


def _force_canonical(monkeypatch, *, existing_ids):
    """Force the canonical cohort and stub its read-only preflight.

    ``existing_ids`` is the set of ids the preflight (read_canonical_memory_item) treats
    as present; any other id reads as None, exactly like a missing / non-active /
    cross-user canonical memory.
    """
    monkeypatch.setattr(mem_mod, '_canonical_write_enabled_or_fail_closed', lambda *a, **k: True)
    existing = set(existing_ids)
    monkeypatch.setattr(
        mem_mod,
        'read_canonical_memory_item',
        lambda uid, memory_id, db_client=None: object() if memory_id in existing else None,
    )


class TestBatchDeleteAuthorizationParity:
    def test_locked_memory_is_rejected_with_402_and_nothing_deleted(self, monkeypatch):
        _force_legacy(monkeypatch)
        get_mock, delete_mock, vectors_mock = _patch_db(
            monkeypatch, [{'id': 'm1', 'is_locked': False}, {'id': 'm2', 'is_locked': True}]
        )
        with pytest.raises(HTTPException) as ei:
            mem_mod.delete_memories_batch(data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['m1', 'm2']), uid='u1')
        assert ei.value.status_code == 402
        # All-or-nothing: the locked memory must not create a bypass to delete the others.
        delete_mock.assert_not_called()
        vectors_mock.assert_not_called()

    def test_missing_or_unauthorized_memory_is_rejected_with_404(self, monkeypatch):
        # 'm2' is absent from the uid-scoped fetch -> missing or owned by another user.
        _force_legacy(monkeypatch)
        get_mock, delete_mock, vectors_mock = _patch_db(monkeypatch, [{'id': 'm1', 'is_locked': False}])
        with pytest.raises(HTTPException) as ei:
            mem_mod.delete_memories_batch(data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['m1', 'm2']), uid='u1')
        assert ei.value.status_code == 404
        delete_mock.assert_not_called()
        vectors_mock.assert_not_called()

    def test_locked_memory_takes_priority_over_visibility_of_others(self, monkeypatch):
        # A single locked memory anywhere in the selection blocks the whole batch.
        _force_legacy(monkeypatch)
        _, delete_mock, vectors_mock = _patch_db(
            monkeypatch,
            [{'id': 'm1', 'is_locked': False}, {'id': 'm2', 'is_locked': False}, {'id': 'm3', 'is_locked': True}],
        )
        with pytest.raises(HTTPException) as ei:
            mem_mod.delete_memories_batch(
                data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['m1', 'm2', 'm3']), uid='u1'
            )
        assert ei.value.status_code == 402
        delete_mock.assert_not_called()


class TestBatchDeleteHappyPath:
    def test_valid_batch_deletes_firestore_docs_and_vectors_once_each(self, monkeypatch):
        _force_legacy(monkeypatch)
        get_mock, delete_mock, vectors_mock = _patch_db(
            monkeypatch, [{'id': 'a', 'is_locked': False}, {'id': 'b', 'is_locked': False}]
        )
        result = mem_mod.delete_memories_batch(data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['a', 'b']), uid='u1')
        assert result == {'status': 'ok'}
        get_mock.assert_called_once_with('u1', ['a', 'b'])
        delete_mock.assert_called_once_with('u1', ['a', 'b'])
        vectors_mock.assert_called_once_with('u1', ['a', 'b'])

    def test_duplicates_are_deduped_before_any_db_call(self, monkeypatch):
        _force_legacy(monkeypatch)
        get_mock, delete_mock, vectors_mock = _patch_db(
            monkeypatch, [{'id': 'a', 'is_locked': False}, {'id': 'b', 'is_locked': False}]
        )
        mem_mod.delete_memories_batch(
            data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['a', 'a', 'b', 'a']), uid='u1'
        )
        # Order-preserving dedupe: no double-counting, no redundant Firestore/Pinecone ops.
        get_mock.assert_called_once_with('u1', ['a', 'b'])
        delete_mock.assert_called_once_with('u1', ['a', 'b'])
        vectors_mock.assert_called_once_with('u1', ['a', 'b'])

    def test_empty_batch_is_a_no_op(self, monkeypatch):
        _force_legacy(monkeypatch)
        get_mock, delete_mock, vectors_mock = _patch_db(monkeypatch, [])
        result = mem_mod.delete_memories_batch(data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=[]), uid='u1')
        assert result == {'status': 'ok'}
        get_mock.assert_not_called()
        delete_mock.assert_not_called()
        vectors_mock.assert_not_called()

    def test_vector_delete_failure_does_not_fail_the_request(self, monkeypatch):
        # Mirrors single-delete: Firestore delete succeeds, best-effort vector cleanup is logged.
        _force_legacy(monkeypatch)
        _, delete_mock, vectors_mock = _patch_db(monkeypatch, [{'id': 'a', 'is_locked': False}])
        vectors_mock.side_effect = RuntimeError('pinecone down')
        result = mem_mod.delete_memories_batch(data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['a']), uid='u1')
        assert result == {'status': 'ok'}
        delete_mock.assert_called_once_with('u1', ['a'])


class TestBatchDeleteCanonicalCohort:
    def test_canonical_cohort_mirrors_single_delete_canonical_path(self, monkeypatch):
        # Canonical cohort preflights every id, then deletes via MemoryService.delete per
        # id (404 on ValueError), and never takes the legacy get_memories_by_ids path.
        _force_canonical(monkeypatch, existing_ids={'a', 'b'})
        svc_mock = MagicMock()
        monkeypatch.setattr(mem_mod, 'MemoryService', lambda **kw: svc_mock)
        get_mock = MagicMock()
        delete_mock = MagicMock()
        monkeypatch.setattr(mem_mod.memories_db, 'get_memories_by_ids', get_mock)
        monkeypatch.setattr(mem_mod.memories_db, 'delete_memories_batch', delete_mock)

        mem_mod.delete_memories_batch(data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['a', 'b']), uid='u1')
        assert svc_mock.delete.call_count == 2
        svc_mock.delete.assert_any_call('u1', 'a')
        svc_mock.delete.assert_any_call('u1', 'b')
        get_mock.assert_not_called()
        delete_mock.assert_not_called()

    def test_canonical_cohort_404_when_memory_not_found_and_nothing_deleted(self, monkeypatch):
        # The preflight rejects a missing id before any MemoryService.delete call, so
        # nothing is mutated — the canonical cohort's all-or-nothing guarantee.
        _force_canonical(monkeypatch, existing_ids=set())  # 'a' reads as missing
        svc_mock = MagicMock()
        monkeypatch.setattr(mem_mod, 'MemoryService', lambda **kw: svc_mock)
        with pytest.raises(HTTPException) as ei:
            mem_mod.delete_memories_batch(data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['a']), uid='u1')
        assert ei.value.status_code == 404
        svc_mock.delete.assert_not_called()

    def test_canonical_cohort_does_not_delete_earlier_valid_id_when_later_id_missing(self, monkeypatch):
        # Regression for the documented all-or-nothing contract: a valid id preceding a
        # missing id must NOT be tombstoned. The earlier per-id delete loop mutated the
        # valid id before the missing one raised 404, deleting part of a batch the API
        # promises to reject wholesale.
        _force_canonical(monkeypatch, existing_ids={'valid'})  # 'missing' reads as missing
        svc_mock = MagicMock()
        monkeypatch.setattr(mem_mod, 'MemoryService', lambda **kw: svc_mock)
        with pytest.raises(HTTPException) as ei:
            mem_mod.delete_memories_batch(
                data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['valid', 'missing']), uid='u1'
            )
        assert ei.value.status_code == 404
        svc_mock.delete.assert_not_called()


class TestBatchDeleteRequestModel:
    def test_accepts_up_to_max(self):
        max_len = mem_mod.MEMORIES_BATCH_MAX
        req = mem_mod.BatchDeleteMemoriesRequest(memory_ids=[f'm{i}' for i in range(max_len)])
        assert len(req.memory_ids) == max_len

    def test_rejects_over_max(self):
        max_len = mem_mod.MEMORIES_BATCH_MAX
        with pytest.raises(ValidationError):
            mem_mod.BatchDeleteMemoriesRequest(memory_ids=[f'm{i}' for i in range(max_len + 1)])

    def test_empty_is_allowed(self):
        req = mem_mod.BatchDeleteMemoriesRequest(memory_ids=[])
        assert req.memory_ids == []


class TestBatchDeleteRateLimitPolicy:
    def test_policy_exists_with_expected_limits(self):
        from utils.rate_limit_config import RATE_POLICIES

        assert 'memories:delete_batch' in RATE_POLICIES
        max_requests, window = RATE_POLICIES['memories:delete_batch']
        # Tighter than memories:delete (60/hour) — each request removes up to 100 memories.
        assert max_requests == 10
        assert window == 3600


class TestBatchDeleteRouteOrdering:
    def test_batch_route_is_registered_before_parametrized_delete(self):
        # FastAPI matches routes in registration order. /v3/memories/batch MUST be registered
        # before /v3/memories/{memory_id}, otherwise "batch" is captured as the {memory_id}
        # path parameter and the endpoint is unreachable.
        delete_paths = [route.path for route in mem_mod.router.routes if 'DELETE' in getattr(route, 'methods', set())]
        assert '/v3/memories/batch' in delete_paths
        assert delete_paths.index('/v3/memories/batch') < delete_paths.index('/v3/memories/{memory_id}')
