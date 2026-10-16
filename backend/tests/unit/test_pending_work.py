"""Hermetic HTTP contracts and strict transaction tests for processing recovery."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import processing_attention as store
from routers import pending_work as routes
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

UID = 'owner'
NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)
CONV_PATH = ('users', UID, 'conversations', 'c1')
ROW = {
    'status': 'completed',
    'finalization_revision': 3,
    'summary_retryable': True,
    'started_at': NOW,
    'finished_at': NOW,
    'structured': {'title': 'Minimum title', 'overview': ''},
}


@pytest.fixture
def database(monkeypatch):
    client = StrictFirestore({CONV_PATH: ROW})
    monkeypatch.setattr(store, 'db', client)
    monkeypatch.setattr(routes, 'db', client)
    monkeypatch.setattr(store.firestore, 'transactional', lambda fn: fn)

    def run(client, fn, *args, **kwargs):
        # This fixture models ordered transactions, not SDK contention/retry behavior.
        with client.lock:
            return fn(client.transaction(), *args, **kwargs)

    monkeypatch.setattr(store, 'run_transactional', run)
    monkeypatch.setattr(routes, 'run_transactional', run)
    return client


def create_item(database, conversation_id='c1'):
    row = database.rows[('users', UID, 'conversations', conversation_id)]
    user_ref = database.collection('users').document(UID)
    ref = SimpleNamespace(id=conversation_id, parent=SimpleNamespace(parent=user_ref))
    updates = {'summary_retryable': True}
    store.create_in_transaction(database.transaction(), UID, ref, row, updates, 'processing_failed', NOW)
    return store.item_id(conversation_id, row)


@pytest.fixture
def http_client(monkeypatch):
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


def test_exactly_once_attention_and_new_generation(database):
    item_id = create_item(database)
    path = ('users', UID, 'processing_attention_items', item_id)
    database.rows[path]['seen'] = True
    assert create_item(database) == item_id
    assert database.rows[path]['seen'] is True
    database.rows[CONV_PATH]['finalization_revision'] += 1
    assert create_item(database) != item_id
    assert len([p for p in database.rows if p[2] == 'processing_attention_items']) == 2


@pytest.mark.parametrize('resolved', [None, {'deleted': True}, {'structured': {'overview': 'Summary'}}])
def test_resolution_predicate(resolved):
    assert not store.unresolved(resolved)
    assert store.unresolved(ROW)  # A deterministic title alone never resolves a failure.


def test_concurrent_retry_one_paid_call(database, http_client, monkeypatch):
    item_id = create_item(database)
    paid = Mock()
    monkeypatch.setattr(routes, '_run', paid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: http_client.post(f'/v1/attention-items/{item_id}/retry'), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    assert responses[0].json()['state'] == 'in_progress'
    paid.assert_called_once()
    # The existing reprocess route uses the very same claim even without an attention id.
    operation, owned = store.claim(UID, 'c1')
    assert not owned
    assert operation['operation_id'] == responses[0].json()['operation_id']


def test_retry_all_replay_is_exact_and_read_before_write(database, http_client, monkeypatch):
    item_id = create_item(database)
    database.rows[('users', UID, 'conversations', 'c2')] = dict(ROW)
    second = create_item(database, 'c2')
    monkeypatch.setattr(
        store,
        'list_items',
        lambda uid: [
            {'id': item_id, 'conversation_id': 'c1', 'retryable': True},
            {'id': second, 'conversation_id': 'c2', 'retryable': True},
        ],
    )
    paid = Mock()
    monkeypatch.setattr(routes, '_run', paid)
    first = http_client.post('/v1/attention-items/retry-all', json={'idempotency_key': 'batch-key'})
    replay = http_client.post('/v1/attention-items/retry-all', json={'idempotency_key': 'batch-key'})
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    assert len(first.json()['operations']) == 2
    assert paid.call_count == 2
    assert len({item['operation_id'] for item in first.json()['operations']}) == 2


def test_reject_stale_generation_and_owner(database):
    item_id = create_item(database)
    database.rows[CONV_PATH]['finalization_revision'] += 1
    with pytest.raises(store.ClaimRejected, match='not_retryable'):
        store.claim(UID, 'c1', item_id)
    with pytest.raises(store.ClaimRejected, match='not_found'):
        store.claim('other-owner', 'c1', item_id)


def test_seen_dismiss_and_unknown(database, http_client, monkeypatch):
    item_id = create_item(database)
    path = ('users', UID, 'processing_attention_items', item_id)

    # Strict fixture exposes transactional updates only; adapt short owner writes to it.
    def items_ref(uid):
        collection = database.collection('users').document(uid).collection('processing_attention_items')
        original_document = collection.document

        def document(doc_id):
            ref = original_document(doc_id)
            ref.update = lambda patch: database.transaction().update(ref, patch)
            return ref

        collection.document = document
        return collection

    monkeypatch.setattr(store, 'items_ref', items_ref)
    monkeypatch.setattr(store, 'list_items', lambda uid: [{'id': item_id}])
    assert http_client.post('/v1/attention-items/seen', json={'all': True}).status_code == 204
    assert database.rows[path]['seen']
    assert http_client.post(f'/v1/attention-items/{item_id}/dismiss').status_code == 204
    assert not database.rows[path]['active']
    assert http_client.post('/v1/attention-items/missing/dismiss').status_code == 404
    assert http_client.post('/v1/attention-items/missing/retry').status_code == 404


def test_pending_exclusions_and_bound(monkeypatch):
    rows = [
        dict(ROW, status='processing'),
        dict(ROW, status='processing', deleted=True),
        dict(ROW, status='processing', discarded=True),
        dict(ROW, status='processing', finalization_status='dead_letter'),
        dict(ROW, status='processing', finalization_status='completed'),
    ]
    query = Mock()
    query.where.return_value = query
    query.limit.return_value = query
    query.stream.return_value = [SimpleNamespace(id=str(i), to_dict=lambda row=row: row) for i, row in enumerate(rows)]
    client = Mock()
    client.collection.return_value.document.return_value.collection.return_value = query
    monkeypatch.setattr(store, 'db', client)
    items = store.pending_conversations(UID)
    assert [item['id'] for item in items] == ['conv:0']
    query.limit.assert_called_once_with(100)
    assert query.where.call_args.kwargs['filter'].value == 'processing'


def test_list_resolves_deleted_and_summarized_and_keeps_fallback_title(monkeypatch):
    collection = Mock()
    collection.where.return_value = collection
    collection.limit.return_value = collection
    items = []
    conversations = {}
    for cid, row in [
        ('deleted', {'deleted': True}),
        ('summary', {'structured': {'overview': 'Done'}}),
        ('missing', None),
        ('failed', ROW),
    ]:
        item = {
            'id': cid,
            'conversation_id': cid,
            'generation': store.generation(row or {}),
            'active': True,
            'seen': False,
            'retry': {'state': 'none', 'operation_id': None},
        }
        snapshot = Mock()
        snapshot.to_dict.return_value = item
        items.append(snapshot)
        conv = Mock(exists=row is not None)
        conv.to_dict.return_value = row
        conv.reference.collection.return_value.document.return_value.get.return_value = Mock(exists=False)
        conversations[cid] = SimpleNamespace(get=lambda conv=conv: conv)
    collection.stream.return_value = items
    monkeypatch.setattr(store, 'items_ref', lambda uid: collection)
    client = Mock()
    client.collection.return_value.document.return_value.collection.return_value.document.side_effect = (
        conversations.get
    )
    monkeypatch.setattr(store, 'db', client)
    result = store.list_items(UID)
    assert [item['id'] for item in result] == ['failed']
    assert result[0]['title'] == 'Minimum title'
    for snapshot in items[:3]:
        snapshot.reference.update.assert_called_once()
    items[3].reference.update.assert_not_called()


def test_pending_sync_excludes_terminal_missing_and_foreign(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    from database import sync_jobs

    redis = Mock()
    redis.zrevrange.return_value = [b'queued', b'working', b'done', b'missing', b'foreign']
    monkeypatch.setattr(sync_jobs, 'r', redis)
    jobs = {
        'queued': {'uid': UID, 'status': 'queued', 'created_at': NOW.timestamp(), 'updated_at': NOW.timestamp()},
        'working': {
            'uid': UID,
            'status': 'processing',
            'created_at': NOW.timestamp(),
            'updated_at': NOW.timestamp(),
            'result': {'new_memories': ['c1']},
        },
        'done': {'uid': UID, 'status': 'completed'},
        'foreign': {'uid': 'different', 'status': 'processing'},
    }
    monkeypatch.setattr(sync_jobs, 'get_sync_job', jobs.get)
    result = sync_jobs.pending_sync_jobs(UID)
    assert [item['id'] for item in result] == ['sync:queued', 'sync:working']
    assert result[1]['conversation_ids'] == ['c1']
    assert result[1]['state'] == 'transcribing'
    assert redis.zrevrange.call_args.args[-2:] == (0, 99)
    assert redis.zrem.call_count == 3


def test_dead_letter_and_attention_commit_in_same_strict_transaction(database):
    from database import conversation_finalization_jobs as jobs

    job_ref = database.collection('conversation_finalization_jobs').document('job')
    database.rows[job_ref.path] = {
        'uid': UID,
        'conversation_id': 'c1',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 1,
        'finalization_revision': 3,
    }
    database.rows[CONV_PATH].update(
        {
            'structured': {'title': '', 'overview': ''},
            'status': 'processing',
            'finalization_job_id': 'job',
            'photos': [{'description': 'A useful photo'}],
        }
    )
    conv_ref = database.collection('users').document(UID).collection('conversations').document('c1')
    transaction = database.transaction()
    assert jobs._mark_finalization_dead_letter_txn(transaction, job_ref, 1, 1, 5, NOW, lambda uid, cid: conv_ref)
    assert database.rows[CONV_PATH]['summary_retryable']
    assert database.rows[CONV_PATH]['status'] == 'completed'
    attention_writes = [entry for entry in transaction.sets if entry[0][2] == 'processing_attention_items']
    assert len(attention_writes) == 1
    assert attention_writes[0][1]['retryable']
    assert not jobs._mark_finalization_dead_letter_txn(
        database.transaction(), job_ref, 1, 1, 5, NOW, lambda uid, cid: conv_ref
    )


def test_enabled_http_get_shapes(monkeypatch, http_client):
    from database import sync_jobs

    item = {
        'id': 'conv-summary:c1:g1',
        'kind': 'conversation_summary_failed',
        'conversation_id': 'c1',
        'title': None,
        'started_at': NOW,
        'duration_seconds': 0,
        'failure_code': 'processing_failed',
        'retryable': True,
        'created_at': NOW,
        'seen': False,
        'retry': {'state': 'none', 'operation_id': None},
    }
    monkeypatch.setattr(store, 'list_items', lambda uid, **kwargs: [item])
    monkeypatch.setattr(store, 'pending_conversations', lambda uid: [])
    monkeypatch.setattr(sync_jobs, 'pending_sync_jobs', lambda uid: [])
    response = http_client.get('/v1/attention-items')
    assert response.status_code == 200
    assert response.json()['unseen_count'] == 1
    assert datetime.fromisoformat(response.json()['items'][0]['started_at']) == NOW
    assert response.json()['items'][0]['retry'] == {'state': 'none', 'operation_id': None}
    assert http_client.get('/v1/pending-work').json() == {'enabled': True, 'items': [], 'attention_unseen_count': 1}


def test_not_retryable_and_completed_claim_replay(database, http_client, monkeypatch):
    item_id = create_item(database)
    item_path = ('users', UID, 'processing_attention_items', item_id)
    database.rows[item_path]['retryable'] = False
    response = http_client.post(f'/v1/attention-items/{item_id}/retry')
    assert response.status_code == 409
    assert response.json() == {'state': 'not_retryable'}
    database.rows[item_path]['retryable'] = True
    operation, owned = store.claim(UID, 'c1', item_id)
    assert owned
    claim_path = (*CONV_PATH, 'processing_retry_claims', operation['claim_id'])
    database.rows[claim_path]['state'] = 'succeeded'
    database.rows[item_path]['active'] = False
    paid = Mock()
    monkeypatch.setattr(routes, '_run', paid)
    response = http_client.post(f'/v1/attention-items/{item_id}/retry')
    assert response.status_code == 200
    assert response.json() == {'operation_id': operation['operation_id'], 'state': 'succeeded'}
    paid.assert_not_called()


def test_retry_after_failure_new_key_and_original_key_replay(database, http_client, monkeypatch):
    item_id = create_item(database)
    calls = []

    def paid(uid, item_id, operation, background_tasks):
        calls.append(operation['operation_id'])
        state = 'failed' if len(calls) == 1 else 'succeeded'
        assert store.finish(uid, operation, state, item_id)
        operation['state'] = state

    monkeypatch.setattr(routes, '_run', paid)
    url = f'/v1/attention-items/{item_id}/retry'
    first = http_client.post(url, headers={'Idempotency-Key': 'first'}).json()
    assert first['state'] == 'failed'
    assert http_client.post(url, headers={'Idempotency-Key': 'first'}).json() == first
    second = http_client.post(url, headers={'Idempotency-Key': 'second'}).json()
    assert second['state'] == 'succeeded'
    assert second['operation_id'] != first['operation_id']
    assert http_client.post(url, headers={'Idempotency-Key': 'first'}).json() == first
    assert len(calls) == 2
    latest = database.rows[(*CONV_PATH, 'processing_retry_claims', store.claim_id('c1', store.generation(ROW)))]
    assert latest['attempt'] == 2


def test_failed_attempt_without_key_can_retry_and_joined_key_stays_pinned(database):
    item_id = create_item(database)
    first, owned = store.claim(UID, 'c1', item_id)
    assert owned
    joined, owned = store.claim(UID, 'c1', item_id, idempotency_key='joined')
    assert not owned and joined['operation_id'] == first['operation_id']
    assert store.finish(UID, first, 'failed', item_id)
    second, owned = store.claim(UID, 'c1', item_id)
    assert owned and second['attempt'] == 2
    replay, owned = store.claim(UID, 'c1', item_id, idempotency_key='joined')
    assert not owned and replay['state'] == 'failed'
    assert replay['operation_id'] == first['operation_id']


def test_expired_lease_reclaim_fences_late_completion(database, monkeypatch):
    item_id = create_item(database)
    monkeypatch.setattr(store, 'now_utc', lambda: NOW)
    first, owned = store.claim(UID, 'c1', item_id, idempotency_key='first')
    assert owned and first['lease_expires_at'] == NOW + timedelta(seconds=store.RETRY_LEASE_SECONDS)
    monkeypatch.setattr(store, 'now_utc', lambda: NOW + timedelta(seconds=store.RETRY_LEASE_SECONDS - 1))
    joined, owned = store.claim(UID, 'c1', item_id, idempotency_key='joined')
    assert not owned and joined['operation_id'] == first['operation_id']
    monkeypatch.setattr(store, 'now_utc', lambda: NOW + timedelta(seconds=store.RETRY_LEASE_SECONDS))
    second, owned = store.claim(UID, 'c1', item_id, idempotency_key='second')
    assert owned and second['attempt'] == 2
    assert not store.finish(UID, first, 'succeeded', item_id)
    path = ('users', UID, 'processing_attention_items', item_id)
    assert database.rows[path]['active']
    assert database.rows[path]['retry']['operation_id'] == second['operation_id']
    replay, owned = store.claim(UID, 'c1', item_id, idempotency_key='first')
    assert not owned and replay['state'] == 'failed' and replay['failure_code'] == 'lease_expired'
    assert replay['operation_id'] == first['operation_id']


def test_concurrent_reclaim_after_failure_starts_one_new_paid_attempt(database, http_client, monkeypatch):
    item_id = create_item(database)
    first, _ = store.claim(UID, 'c1', item_id)
    store.finish(UID, first, 'failed', item_id)
    paid = Mock()
    monkeypatch.setattr(routes, '_run', paid)
    url = f'/v1/attention-items/{item_id}/retry'
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda key: http_client.post(url, headers={'Idempotency-Key': key}), ['a', 'b']))
    assert responses[0].json() == responses[1].json()
    assert responses[0].json()['operation_id'] != first['operation_id']
    paid.assert_called_once()


def test_retry_all_failed_attempt_replay_and_new_batch_key(database, http_client, monkeypatch):
    item_id = create_item(database)
    monkeypatch.setattr(store, 'list_items', lambda uid: [{'id': item_id, 'conversation_id': 'c1', 'retryable': True}])
    calls = []

    def paid(uid, item_id, operation, background_tasks):
        calls.append(operation['operation_id'])
        store.finish(uid, operation, 'failed', item_id)
        operation['state'] = 'failed'

    monkeypatch.setattr(routes, '_run', paid)
    url = '/v1/attention-items/retry-all'
    first = http_client.post(url, json={'idempotency_key': 'batch-a'}).json()
    assert http_client.post(url, json={'idempotency_key': 'batch-a'}).json() == first
    second = http_client.post(url, json={'idempotency_key': 'batch-b'}).json()
    assert first['operations'][0]['operation_id'] != second['operations'][0]['operation_id']
    assert len(calls) == 2


def test_sync_admission_always_indexes_jobs(monkeypatch):
    from database import sync_jobs

    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    redis = Mock()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    job = sync_jobs.create_sync_job(UID, 1, 1, job_id='always-indexed')
    assert job['status'] == 'queued'
    assert redis.zadd.call_args.args[1].keys() == {'always-indexed'}
    redis.expire.assert_called_once()


def test_attention_success_key_replays_after_explicit_reprocess_starts(database):
    item_id = create_item(database)
    original, owned = store.claim(UID, 'c1', item_id, idempotency_key='attention-key')
    assert owned
    assert store.finish(UID, original, 'succeeded', item_id)
    manual, owned = store.claim(UID, 'c1', restart_succeeded=True)
    assert owned and manual['operation_id'] != original['operation_id']
    replay, owned = store.claim(UID, 'c1', item_id, idempotency_key='attention-key')
    assert not owned
    assert replay['operation_id'] == original['operation_id']
    assert replay['state'] == 'succeeded'


def test_typed_pending_projection_serializes_rows(monkeypatch, http_client):
    from database import sync_jobs

    monkeypatch.setattr(store, 'list_items', lambda uid, **kwargs: [])
    row = {
        'id': 'conv:c1',
        'kind': 'conversation',
        'state': 'summarizing',
        'conversation_ids': ['c1'],
        'started_at': NOW,
        'duration_seconds': 12.5,
        'updated_at': None,
        'internal_only': 'omit',
    }
    monkeypatch.setattr(store, 'pending_conversations', lambda uid: [row])
    monkeypatch.setattr(sync_jobs, 'pending_sync_jobs', lambda uid: [])
    response = http_client.get('/v1/pending-work')
    assert response.status_code == 200
    body = response.json()
    assert body['enabled'] is True
    item = body['items'][0]
    assert set(item) == set(row) - {'internal_only'}
    assert item['duration_seconds'] == 12.5
    assert item['updated_at'] is None
    assert datetime.fromisoformat(item['started_at']) == NOW


def test_recovery_openapi_has_typed_success_and_bodyless_204(http_client):
    spec = http_client.get('/openapi.json').json()
    paths = spec['paths']
    for method, path, schema in [
        ('get', '/v1/pending-work', 'PendingWorkSnapshot'),
        ('get', '/v1/attention-items', 'AttentionItemsPage'),
        ('post', '/v1/attention-items/retry-all', 'AttentionRetryAllResponse'),
        ('post', '/v1/attention-items/{item_id}/retry', 'AttentionRetryResponse'),
    ]:
        assert paths[path][method]['responses']['200']['content']['application/json']['schema'] == {
            '$ref': '#/components/schemas/' + schema
        }
    for path in ['/v1/attention-items/seen', '/v1/attention-items/{item_id}/dismiss']:
        responses = paths[path]['post']['responses']
        assert '200' not in responses
        assert 'content' not in responses['204']
    assert paths['/v1/attention-items/seen']['post']['requestBody']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/SeenRequest'
    }
    assert paths['/v1/attention-items/retry-all']['post']['requestBody']['content']['application/json']['schema'] == {
        '$ref': '#/components/schemas/RetryAllRequest'
    }
