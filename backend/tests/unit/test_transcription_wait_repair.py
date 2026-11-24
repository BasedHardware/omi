"""The legacy observation is a separate one-shot display stamp, never custody."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from database import transcription_wait_repair as repair
from tests.unit.fixtures.strict_firestore_transaction import (
    StrictFirestore,
    StrictFirestoreDocument,
    StrictFirestoreSnapshot,
)
from utils.conversations import transcribing_hold

ROW = ('users', 'synthetic', 'conversations', 'capture')
JOB = ('batch_pipeline_prod_jobs', 'job')
T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)


@pytest.fixture
def source(monkeypatch):
    client = StrictFirestore(
        {
            ROW: {
                'status': 'completed',
                'record_lane_owner': 'batch_live_v1',
                'home_transcription_pending_at': T0,
                'home_transcription_deadline_at': T0 + timedelta(hours=2),
            },
            JOB: {'owner_id': 'synthetic', 'conversation_id': 'capture', 'state': 'ready', 'audio_uri': 'retained'},
        }
    )
    monkeypatch.setattr(repair.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(repair, 'run_transactional', lambda client, fn, **kw: fn(client.transaction()))
    # Keep the shared strict transaction's reference and read-before-write
    # assertions. Only this boundary's two flat metadata masks are modeled
    # locally; no query, retry or contention semantics are added to the fake.
    original_get = StrictFirestoreDocument.get
    client.metadata_reads = []

    def metadata_get(ref, transaction=None, *, field_paths=None, **kwargs):
        assert field_paths in (repair.ROW_FIELDS, repair.JOB_FIELDS)
        assert not {'structured', 'transcript_segments', 'user_title'} & set(field_paths)
        client.metadata_reads.append(list(field_paths))
        snapshot = original_get(ref, transaction=transaction, **kwargs)
        data = snapshot.to_dict()
        return StrictFirestoreSnapshot(
            None if data is None else {key: value for key, value in data.items() if key in field_paths}
        )

    monkeypatch.setattr(StrictFirestoreDocument, 'get', metadata_get)
    return client


def run(client, *, apply=False):
    ref = client.collection(JOB[0]).document(JOB[1])
    return repair.observe_legacy_queue(client, 'synthetic', 'capture', [ref], T0.timestamp() + 30 * 3600, apply=apply)


def test_dry_run_has_no_writes_and_apply_is_one_shot(source):
    before = deepcopy(source.rows)
    assert run(source) == 'eligible'
    assert source.rows == before
    assert all(not tx.updates and not tx.sets for tx in source.transactions)
    assert run(source, apply=True) == 'observed'
    assert source.rows[JOB] == before[JOB]
    row = source.rows[ROW]
    assert row == {**before[ROW], repair.OBSERVED_FIELD: T0.timestamp() + 30 * 3600}
    assert transcribing_hold.deadline(row) == T0 + timedelta(hours=54)
    # A repeated operator invocation can never extend the display wait.
    ref = source.collection(JOB[0]).document(JOB[1])
    assert (
        repair.observe_legacy_queue(source, 'synthetic', 'capture', [ref], T0.timestamp() + 50 * 3600, apply=True)
        == 'already_stamped'
    )
    assert transcribing_hold.deadline(row) == T0 + timedelta(hours=54)
    assert not source.transactions[-1].updates


@pytest.mark.parametrize(
    'change',
    [
        {'state': 'leased'},
        {'state': 'record_pending'},
        {'state': 'committed'},
        {'owner_id': 'different-owner'},
        {'conversation_id': 'different-capture'},
        {'audio_uri': None},
    ],
)
def test_changed_job_or_unknown_audio_refuses_observation(source, change):
    source.rows[JOB].update(change)
    before = deepcopy(source.rows)
    assert run(source, apply=True) == 'job_ineligible'
    assert source.rows == before


@pytest.mark.parametrize(
    'change,expected',
    [
        ({'record_admitted_at': 100}, 'already_stamped'),
        ({repair.OBSERVED_FIELD: 100}, 'already_stamped'),
        ({'status': 'in_progress'}, 'row_ineligible'),
        ({'record_projection_revision': 1}, 'row_ineligible'),
        ({'deleted': True}, 'row_ineligible'),
        ({'discarded': True}, 'row_ineligible'),
        ({'record_upload_failed': True}, 'row_ineligible'),
        ({'record_audio_partial': {'generation': 1}}, 'row_ineligible'),
        ({'record_upload_sessions': {'producer': {}}}, 'row_ineligible'),
    ],
)
def test_fresh_seal_recovery_custody_and_tombstones_win(source, change, expected):
    source.rows[ROW].update(change)
    before = deepcopy(source.rows)
    assert run(source, apply=True) == expected
    assert source.rows == before


def test_missing_job_is_not_a_queue_observation(source):
    assert (
        repair.observe_legacy_queue(source, 'synthetic', 'capture', [], T0.timestamp(), apply=True) == 'row_ineligible'
    )
    assert not source.transactions[-1].updates


def test_operator_observation_fetches_only_state_metadata(source):
    assert run(source) == 'eligible'
    assert source.metadata_reads == [repair.ROW_FIELDS, repair.JOB_FIELDS]
