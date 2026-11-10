"""The in-flight ledger is fail-open, CAS-serialized and readable; loopback emulator only."""

from __future__ import annotations

import os
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import conversations
from database import pipeline_ledger
from database.record_audio import seal_record_audio

pytestmark = pytest.mark.integration


@pytest.fixture
def client():
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback emulator required; no cloud fallback')
    return firestore.Client(project=f'pipeline-ledger-{uuid4().hex[:12]}', credentials=AnonymousCredentials())


def _conversation_ref(client, uid, capture_id):
    return client.collection('users').document(uid).collection('conversations').document(capture_id)


def _seed(client, uid, capture_id, **fields):
    _conversation_ref(client, uid, capture_id).set(
        {
            'id': capture_id,
            'status': 'completed',
            'data_protection_level': 'standard',
            'record_lane_owner': 'batch_live_v1',
            **fields,
        }
    )


def _ledger(client, uid, capture_id):
    snapshot = client.collection('users').document(uid).collection('pipeline_ledger').document(capture_id).get()
    return snapshot.to_dict() if snapshot.exists else None


def test_seal_writes_ledger_after_real_state(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-seal', 'c-seal'
    _seed(client, uid, capture_id)

    assert seal_record_audio(uid, capture_id, firestore_client=client) is None

    row = _conversation_ref(client, uid, capture_id).get().to_dict()
    assert row['record_audio_closed'] is True
    doc = _ledger(client, uid, capture_id)
    assert doc['stage'] == pipeline_ledger.SEALED
    assert doc['attempt'] == 1
    assert doc['deadline_at'] is not None
    assert doc['expires_at'] is None
    assert doc['schema_version'] == 1
    assert doc['owner_key'] == pipeline_ledger.owner_key(uid)


def test_duplicate_seal_does_not_double_count(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-dup', 'c-dup'
    _seed(client, uid, capture_id)

    assert seal_record_audio(uid, capture_id, firestore_client=client) is None
    assert seal_record_audio(uid, capture_id, firestore_client=client) is None

    doc = _ledger(client, uid, capture_id)
    assert doc['attempt'] == 1
    assert len(doc['transitions']) == 1


def test_upload_failure_writes_a_bounded_terminal(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-fail', 'c-fail'
    _seed(client, uid, capture_id, record_upload_failed=True)

    assert seal_record_audio(uid, capture_id, firestore_client=client) == 'upload_failed'

    doc = _ledger(client, uid, capture_id)
    assert doc['stage'] == 'failed:upload_failed'
    assert doc['terminal'] is True
    assert doc['terminal_reason'] == 'failed:upload_failed'
    assert doc['end_type'] == 'unknown'
    assert doc['expires_at'] is not None


def test_notes_writes_noted_after_real_state(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    monkeypatch.setattr(conversations, 'db', client)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *_: None)
    monkeypatch.setattr(conversations, '_delete_conversation_search_index', lambda *_: None)
    uid, capture_id = 'u-notes', 'c-notes'
    _seed(
        client,
        uid,
        capture_id,
        status='processing',
        summary_title_provenance='server_minimum',
        summary_first_pending_at=100,
        summary_due_at=220,
        sync_content_revision=3,
    )

    assert conversations.persist_processing_result_with_lifecycle(
        uid,
        {
            'id': capture_id,
            'status': 'completed',
            'sync_content_revision': 3,
            'data_protection_level': 'standard',
            'structured': {'title': 'Title', 'overview': 'Synthetic real summary'},
        },
    )

    row = _conversation_ref(client, uid, capture_id).get().to_dict()
    assert row['summary_completed_at']
    doc = _ledger(client, uid, capture_id)
    assert doc['stage'] == pipeline_ledger.NOTED
    assert doc['attempt'] == 1
    assert doc['home_ready_at'] is not None


def test_disabled_ledger_leaves_real_state_unchanged(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'off')
    uid, capture_id = 'u-off', 'c-off'
    _seed(client, uid, capture_id)

    assert seal_record_audio(uid, capture_id, firestore_client=client) is None

    row = _conversation_ref(client, uid, capture_id).get().to_dict()
    assert row['record_audio_closed'] is True
    assert _ledger(client, uid, capture_id) is None


def test_ledger_failure_after_real_commit_leaves_real_state_unchanged(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-boom', 'c-boom'
    _seed(client, uid, capture_id)

    def boom(*_args, **_kwargs):
        raise RuntimeError('synthetic ledger plan failure')

    monkeypatch.setattr(pipeline_ledger, 'plan_advance', boom)

    assert seal_record_audio(uid, capture_id, firestore_client=client) is None

    row = _conversation_ref(client, uid, capture_id).get().to_dict()
    assert row['record_audio_closed'] is True
    assert _ledger(client, uid, capture_id) is None


def test_stale_advance_cannot_overwrite_a_newer_stage(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-stale', 'c-stale'
    _seed(client, uid, capture_id)

    assert pipeline_ledger.advance(uid, capture_id, pipeline_ledger.SEALED, now=100, firestore_client=client)
    assert pipeline_ledger.advance(uid, capture_id, pipeline_ledger.NOTED, now=200, firestore_client=client)
    assert not pipeline_ledger.advance(uid, capture_id, pipeline_ledger.SEALED, now=300, firestore_client=client)

    doc = _ledger(client, uid, capture_id)
    assert doc['stage'] == pipeline_ledger.NOTED
    assert doc['attempt'] == 2


def test_census_window_reads_the_committed_rows(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-window', 'c-window'
    _seed(client, uid, capture_id)
    assert seal_record_audio(uid, capture_id, firestore_client=client) is None

    rows = pipeline_ledger.census_window(0, 10**12, firestore_client=client)
    assert [row['capture_id'] for row in rows] == [capture_id]
    assert rows[0]['stage'] == pipeline_ledger.SEALED
