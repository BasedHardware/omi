"""Emulator-level concurrency tests for stale-processing recovery.

These tests require a running Firestore emulator (FIRESTORE_EMULATOR_HOST).
They are wired into the listen-pusher gauntlet (run.sh) so CI always exercises
them against a provisioned emulator.  They verify four correctness invariants
that unit tests with mocks cannot prove:

1. Live-session fencing — recording-session creation/renewal racing recovery
   stays serializable and never exposes a committed binding without its marker.
2. Multi-pod cursor CAS — two pods advancing the cursor concurrently; exactly
   one CAS succeeds and the generation advances by exactly one.
3. Production durable-finalization owner vs orphan race — the real
   ``create_or_get_finalization_intent`` transaction and orphan terminalization
   race on the same conversation; exactly one commits and no active work is
   falsely completed.
4. Deferred reacquire vs orphan sweep — the atomic ``reacquire_deferred_processing``
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
from database import recording_sessions as recording_sessions_db
from database.firestore_transaction_retry import FirestoreContentionExhausted
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.processing_trigger import ProcessingTrigger
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


def _cleanup_recording_session(uid: str, recording_session_id: str):
    client = _client()
    client.collection('users').document(uid).collection('recording_sessions').document(recording_session_id).delete()


def test_recording_session_creation_and_recovery_sweep_race_is_serializable():
    """Opening a session commits its conversation marker in the same transaction."""
    uid = 'test-race-user'
    cid = 'live-recording-creation-race'
    recording_session_id = 'new-live-recording-session'
    now = datetime.now(timezone.utc)
    _cleanup_conversation(uid, cid)
    _cleanup_recording_session(uid, recording_session_id)
    _cleanup_finalization_jobs(uid, cid)

    client = _client()
    conv_ref = client.collection('users').document(uid).collection('conversations').document(cid)
    conv_ref.set(
        {
            'id': cid,
            'status': 'in_progress',
            'source': 'omi',
            'finished_at': now - timedelta(hours=3),
            'audio_files': [{'id': 'live-audio'}],
            'external_data': {'preserved': True},
        }
    )

    barrier = threading.Barrier(2)
    results: dict[str, object] = {}
    errors: list[BaseException] = []

    def open_session():
        barrier.wait()
        try:
            results['binding'] = lifecycle_service.open_live_recording_session(
                uid,
                recording_session_id,
                cid,
                firestore_client=client,
            )
        except Exception as error:
            errors.append(error)

    def sweep_recovery():
        barrier.wait()
        try:
            results['intent'] = jobs_db.create_or_get_finalization_intent(
                uid,
                cid,
                requires_byok=False,
                finalization_admission=lambda conv: lifecycle_service._finalization_admission(conv, cid),
                trigger=ProcessingTrigger.SERVER_RECOVERY,
                recovery_cutoff=now - timedelta(hours=2),
                firestore_client=client,
            )
        except Exception as error:
            errors.append(error)

    opener = threading.Thread(target=open_session)
    sweep = threading.Thread(target=sweep_recovery)
    opener.start()
    sweep.start()
    opener.join(timeout=15)
    sweep.join(timeout=15)

    assert not errors, f'unexpected emulator failures surfaced: {errors}'
    final_conversation = conv_ref.get().to_dict() or {}
    assert final_conversation['external_data'] == {
        'preserved': True,
        'recording_session_id': recording_session_id,
    }
    assert results['binding']['conversation_id'] == cid
    if results['intent']['status'] == 'refused_active_recording_session':
        assert final_conversation['status'] == 'in_progress'
        assert results['binding']['conversation_snapshot']['status'] == 'in_progress'
        assert not final_conversation.get('finalization_job_id')
    else:
        # Recovery linearized first; the later session open observes a
        # processing row rather than creating an unfenced in-progress window.
        assert results['intent']['status'] == 'queued'
        assert final_conversation['status'] == 'processing'
        assert results['binding']['conversation_snapshot']['status'] == 'processing'
        assert final_conversation.get('finalization_job_id')

    _cleanup_conversation(uid, cid)
    _cleanup_recording_session(uid, recording_session_id)
    _cleanup_finalization_jobs(uid, cid)


def test_live_recording_lease_and_recovery_sweep_race_keeps_session_in_progress():
    """A renewal racing SERVER_RECOVERY conflicts on the same session lease."""
    uid = 'test-race-user'
    cid = 'live-recording-recovery-race'
    recording_session_id = 'live-recording-session'
    now = datetime.now(timezone.utc)
    _cleanup_conversation(uid, cid)
    _cleanup_recording_session(uid, recording_session_id)
    _cleanup_finalization_jobs(uid, cid)

    client = _client()
    conv_ref = client.collection('users').document(uid).collection('conversations').document(cid)
    conv_ref.set(
        {
            'id': cid,
            'status': 'in_progress',
            'source': 'omi',
            'finished_at': now - timedelta(hours=3),
            'audio_files': [{'id': 'live-audio'}],
            'external_data': {'recording_session_id': recording_session_id},
        }
    )
    recording_sessions_db.create_or_get_recording_session(
        uid,
        recording_session_id,
        cid,
        firestore_client=client,
    )

    barrier = threading.Barrier(2)
    results: dict[str, object] = {}
    errors: list[BaseException] = []

    def renew_live_lease():
        barrier.wait()
        try:
            results['renewed'] = recording_sessions_db.renew_recording_session_lease(
                uid,
                recording_session_id,
                cid,
                firestore_client=client,
            )
        except Exception as error:
            errors.append(error)

    def sweep_recovery():
        barrier.wait()
        try:
            results['intent'] = jobs_db.create_or_get_finalization_intent(
                uid,
                cid,
                requires_byok=False,
                finalization_admission=lambda conv: lifecycle_service._finalization_admission(conv, cid),
                trigger=ProcessingTrigger.SERVER_RECOVERY,
                recovery_cutoff=now - timedelta(hours=2),
                firestore_client=client,
            )
        except Exception as error:
            errors.append(error)

    renewal = threading.Thread(target=renew_live_lease)
    sweep = threading.Thread(target=sweep_recovery)
    renewal.start()
    sweep.start()
    renewal.join(timeout=15)
    sweep.join(timeout=15)

    assert not errors, f'unexpected emulator failures surfaced: {errors}'
    assert results['renewed'] is True
    assert results['intent']['status'] == 'refused_active_recording_session'
    final_conversation = conv_ref.get().to_dict() or {}
    assert final_conversation['status'] == 'in_progress'
    assert not final_conversation.get('finalization_job_id')

    _cleanup_conversation(uid, cid)
    _cleanup_recording_session(uid, recording_session_id)
    _cleanup_finalization_jobs(uid, cid)


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


# ---------------------------------------------------------------------------
# 4. Concurrent deferred reacquires: exactly one enrichment owner
# ---------------------------------------------------------------------------


def test_concurrent_deferred_reacquires_have_exactly_one_winner():
    """Two simultaneous first opens must never launch duplicate enrichment."""
    uid = 'test-race-user'
    cid = 'deferred-double-open-conv-1'
    _cleanup_conversation(uid, cid)

    client = _client()
    conv_ref = client.collection('users').document(uid).collection('conversations').document(cid)
    conv_ref.set({'id': cid, 'status': 'processing', 'deferred': True})

    results: list[bool] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def reacquire():
        barrier.wait()
        try:
            results.append(jobs_db.reacquire_deferred_processing(uid, cid))
        except Exception as error:
            errors.append(error)

    threads = [threading.Thread(target=reacquire) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not errors, f'unexpected emulator failures surfaced: {errors}'
    assert sorted(results) == [False, True], f'exactly one open must own enrichment: {results}'

    final_data = conv_ref.get().to_dict() or {}
    assert final_data.get('status') == 'processing'
    assert final_data.get('deferred') is False
    assert final_data.get('processing_admitted_at') is not None

    _cleanup_conversation(uid, cid)


# ---------------------------------------------------------------------------
# 5. Unstampable (1 MiB) orphan: the server-owned update_time stands in for the
#    admission fence the document is too large to carry
# ---------------------------------------------------------------------------


def test_unstampable_orphan_is_fenced_by_the_server_owned_update_time():
    """A legacy row whose document rejects the admission stamp is terminalized
    only once no writer has touched it for the staleness window. ``update_time``
    is server-owned and read inside the transaction, so a live writer (or a row
    that has since acquired a fence or a durable owner) is never terminalized.

    The emulator does not enforce the 1 MiB document ceiling, so the oversize
    rejection itself is covered hermetically in
    ``test_stale_processing_reconciliation.py``; what only real Firestore can
    prove is that the snapshot carries a usable ``update_time`` and that the
    fences hold against it."""
    uid = 'test-race-user'
    cid = 'unstampable-conv-1'
    _cleanup_conversation(uid, cid)

    client = _client()
    conv_ref = client.collection('users').document(uid).collection('conversations').document(cid)
    conv_ref.set({'id': cid, 'status': 'processing', 'has_content': True})

    # Just written: inside the staleness window, so it is fenced out.
    assert jobs_db.complete_unstampable_orphan_conversation(uid, cid, stale_after=timedelta(seconds=900)) is False
    assert (conv_ref.get().to_dict() or {}).get('status') == 'processing'

    # A durable finalization owner fences it out even once stale.
    conv_ref.update({'finalization_job_id': 'job-1'})
    assert jobs_db.complete_unstampable_orphan_conversation(uid, cid, stale_after=timedelta(seconds=0)) is False
    assert (conv_ref.get().to_dict() or {}).get('status') == 'processing'

    # Unowned and untouched for the window: exactly one terminal, transcript intact.
    conv_ref.update({'finalization_job_id': firestore.DELETE_FIELD})
    assert jobs_db.complete_unstampable_orphan_conversation(uid, cid, stale_after=timedelta(seconds=0)) is True
    final_data = conv_ref.get().to_dict() or {}
    assert final_data.get('status') == 'completed'
    assert final_data.get('has_content') is True

    # A terminalized row is never terminalized twice.
    assert jobs_db.complete_unstampable_orphan_conversation(uid, cid, stale_after=timedelta(seconds=0)) is False

    _cleanup_conversation(uid, cid)


@pytest.mark.parametrize('status', ['queued', 'leased'])
def test_byok_lost_owner_reclaims_through_real_query_and_reconnect(status):
    """Legacy discovery and stale-epoch fencing execute on the local emulator."""
    client = _client()
    now = datetime.now(timezone.utc)
    job_id = f'byok-lease-reclaim-{status}'
    ref = client.collection(jobs_db.FINALIZATION_JOBS_COLLECTION).document(job_id)
    for state in ('queued', 'leased'):
        client.collection(jobs_db.STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(f'byok_reclaim_{state}').delete()
    ref.set(
        {
            'status': status,
            'requires_byok': True,
            'dispatch_generation': 1,
            'lease_epoch': 7,
            'lease_expires_at': now - timedelta(seconds=1),
            'created_at': now - timedelta(days=30),
            'updated_at': now - timedelta(hours=1),
            'fanout_status': 'completed',
        }
    )
    try:
        result = jobs_db.recover_stranded_byok_jobs(limit=1, firestore_client=client)
        assert result['errors'] == 0
        reclaimed = ref.get().to_dict()
        assert reclaimed['status'] == 'blocked_byok'
        assert reclaimed['lease_epoch'] == 8
        assert 'reconcile_after_at' not in reclaimed
        assert not jobs_db.mark_finalization_completed(job_id, 1, 7, firestore_client=client)
        assert (
            jobs_db.claim_finalization_job(job_id, 1, allow_byok=False, firestore_client=client)['status']
            == 'blocked_byok'
        )
        assert jobs_db.resume_blocked_byok_job_for_live_session(job_id, firestore_client=client)['status'] == 'queued'
        assert 'reconcile_after_at' in ref.get().to_dict()
        claim = jobs_db.claim_finalization_job(job_id, 1, allow_byok=True, firestore_client=client)
        assert claim['status'] == 'claimed' and claim['lease_epoch'] == 9
        assert not jobs_db.mark_finalization_completed(job_id, 1, 7, firestore_client=client)
        assert jobs_db.mark_finalization_completed(job_id, 1, 9, firestore_client=client)
        # Cursor snapshot remains usable after its row has changed status.
        assert jobs_db.recover_stranded_byok_jobs(limit=1, firestore_client=client)['errors'] == 0
    finally:
        ref.delete()
        for state in ('queued', 'leased'):
            client.collection(jobs_db.STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(
                f'byok_reclaim_{state}'
            ).delete()


@pytest.mark.parametrize('winner', ['reconnect', 'abandonment', 'concurrent'])
def test_reclaim_and_abandonment_fence_reconnect_on_local_emulator(winner):
    """Real query plus transactions: either live reconnect or terminal wins."""
    client = _client()
    now = datetime.now(timezone.utc)
    old_activity = now - timedelta(days=30)
    uid = f'byok-compose-{winner}'
    job_id = f'byok-compose-{winner}'
    cid = 'conversation'
    job_ref = client.collection(jobs_db.FINALIZATION_JOBS_COLLECTION).document(job_id)
    conv_ref = client.collection('users').document(uid).collection('conversations').document(cid)
    job_ref.set(
        {
            'uid': uid,
            'conversation_id': cid,
            'finalization_revision': 1,
            'requires_byok': True,
            'status': 'leased',
            'dispatch_generation': 1,
            'lease_epoch': 7,
            'lease_expires_at': now - timedelta(seconds=1),
            'created_at': old_activity,
            'updated_at': old_activity,
            'fanout_status': 'pending',
        }
    )
    conv_ref.set(
        {
            'id': cid,
            'status': 'processing',
            'finalization_job_id': job_id,
            'finalization_revision': 1,
            'structured': {'title': 'Retained recording'},
        }
    )
    bound = jobs_db.get_byok_abandoned_after()
    try:
        jobs_db.claim_finalization_replay(job_id, stale_after=timedelta(minutes=5), firestore_client=client)
        data = job_ref.get().to_dict()
        assert data['status'] == 'blocked_byok' and data['lease_epoch'] == 8
        assert data['byok_last_activity_at'] == old_activity
        # An abandonment candidate scanned before reclaim loses its status/epoch fence.
        stale = jobs_db.abandon_byok_finalization_job(
            job_id,
            expected_status='leased',
            expected_dispatch_generation=1,
            expected_lease_epoch=7,
            abandoned_after=bound,
            firestore_client=client,
        )
        assert stale['status'] == 'fenced'
        candidates = jobs_db.get_abandoned_byok_job_candidates(abandoned_after=bound, firestore_client=client)
        assert any(row['job_id'] == job_id and row['status'] == 'blocked_byok' for row in candidates['candidates'])

        def abandon():
            return jobs_db.abandon_byok_finalization_job(
                job_id,
                expected_status='blocked_byok',
                expected_dispatch_generation=1,
                expected_lease_epoch=8,
                abandoned_after=bound,
                firestore_client=client,
            )

        if winner == 'concurrent':
            barrier = threading.Barrier(2)
            outcomes = {}
            errors = []

            def race(name, action):
                try:
                    barrier.wait(timeout=10)
                    outcomes[name] = action()['status']
                except Exception as error:
                    errors.append(error)

            threads = [
                threading.Thread(target=race, args=('abandon', abandon)),
                threading.Thread(
                    target=race,
                    args=(
                        'resume',
                        lambda: jobs_db.resume_blocked_byok_job_for_live_session(
                            job_id,
                            firestore_client=client,
                        ),
                    ),
                ),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=60)
                assert not thread.is_alive()
            assert not errors, errors
            assert (outcomes['resume'], outcomes['abandon']) in {
                ('queued', 'fenced'),
                ('dead_letter', 'abandoned'),
            }
            expected = 'processing' if outcomes['resume'] == 'queued' else 'completed'
            assert conv_ref.get().to_dict()['status'] == expected
        elif winner == 'reconnect':
            resumed = jobs_db.resume_blocked_byok_job_for_live_session(job_id, firestore_client=client)
            assert resumed['status'] == 'queued'
            assert 'byok_last_activity_at' not in job_ref.get().to_dict()
            assert abandon()['status'] == 'fenced'
            claim = jobs_db.claim_finalization_job(job_id, 1, allow_byok=True, firestore_client=client)
            assert claim['status'] == 'claimed' and claim['lease_epoch'] == 9
            assert conv_ref.get().to_dict()['status'] == 'processing'
        else:
            assert abandon() == {'status': 'abandoned', 'conversation_outcome': 'closed'}
            assert job_ref.get().to_dict()['last_failure_code'] == jobs_db.BYOK_ABANDONED_FAILURE_CODE
            assert conv_ref.get().to_dict()['status'] == 'completed'
            assert (
                jobs_db.resume_blocked_byok_job_for_live_session(job_id, firestore_client=client)['status']
                == 'dead_letter'
            )
            assert abandon()['status'] == 'fenced'
            assert not jobs_db.mark_finalization_completed(job_id, 1, 7, firestore_client=client)
    finally:
        job_ref.delete()
        conv_ref.delete()
