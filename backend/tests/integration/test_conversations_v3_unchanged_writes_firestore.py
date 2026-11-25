"""Exercise committed v3 writes, including the installed Home commit hook."""

from datetime import datetime, timedelta, timezone
import json
import os
from unittest.mock import patch
from uuid import uuid4

from google.api_core.exceptions import Aborted, AlreadyExists
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.transaction import Transaction
import pytest

from database import conversations
from database import conversations_v3 as store, conversations_v3_leases as leases, firestore_write_probe
from database.home_feed_writer import CONTROL
from utils import cloud_tasks
from utils.conversations.v3 import metrics, service, triggers
from utils.encryption import encrypt
from utils.home_feed.projection import DISPLAY, reveal_display


@pytest.fixture
def owner(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('requires a loopback Firestore emulator')
    client = firestore.Client(project='demo-v3-unchanged-writes', credentials=AnonymousCredentials())
    user = client.collection('users').document('test-' + uuid4().hex)
    monkeypatch.setenv('CONVERSATIONS_V3_SKIP_UNCHANGED_WRITES', 'on')
    monkeypatch.setenv('CONVERSATIONS_V3_TASKS_URL', 'https://tasks.example.test')
    try:
        yield client, user
    finally:
        client.recursive_delete(user)
        client.close()


@pytest.fixture
def confirmed_paths():
    paths = []
    original = firestore_write_probe._after

    def capture(writes, response, partial):
        original(writes, response, partial)
        if not partial:
            paths.extend('/'.join(firestore_write_probe.write_op(write)[2][2:]) for write in writes)

    with patch.object(firestore_write_probe, '_after', side_effect=capture):
        yield paths


def projection_rows(count):
    at = datetime(2026, 11, 25, tzinfo=timezone.utc)
    rows = []
    for index in range(count):
        start = at + timedelta(minutes=index)
        rows.append(
            {
                'id': f'card-{index}',
                'v3_derived': True,
                'status': 'completed',
                'source': 'omi',
                'created_at': start,
                'started_at': start,
                'finished_at': start + timedelta(seconds=5),
                'data_protection_level': 'enhanced',
                'structured': {'title': f'Synthetic card {index}'},
                'transcript_segments': [{'id': f'segment-{index}', 'start': 0, 'end': 5, 'text': 'Synthetic speech'}],
            }
        )
    return rows


def projection_pass(owner, rows, cache, recordings=()):
    client, user = owner
    coll = user.collection('conversations')
    existing = {}
    planned = []
    for row in rows:
        snapshot = coll.document(row['id']).get()
        prior = snapshot.to_dict() or {}
        if snapshot.exists:
            existing[row['id']] = {**prior, '_v3_revision': snapshot.update_time}
        # The live planner carries prior bookkeeping through to the next plan.
        planned.append({**prior, **row})
    sources = {rid: store.recording_input(user.id, coll.document(rid).get()) for rid in recordings}
    token = leases.acquire(user.id, 'builder', firestore_client=client)
    assert token
    try:
        leases.renew(user.id, 'builder', token, firestore_client=client)
        return store.commit_projection(user.id, token, sources, existing, planned, cache, firestore_client=client)
    finally:
        leases.release(user.id, 'builder', token, firestore_client=client)


@pytest.mark.asyncio
async def test_noop_pass_bills_three_lease_writes_and_no_home_dirty_merges(owner, confirmed_paths):
    _, user = owner
    rows = projection_rows(24)
    cache = [{'fingerprint': 'canonical', 'entries': [{'title': 'Synthetic'}]}]
    coll = user.collection('conversations')
    for index in range(3):
        rid = f'recording-{index}'
        coll.document(rid).set({'id': rid, 'recording': True, 'status': 'completed'})
        for row in rows[index::3]:
            row['v3_recording_ids'] = [rid]
    recordings = tuple(f'recording-{index}' for index in range(3))
    projection_pass(owner, rows, cache, recordings)
    control = user.collection('episode_links').document(CONTROL)
    control.set({'ready': True}, merge=True)
    card = coll.document('card-0')
    revision = card.get().update_time
    before = metrics.RECONCILE_BILLED_WRITES.labels('builder')._sum.get()
    confirmed_paths.clear()

    @service._measure_reconcile_writes
    async def run():
        return await service.run_blocking(service.db_executor, projection_pass, owner, rows, cache, recordings)

    assert await run() == set()
    assert card.get().update_time == revision
    assert control.get().to_dict()['ready'] is True
    assert len(confirmed_paths) <= 10
    assert confirmed_paths == ['conversation_v3_leases/builder'] * 3
    assert metrics.RECONCILE_BILLED_WRITES.labels('builder')._sum.get() - before == 3


def test_one_changed_field_writes_and_invalidates_home(owner, confirmed_paths):
    _, user = owner
    rows = projection_rows(2)
    projection_pass(owner, rows, [])
    control = user.collection('episode_links').document(CONTROL)
    control.set({'ready': True}, merge=True)
    generation = control.get().to_dict()['generation']
    confirmed_paths.clear()

    rows[0]['structured']['title'] = 'Changed title'
    projection_pass(owner, rows, [])
    assert user.collection('conversations').document('card-0').get().to_dict()['structured']['title'] == 'Changed title'
    assert [path for path in confirmed_paths if path.startswith('conversations/')] == ['conversations/card-0']
    assert f'episode_links/{CONTROL}' in confirmed_paths
    assert 'episode_links/card-0' in confirmed_paths
    assert 'episode_links/card-1' not in confirmed_paths
    assert control.get().to_dict()['ready'] is False
    assert control.get().to_dict()['generation'] != generation


def test_flag_off_restores_projection_and_pending_writes(owner, confirmed_paths, monkeypatch):
    client, user = owner
    rows = projection_rows(2)
    projection_pass(owner, rows, [])
    monkeypatch.setenv('CONVERSATIONS_V3_SKIP_UNCHANGED_WRITES', 'off')
    confirmed_paths.clear()
    projection_pass(owner, rows, [])
    assert 'conversations/card-0' in confirmed_paths
    assert 'conversations/card-1' in confirmed_paths
    assert 'episode_links/card-0' in confirmed_paths
    assert 'episode_links/card-1' in confirmed_paths
    assert len(confirmed_paths) > 3
    recording = user.collection('conversations').document('live')
    recording.set({'recording': True, 'v3_pending': True, 'v3_pending_since': datetime.now(timezone.utc)})
    confirmed_paths.clear()
    assert store.mark_pending(user.id, recording.id, firestore_client=client)
    assert 'conversations/live' in confirmed_paths


def test_edit_at_commit_preserves_pending_then_fresh_plan_converges(owner):
    client, user = owner
    coll = user.collection('conversations')
    rows = projection_rows(1)
    projection_pass(owner, rows, [])
    card = coll.document('card-0')
    source = coll.document('live')
    source.set({'recording': True, 'v3_pending': True, 'v3_pending_since': datetime.now(timezone.utc)})
    recording = store.recording_input(user.id, source.get())
    existing = {'card-0': {'_v3_revision': card.get().update_time}}
    token = leases.acquire(user.id, 'builder', firestore_client=client)
    api = client._firestore_api
    original_commit = api.commit
    original_rollback = api.rollback
    lost = False
    edited = False

    def commit(*args, **kwargs):
        nonlocal lost
        if not lost:
            # Model a competing edit winning at the server's commit boundary.
            # The emulator locks reads pessimistically, so apply it as soon as
            # the losing transaction releases its locks.
            lost = True
            raise Aborted('competing writer at commit')
        return original_commit(*args, **kwargs)

    def rollback(*args, **kwargs):
        nonlocal edited
        result = original_rollback(*args, **kwargs)
        if lost and not edited:
            edited = True
            card.update({'structured.title': 'Concurrent title'})
        return result

    try:
        with patch.object(api, 'commit', side_effect=commit), patch.object(api, 'rollback', side_effect=rollback):
            with pytest.raises(store.Conflict, match='source_changed'):
                store.commit_projection(
                    user.id, token, {'live': recording}, existing, rows, [], firestore_client=client
                )
        assert edited
        assert card.get().to_dict()['structured']['title'] == 'Concurrent title'
        assert source.get().to_dict()['v3_pending'] is True
        rows[0]['structured']['title'] = 'Concurrent title'
        store.commit_projection(
            user.id,
            token,
            {'live': store.recording_input(user.id, source.get())},
            {'card-0': {'_v3_revision': card.get().update_time}},
            rows,
            [],
            firestore_client=client,
        )
        assert card.get().to_dict()['structured']['title'] == 'Concurrent title'
        assert source.get().to_dict()['v3_pending'] is False
    finally:
        leases.release(user.id, 'builder', token, firestore_client=client)


def test_already_pending_wake_racing_active_minute_keeps_durable_work(owner, confirmed_paths, monkeypatch):
    client, user = owner
    coll = user.collection('conversations')
    source = coll.document('live')
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    source.set({'id': 'live', 'recording': True, 'v3_pending': True, 'v3_pending_since': now})
    monkeypatch.setenv('SYNC_TASKS_PROJECT', 'demo-v3-unchanged-writes')
    monkeypatch.setenv('SYNC_TASKS_LOCATION', 'us-central1')
    api = cloud_tasks.tasks_v2.CloudTasksClient(credentials=AnonymousCredentials())
    names = []

    def create_task(*, parent, task):
        names.append(task.name)
        if len(names) == 2:
            raise AlreadyExists('active minute task')

    original_enqueue = triggers.enqueue

    def enqueue(uid, *, manual_end_id=None):
        return original_enqueue(uid, at=now, manual_end_id=manual_end_id)

    with (
        patch.object(store, 'get_firestore_client', return_value=client),
        patch.object(triggers, 'enqueue', side_effect=enqueue),
        patch.object(cloud_tasks, '_get_tasks_client', return_value=api),
        patch.object(cloud_tasks, '_invoker_sa', return_value='test@example.test'),
        patch.object(api, 'create_task', side_effect=create_task),
    ):
        triggers.enqueue(user.id)
        loaded = store.recording_input(user.id, source.get())
        token = leases.acquire(user.id, 'builder', firestore_client=client)
        try:
            source.update({'transcript_segments': [{'id': 'new', 'start': 0, 'end': 1, 'text': 'new speech'}]})
            before = source.get()
            confirmed_paths.clear()
            triggers.changed(user.id, source.id)
            assert names[0] == names[1]
            assert confirmed_paths == []
            assert source.get().update_time == before.update_time
            assert store.commit_projection(user.id, token, {'live': loaded}, {}, [], [], firestore_client=client) == {
                'live'
            }
            assert source.get().to_dict()['v3_pending'] is True

            confirmed_paths.clear()
            triggers.changed(user.id, source.id, manual_end=True)
            assert 'conversations/live' in confirmed_paths
            assert source.get().to_dict()['v3_manual_end'] is True
            assert names[2].startswith(names[0] + '-end-')
        finally:
            leases.release(user.id, 'builder', token, firestore_client=client)


def test_pending_without_a_sweep_timestamp_repairs_the_legacy_marker(owner, confirmed_paths):
    client, user = owner
    source = user.collection('conversations').document('legacy')
    source.set({'recording': True, 'v3_pending': True})
    confirmed_paths.clear()
    assert store.mark_pending(user.id, source.id, firestore_client=client)
    assert 'conversations/legacy' in confirmed_paths
    assert isinstance(source.get().to_dict()['v3_pending_since'], datetime)


def test_multibatch_projection_reads_back_an_unchanged_prefix(owner, confirmed_paths):
    _, user = owner
    rows = projection_rows(2)
    projection_pass(owner, rows, [])
    confirmed_paths.clear()
    rows[1]['structured']['title'] = 'Changed in the final batch'
    with patch.object(store, 'BATCH_ROW_BYTES', 1):
        projection_pass(owner, rows, [])
    assert [path for path in confirmed_paths if path.startswith('conversations/')] == ['conversations/card-1']
    assert 'episode_links/card-0' not in confirmed_paths


def test_privacy_filter_change_is_persisted_before_equality(owner, confirmed_paths):
    _, user = owner
    rows = projection_rows(1)
    projection_pass(owner, rows, [])
    card = user.collection('conversations').document('card-0')
    rows[0]['transcript_segments'][0]['recurring_voice_id'] = 'revoked-voice'
    prepared = conversations.encode_conversation_for_write(user.id, rows[0], 'enhanced')
    card.update(
        {
            'transcript_segments': prepared['transcript_segments'],
            'transcript_segments_compressed': True,
        }
    )
    confirmed_paths.clear()
    projection_pass(owner, rows, [])
    assert 'conversations/card-0' in confirmed_paths
    stored = card.get().to_dict()
    segments = conversations.decode_transcript_segments_blob(user.id, stored['transcript_segments'], True)
    assert 'recurring_voice_id' not in segments[0]


@pytest.mark.asyncio
async def test_reconcile_histogram_excludes_notes_followup(owner, confirmed_paths):
    client, user = owner
    projection_pass(owner, [], [])
    followup = user.collection('test_followup').document('notes')
    before = metrics.RECONCILE_BILLED_WRITES.labels('builder')._sum.get()
    confirmed_paths.clear()

    async def drain(uid):
        assert uid == user.id
        await service.run_blocking(service.db_executor, followup.set, {'processed': True})

    with (
        patch.object(store, 'get_firestore_client', return_value=client),
        patch.object(leases, 'get_firestore_client', return_value=client),
        patch.object(store, 'load', return_value=({}, {}, [])),
        patch.object(service, 'has_pending', return_value=False),
        patch.object(service, 'drain_processing', side_effect=drain),
    ):
        assert await service.reconcile(user.id) == 'committed'

    assert confirmed_paths == ['conversation_v3_leases/builder'] * 3 + ['test_followup/notes']
    assert metrics.RECONCILE_BILLED_WRITES.labels('builder')._sum.get() - before == 3


def test_reconcile_repairs_equal_but_unreadable_home_display(owner, confirmed_paths):
    _, user = owner
    rows = projection_rows(1)
    projection_pass(owner, rows, [])
    card = user.collection('conversations').document('card-0')
    display = reveal_display(user.id, card.get().to_dict()[DISPLAY])
    assert display is not None
    oversized = encrypt(' ' * 7000 + json.dumps(display), user.id)
    assert len(oversized) > 8192
    assert reveal_display(user.id, oversized) is None
    card.update({DISPLAY: oversized})
    control = user.collection('episode_links').document(CONTROL)
    control.set({'ready': True}, merge=True)
    generation = control.get().to_dict()['generation']
    confirmed_paths.clear()

    projection_pass(owner, rows, [])

    assert reveal_display(user.id, card.get().to_dict()[DISPLAY]) == display
    assert 'conversations/card-0' in confirmed_paths
    assert 'episode_links/card-0' in confirmed_paths
    assert control.get().to_dict()['ready'] is False
    assert control.get().to_dict()['generation'] != generation


def test_noop_stages_no_conversation_writes_and_reads_the_same_documents(owner, monkeypatch):
    client, user = owner
    rows = projection_rows(1)
    projection_pass(owner, rows, [])
    path = user.collection('conversations').document('card-0').path
    staged = []
    reads = []
    api = client._firestore_api
    original_get = api.batch_get_documents
    original_set = Transaction.set
    original_update = Transaction.update

    def batch_get(*args, **kwargs):
        reads.extend(kwargs['request']['documents'])
        return original_get(*args, **kwargs)

    def stage(original):
        def record(tx, ref, *args, **kwargs):
            staged.append(ref.path)
            return original(tx, ref, *args, **kwargs)

        return record

    with (
        patch.object(api, 'batch_get_documents', side_effect=batch_get),
        patch.object(Transaction, 'set', stage(original_set)),
        patch.object(Transaction, 'update', stage(original_update)),
    ):
        projection_pass(owner, rows, [])
        assert path not in staged
        enabled_reads = reads.copy()

        staged.clear()
        reads.clear()
        monkeypatch.setenv('CONVERSATIONS_V3_SKIP_UNCHANGED_WRITES', 'off')
        projection_pass(owner, rows, [])
        assert staged.count(path) == 1
        assert len(enabled_reads) == len(reads) == 8
        assert enabled_reads == reads
