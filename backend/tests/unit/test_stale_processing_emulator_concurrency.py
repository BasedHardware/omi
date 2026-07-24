"""Emulator-level concurrency tests for stale-processing recovery.

These tests require a running Firestore emulator (FIRESTORE_EMULATOR_HOST).
They verify two correctness invariants that unit tests with mocks cannot prove:

1. Multi-pod cursor CAS — two pods advancing the cursor concurrently; exactly
   one CAS succeeds and the generation advances by exactly one.
2. Finalizer-vs-orphan race — durable-job attachment and orphan terminalization
   racing on the same conversation; exactly one transaction commits and no
   active work is falsely completed.

Run: cd backend && FIRESTORE_EMULATOR_HOST=localhost:8080 \
    .venv/bin/python -m pytest tests/unit/test_stale_processing_emulator_concurrency.py
"""

import os
import threading
from datetime import datetime, timedelta, timezone

import pytest

from database import conversation_finalization_jobs as jobs_db
from firebase_admin import firestore

_EMULATOR = os.getenv('FIRESTORE_EMULATOR_HOST')
pytestmark = pytest.mark.skipif(not _EMULATOR, reason='requires FIRESTORE_EMULATOR_HOST')


def _client():
    return jobs_db._client(None)


def _cleanup_cursor():
    client = _client()
    client.collection(jobs_db.STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(
        jobs_db.STALE_PROCESSING_SWEEP_STATE_DOC
    ).delete()


def _cleanup_conversation(uid: str, cid: str):
    client = _client()
    client.collection('users').document(uid).collection('conversations').document(cid).delete()


# ---------------------------------------------------------------------------
# 1. Multi-pod cursor CAS: competing writers cannot rewind progress
# ---------------------------------------------------------------------------


def test_competing_cursor_writers_cas_prevents_rewind():
    """Two pods advance the cursor concurrently from the same generation.
    Exactly one CAS succeeds; the loser is fenced out and the generation
    advances by exactly one — no rewind."""
    _cleanup_cursor()

    cursor = jobs_db.get_stale_processing_sweep_cursor()
    assert cursor == {'resume_after_path': None, 'generation': 0}

    results: dict[str, bool] = {}
    barrier = threading.Barrier(2)

    def pod(name: str, new_path: str):
        barrier.wait()
        results[name] = jobs_db.advance_stale_processing_sweep_cursor(0, new_path)

    t1 = threading.Thread(target=pod, args=('pod-a', 'users/u1/conversations/c1'))
    t2 = threading.Thread(target=pod, args=('pod-b', 'users/u2/conversations/c2'))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # Exactly one writer committed.
    assert sum(v for v in results.values()) == 1, f'expected exactly one winner, got {results}'

    final = jobs_db.get_stale_processing_sweep_cursor()
    assert final['generation'] == 1
    assert final['resume_after_path'] in ('users/u1/conversations/c1', 'users/u2/conversations/c2')

    _cleanup_cursor()


def test_serial_cursor_advances_are_all_committed():
    """Serial advances from two pods each bump the generation — no CAS loss
    when they don't overlap."""
    _cleanup_cursor()

    assert jobs_db.advance_stale_processing_sweep_cursor(0, 'users/u/c/a') is True
    mid = jobs_db.get_stale_processing_sweep_cursor()
    assert mid == {'resume_after_path': 'users/u/c/a', 'generation': 1}

    assert jobs_db.advance_stale_processing_sweep_cursor(1, None) is True
    final = jobs_db.get_stale_processing_sweep_cursor()
    assert final == {'resume_after_path': None, 'generation': 2}

    _cleanup_cursor()


# ---------------------------------------------------------------------------
# 2. Finalizer-vs-orphan race: exactly one transaction commits
# ---------------------------------------------------------------------------


def _attach_finalization_job_txn(transaction, conv_ref, job_id):
    """Simulate a finalizer attaching durable ownership inside a transaction
    that verifies the row is still processing and has no existing job."""
    snapshot = conv_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    data = snapshot.to_dict() or {}
    if data.get('status') != 'processing':
        return False
    if data.get('finalization_job_id'):
        return False
    transaction.update(conv_ref, {'finalization_job_id': job_id})
    return True


def test_finalizer_vs_orphan_race_exactly_one_wins():
    """A durable-job attachment and an orphan terminalization race on the same
    bare-processing conversation. Exactly one transaction commits; the other is
    fenced by the precondition check on retry."""
    uid = 'test-race-user'
    cid = 'race-conv-1'
    old_admitted = datetime.now(timezone.utc) - timedelta(seconds=1000)
    _cleanup_conversation(uid, cid)

    client = _client()
    conv_ref = client.collection('users').document(uid).collection('conversations').document(cid)
    conv_ref.set(
        {
            'id': cid,
            'status': 'processing',
            'processing_admitted_at': old_admitted,
            'transcript_segments': [{'text': 'race test'}],
        }
    )

    results: dict[str, bool] = {}
    barrier = threading.Barrier(2)

    def orphan_terminalize():
        barrier.wait()
        results['orphan'] = jobs_db.complete_orphan_conversation(uid, cid, expected_admitted_at=old_admitted)

    def finalizer_attach():
        barrier.wait()
        txn = client.transaction()
        transactional = firestore.transactional(_attach_finalization_job_txn)
        results['finalizer'] = transactional(txn, conv_ref, 'job-race-1')

    t1 = threading.Thread(target=orphan_terminalize)
    t2 = threading.Thread(target=finalizer_attach)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # Exactly one transaction committed.
    assert sum(v for v in results.values()) == 1, f'expected exactly one winner, got {results}'

    final_data = conv_ref.get().to_dict() or {}

    if results.get('orphan'):
        # The orphan won: the conversation is completed and no durable job was
        # attached — no active work was falsely completed.
        assert final_data.get('status') == 'completed'
        assert not final_data.get('finalization_job_id')
    else:
        # The finalizer won: the durable job is attached and the conversation
        # is still processing — the orphan was fenced out.
        assert final_data.get('finalization_job_id') == 'job-race-1'
        assert final_data.get('status') == 'processing'

    _cleanup_conversation(uid, cid)
