"""Emulator tests for Firestore revisions and rollback across V3 and sync writers."""

import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.types import BeginTransactionRequest
import pytest

from database import conversations_v3 as v3, conversations_v3_leases as leases
from database.conversations_v3_sync_repair import repair
from utils.conversations.v3 import Conflict
from utils.sync.assignment import assign_in_transaction


@pytest.fixture
def owner():
    if not os.environ.get('FIRESTORE_EMULATOR_HOST'):
        pytest.skip('requires the Firestore emulator')
    client = firestore.Client(project='demo-v3-sync-custody', credentials=AnonymousCredentials())
    user = client.collection('users').document('custody-test-' + uuid4().hex)
    try:
        yield client, user, user.collection('conversations')
    finally:
        client.recursive_delete(user)
        client.close()


def source(cid, start, text):
    return {
        'id': cid,
        'recording': True,
        'source': 'omi',
        'status': 'completed',
        'data_protection_level': 'standard',
        'started_at': start,
        'finished_at': start + timedelta(seconds=20),
        'sync_content_revision': 1,
        'transcript_segments': [{'id': cid, 'start': 0, 'end': 20, 'text': text}],
    }


def seed(owner):
    _, _, coll = owner
    begin = datetime(2026, 11, 20, tzinfo=timezone.utc)
    early = source('early', begin, 'The first synthetic speaker described a distinct topic.')
    late = source('late', begin + timedelta(seconds=180), 'The other synthetic speaker discussed navigation.')
    card = {
        'id': 'card',
        'v3_derived': True,
        'status': 'completed',
        'started_at': late['started_at'],
        'finished_at': late['finished_at'],
        'structured': {'title': 'Original edited title'},
        'v3_recording_ids': ['late'],
        'transcript_segments': late['transcript_segments'],
    }
    late['claims'] = [{'conversation_id': 'card', 'start': late['started_at'], 'end': late['finished_at']}]
    for row in (early, late, card):
        coll.document(row['id']).set(row)
    return begin, late['claims']


def test_stale_reconcile_cannot_put_claims_back_after_sync_redirect(owner):
    client, user, coll = owner
    begin, claims = seed(owner)
    token = leases.acquire(user.id, 'builder', firestore_client=client)
    stale = v3.recording_input(user.id, coll.document('late').get())
    stale_card = coll.document('card').get().to_dict()

    @firestore.transactional
    def merge(tx):
        return assign_in_transaction(
            tx,
            user,
            source('bridge', begin + timedelta(seconds=90), 'Unrelated synthetic speech about the weather.'),
            candidate_id='late',
            decode=deepcopy,
            encode=deepcopy,
            invalidate=lambda payload: None,
        )

    # The bridge upload already has an early anchor on retry. The two explicit hints
    # make both sources known without relying on separately seeded assignment indexes.
    coll.document('bridge').set(source('bridge', begin, 'Unrelated synthetic speech about the weather.'))
    result, _, _ = merge(client.transaction())
    assert result['id'] == 'bridge'
    assert coll.document('late').get().to_dict()['claims'] == []
    assert coll.document('bridge').get().to_dict()['claims'] == claims

    with pytest.raises(Conflict, match='source_changed'):
        v3.commit_projection(user.id, token, {'late': stale}, {}, [], {}, firestore_client=client)
    assert coll.document('late').get().to_dict()['claims'] == []
    assert coll.document('card').get().to_dict()['v3_recording_ids'] == ['bridge']

    user.collection('deleted_conversations').document('card').set({'conversation_id': 'card'})
    v3.release_claims(user.id, stale_card, firestore_client=client)
    bridge = coll.document('bridge').get().to_dict()
    assert bridge['claims'] == []
    assert bridge['deleted_spans'] == claims


def test_historical_repair_preview_retry_rollback_and_races(owner):
    client, user, coll = owner
    _, claims = seed(owner)
    late = coll.document('late')
    card = coll.document('card')
    early = coll.document('early')
    late.update({'deleted': True, 'discarded': True, 'sync_merged_into': 'middle'})
    coll.document('middle').set({'deleted': True, 'sync_merged_into': 'early', 'recording': True})
    early.update(
        {
            'sync_merged_from': ['late', 'middle'],
            'transcript_segments': [
                *early.get().to_dict()['transcript_segments'],
                {**late.get().to_dict()['transcript_segments'][0], 'start': 180, 'end': 200},
            ],
        }
    )

    def run(mode='preview', receipt=None):
        return repair(client, user.id, 'late', mode=mode, receipt=receipt)

    before = card.get().to_dict()
    preview = run()
    assert preview['chain'] == ['late', 'middle', 'early']
    assert preview['patches']['early']['claims'] == claims
    assert card.get().to_dict() == before
    card.update({'structured.title': 'Edited after preview'})
    assert run('apply', preview['receipt']) == {'outcome': 'skipped', 'reason': 'preview_changed'}
    receipt = run()['receipt']
    assert run('apply', receipt) == run('apply', receipt) == {'outcome': 'applied', 'receipt': receipt}
    assert late.get().to_dict()['claims'] == []
    assert card.get().to_dict()['v3_recording_ids'] == ['early']
    assert card.get().to_dict()['structured']['title'] == 'Edited after preview'
    assert run('rollback', receipt) == run('rollback', receipt) == {'outcome': 'rolled_back', 'receipt': receipt}
    assert 'claims' not in early.get().to_dict()
    assert late.get().to_dict()['claims'] == claims
    assert card.get().to_dict()['v3_recording_ids'] == ['late']

    receipt = run()['receipt']
    assert run('apply', receipt)['outcome'] == 'applied'
    card.update({'structured.title': 'Edited after apply'})
    assert run('rollback', receipt) == {'outcome': 'skipped', 'reason': 'changed_since_apply'}
    assert card.get().to_dict()['structured']['title'] == 'Edited after apply'
    user.collection('deleted_conversations').document('card').set({'conversation_id': 'card'})
    assert run('rollback', receipt) == {'outcome': 'skipped', 'reason': 'tombstoned'}
    assert early.get().to_dict()['claims'] == claims


@pytest.mark.parametrize('failure', ['expired_read', 'aborted_commit'])
def test_projection_restarts_with_fresh_transaction(owner, monkeypatch, failure):
    from google.api_core.exceptions import Aborted, InvalidArgument

    client, user, coll = owner
    seed(owner)
    token = leases.acquire(user.id, 'builder', firestore_client=client)
    source_snapshot = coll.document('early').get()
    recording = v3.recording_input(user.id, source_snapshot)
    api = client._firestore_api
    original_begin = api.begin_transaction
    began = []
    retry_ids = []

    def begin(*args, **kwargs):
        request = BeginTransactionRequest(kwargs['request'])
        retry_ids.append(request.options.read_write.retry_transaction)
        result = original_begin(*args, **kwargs)
        began.append(result.transaction)
        return result

    monkeypatch.setattr(api, 'begin_transaction', begin)
    method = 'batch_get_documents' if failure == 'expired_read' else 'commit'
    original = getattr(api, method)

    def fail_once(*args, **kwargs):
        if len(began) == 1:
            if failure == 'expired_read':
                raise InvalidArgument('The referenced transaction has expired or is no longer valid')
            raise Aborted('cross-transaction contention')
        return original(*args, **kwargs)

    monkeypatch.setattr(api, method, fail_once)
    original_rollback = api.rollback

    def rollback(*args, **kwargs):
        original_rollback(*args, **kwargs)
        raise InvalidArgument('The referenced transaction has expired or is no longer valid')

    monkeypatch.setattr(api, 'rollback', rollback)
    assert v3.commit_projection(user.id, token, {'early': recording}, {}, [], [], firestore_client=client) == set()
    assert len(began) == 2 and began[0] != began[1]
    assert retry_ids == [b'', b'']
    assert coll.document('early').get().to_dict()['v3_pending'] is False


def test_projection_splits_33_pointer_backed_rows(owner, monkeypatch):
    import hashlib
    import json

    from database._client import in_transaction_body
    from utils.other import object_lake

    client, user, coll = owner
    begin, _ = seed(owner)
    source_ref = coll.document('early')
    source_ref.update({'v3_pending': True})
    recording = v3.recording_input(user.id, source_ref.get())
    token = leases.acquire(user.id, 'builder', firestore_client=client)
    rows = [
        {
            'id': f'derived-{index}',
            'status': 'completed',
            'started_at': begin,
            'finished_at': begin + timedelta(seconds=20),
            'v3_recording_ids': ['early'],
            'transcript_segments': recording['transcript_segments'],
        }
        for index in range(33)
    ]
    bucket = 'test-transcript-lake'
    monkeypatch.setenv('BUCKET_OBJECT_LAKE', bucket)
    monkeypatch.setenv('OBJECT_LAKE_READ_ENABLED', 'true')
    blob = json.dumps(recording['transcript_segments']).encode()
    digest = hashlib.sha256(blob).hexdigest()
    reads = []

    def encode(row, uid, *_args, **_kwargs):
        ref = object_lake.LakeObjectRef(
            bucket, f'v1/spaces/{uid}/transcript/{row["id"]}/{digest}', digest, len(blob) + 64, 'transcript', 1
        )
        return {**row, 'transcript_segments': ref.to_pointer_dict(), 'transcript_segments_compressed': True}

    def read(ref):
        assert not in_transaction_body()
        reads.append(ref.key)
        return blob

    monkeypatch.setattr(v3.conversations, '_prepare_conversation_for_write', encode)
    monkeypatch.setattr(object_lake, 'get_space_object', read)
    assert v3.commit_projection(user.id, token, {'early': recording}, {}, rows, [], firestore_client=client) == set()
    assert len(reads) == len(set(reads)) == 33
    stored = source_ref.get().to_dict()
    assert stored['v3_pending'] is False
    assert {claim['conversation_id'] for claim in stored['claims']} == {row['id'] for row in rows}
    assert all(isinstance(coll.document(row['id']).get().get('transcript_segments'), dict) for row in rows)
