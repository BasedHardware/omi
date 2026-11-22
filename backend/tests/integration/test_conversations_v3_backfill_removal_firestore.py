"""Verify backfill removal and link retention with real Firestore transactions."""

import json
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import conversations_v3 as store, conversations_v3_leases as leases
from database.conversations_v3_undo_removals import removal_ref
from utils.encryption import encrypt


@pytest.fixture
def backfill():
    if not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('requires a loopback Firestore emulator')
    client = firestore.Client(project='demo-backfill-removal', credentials=AnonymousCredentials())
    user = client.collection('users').document('synthetic-' + uuid4().hex)
    token = leases.acquire(user.id, store.BACKFILL_LEASE, firestore_client=client)
    assert token
    yield client, user, token
    client.close()


def test_rederive_removes_only_unlinked_rows_and_their_claims(backfill):
    client, user, token = backfill
    coll = user.collection('conversations')
    now = datetime.now(timezone.utc)
    ids = ('task', 'legacy', 'evidence', 'canonical', 'source-ref', 'unlinked')
    claims = [{'conversation_id': cid, 'start': now, 'end': now} for cid in ids]
    coll.document('recording').set({'recording': True, 'status': 'completed', 'claims': claims})
    for cid in ids:
        coll.document(cid).set({'v3_derived': True, 'backfilled': True})
    user.collection('action_items').document('task-link').set({'conversation_id': 'task'})
    user.collection('memories').document('legacy-link').set({'memory_id': 'legacy'})
    user.collection('memories').document('evidence-link').set(
        {
            'data_protection_level': 'enhanced',
            'evidence': encrypt(json.dumps([{'source_id': 'evidence'}]), user.id),
        }
    )
    user.collection('memory_items').document('canonical-link').set(
        {
            'evidence': [{'source_id': 'canonical', 'source_type': 'conversation'}],
            'source_refs': [{'conversation_id': 'source-ref'}],
        }
    )

    def read(cid):
        snap = coll.document(cid).get()
        return {**(snap.to_dict() or {}), '_v3_revision': snap.update_time}

    removed = set()
    store.commit_projection(
        user.id,
        token,
        {'recording': read('recording')},
        {cid: read(cid) for cid in ids},
        [],
        [],
        remove=ids,
        removed_ids=removed,
        key=store.BACKFILL_LEASE,
        firestore_client=client,
    )

    assert removed == {'unlinked'}
    assert coll.document('recording').get().get('claims') == claims[:-1]
    for cid in ids[:-1]:
        assert coll.document(cid).get().exists
        assert not removal_ref(user, cid).get().exists
    assert not coll.document('unlinked').get().exists
    assert removal_ref(user, 'unlinked').get().to_dict() == {'removed_by_backfill_rederive': True}


def test_unreadable_evidence_leaves_row_and_marker_untouched(backfill):
    client, user, token = backfill
    row = user.collection('conversations').document('candidate')
    row.set({'v3_derived': True, 'backfilled': True})
    snap = row.get()
    user.collection('memories').document('unknown-link').set({'evidence': 'unreadable'})
    with pytest.raises(ValueError, match='Stored memory source references are unreadable'):
        store.commit_projection(
            user.id,
            token,
            {},
            {'candidate': {**(snap.to_dict() or {}), '_v3_revision': snap.update_time}},
            [],
            [],
            remove=('candidate',),
            key=store.BACKFILL_LEASE,
            firestore_client=client,
        )
    assert row.get().exists
    assert not removal_ref(user, 'candidate').get().exists
