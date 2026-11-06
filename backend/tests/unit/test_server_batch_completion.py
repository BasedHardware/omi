"""Strict ordering and generation guards for the zero-preview terminal commit.

Rollback, real transforms and retry semantics are covered by the emulator
suite; StrictFirestore deliberately does not approximate those boundaries.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from database import conversation_finalization_jobs as jobs
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import lifecycle

UID, CID, JOB = 'owner', 'capture', 'job'
ROW = ('users', UID, 'conversations', CID)
JOB_ROW = (jobs.FINALIZATION_JOBS_COLLECTION, JOB)
NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)


def capture():
    return {
        'id': CID,
        'status': 'processing',
        'record_lane_owner': 'batch_live_v1',
        'external_data': {'server_batch_only': True, 'recording_session_id': 'session'},
        'private_cloud_sync_enabled': True,
        'data_protection_level': 'standard',
        'finalization_job_id': JOB,
        'finalization_revision': 3,
        'transcript_segments': [],
    }


def job():
    return {
        'uid': UID,
        'conversation_id': CID,
        'status': 'leased',
        'dispatch_generation': 2,
        'lease_epoch': 4,
        'finalization_revision': 3,
        'fanout_status': 'pending',
    }


def complete(db, admitted=None, generation=2, epoch=4):
    return jobs._complete_server_batch_capture_txn(
        db.transaction(),
        db.collection(jobs.FINALIZATION_JOBS_COLLECTION).document(JOB),
        db.document('/'.join(ROW)),
        UID,
        CID,
        admitted or capture(),
        generation,
        epoch,
        NOW,
    )


@pytest.mark.parametrize('gate,seconds', [('on', 7200), ('off', 600)])
def test_atomic_terminal_preserves_relevance_and_replay_does_not_repeat_delta(monkeypatch, gate, seconds):
    monkeypatch.setenv('HOME_TRANSCRIPTION_PRESENTATION_GATE', gate)
    monkeypatch.setenv('HOME_TRANSCRIPTION_DEADLINE_SECONDS', str(seconds))
    prior = {'verdict': 'keep', 'decided_by': 'user', 'reason': 'restored', 'trigger': 'user_restore'}
    row = {**capture(), 'relevance_decision': prior}
    db = StrictFirestore({ROW: row, JOB_ROW: job()})
    delta = Mock()
    monkeypatch.setattr(jobs, '_record_projection_delta', delta)
    assert complete(db) == 'completed'
    assert db.rows[ROW]['status'] == db.rows[JOB_ROW]['status'] == 'completed'
    assert db.rows[ROW]['relevance_decision'] == prior
    assert db.rows[ROW]['transcript_segments'] == []
    assert db.rows[ROW]['home_transcription_pending_at'] == NOW
    deadline = NOW + timedelta(seconds=seconds)
    assert db.rows[ROW]['home_transcription_deadline_at'] == deadline
    terminal = db.rows[JOB_ROW]
    assert terminal['fanout_status'] == 'completed'
    assert terminal['fanout_lease_epoch'] == 4
    assert terminal['terminal_outcome'] == 'success'
    assert terminal['finalization_outcome'] == 'server_batch_capture'
    assert terminal['fanout_key'] == 'conversation:capture:finalization:3'
    assert complete(db) == 'completed'
    assert not db.transactions[-1].has_written
    assert db.rows[ROW]['home_transcription_deadline_at'] == deadline
    delta.assert_called_once_with(db.transactions[0], None, job(), leased=-1, completed=1, success=1)
    assert jobs._mark_finalization_completed_txn(
        db.transaction(), db.collection(jobs.FINALIZATION_JOBS_COLLECTION).document(JOB), 2, 4, NOW
    )  # Existing outer worker acknowledgement remains an idempotent no-op.
    assert not db.transactions[-1].has_written


def test_terminal_stamps_relevance_from_current_snapshot():
    db = StrictFirestore({ROW: capture(), JOB_ROW: job()})
    assert complete(db) == 'completed'
    decision = db.rows[ROW]['relevance_decision']
    assert decision['verdict'] == 'keep'
    assert decision['trigger'] == 'lifecycle_terminal'


@pytest.mark.parametrize('generation,epoch', [(1, 4), (2, 3), (3, 5)])
@pytest.mark.parametrize('terminal', [False, True])
def test_old_generation_or_lease_cannot_write_or_replay(generation, epoch, terminal):
    db = StrictFirestore({ROW: capture(), JOB_ROW: job()})
    if terminal:
        assert complete(db) == 'completed'
    before = deepcopy(db.rows)
    assert complete(db, generation=generation, epoch=epoch) == 'lease_conflict'
    assert db.rows == before
    assert not db.transactions[-1].has_written


@pytest.mark.parametrize(
    'change',
    [
        {'private_cloud_sync_enabled': False},
        {'uses_custom_stt': True},
        {'deleted': True},
        {'discarded': True},
        {'is_locked': True},
        {'data_protection_level': 'e2ee'},
        {'record_lane_owner': 'legacy_final_pass_v1'},
        {'external_data': {'server_batch_only': False}},
        {'external_data': {'server_batch_only': True, 'recording_session_id': 'successor'}},
        {'server_batch_only': True},
        {'finalization_job_id': 'successor'},
        {'finalization_revision': 4},
        {'status': 'in_progress'},
        {'status': 'completed'},
    ],
)
def test_current_capture_guard_fences_without_completing_conversation(monkeypatch, change):
    row = {**capture(), **change}
    db = StrictFirestore({ROW: row, JOB_ROW: job()})
    delta = Mock()
    monkeypatch.setattr(jobs, '_record_projection_delta', delta)
    assert complete(db) == 'fenced'
    assert db.rows[ROW] == row
    assert db.rows[JOB_ROW]['terminal_outcome'] == 'stale'
    assert db.rows[JOB_ROW]['fanout_status'] == 'fenced'
    assert complete(db) == 'fenced'
    assert not db.transactions[-1].has_written
    delta.assert_called_once_with(db.transactions[0], None, job(), leased=-1, completed=1, stale=1)


@pytest.mark.parametrize(
    'change',
    [
        {'uid': 'other'},
        {'conversation_id': 'other'},
        {'finalization_revision': 5},
        {'finalization_revision': None},
    ],
)
def test_immutable_job_binding_guard(change):
    db = StrictFirestore({ROW: capture(), JOB_ROW: {**job(), **change}})
    assert complete(db) == 'fenced'
    assert db.rows[ROW]['status'] == 'processing'


@pytest.mark.parametrize('missing', [ROW, JOB_ROW])
def test_missing_owner_is_not_success(missing):
    rows = {ROW: capture(), JOB_ROW: job()}
    rows.pop(missing)
    db = StrictFirestore(rows)
    assert complete(db) == ('missing' if missing == JOB_ROW else 'fenced')
    assert ROW not in db.rows or db.rows[ROW]['status'] == 'processing'


@pytest.mark.parametrize(
    'change', [{'fanout_status': 'pending'}, {'finalization_outcome': 'fenced'}, {'status': 'dead_letter'}]
)
def test_other_terminal_is_not_a_server_batch_replay(change):
    db = StrictFirestore({ROW: capture(), JOB_ROW: job()})
    assert complete(db) == 'completed'
    db.rows[JOB_ROW].update(change)
    before = deepcopy(db.rows)
    assert complete(db) != 'completed'
    assert db.rows == before


def test_lifecycle_effects_run_after_commit_and_on_same_generation_replay(monkeypatch):
    db = StrictFirestore({ROW: capture(), JOB_ROW: job()})
    monkeypatch.setattr(jobs.firestore, 'transactional', lambda fn: fn)
    calls = []

    def observe(name):
        def effect(*args, **kwargs):
            assert db.rows[ROW]['status'] == db.rows[JOB_ROW]['status'] == 'completed'
            calls.append(name)

        return effect

    monkeypatch.setattr(jobs, 'stop_quiet_check_for_conversation', observe('quiet'))
    monkeypatch.setattr(jobs, 'invalidate_people_stats_cache', observe('people'))
    monkeypatch.setattr(jobs.conversations_db, 'serving_for', lambda *args: True)
    monkeypatch.setattr(jobs.conversations_db, 'sync_conversation_search_index_public', observe('search'))
    for _ in range(2):
        assert (
            lifecycle.complete_server_batch_capture(UID, CID, capture(), JOB, 2, 4, firestore_client=db) == 'completed'
        )
    assert calls == ['quiet', 'people', 'search'] * 2


@pytest.mark.parametrize('failure', ['fenced', 'abort'])
def test_failed_transaction_publishes_no_effects(monkeypatch, failure):
    db = StrictFirestore({ROW: {**capture(), 'discarded': True}, JOB_ROW: job()})

    def transactional(fn):
        def run(*args, **kwargs):
            if failure == 'abort':
                raise RuntimeError('before commit')
            return fn(*args, **kwargs)

        return run

    monkeypatch.setattr(jobs.firestore, 'transactional', transactional)
    effects = Mock()
    monkeypatch.setattr(jobs, 'stop_quiet_check_for_conversation', effects)
    monkeypatch.setattr(jobs, 'invalidate_people_stats_cache', effects)
    monkeypatch.setattr(jobs.conversations_db, 'sync_conversation_search_index_public', effects)
    if failure == 'abort':
        with pytest.raises(RuntimeError, match='before commit'):
            lifecycle.complete_server_batch_capture(UID, CID, capture(), JOB, 2, 4, firestore_client=db)
    else:
        assert lifecycle.complete_server_batch_capture(UID, CID, capture(), JOB, 2, 4, firestore_client=db) == 'fenced'
    effects.assert_not_called()
