"""The in-flight ledger is fail-open, CAS-serialized and readable; loopback emulator only."""

from __future__ import annotations

import os
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import conversations
from database import pipeline_ledger
from database.record_audio import mark_record_upload_failed, seal_record_audio, set_record_upload_pending

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
    client.collection('users').document(uid).set({'id': uid})
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
    assert doc['expires_at'] is not None
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


def test_reconnect_reseal_admits_once_per_capture(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-readmit', 'c-readmit'
    _seed(client, uid, capture_id)

    assert seal_record_audio(uid, capture_id, firestore_client=client) is None
    assert set_record_upload_pending(uid, capture_id, 'token', True, firestore_client=client)
    assert set_record_upload_pending(uid, capture_id, 'token', False, firestore_client=client)
    assert seal_record_audio(uid, capture_id, firestore_client=client) is None

    doc = _ledger(client, uid, capture_id)
    assert doc['attempt'] == 1
    assert [entry['stage'] for entry in doc['transitions']].count(pipeline_ledger.SEALED) == 1


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
    assert doc['end_at'] is not None
    assert doc['expires_at'] is not None


def test_upload_failure_uses_the_persisted_failure_clock(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-failclock', 'c-failclock'
    _seed(client, uid, capture_id, record_upload_failed=True, record_upload_failed_at=1234.5)

    assert seal_record_audio(uid, capture_id, firestore_client=client) == 'upload_failed'

    doc = _ledger(client, uid, capture_id)
    assert doc['end_at'] == 1234.5


def test_delete_conversation_removes_the_sibling_ledger_row(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    monkeypatch.setattr(conversations, 'db', client)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations, '_delete_conversation_search_index', lambda *_: None)
    monkeypatch.setattr(conversations, 'stop_quiet_check_for_conversation', lambda *_, **__: None)
    monkeypatch.setattr(conversations, 'leave_capture_group', lambda *_, **__: None)
    monkeypatch.setattr(conversations.speaker_auto_enroll, 'retract_conversation', lambda *_, **__: None)
    monkeypatch.setattr('database.proactivity.purge_source_items', lambda **_: None)
    uid, capture_id = 'u-delete', 'c-delete'
    _seed(client, uid, capture_id)
    assert pipeline_ledger.advance(uid, capture_id, pipeline_ledger.SEALED, now=100, firestore_client=client)
    assert _ledger(client, uid, capture_id) is not None

    conversations.delete_conversation(uid, capture_id)

    assert _conversation_ref(client, uid, capture_id).get().exists is False
    assert _ledger(client, uid, capture_id) is None


def test_account_erasure_removes_the_pipeline_ledger(client, monkeypatch):
    from types import SimpleNamespace

    from database import user_data_deletion
    from database._client import delete_collection_recursive

    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-erase', 'c-erase'
    _seed(client, uid, capture_id)
    assert pipeline_ledger.advance(uid, capture_id, pipeline_ledger.SEALED, now=100, firestore_client=client)
    assert _ledger(client, uid, capture_id) is not None

    monkeypatch.setattr('database.batch_pipeline_purge.purge_batch_owner', lambda _uid: None)
    monkeypatch.setattr(user_data_deletion, 'get_data_plane_firestore_client', lambda: client)
    monkeypatch.setattr(user_data_deletion, 'search_apps_db', lambda _uid, my_apps: [])
    monkeypatch.setattr(user_data_deletion, 'delete_generic_cache', lambda *_a, **_kw: None)
    monkeypatch.setattr(user_data_deletion, 'stop_quiet_checks_for_account', lambda *_a, **_kw: None)
    monkeypatch.setattr(user_data_deletion, 'generation_ref', lambda _ref: SimpleNamespace(delete=lambda: None))

    result = user_data_deletion.purge_user_subtree(
        uid, client, lambda sub, **kw: delete_collection_recursive(sub, client=client)
    )

    assert result['status'] == 'ok'
    assert _ledger(client, uid, capture_id) is None


def test_erasure_sweeps_a_ledger_write_that_lands_after_the_collection_walk(client, monkeypatch):
    from types import SimpleNamespace

    from database import user_data_deletion
    from database._client import delete_collection_recursive

    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-erase-race', 'c-erase-race'
    _seed(client, uid, capture_id)
    # The collection must already exist so the account walk enumerates and
    # sweeps it before the root delete; the delayed write lands after that.
    client.collection('users').document(uid).collection(pipeline_ledger.COLLECTION).document('existing').set(
        {'stage': pipeline_ledger.CAPTURING}
    )

    fired = []
    calls = []

    def racing_delete(sub, *, client):
        calls.append(getattr(sub, 'id', None))
        delete_collection_recursive(sub, client=client)
        if getattr(sub, 'id', None) == pipeline_ledger.COLLECTION and not fired:
            fired.append(True)
            # A delayed seal/upload-failure commits after the ledger sweep but
            # before the owner root is deleted, so the owner fence still allows
            # the row. Only the post-root sweep can remove it.
            assert pipeline_ledger.advance(uid, capture_id, pipeline_ledger.SEALED, now=100, firestore_client=client)

    monkeypatch.setattr('database.batch_pipeline_purge.purge_batch_owner', lambda _uid: None)
    monkeypatch.setattr(user_data_deletion, 'get_data_plane_firestore_client', lambda: client)
    monkeypatch.setattr(user_data_deletion, 'search_apps_db', lambda _uid, my_apps: [])
    monkeypatch.setattr(user_data_deletion, 'delete_generic_cache', lambda *_a, **_kw: None)
    monkeypatch.setattr(user_data_deletion, 'stop_quiet_checks_for_account', lambda *_a, **_kw: None)
    monkeypatch.setattr(user_data_deletion, 'generation_ref', lambda _ref: SimpleNamespace(delete=lambda: None))

    result = user_data_deletion.purge_user_subtree(uid, client, racing_delete)

    assert result['status'] == 'ok'
    assert fired == [True]
    assert [name for name in calls if name == pipeline_ledger.COLLECTION] == [
        pipeline_ledger.COLLECTION,
        pipeline_ledger.COLLECTION,
    ]
    assert (
        client.collection('users')
        .document(uid)
        .collection(pipeline_ledger.COLLECTION)
        .document('existing')
        .get()
        .exists
        is False
    )
    assert _ledger(client, uid, capture_id) is None


def test_delayed_ledger_write_does_not_recreate_after_source_delete(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-del', 'c-del'
    _seed(client, uid, capture_id)
    original = pipeline_ledger.advance

    def delete_then_advance(*args, **kwargs):
        _conversation_ref(client, uid, capture_id).delete()
        return original(*args, **kwargs)

    monkeypatch.setattr(pipeline_ledger, 'advance', delete_then_advance)
    assert seal_record_audio(uid, capture_id, firestore_client=client) is None
    assert _ledger(client, uid, capture_id) is None


def test_late_event_from_an_older_revision_is_refused(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-order', 'c-order'
    _seed(client, uid, capture_id)
    owner_ref = client.collection('users').document(uid)
    source_ref = _conversation_ref(client, uid, capture_id)

    assert pipeline_ledger.advance(
        uid,
        capture_id,
        'failed:upload_failed',
        revision=10,
        reopen=True,
        source_ref=source_ref,
        owner_ref=owner_ref,
        firestore_client=client,
    )
    assert pipeline_ledger.advance(
        uid,
        capture_id,
        pipeline_ledger.SEALED,
        revision=20,
        reopen=True,
        source_ref=source_ref,
        owner_ref=owner_ref,
        firestore_client=client,
    )
    assert not pipeline_ledger.advance(
        uid,
        capture_id,
        'failed:upload_failed',
        revision=15,
        reopen=True,
        source_ref=source_ref,
        owner_ref=owner_ref,
        firestore_client=client,
    )
    doc = _ledger(client, uid, capture_id)
    assert doc['stage'] == pipeline_ledger.SEALED
    assert doc['revision'] == 20


def test_disabled_ledger_leaves_real_state_unchanged(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'off')
    uid, capture_id = 'u-off', 'c-off'
    _seed(client, uid, capture_id)

    assert seal_record_audio(uid, capture_id, firestore_client=client) is None

    row = _conversation_ref(client, uid, capture_id).get().to_dict()
    assert row['record_audio_closed'] is True
    assert 'record_admitted_at' not in row
    assert _ledger(client, uid, capture_id) is None


def test_ledger_off_restores_the_upload_failure_payload(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'off')
    uid, capture_id = 'u-off-fail', 'c-off-fail'
    _seed(client, uid, capture_id)

    assert mark_record_upload_failed(uid, capture_id, firestore_client=client)

    row = _conversation_ref(client, uid, capture_id).get().to_dict()
    assert row['record_upload_failed'] is True
    assert 'record_upload_failed_at' not in row
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


def test_source_revision_failure_cannot_fail_the_seal(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    uid, capture_id = 'u-revboom', 'c-revboom'
    _seed(client, uid, capture_id)

    def boom(_snapshot):
        raise RuntimeError('synthetic source revision failure')

    monkeypatch.setattr(pipeline_ledger, 'source_revision', boom)

    assert seal_record_audio(uid, capture_id, firestore_client=client) is None

    row = _conversation_ref(client, uid, capture_id).get().to_dict()
    assert row['record_audio_closed'] is True
    assert _ledger(client, uid, capture_id)['stage'] == pipeline_ledger.SEALED


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

    rows = pipeline_ledger.census_window(0, 10**12, uid=uid, firestore_client=client)
    assert len(rows) == 1
    assert rows[0]['stage'] == pipeline_ledger.SEALED
    assert rows[0]['owner_key'] == pipeline_ledger.owner_key(uid)
    assert 'capture_id' not in rows[0]


def test_census_window_never_reads_another_owner(client, monkeypatch):
    monkeypatch.setenv('PIPELINE_LEDGER', 'on')
    assert pipeline_ledger.advance('u-a', 'c-a', pipeline_ledger.SEALED, now=100, firestore_client=client)
    assert pipeline_ledger.advance('u-b', 'c-b', pipeline_ledger.SEALED, now=100, firestore_client=client)

    rows = pipeline_ledger.census_window(0, 10**12, uid='u-a', firestore_client=client)
    assert [row['owner_key'] for row in rows] == [pipeline_ledger.owner_key('u-a')]
