"""Real local Firestore contracts behind Dream's hermetic queue fixture.

Run only through test.sh with FIRESTORE_EMULATOR_HOST set to loopback and a
synthetic demo project. No cloud credentials or customer data are accepted.
"""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from config.dream_agent import Caps
from database import dream_store

pytestmark = pytest.mark.integration


def test_dirty_queue_transforms_queries_and_transaction_deletes(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('local Firestore emulator required')
    database = firestore.Client(project='demo-dream-coalesce', credentials=AnonymousCredentials())
    uid = 'synthetic-' + str(uuid4())
    monkeypatch.setenv('DREAM_AGENT_MODE', 'shadow')
    monkeypatch.setenv('DREAM_AGENT_UID_ALLOWLIST', uid)
    database.collection('users').document(uid).set({})
    state = dream_store.state_ref(database, uid)
    dream_store.mark_dirty(uid, [('conversations', 'first')], firestore_client=database)
    dream_store.mark_dirty(uid, [('conversations', 'first')], firestore_client=database)
    assert dream_store.dirty_count(uid, firestore_client=database) == 1
    first = dream_store.dirty_refs(uid, firestore_client=database)[0].to_dict()
    assert first['change_count'] == 2
    assert isinstance(first['last_changed_at'], datetime)
    dream_store.mark_dirty(uid, [('conversations', str(i)) for i in range(501)], firestore_client=database)
    queued = dream_store.dirty_refs(uid, firestore_client=database)
    assert dream_store.dirty_count(uid, firestore_client=database) == 500
    assert all(s.to_dict()['id'] != 'first' for s in queued)
    assert state.get().to_dict()['dirty_dropped'] == 2
    assert [s.to_dict()['last_changed_at'] for s in queued] == sorted(
        (s.to_dict()['last_changed_at'] for s in queued), reverse=True
    )
    lease = dream_store.acquire(uid, Caps(), now=datetime.now(timezone.utc), firestore_client=database)
    consumed = [queued[0].to_dict()]
    dream_store.mark_dirty(uid, [('conversations', consumed[0]['id'])], firestore_client=database)
    dream_store.finish(uid, lease, {'tokens': 1}, success=True, consumed=consumed, firestore_client=database)
    # A refreshed version survives the transaction's acknowledgement.
    assert dream_store.dirty_count(uid, firestore_client=database) == 500
    lease = dream_store.acquire(uid, Caps(), firestore_client=database)
    consumed = [s.to_dict() for s in dream_store.dirty_refs(uid, limit=400, firestore_client=database)]
    dream_store.finish(
        uid, lease, {'tokens': 0}, success=True, consumed=consumed, refund=True, firestore_client=database
    )
    assert dream_store.dirty_count(uid, firestore_client=database) == 100
    assert state.get().to_dict()['passes'] == 1
    assert database.collection('dream_spend').document(lease['day']).get().to_dict()['reserved_usd'] == pytest.approx(
        0.24
    )
