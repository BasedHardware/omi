"""Real Firestore transactions for paid-once quiet notes and resumed-input fencing.

Only loopback emulator data is accepted. The production codec, leases, source
queries, reservation and summary writer run unchanged against Firestore.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

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
        return SimpleNamespace(status='completed')

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
