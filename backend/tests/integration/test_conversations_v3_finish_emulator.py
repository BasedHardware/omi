"""Run the Finish read and race proofs with the loopback Firestore emulator."""

import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import conversations_v3_live as store
from utils.conversations.v3 import live


@pytest.fixture
def owner():
    endpoint = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{endpoint}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('This proof requires the loopback Firestore emulator')
    client = firestore.Client(project=os.getenv('GCLOUD_PROJECT', 'demo-listen'), credentials=AnonymousCredentials())
    uid = uuid4().hex
    try:
        yield client, uid, client.collection('users').document(uid).collection('conversations')
    finally:
        client.close()


def test_recent_source_query_ranges_orders_projects_and_limits(owner):
    client, uid, recordings = owner
    now = datetime.now(timezone.utc)
    for index in reversed(range(store.RECENT_FINISH_LIMIT + 2)):
        recordings.document(f'source-{index}').set(
            {
                'finished_at': now - timedelta(seconds=index),
                'external_data': {'recording_session_id': f'listen-{index}', 'not_projected': True},
                'transcript_segments': [{'text': 'synthetic'}],
            }
        )
    recordings.document('old').set({'finished_at': now - store.RECENT_FINISH_AGE - timedelta(seconds=1)})
    recordings.document('missing_clock').set({'recording': True})
    client.collection('users').document(uid + '-other').collection('conversations').document('foreign').set(
        {'finished_at': now}
    )

    @firestore.transactional
    def scan(tx):
        return store._recent_finish_sources(recordings, tx, now)

    snapshots = scan(client.transaction())
    assert [row.id for row in snapshots] == [f'source-{index}' for index in range(store.RECENT_FINISH_LIMIT)]
    assert snapshots[0].to_dict() == {'finished_at': now, 'external_data': {'recording_session_id': 'listen-0'}}

    # A later logical clock places source-0 exactly on the inclusive cutoff.
    now += store.RECENT_FINISH_AGE
    assert [row.id for row in scan(client.transaction())] == ['source-0']


def _recording(now):
    return {
        'created_at': now - timedelta(seconds=30),
        'started_at': now - timedelta(seconds=30),
        'finished_at': now,
        'recording': True,
        'status': 'completed',
        'source': 'omi',
        'external_data': {'recording_session_id': 'test-listen'},
        'has_content': True,
        'v3_pending': True,
        'v3_speech_landed_at': now,
    }


def _window(end, *, is_live):
    return {
        'started_at': end - timedelta(minutes=1),
        'finished_at': end,
        'v3_derived': True,
        'status': 'in_progress' if is_live else 'completed',
        'tile_state': 'live' if is_live else 'done',
    }


@pytest.mark.parametrize('window_age', [timedelta(minutes=30), live.MAX_IDLE + timedelta(minutes=1)])
def test_finish_rechecks_window_inserted_after_initial_lookup(owner, window_age):
    client, uid, recordings = owner
    now = datetime.now(timezone.utc)
    recording = recordings.document('recent-source')
    recording.set(_recording(now))
    assert store.live_window(uid, now=now, max_idle=live.MAX_IDLE, pick=live.active, firestore_client=client) is None

    producer = firestore.Client(project=client.project, credentials=AnonymousCredentials())
    try:
        window = producer.collection('users').document(uid).collection('conversations').document('projected-window')
        window.set(_window(now - window_age, is_live=True))
    finally:
        producer.close()

    outcome, _ = store.request_recording_finish(uid, now=now, firestore_client=client)
    current = recording.get().to_dict()
    if window_age < live.MAX_IDLE:
        assert outcome == 'no_live_window'
        assert live.FINISH_RECORDING_FIELD not in current
        assert 'v3_manual_end_requested' not in current and 'v3_manual_end' not in current
    else:
        assert outcome == 'recording_cut'
        assert current[live.FINISH_RECORDING_FIELD] and current['v3_manual_end']


def test_finish_declines_when_transactional_window_lookup_reaches_its_bound(owner, monkeypatch):
    client, uid, recordings = owner
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(store, 'READ_CAP', 2)
    source = recordings.document('recent-source')
    source.set(_recording(now))
    for minutes in (30, 31):
        recordings.document(f'finished-window-{minutes}').set(_window(now - timedelta(minutes=minutes), is_live=False))

    outcome, recording = store.request_recording_finish(uid, now=now, firestore_client=client)
    assert (outcome, recording) == ('window_lookup_capped', None)
    assert live.FINISH_RECORDING_FIELD not in source.get().to_dict()
