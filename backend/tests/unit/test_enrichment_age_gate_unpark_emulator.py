"""Real Firestore newest-first paging and atomic unpark; isolated loopback emulator only."""

import os
from unittest.mock import Mock

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from utils.enrichment import age_gate, outbox
from utils.enrichment import unpark

pytestmark = pytest.mark.skipif(
    not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')),
    reason='isolated loopback Firestore emulator required',
)

NOW = 10_000_000.0
BINDING = {
    'queue': 'enrichment',
    'handler': 'https://worker.invalid/v2/enrichment/run',
    'audience': 'https://worker.invalid/v2/enrichment/run',
    'invoker_sa': 'synthetic@example.invalid',
}


@pytest.fixture
def source(monkeypatch):
    client = firestore.Client(project='demo-enrichment-unpark', credentials=AnonymousCredentials())
    collection = client.collection(outbox.COLLECTION)
    for snapshot in collection.where(filter=firestore.FieldFilter('age_gate_parked', '==', True)).stream():
        snapshot.reference.delete()
    monkeypatch.setattr(unpark, 'assert_batch_write_allowed', lambda *args, **kwargs: 1)
    monkeypatch.setattr(unpark.time, 'time', lambda: NOW)
    ids = []
    conversations = []
    for name, parked_at in (('older', 100), ('newest', 300), ('middle', 200)):
        uid, cid = f'synthetic-unpark-{name}', f'capture-{name}'
        document_id = outbox.key(uid, cid)
        ids.append(document_id)
        ref = collection.document(document_id)
        conversations.append((ref, client.collection('users').document(uid).collection('conversations').document(cid)))
        ref.set(
            {
                'document_id': document_id,
                'uid': uid,
                'conversation_id': cid,
                'language': 'en',
                'first_pending_at': NOW - 3600,
                'age_gate_parked': True,
                'deferred_reason': age_gate.REASON,
                'deferred_since': parked_at,
                'dormant': True,
                'due_at': None,
                'task_due_at': None,
                'task_token': name * 8,
                'lease_until': 0,
                'owner': None,
                'dispatch': dict(BINDING),
                'version': 3,
            }
        )
        conversations[-1][1].set({'created_at': NOW - 3600, 'content': 'untouched'})
    try:
        yield client, collection, ids, conversations
    finally:
        for ref, conversation in conversations:
            ref.delete()
            conversation.delete()
        client.close()


def test_real_discovery_is_newest_first_and_resumes_after_opaque_cursor(source):
    client, _, ids, _ = source
    first, cursor = unpark.discover(client, limit=2)
    assert first == [ids[1], ids[2]]
    second, end = unpark.discover(client, limit=2, after=cursor)
    assert second == [ids[0]] and end is not None
    empty, wrapped = unpark.discover(client, limit=2, after=end)
    assert empty == [] and wrapped is None


def test_real_transaction_unparks_atomically_and_failed_enqueue_leaves_due_debt(source, monkeypatch):
    client, collection, ids, conversations = source
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    monkeypatch.delenv('ENRICHMENT_AGE_GATE_UNPARK_ENABLED', raising=False)
    page, _ = unpark.discover(client, limit=3)
    assert len(page) == 3 and set(page) == set(ids)
    plan = unpark.plan_unpark(client, page, now=NOW, max_age_seconds=age_gate.max_age_seconds())
    wake = Mock(side_effect=[None, RuntimeError('synthetic lost ack'), None])
    assert unpark.apply_unpark(client, plan, plan['plan_sha256'], pace_seconds=0, wake=wake) == {
        'enqueue_error': 1,
        'unparked': 2,
    }
    for index, (ref, conversation) in enumerate(conversations):
        persisted = ref.get().to_dict()
        assert persisted['age_gate_parked'] is False
        assert persisted['deferred_reason'] is None and 'deferred_since' not in persisted
        assert persisted['dormant'] is False and persisted['due_at'] == persisted['task_due_at'] == NOW
        assert persisted['version'] == 3 and persisted['first_pending_at'] == NOW - 3600
        assert persisted['dispatch'] == BINDING
        assert conversation.get().to_dict()['content'] == 'untouched'
        assert persisted['task_token'] != ('older' * 8, 'newest' * 8, 'middle' * 8)[index]
    assert unpark.apply_unpark(client, plan, plan['plan_sha256'], pace_seconds=0, wake=Mock()) == {'state_changed': 3}


def test_real_transaction_rejects_changed_parked_token_without_overwrite(source, monkeypatch):
    client, _, ids, _ = source
    monkeypatch.setenv('ENRICHMENT_MAX_AGE_HOURS', '72')
    document_id = ids[0]
    plan = unpark.plan_unpark(client, [document_id], now=NOW, max_age_seconds=age_gate.max_age_seconds())
    ref = client.collection(outbox.COLLECTION).document(document_id)
    before = ref.get().to_dict()
    ref.update({'task_token': 'replacement-token'})
    assert unpark.apply_unpark(client, plan, plan['plan_sha256'], pace_seconds=0) == {'state_changed': 1}
    assert ref.get().to_dict() == {**before, 'task_token': 'replacement-token'}
