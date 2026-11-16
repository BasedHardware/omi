"""Real Firestore transactions for paid-once quiet notes and resumed-input fencing.

Only loopback emulator data is accepted. The production codec, leases, source
queries, reservation and summary writer run unchanged against Firestore.
"""

import os
import asyncio
import json
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from threading import Event

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import _client, conversations_v3 as store, conversations_v3_leases as leases
from database import conversations_v3_quiet as attempts, conversations_v3_processing as writers
from utils.conversations.v3 import quiet, summary, summary_input, service

pytestmark = pytest.mark.integration


@pytest.fixture
def seeded(monkeypatch):
    assert os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(
        ('127.0.0.1:', 'localhost:')
    ), 'loopback emulator required'
    client = firestore.Client(project='demo-quiet-summary', credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, '_firestore_client', client)
    monkeypatch.setattr(_client, '_data_plane_firestore_client', client)
    uid, cid, rid = 'quiet-test-' + uuid4().hex, 'canonical', 'recording'
    coll = store.user_conversations(client, uid)
    end = datetime.now(timezone.utc) - timedelta(seconds=40)
    start = end - timedelta(seconds=7180)
    segments = [
        {
            'id': f's{i}',
            'text': 'A synthetic planning decision for Friday.',
            'start': i * 20,
            'end': i * 20 + 19,
            'is_user': True,
        }
        for i in range(359)
    ]
    source = {
        'id': rid,
        'source': 'omi',
        'recording': True,
        'status': 'in_progress',
        'created_at': start,
        'started_at': start,
        'finished_at': end,
        'data_protection_level': 'standard',
        'transcript_segments': segments,
        'v3_quiet_due': end + timedelta(seconds=30),
        'v3_quiet_pending': True,
    }
    source['v3_quiet_generation'] = summary_input.fingerprint(source)
    row = {
        'id': cid,
        'source': 'omi',
        'v3_derived': True,
        'kind': 'conversation',
        'status': 'in_progress',
        'tile_state': 'live',
        'created_at': start,
        'started_at': start,
        'finished_at': end,
        'v3_recording_ids': [rid],
        'v3_source_hashes': {rid: summary_input.fingerprint(source)},
        'transcript_segments': segments,
        'data_protection_level': 'standard',
        'structured': {'title': 'My title', 'emoji': '💬'},
        'title_locked': True,
    }
    coll.document(rid).set(source)
    coll.document(cid).set(row)
    leases.lease_ref(client, uid, 'builder').set({'open_id': cid})
    try:
        yield client, uid, cid, rid, coll
    finally:
        for doc in coll.stream():
            doc.reference.delete()
        for doc in client.collection('users').document(uid).collection('conversation_v3_leases').stream():
            doc.reference.delete()
        client.collection('account_deletions').document(uid).delete()
        client.close()


def claim(seeded):
    client, uid, cid, rid, coll = seeded
    token = leases.acquire(uid, 'summary-' + cid, firestore_client=client)
    snapshot = coll.document(cid).get()
    permit = attempts.reserve(uid, cid, token, snapshot.update_time, quiet=True, firestore_client=client)
    return token, permit


def persist(seeded, token, permit):
    client, uid, cid, _, _ = seeded
    writers.store_summary(
        uid,
        cid,
        token,
        permit['revision'],
        {
            'title': 'Generated replacement',
            'emoji': '💬',
            'sections': [{'heading': 'Plan', 'body_markdown': 'Ship Friday.'}],
        },
        permit['row']['finished_at'],
        input_hash=permit['input_hash'],
        source_revisions=permit['sources'],
        firestore_client=client,
    )


@pytest.fixture
def builder_path(monkeypatch):
    from utils.conversations.v3 import visibility

    dispatched = []
    monkeypatch.setattr(service.context, 'outline_sources', lambda *a: ({}, [], []))
    monkeypatch.setattr(visibility, 'hydrate_recognition', lambda *a: None)
    monkeypatch.setattr(service, 'enqueue', lambda *a, **kw: None)
    monkeypatch.setattr(service, 'dispatch_quiet', lambda *a, **kw: dispatched.append((a, kw)), raising=False)
    monkeypatch.setattr(
        service.models,
        'outline',
        lambda *a: '{"conversations":[{"first_line":1,"title":"Plan","line":"You planned Friday.","kind":"conversation","sections":[]}]}',
    )
    monkeypatch.setattr(quiet, 'require_generated_compute', lambda *a, **kw: None)
    return dispatched


def test_contending_deliveries_on_open_and_replay_reserve_one_paid_snapshot(seeded):
    client, uid, cid, _, coll = seeded
    token = leases.acquire(uid, 'summary-' + cid, firestore_client=client)
    revision = coll.document(cid).get().update_time

    def compete(_):
        return attempts.reserve(uid, cid, token, revision, quiet=True, firestore_client=client)

    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(compete, range(3)))
    assert sum(result is not None for result in results) == 1
    assert attempts.reserve(uid, cid, token, revision, firestore_client=client) is None
    persist(seeded, token, next(result for result in results if result))
    result = store.decode_row(uid, coll.document(cid).get())
    assert result['structured']['title'] == 'My title'
    assert result['structured']['sections'][0]['body_markdown'] == 'Ship Friday.'
    assert result['status'] == 'in_progress' and result['tile_state'] == 'live'
    assert not result.get('v3_process_pending') and not result.get('v3_process_attempts')
    assert summary.fresh(result)
    assert len(leases.lease_ref(client, uid, 'summary-' + cid).get().to_dict()['snapshot_inputs']) == 1


@pytest.mark.parametrize('gap_seconds', [300, 900])
def test_finished_on_open_ignores_unrelated_pending_recording_at_reserve_and_store(seeded, gap_seconds):
    client, uid, cid, rid, coll = seeded
    coll.document(cid).update({'status': 'completed', 'tile_state': 'done'})
    leases.lease_ref(client, uid, 'builder').update({'open_id': 'another-conversation'})
    end = coll.document(cid).get().to_dict()['finished_at']
    unrelated_start = end + timedelta(seconds=gap_seconds)
    coll.document('unrelated-pending').set(
        {
            'recording': True,
            'v3_pending': True,
            'status': 'in_progress',
            'started_at': unrelated_start,
            'finished_at': unrelated_start + timedelta(seconds=10),
            'transcript_segments': [
                {'text': 'A separate ongoing conversation.', 'start': 0, 'end': 10, 'is_user': True}
            ],
        }
    )
    token = leases.acquire(uid, 'summary-' + cid, firestore_client=client)
    revision = coll.document(cid).get().update_time
    permit = attempts.reserve(uid, cid, token, revision, firestore_client=client)
    assert permit is not None
    assert set(permit['sources']) == {rid}
    # A further unrelated append during generation cannot revoke the older window's write.
    coll.document('unrelated-pending').update({'finished_at': unrelated_start + timedelta(seconds=20)})
    persist(seeded, token, permit)
    result = store.decode_row(uid, coll.document(cid).get())
    assert result['structured']['sections'][0]['body_markdown'] == 'Ship Friday.'
    assert result['status'] == 'completed' and result['tile_state'] == 'done'


def test_finished_on_open_still_fences_nearby_pending_source_at_commit(seeded):
    client, uid, cid, rid, coll = seeded
    coll.document(cid).update({'status': 'completed', 'tile_state': 'done'})
    token = leases.acquire(uid, 'summary-' + cid, firestore_client=client)
    permit = attempts.reserve(uid, cid, token, coll.document(cid).get().update_time, firestore_client=client)
    assert permit
    start = permit['row']['finished_at'] + timedelta(seconds=299)
    coll.document('nearby-pending').set({'recording': True, 'v3_pending': True, 'started_at': start})
    with pytest.raises(store.Conflict, match='summary_source_changed'):
        persist(seeded, token, permit)


def test_noop_projection_batches_keep_encrypted_doc_revisions_unchanged(seeded):
    client, uid, cid, rid, coll = seeded
    original = coll.document(cid).get().to_dict()
    rows, existing, revisions, encoded_size = [], {}, {}, 0
    for index in range(4):
        row = {
            **deepcopy(original),
            'id': f'closed-{index}',
            'status': 'completed',
            'tile_state': 'done',
            'data_protection_level': 'enhanced',
            'structured': {
                'title': 'Large retained notes',
                'emoji': '💬',
                'sections': [{'heading': 'Retained', 'body_markdown': 'Synthetic. ' * 53000}],
            },
        }
        encoded = store.conversations._prepare_conversation_for_write(row, uid, 'enhanced', allow_offload=False)
        encoded_size += len(json.dumps(encoded, default=str).encode())
        coll.document(row['id']).set(encoded)
        snapshot = coll.document(row['id']).get()
        decoded = store.decode_row(uid, snapshot)
        existing[row['id']] = decoded
        rows.append(deepcopy(decoded))
        revisions[row['id']] = snapshot.update_time
    assert encoded_size > 2 * 1024 * 1024
    token = leases.acquire(uid, 'builder', firestore_client=client)
    store.commit_projection(uid, token, {}, existing, rows, [], firestore_client=client)
    assert {key: coll.document(key).get().update_time for key in revisions} == revisions


@pytest.mark.asyncio
async def test_competing_quiet_and_on_open_catchup_preserve_inflight_paid_result(seeded, builder_path, monkeypatch):
    client, uid, cid, rid, coll = seeded
    await service.reconcile(uid, on_open=True, conversation_id=cid)
    entered, resume = Event(), Event()
    paid = []

    def write(owner, row, emit):
        paid.append(row['id'])
        entered.set()
        assert resume.wait(15)
        return {'title': 'Plan', 'sections': [{'heading': 'Plan', 'body_markdown': 'The paid result survived.'}]}

    monkeypatch.setattr(summary, 'write', write)
    generation = coll.document(rid).get().to_dict()['v3_quiet_generation']
    first = asyncio.create_task(quiet.run(uid, rid, generation))
    try:
        assert await asyncio.to_thread(entered.wait, 10)
        before = coll.document(cid).get().update_time, coll.document(rid).get().update_time
        assert await quiet.run(uid, rid, generation) == 'retry'
        assert await service.reconcile(uid, on_open=True, conversation_id=cid) in {'busy', 'committed'}
        assert (coll.document(cid).get().update_time, coll.document(rid).get().update_time) == before
    finally:
        resume.set()
        await first
    current = store.decode_row(uid, coll.document(cid).get())
    assert current['structured']['sections'][0]['body_markdown'] == 'The paid result survived.'
    assert paid == [cid]


@pytest.mark.asyncio
async def test_catchup_preserves_discovery_of_unprojected_partial_tail(seeded, builder_path, monkeypatch):
    client, uid, cid, rid, coll = seeded
    start = coll.document(cid).get().to_dict()['finished_at'] + timedelta(seconds=1)
    coll.document('pending-tail').set(
        {
            'id': 'pending-tail',
            'recording': True,
            'status': 'in_progress',
            'v3_pending': True,
            'v3_pending_since': start,
            'created_at': start,
            'started_at': start,
            'finished_at': start,
            'record_audio_partial': {'generation': 2, 'applied_generation': 1},
            'transcript_segments': [],
        }
    )
    monkeypatch.setattr(summary, 'write', lambda *a: pytest.fail('known pending tail bought notes'))
    generation = coll.document(rid).get().to_dict()['v3_quiet_generation']
    assert await quiet.run(uid, rid, generation) == 'settled'
    assert coll.document('pending-tail').get().to_dict()['v3_pending']
    assert not coll.document(cid).get().to_dict().get('summary_covers_through')
    assert not leases.lease_ref(client, uid, 'summary-' + cid).get().to_dict().get('snapshot_inputs')


@pytest.mark.asyncio
async def test_reconcile_recovers_quiet_obligation_after_accepted_content_trigger_crash(
    seeded, builder_path, monkeypatch
):
    client, uid, cid, rid, coll = seeded
    # Accepted transcript custody committed v3_pending, then the process died before changed().
    coll.document(rid).update(
        {
            'v3_pending': True,
            'v3_pending_since': datetime.now(timezone.utc),
            'v3_quiet_pending': firestore.DELETE_FIELD,
            'v3_quiet_generation': firestore.DELETE_FIELD,
            'v3_quiet_due': firestore.DELETE_FIELD,
        }
    )
    await service.reconcile(uid)
    source = coll.document(rid).get().to_dict()
    assert source['v3_pending'] is False and source['v3_quiet_pending'] is True
    assert source['v3_quiet_generation'] == summary_input.fingerprint(store.decode_row(uid, coll.document(rid).get()))
    assert any(args[:2] == (uid, rid) for args, _kw in builder_path)
    coll.document(rid).update({'v3_quiet_due': datetime.now(timezone.utc) - timedelta(seconds=1)})
    monkeypatch.setattr(
        summary, 'write', lambda *a: {'title': 'Plan', 'sections': [{'heading': 'Plan', 'body_markdown': 'Recovered.'}]}
    )
    assert await quiet.run(uid, rid, source['v3_quiet_generation']) == 'settled'
    assert store.decode_row(uid, coll.document(cid).get())['structured']['sections'][0]['body_markdown'] == 'Recovered.'


@pytest.mark.asyncio
@pytest.mark.parametrize('resolve_speaker', [False, True])
async def test_normal_final_persistence_is_fresh_on_open_without_a_speculative_permit(
    seeded, monkeypatch, resolve_speaker
):
    from utils.conversations import process_conversation

    client, uid, cid, rid, coll = seeded
    coll.document(cid).update({'v3_process_pending': True, 'status': 'processing'})
    full_calls = []

    def process(owner, language, row, **kw):
        full_calls.append(row.id)
        if resolve_speaker:
            row.transcript_segments[0].is_user = False
        coll.document(cid).update(
            {
                'status': 'completed',
                'transcript_segments': [segment.model_dump() for segment in row.transcript_segments],
                'structured': {
                    'title': 'Final',
                    'emoji': '💬',
                    'sections': [{'heading': 'Plan', 'body_markdown': 'Authoritative final notes.'}],
                },
            }
        )
        kw['persistence_observer'](True)
        row.status = 'completed'
        return row

    monkeypatch.setattr(process_conversation, 'process_conversation', process)
    await service.drain_processing(uid)
    current = store.decode_row(uid, coll.document(cid).get())
    assert summary.fresh(current) and current['summary_is_snapshot'] is False
    monkeypatch.setattr(summary, 'write', lambda *a: pytest.fail('final notes bought another on-open call'))
    assert await summary.prepare(uid, current) is None
    assert [frame async for frame in summary.stream(uid, current)][0].startswith('done: ')
    assert full_calls == [cid]
    assert not leases.lease_ref(client, uid, 'summary-' + cid).get().to_dict().get('snapshot_inputs')


@pytest.mark.parametrize(
    'race', ['resume', 'new_recording', 'correction', 'split', 'delete', 'lock', 'private', 'account_deletion']
)
def test_late_model_write_loses_every_input_and_privacy_fence(seeded, race):
    client, uid, cid, rid, coll = seeded
    token, permit = claim(seeded)
    assert permit
    if race == 'resume':
        # Speech has committed on the transport; canonical projection has not caught up.
        source = coll.document(rid).get().to_dict()
        source['transcript_segments'].append({'text': 'Resumed speech', 'start': 7180, 'end': 7189, 'is_user': True})
        coll.document(rid).update({'transcript_segments': source['transcript_segments'], 'v3_pending': True})
    elif race == 'new_recording':
        coll.document('new-transport').set(
            {'recording': True, 'v3_pending': True, 'transcript_segments': [{'text': 'Resumed'}]}
        )
    elif race == 'correction':
        source = coll.document(cid).get().to_dict()
        source['transcript_segments'][0]['text'] = 'Same-time corrected words'
        coll.document(cid).update({'transcript_segments': source['transcript_segments']})
    elif race == 'split':
        coll.document(cid).update({'finished_at': permit['row']['finished_at'] - timedelta(minutes=20)})
    elif race == 'account_deletion':
        client.collection('account_deletions').document(uid).set({'status': 'pending'})
    else:
        coll.document(cid).update(
            {'deleted': True}
            if race == 'delete'
            else {'is_locked': True} if race == 'lock' else {'data_protection_level': 'private'}
        )
    with pytest.raises(store.Conflict):
        persist(seeded, token, permit)
    assert not coll.document(cid).get().to_dict().get('summary_covers_through')


@pytest.mark.parametrize('guard', ['active', 'tail', 'media', 'short', 'new_pending'])
def test_not_ready_content_never_spends_a_permit(seeded, guard):
    client, uid, cid, rid, coll = seeded
    if guard == 'active':
        coll.document(cid).update({'finished_at': datetime.now(timezone.utc)})
    elif guard == 'tail':
        coll.document(rid).update({'record_audio_partial': {'generation': 2, 'applied_generation': 1}})
    elif guard == 'media':
        coll.document(cid).update({'kind': 'media'})
    elif guard == 'short':
        coll.document(cid).update({'transcript_segments': [{'text': 'brief', 'start': 0, 'end': 1, 'is_user': True}]})
    else:
        coll.document('pending').set({'recording': True, 'v3_pending': True})
    token, permit = claim(seeded)
    assert permit is None
    assert not leases.lease_ref(client, uid, 'summary-' + cid).get().to_dict().get('snapshot_inputs')


@pytest.mark.asyncio
async def test_two_hour_live_snapshot_and_duplicate_tasks_never_enter_full_processor(seeded, monkeypatch):
    client, uid, cid, rid, coll = seeded
    calls = []
    monkeypatch.setattr(quiet, 'require_generated_compute', lambda *a, **kw: None)
    monkeypatch.setattr(service, 'reconcile', _noop_reconcile)

    def write(owner, row, emit):
        calls.append((owner, row['id']))
        assert row['status'] == 'in_progress' and row['finished_at'] - row['started_at'] > timedelta(minutes=119)
        emit('## Plan\nShip Friday.')
        return {'title': 'Plan', 'sections': [{'heading': 'Plan', 'body_markdown': 'Ship Friday.'}]}

    monkeypatch.setattr(summary, 'write', write)
    from utils.conversations import process_conversation, lifecycle

    monkeypatch.setattr(
        process_conversation, 'process_conversation', lambda *a, **kw: pytest.fail('early full processing')
    )
    monkeypatch.setattr(lifecycle, 'complete', lambda *a, **kw: pytest.fail('early closure'))
    generation = coll.document(rid).get().to_dict()['v3_quiet_generation']
    assert await quiet.run(uid, rid, generation) == 'settled'
    assert await quiet.run(uid, rid, generation) == 'superseded'
    canonical = store.decode_row(uid, coll.document(cid).get())
    assert calls == [(uid, cid)]
    assert canonical['status'] == 'in_progress' and canonical['tile_state'] == 'live'
    assert not canonical.get('v3_process_pending')
    assert summary.fresh(canonical)
    # All final derived work is still owed to the ordinary close owner.
    assert not canonical.get('v3_process_attempts')


async def _noop_reconcile(*a, **kw):
    return 'committed'


@pytest.mark.asyncio
async def test_real_builder_quiet_snapshot_then_normal_close_runs_final_work_once(seeded, monkeypatch):
    client, uid, cid, rid, coll = seeded
    from utils.conversations.v3 import models, visibility
    from utils.conversations import process_conversation
    from types import SimpleNamespace

    monkeypatch.setattr(quiet, 'require_generated_compute', lambda *a, **kw: None)
    monkeypatch.setattr(service.context, 'outline_sources', lambda *a: ({}, [], []))
    monkeypatch.setattr(visibility, 'hydrate_recognition', lambda *a: None)
    monkeypatch.setattr(service, 'enqueue', lambda *a, **kw: None)
    monkeypatch.setattr(
        models,
        'outline',
        lambda *a: '{"conversations":[{"first_line":1,"title":"Plan","line":"You planned Friday.","kind":"conversation","sections":[]}]}',
    )
    early, final = [], []

    def write(owner, row, emit):
        early.append(row['id'])
        return {'title': 'Plan', 'sections': [{'heading': 'Plan', 'body_markdown': 'Provisional notes.'}]}

    def process(owner, language, row, **kw):
        final.append(row.id)
        coll.document(row.id).update(
            {
                'status': 'completed',
                'structured': {'title': 'Final', 'sections': [{'heading': 'Plan', 'body_markdown': 'Final notes.'}]},
            }
        )
        kw['persistence_observer'](True)
        row.status = 'completed'
        return row

    monkeypatch.setattr(summary, 'write', write)
    monkeypatch.setattr(process_conversation, 'process_conversation', process)
    assert store.mark_pending(uid, rid, firestore_client=client)
    # Control only the acceptance clock so the real path runs immediately instead of sleeping 30s.
    coll.document(rid).update({'v3_quiet_due': datetime.now(timezone.utc) - timedelta(seconds=1)})
    generation = coll.document(rid).get().to_dict()['v3_quiet_generation']
    assert await quiet.run(uid, rid, generation) == 'settled'
    assert early == [cid] and not final
    current = store.decode_row(uid, coll.document(cid).get())
    assert current['status'] == 'in_progress' and current['tile_state'] == 'live'
    assert len(current['transcript_segments']) == 359
    assert len(list(coll.where(filter=firestore.FieldFilter('v3_derived', '==', True)).stream())) == 1

    class ClosedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.now(timezone.utc) + timedelta(minutes=15)

    monkeypatch.setattr(service, 'datetime', ClosedClock)
    await service.reconcile(uid)
    await service.reconcile(uid)  # Replay must not rerun normal derived work.
    assert final == [cid]
    current = store.decode_row(uid, coll.document(cid).get())
    assert current['status'] == 'completed' and not current['v3_process_pending']
    assert current['structured']['sections'][0]['body_markdown'] == 'Final notes.'
    next_start = datetime.now(timezone.utc) + timedelta(minutes=14, seconds=30)
    coll.document('later-recording').set(
        {
            'id': 'later-recording',
            'recording': True,
            'v3_pending': True,
            'v3_pending_since': next_start,
            'source': 'omi',
            'status': 'in_progress',
            'created_at': next_start,
            'started_at': next_start,
            'finished_at': next_start + timedelta(seconds=10),
            'transcript_segments': [
                {'text': 'An unrelated conversation fifteen minutes later.', 'start': 0, 'end': 10, 'is_user': True}
            ],
        }
    )
    await service.reconcile(uid)
    copies = list(coll.where(filter=firestore.FieldFilter('v3_derived', '==', True)).stream())
    assert len(copies) == 2 and final == [cid]
    later = next(doc.to_dict() for doc in copies if doc.id != cid)
    assert later['status'] == 'in_progress' and later['started_at'] == next_start


@pytest.mark.asyncio
async def test_budget_denial_settles_quiet_obligation_without_spending_or_repeating(seeded, monkeypatch):
    from fastapi import HTTPException

    client, uid, cid, rid, coll = seeded
    monkeypatch.setattr(service, 'reconcile', _noop_reconcile)

    def denied(*a, **kw):
        raise HTTPException(402, 'usage_budget_exhausted')

    monkeypatch.setattr(quiet, 'require_generated_compute', denied)
    generation = coll.document(rid).get().to_dict()['v3_quiet_generation']
    assert await quiet.run(uid, rid, generation) == 'settled'
    assert await quiet.run(uid, rid, generation) == 'superseded'
    assert not coll.document(rid).get().to_dict()['v3_quiet_pending']
    assert not leases.lease_ref(client, uid, 'summary-' + cid).get().to_dict().get('snapshot_inputs')
