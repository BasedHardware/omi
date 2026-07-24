"""Emulator-level concurrency tests for stale-processing recovery.

These tests require a running Firestore emulator (FIRESTORE_EMULATOR_HOST).
They are wired into the listen-pusher gauntlet (run.sh) so CI always exercises
them against a provisioned emulator.  They verify three correctness invariants
that unit tests with mocks cannot prove:

1. Multi-pod cursor CAS — two pods advancing the cursor concurrently; exactly
   one CAS succeeds and the generation advances by exactly one.
2. Production durable-finalization owner vs orphan race — the real
   ``create_or_get_finalization_intent`` transaction and orphan terminalization
   race on the same conversation; exactly one commits and no active work is
   falsely completed.
3. Deferred reacquire vs orphan sweep — the atomic ``reacquire_deferred_processing``
   transaction and orphan terminalization race; exactly one commits and no stale
   processor produces side effects.

Run: cd backend && FIRESTORE_EMULATOR_HOST=localhost:8080 \
    .venv/bin/python -m pytest tests/unit/test_stale_processing_emulator_concurrency.py
"""

import os
import threading
from datetime import datetime, timedelta, timezone

import pytest

from database import conversation_finalization_jobs as jobs_db
from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.conversations import lifecycle as lifecycle_service
from firebase_admin import firestore
from google.api_core.exceptions import Aborted

# Only expected Firestore transaction contention may be treated as a CAS loss.
# Any other exception is a real failure and must surface, never be swallowed.
_CONTENTION = (Aborted, FirestoreContentionExhausted)

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
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def pod(name: str, new_path: str):
        barrier.wait()
        try:
            results[name] = jobs_db.advance_stale_processing_sweep_cursor(0, new_path)
        except _CONTENTION:
            # Expected transaction contention: the other pod's commit won, so
            # this one lost (equivalent to a CAS False).
            results[name] = False
        except Exception as error:
            errors.append(error)
            results[name] = False

    t1 = threading.Thread(target=pod, args=('pod-a', 'users/u1/conversations/c1'))
    t2 = threading.Thread(target=pod, args=('pod-b', 'users/u2/conversations/c2'))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    # Unexpected failures must surface — only expected contention may be a CAS loss.
    assert not errors, f'unexpected emulator failures surfaced: {errors}'
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
# 2. Production durable-finalization owner vs orphan race
# ---------------------------------------------------------------------------


def _cleanup_finalization_jobs(uid: str, cid: str):
    client = _client()
    for doc in (
        client.collection(jobs_db.FINALIZATION_JOBS_COLLECTION)
        .where('uid', '==', uid)
        .where('conversation_id', '==', cid)
        .stream()
    ):
        doc.reference.delete()


def test_production_finalizer_vs_orphan_race_exactly_one_wins():
    """The production ``create_or_get_finalization_intent`` transaction and
    orphan terminalization race on the same bare-processing conversation.
    Exactly one commits; the other is fenced by the transaction's precondition
    checks on retry."""
    uid = 'test-race-user'
    cid = 'race-conv-prod-1'
    old_admitted = datetime.now(timezone.utc) - timedelta(seconds=1000)
    _cleanup_conversation(uid, cid)
    _cleanup_finalization_jobs(uid, cid)

    client = _client()
    conv_ref = client.collection('users').document(uid).collection('conversations').document(cid)
    conv_ref.set(
        {
            'id': cid,
            'status': 'processing',
            'processing_admitted_at': old_admitted,
            'has_content': True,
        }
    )

    results: dict[str, object] = {}
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def orphan_terminalize():
        barrier.wait()
        try:
            results['orphan'] = jobs_db.complete_orphan_conversation(uid, cid, expected_admitted_at=old_admitted)
        except _CONTENTION:
            results['orphan'] = False
        except Exception as error:
            errors.append(error)
            results['orphan'] = False

    def production_finalizer():
        barrier.wait()
        try:
            intent = jobs_db.create_or_get_finalization_intent(
                uid,
                cid,
                requires_byok=False,
                finalization_admission=lambda conv: lifecycle_service._finalization_admission(conv, cid),
            )
            results['finalizer'] = bool(intent.get('job_id'))
        except _CONTENTION:
            results['finalizer'] = False
        except Exception as error:
            errors.append(error)
            results['finalizer'] = False

    t1 = threading.Thread(target=orphan_terminalize)
    t2 = threading.Thread(target=production_finalizer)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    # Unexpected failures must surface — only expected contention may fence a racer.
    assert not errors, f'unexpected emulator failures surfaced: {errors}'
    orphan_won = bool(results.get('orphan'))
    finalizer_won = bool(results.get('finalizer'))
    assert orphan_won != finalizer_won, f'expected exactly one winner, got {results}'

    final_data = conv_ref.get().to_dict() or {}

    if orphan_won:
        assert final_data.get('status') == 'completed'
        assert not final_data.get('finalization_job_id')
    else:
        assert final_data.get('finalization_job_id')
        assert final_data.get('status') == 'processing'

    _cleanup_conversation(uid, cid)
    _cleanup_finalization_jobs(uid, cid)


# ---------------------------------------------------------------------------
# 3. Deferred reacquire vs orphan sweep: no stale terminalization
# ---------------------------------------------------------------------------


def test_deferred_reacquire_prevents_orphan_terminalization():
    """The atomic ``reacquire_deferred_processing`` prevents the orphan sweep
    from terminalizing a deferred row. The lease renewal is atomic with
    clearing deferred, so the orphan either sees ``deferred=True`` (skips) or
    sees a changed ``processing_admitted_at`` (CAS-fenced). No stale writes or
    derived effects from a terminalized enrichment can occur."""
    uid = 'test-race-user'
    cid = 'deferred-race-conv-1'
    old_admitted = datetime.now(timezone.utc) - timedelta(seconds=1000)
    _cleanup_conversation(uid, cid)

    client = _client()
    conv_ref = client.collection('users').document(uid).collection('conversations').document(cid)
    conv_ref.set(
        {
            'id': cid,
            'status': 'processing',
            'processing_admitted_at': old_admitted,
            'deferred': True,
        }
    )

    results: dict[str, object] = {}
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def orphan_terminalize():
        barrier.wait()
        try:
            results['orphan'] = jobs_db.complete_orphan_conversation(uid, cid, expected_admitted_at=old_admitted)
        except _CONTENTION:
            results['orphan'] = False
        except Exception as error:
            errors.append(error)
            results['orphan'] = False

    def deferred_reacquire():
        barrier.wait()
        try:
            results['reacquire'] = jobs_db.reacquire_deferred_processing(uid, cid)
        except _CONTENTION:
            results['reacquire'] = False
        except Exception as error:
            errors.append(error)
            results['reacquire'] = False

    t1 = threading.Thread(target=orphan_terminalize)
    t2 = threading.Thread(target=deferred_reacquire)
    t1.start()
    t2.start()
    t1.join(timeout=15)
    t2.join(timeout=15)

    # Unexpected failures must surface — only expected contention may fence a racer.
    assert not errors, f'unexpected emulator failures surfaced: {errors}'

    # reacquire always wins: it atomically clears deferred and renews the lease.
    # The orphan is fenced: either by deferred=True (if it reads before
    # reacquire commits) or by the changed processing_admitted_at (if it reads
    # after). The conversation must remain processing for the enrichment.
    assert results.get('reacquire') is True, f'reacquire should succeed, got {results}'
    assert results.get('orphan') is False, f'orphan should be fenced, got {results}'

    final_data = conv_ref.get().to_dict() or {}
    assert final_data.get('status') == 'processing', 'conversation should still be processing'
    assert final_data.get('deferred') is False, 'deferred should be cleared'
    assert final_data.get('processing_admitted_at') != old_admitted, 'lease should be renewed'

    _cleanup_conversation(uid, cid)
