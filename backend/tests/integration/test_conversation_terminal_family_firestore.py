"""Emulator proof: the atomic update retains legacy processor merge semantics.

No cloud project or credentials are accepted. This proves non-map parent
replacement before teaching the hermetic fake that Firestore behavior.
"""

import os
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database.conversation_processing_result import update_fields

pytestmark = pytest.mark.skipif(not os.getenv('FIRESTORE_EMULATOR_HOST'), reason='local Firestore emulator required')


@pytest.mark.parametrize('parent', [None, 42, {}, {'kept': 'old', 'nested': None}])
def test_atomic_processor_update_matches_legacy_merge_over_nonmap_parents(parent):
    host = os.environ['FIRESTORE_EMULATOR_HOST']
    assert host.startswith(('127.0.0.1:', 'localhost:')), 'This proof is local-only'
    client = firestore.Client(project='demo-lcphase2a', credentials=AnonymousCredentials())
    collection = client.collection('phase2a_merge_proof')
    name = uuid4().hex
    legacy, atomic = collection.document(name + '-legacy'), collection.document(name + '-atomic')
    initial = {'structured': parent, 'status': 'processing', 'kept': 'outside'}
    payload = {'structured': {'title': 'new', 'nested': {'literal.dot': 'new'}}, 'status': 'completed'}
    legacy.set(initial)
    atomic.set(initial)
    legacy.set(payload, merge=True)

    @firestore.transactional
    def commit(transaction):
        assert atomic.get(transaction=transaction).exists
        transaction.update(atomic, update_fields(payload))

    commit(client.transaction())
    assert atomic.get().to_dict() == legacy.get().to_dict()
    result = atomic.get().to_dict()
    assert result['structured']['title'] == 'new'
    assert result['structured']['nested'] == {'literal.dot': 'new'}
    assert result['status'] == 'completed' and result['kept'] == 'outside'


@pytest.mark.parametrize('overview', ['Actual notes', ''])
def test_legacy_background_notes_commit_native_visibility(monkeypatch, overview):
    from database import conversations as db
    from tests.unit.test_conversations_v3_native_manual_visibility_writes import rows
    from utils.conversations import lifecycle
    from utils.conversations.v3 import policy

    assert os.environ['FIRESTORE_EMULATOR_HOST'].startswith(('127.0.0.1:', 'localhost:'))
    client = firestore.Client(project='demo-lcphase2a', credentials=AnonymousCredentials())
    uid = 'native-visibility-' + uuid4().hex
    source, derived = rows()
    conversations = client.collection('users').document(uid).collection('conversations')
    raw = conversations.document('r')
    target = conversations.document(derived['id'])
    raw.set(source)
    if not overview:
        derived.update(
            structured={'overview': 'Previous notes'},
            summary_covers_through=derived['finished_at'],
            v3_notes_written=True,
            v3_native_manual_notes_visibility=policy.native_manual_notes_receipt(derived),
        )
    target.set(derived)
    monkeypatch.setattr(db, 'db', client)
    monkeypatch.setattr(db.pipeline_ledger, 'record_summary', lambda *args, **kwargs: None)
    monkeypatch.setattr(db.terminal_settled, 'serving', lambda uid: False)
    try:
        assert lifecycle.persist_processed_conversation(
            uid,
            {
                'id': derived['id'],
                'status': 'completed',
                'sync_content_revision': derived['sync_content_revision'],
                'structured': {'title': 'Title', 'overview': overview},
                'data_protection_level': 'standard',
            },
        )
        saved = target.get().to_dict()
        assert not saved.get('v3_notes_written')
        assert saved['structured']['overview'] == overview
        expected = policy.native_manual_notes_receipt(derived) if overview else None
        assert saved.get(policy.NATIVE_MANUAL_NOTES_VISIBILITY) == expected
        if not overview:
            assert saved['summary_covers_through'] is None
    finally:
        target.delete()
        raw.delete()
