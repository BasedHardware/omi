"""Emulator proof: the atomic update retains legacy processor merge semantics.

No cloud project or credentials are accepted. This proves non-map parent
replacement before teaching the hermetic fake that Firestore behavior.
"""

import os
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database.conversations import _processing_result_update_fields

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
        transaction.update(atomic, _processing_result_update_fields(payload))

    commit(client.transaction())
    assert atomic.get().to_dict() == legacy.get().to_dict()
    result = atomic.get().to_dict()
    assert result['structured']['title'] == 'new'
    assert result['structured']['nested'] == {'literal.dot': 'new'}
    assert result['status'] == 'completed' and result['kept'] == 'outside'
