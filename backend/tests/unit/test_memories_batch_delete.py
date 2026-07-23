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
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from unittest.mock import MagicMock  # noqa: E402

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from routers import memories as mem_mod  # noqa: E402
from models.product_memory import MemoryItem, MemoryItemStatus, MemoryLayer, ProcessingState  # noqa: E402
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState  # noqa: E402
from utils.memory import canonical_memory_adapter as canonical_adapter  # noqa: E402


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
    """Force the canonical cohort and stub its atomic batch adapter."""
    monkeypatch.setattr(mem_mod, '_canonical_write_enabled_or_fail_closed', lambda *a, **k: True)
    existing = set(existing_ids)

    def delete_batch(uid, memory_ids, db_client=None):
        if any(memory_id not in existing for memory_id in memory_ids):
            raise canonical_adapter.CanonicalMemoryNotFoundError("canonical memory not found")

    delete_mock = MagicMock(side_effect=delete_batch)
    monkeypatch.setattr(mem_mod, 'delete_canonical_memories_batch', delete_mock)
    return delete_mock


def _canonical_item(memory_id):
    now = datetime.now(timezone.utc)
    return MemoryItem(
        memory_id=memory_id,
        uid='u1',
        version=1,
        tier=MemoryLayer.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=f'fact {memory_id}',
        evidence=[
            MemoryEvidence(
                evidence_id=f'ev_{memory_id}',
                source_id='conv-1',
                source_type='conversation',
                source_version='v1',
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility='private',
        user_asserted=False,
        captured_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=30),
        ledger_commit_id='c1',
        ledger_sequence=1,
        item_revision=1,
        source_commit_id='c1',
        source_commit_sequence=1,
        content_hash='h',
        account_generation=1,
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
        # Canonical cohort delegates the full selection to one atomic adapter call and
        # never takes the legacy get_memories_by_ids path.
        atomic_delete_mock = _force_canonical(monkeypatch, existing_ids={'a', 'b'})
        get_mock = MagicMock()
        delete_mock = MagicMock()
        monkeypatch.setattr(mem_mod.memories_db, 'get_memories_by_ids', get_mock)
        monkeypatch.setattr(mem_mod.memories_db, 'delete_memories_batch', delete_mock)

        mem_mod.delete_memories_batch(data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['a', 'b']), uid='u1')
        atomic_delete_mock.assert_called_once_with('u1', ['a', 'b'], db_client=mem_mod.db_client_module.db)
        get_mock.assert_not_called()
        delete_mock.assert_not_called()

    def test_canonical_cohort_404_when_memory_not_found_and_nothing_deleted(self, monkeypatch):
        atomic_delete_mock = _force_canonical(monkeypatch, existing_ids=set())
        with pytest.raises(HTTPException) as ei:
            mem_mod.delete_memories_batch(data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['a']), uid='u1')
        assert ei.value.status_code == 404
        atomic_delete_mock.assert_called_once()

    def test_canonical_cohort_does_not_delete_earlier_valid_id_when_later_id_missing(self, monkeypatch):
        # Regression for the documented all-or-nothing contract: the route makes one
        # transactional adapter call, so it has no per-id fallback that could commit
        # "valid" before discovering "missing".
        atomic_delete_mock = _force_canonical(monkeypatch, existing_ids={'valid'})
        with pytest.raises(HTTPException) as ei:
            mem_mod.delete_memories_batch(
                data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['valid', 'missing']), uid='u1'
            )
        assert ei.value.status_code == 404
        atomic_delete_mock.assert_called_once_with(
            'u1',
            ['valid', 'missing'],
            db_client=mem_mod.db_client_module.db,
        )

    def test_canonical_batch_adapter_failure_never_falls_back_to_per_id_delete(self, monkeypatch):
        atomic_delete_mock = _force_canonical(monkeypatch, existing_ids={'a', 'b'})
        atomic_delete_mock.side_effect = RuntimeError('transaction commit failed')
        svc_mock = MagicMock()
        monkeypatch.setattr(mem_mod, 'MemoryService', lambda **kw: svc_mock)

        with pytest.raises(RuntimeError, match='transaction commit failed'):
            mem_mod.delete_memories_batch(
                data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['a', 'b']),
                uid='u1',
            )

        atomic_delete_mock.assert_called_once()
        svc_mock.delete.assert_not_called()

    def test_canonical_internal_validation_error_is_not_mislabeled_as_404(self, monkeypatch):
        atomic_delete_mock = _force_canonical(monkeypatch, existing_ids={'a'})
        atomic_delete_mock.side_effect = ValueError('malformed canonical payload')

        with pytest.raises(ValueError, match='malformed canonical payload'):
            mem_mod.delete_memories_batch(
                data=mem_mod.BatchDeleteMemoriesRequest(memory_ids=['a']),
                uid='u1',
            )

    def test_atomic_adapter_reads_entire_batch_before_queuing_writes(self, monkeypatch):
        class Snapshot:
            def __init__(self, payload=None):
                self.exists = payload is not None
                self._payload = payload

            def to_dict(self):
                return self._payload

        class Document:
            def __init__(self, path):
                self.path = path

            def get(self, transaction=None):
                payload = _canonical_item('valid').model_dump(mode='json') if self.path.endswith('/valid') else None
                return Snapshot(payload)

        transaction = MagicMock()
        client = MagicMock()
        client.transaction.return_value = transaction
        client.document.side_effect = Document

        def transactional_for_test(function):
            def run(txn):
                result = function(txn)
                txn.commit()
                return result

            return run

        monkeypatch.setattr(canonical_adapter, 'transactional', transactional_for_test)
        monkeypatch.setattr(
            canonical_adapter,
            'read_memory_v3_trusted_account_generation',
            lambda **kwargs: SimpleNamespace(read_error_reason=None, account_generation=1, head_commit_id='c1'),
        )

        with pytest.raises(ValueError, match='canonical memory not found: missing'):
            canonical_adapter.delete_canonical_memories_batch(
                'u1',
                ['valid', 'missing'],
                db_client=client,
            )

        transaction.set.assert_not_called()
        transaction.commit.assert_not_called()


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

# The atomic canonical regression above intentionally exercises read-before-write ordering.
