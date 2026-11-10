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
        conversations[cid] = Mock()
        conversations[cid].get.return_value = conv
        conversations[cid].collection.return_value.document.return_value.get.return_value = Mock(exists=False)
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


def attention_query(database, monkeypatch, ids):
    """Use strict document/transaction semantics; the query only supplies frozen snapshots."""
    snapshots = []
    for item_id in ids:
        ref = database.collection('users').document(UID).collection('processing_attention_items').document(item_id)
        snapshot = ref.get()
        snapshot.reference = ref
        snapshots.append(snapshot)
    query = Mock()
    query.where.return_value = query
    query.limit.return_value = query
    query.start_after.return_value = query
    query.stream.return_value = snapshots
    query.document.side_effect = (
        database.collection('users').document(UID).collection('processing_attention_items').document
    )
    monkeypatch.setattr(store, 'items_ref', lambda uid: query)
    monkeypatch.setattr(store, 'now_utc', lambda: NOW)
    monkeypatch.delenv('PROCESSING_ATTENTION_NON_RETRYABLE_EXPIRY_ENABLED', raising=False)
    return snapshots


def permanent_item(database, conversation_id='c1', **overrides):
    item_id = create_item(database, conversation_id)
    path = ('users', UID, 'processing_attention_items', item_id)
    database.rows[path].update(
        retryable=False, failure_code='recovery_structure_unavailable', created_at=NOW - store.NON_RETRYABLE_ITEM_TTL
    )
    database.rows[path].update(overrides)
    return item_id, path


@pytest.mark.parametrize('expiry_enabled', [True, False])
def test_list_expires_only_old_non_retryable_items(database, monkeypatch, expiry_enabled):
    ids = []
    paths = []
    for cid, overrides in [
        ('expired', {}),
        ('retryable', {'retryable': True}),
        ('recent', {'created_at': NOW - store.NON_RETRYABLE_ITEM_TTL + timedelta(seconds=1)}),
        ('transient', {'failure_code': 'processing_failed'}),
        ('running', {'retry': {'state': 'in_progress'}}),
    ]:
        database.rows[('users', UID, 'conversations', cid)] = dict(ROW)
        item_id, path = permanent_item(database, cid, **overrides)
        ids.append(item_id)
        paths.append(path)
    attention_query(database, monkeypatch, ids)
    if not expiry_enabled:
        monkeypatch.setenv('PROCESSING_ATTENTION_NON_RETRYABLE_EXPIRY_ENABLED', 'false')
    result = store.list_items(UID)
    assert [item['id'] for item in result] == (ids[1:] if expiry_enabled else ids)
    assert database.rows[paths[0]]['active'] is not expiry_enabled
    assert all(database.rows[path]['active'] for path in paths[1:])
    if expiry_enabled:
        assert database.rows[paths[0]]['expired_at'] == NOW
        assert database.rows[paths[0]]['expiry_reason'] == 'non_retryable_ttl'
    else:
        monkeypatch.setenv('PROCESSING_ATTENTION_NON_RETRYABLE_EXPIRY_ENABLED', 'true')
        assert [item['id'] for item in store.list_items(UID)] == ids[1:]


@pytest.mark.parametrize(
    'created_at, expires',
    [
        (datetime(2026, 10, 1), True),
        ('2026-10-01T00:00:00Z', True),
        ('2026-10-01T02:00:00+02:00', True),
        (None, False),
        ('invalid', False),
    ],
)
def test_expiry_normalizes_legacy_created_at(database, monkeypatch, created_at, expires):
    item_id, path = permanent_item(database, created_at=created_at)
    attention_query(database, monkeypatch, [item_id])
    assert bool(store.list_items(UID)) is not expires
    assert database.rows[path]['active'] is not expires


@pytest.mark.parametrize('failure_code', ['processing_failed', 'final_attempt_failed', 'durable_attempts_exhausted'])
def test_transient_non_retryable_items_do_not_expire(database, monkeypatch, failure_code):
    item_id, path = permanent_item(database, failure_code=failure_code)
    attention_query(database, monkeypatch, [item_id])
    assert len(store.list_items(UID)) == 1
    assert database.rows[path]['active']


def test_failed_claim_repairs_retryability_before_expiry(database, monkeypatch):
    item_id, path = permanent_item(database, retry={'state': 'failed'})
    claim_ref = (
        database.collection('users')
        .document(UID)
        .collection('conversations')
        .document('c1')
        .collection('processing_retry_claims')
        .document(store.claim_id('c1', store.generation(ROW)))
    )
    database.rows[claim_ref.path] = {'state': 'failed', 'operation_id': 'legacy'}
    attention_query(database, monkeypatch, [item_id])
    result = store.list_items(UID)
    assert result[0]['retryable'] is True
    assert result[0]['retry'] == {'state': 'failed', 'operation_id': 'legacy'}
    assert database.rows[path]['active']
    assert not any(tx.updates for tx in database.transactions)


@pytest.mark.parametrize('claim_first', [True, False])
def test_stale_poll_cannot_expire_concurrent_retry(database, monkeypatch, claim_first):
    item_id, path = permanent_item(database)
    attention_query(database, monkeypatch, [item_id])
    original_run = store.run_transactional
    operations = []

    def interleave(client, fn, *args, **kwargs):
        if fn is store.expire_in_transaction:
            if claim_first:
                # The normal reprocess path can claim without an attention id.
                operations.append(store.claim(UID, 'c1')[0])
            result = original_run(client, fn, *args, **kwargs)
            if not claim_first:
                with pytest.raises(store.ClaimRejected, match='not_retryable'):
                    store.claim(UID, 'c1', item_id)
            return result
        return original_run(client, fn, *args, **kwargs)

    monkeypatch.setattr(store, 'run_transactional', interleave)
    result = store.list_items(UID)
    assert bool(result) is claim_first
    assert database.rows[path]['active'] is claim_first
    if claim_first:
        assert store.finish(UID, operations[0], 'failed', item_id)
        assert database.rows[path]['active']  # A failed retry remains visible.


@pytest.mark.parametrize('change', ['retry', 'delete', 'version'])
def test_expiry_refuses_changed_snapshot(database, monkeypatch, change):
    item_id, path = permanent_item(database)
    observed = attention_query(database, monkeypatch, [item_id])[0]
    if change == 'retry':
        database.rows[path]['retryable'] = True
        store.claim(UID, 'c1', item_id)
    elif change == 'delete':
        database.rows.pop(path)
    else:
        # Same data written again is still a different Firestore document version.
        observed.update_time = NOW - timedelta(seconds=1)
    assert len(store.list_items(UID)) == 1
    assert not any('expired_at' in patch for tx in database.transactions for _, patch in tx.updates)


def test_attention_limit_is_after_expiry_filter(database, http_client, monkeypatch):
    ids = []
    for index in range(5):
        cid = f'c{index}'
        database.rows[('users', UID, 'conversations', cid)] = dict(ROW)
        item_id, _ = permanent_item(database, cid, **({'retryable': True} if index >= 3 else {}))
        ids.append(item_id)
    attention_query(database, monkeypatch, ids)
    assert [item['id'] for item in store.list_items(UID, limit=2)] == ids[3:]
    # Rebuild the query with the remaining active set for the HTTP badge.
    attention_query(database, monkeypatch, ids[3:])
    monkeypatch.setattr(store, 'LIMIT', 2)
    monkeypatch.setattr(store, 'pending_conversations', lambda uid: [])
    monkeypatch.setattr(routes.sync_jobs, 'pending_sync_jobs', lambda uid: [])
    monkeypatch.setattr(routes, 'ownership_enabled', lambda uid: False)
    assert http_client.get('/v1/pending-work').json()['attention_unseen_count'] == 2


def test_attention_zero_limit_returns_nothing(database, monkeypatch):
    item_id, path = permanent_item(database)
    attention_query(database, monkeypatch, [item_id])
    assert store.list_items(UID, limit=0) == []
    assert store.list_items(UID, limit=-1) == []
    assert database.rows[path]['active'] is True
    assert not any(tx.updates for tx in database.transactions)


def test_attention_scan_is_bounded_and_paginates(database, monkeypatch):
    item_id, _ = permanent_item(database)
    attention_query(database, monkeypatch, [item_id])
    query = store.items_ref(UID)
    cursor = object()
    assert store.list_items(UID, start_after=cursor) == []
    query.limit.assert_called_once_with(store.SCAN_LIMIT)
    query.start_after.assert_called_once_with(cursor)


class _PagingRef:
    def __init__(self, database, path):
        self._database = database
        self.path = path
        self.id = path[-1]

    def update(self, patch):
        self._database.rows[self.path].update(patch)


class _PagingQuery:
    """Ordered-by-id query double that honors ``start_after`` and ``limit``."""

    def __init__(self, database, path):
        self._database = database
        self._path = path
        self._after = None
        self._limit = None
        self._filters = []

    def where(self, *, filter):
        self._filters.append((filter.field_path, filter.value))
        return self

    def start_after(self, cursor):
        self._after = cursor.id
        return self

    def limit(self, count):
        self._limit = count
        return self

    def stream(self):
        rows = []
        for path, value in sorted(self._database.rows.items()):
            if path[:-1] != self._path:
                continue
            if self._after is not None and path[-1] <= self._after:
                continue
            if not all(value.get(field) == expected for field, expected in self._filters):
                continue
            rows.append(
                SimpleNamespace(
                    id=path[-1],
                    to_dict=lambda value=value: dict(value),
                    reference=_PagingRef(self._database, path),
                )
            )
        return iter(rows[: self._limit])


def test_attention_pages_past_scan_limit_without_skipping(database, monkeypatch):
    expected = []
    for index in range(620):
        cid = f'c{index:04d}'
        resolved = index % 6 == 0
        database.rows[('users', UID, 'conversations', cid)] = dict(
            ROW, structured={'title': 't', 'overview': 'done' if resolved else ''}
        )
        item_id = f'item-{index:04d}'
        database.rows[('users', UID, 'processing_attention_items', item_id)] = {
            'id': item_id,
            'conversation_id': cid,
            'generation': store.generation(ROW),
            'active': True,
            'seen': False,
            'retry': {'state': 'none', 'operation_id': None},
        }
        if not resolved:
            expected.append(item_id)
    monkeypatch.setattr(
        store, 'items_ref', lambda uid: _PagingQuery(database, ('users', UID, 'processing_attention_items'))
    )
    monkeypatch.setattr(store, 'now_utc', lambda: NOW)
    monkeypatch.delenv('PROCESSING_ATTENTION_NON_RETRYABLE_EXPIRY_ENABLED', raising=False)
    ids = [item['id'] for item in store.list_items(UID)]
    assert len(expected) > store.SCAN_LIMIT
    assert ids == expected
    assert len(ids) == len(set(ids))


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
    monkeypatch.setattr(sync_jobs, 'pending_sync_jobs', lambda uid, *, listed_conversation_ids=None: [])
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
    monkeypatch.setattr(sync_jobs, 'pending_sync_jobs', lambda uid, *, listed_conversation_ids=None: [])
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


@pytest.mark.parametrize('enabled', [None, False, True])
def test_pending_sync_dedupes_only_fully_listed_recordings(monkeypatch, enabled):
    from database import sync_jobs

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.delenv('HOME_PROCESSING_OWNERSHIP_UIDS', raising=False)
    if enabled is None:
        monkeypatch.delenv('HOME_PROCESSING_OWNERSHIP_ENABLED', raising=False)
    else:
        monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_ENABLED', str(enabled).lower())
    redis = Mock()
    from utils.episodes import home_processing

    monkeypatch.setattr(home_processing, 'live_owner', lambda uid: None)
    redis.zrevrange.return_value = ['covered', 'partial', 'unknown', 'outside']
    monkeypatch.setattr(sync_jobs, 'r', redis)

    def job(ids):
        return {
            'uid': UID,
            'status': 'processing',
            'created_at': NOW.timestamp(),
            'updated_at': NOW.timestamp(),
            'result': {'new_memories': ids},
        }

    jobs = {'covered': job(['a', 'b']), 'partial': job(['a', 'c']), 'unknown': job([]), 'outside': job(['c'])}
    monkeypatch.setattr(sync_jobs, 'get_sync_job', jobs.get)
    items = sync_jobs.pending_sync_jobs(UID, listed_conversation_ids={'a', 'b'})
    # The partial job represents c; its later chunk job must not count c twice.
    expected = ['partial', 'unknown'] if enabled is not False else list(jobs)
    assert [item['id'] for item in items] == ['sync:' + key for key in expected]
    if enabled is not False:
        assert items[0]['conversation_ids'] == ['c']
        assert items[0]['recording_count'] == 1
    # Hidden work is still pending, so its index entry must survive.
    redis.zrem.assert_not_called()


@pytest.mark.parametrize('attached', [False, True])
def test_live_owner_hides_recordings_and_observes_attach_gap(caplog, attached):
    caplog.set_level('INFO')
    from utils.episodes import home_processing, metrics

    owner = {
        'id': 'e',
        'status': 'live',
        'started_at': NOW,
        'last_activity_at': NOW + timedelta(minutes=10),
        'conversation_ids': ['c1'] if attached else [],
    }
    row = {'id': 'c1', 'recorded_start': NOW + timedelta(minutes=1), 'recorded_end': NOW + timedelta(minutes=2)}
    before = metrics.EPISODE_HOME_ATTACH_GAP_TOTAL._value.get()
    assert home_processing.owns_recording(owner, row)
    assert metrics.EPISODE_HOME_ATTACH_GAP_TOTAL._value.get() - before == (0 if attached else 1)
    assert ('event=episode_attach_gap' in caplog.text) is not attached
    if not attached:
        assert not home_processing.owns_recording(owner, dict(row, episode_id='closed-owner'))
    assert not home_processing.owns_recording(None, row)
    assert not home_processing.owns_recording(owner, dict(row, id='outside', recorded_start=NOW - timedelta(days=1)))


def test_live_owner_flag_off_does_not_read_episode(monkeypatch):
    from utils.episodes import home_processing

    monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_ENABLED', 'false')
    read = Mock(side_effect=AssertionError('flag off must not read Firestore'))
    monkeypatch.setattr(home_processing.episodes, 'get_current_episode', read)
    assert home_processing.live_owner(UID) is None
    read.assert_not_called()


def test_live_owner_enabled_by_default(monkeypatch):
    from utils.episodes import home_processing

    monkeypatch.delenv('HOME_PROCESSING_OWNERSHIP_ENABLED', raising=False)
    monkeypatch.delenv('HOME_PROCESSING_OWNERSHIP_UIDS', raising=False)
    monkeypatch.setattr(home_processing, 'episodes_enabled_for', lambda uid: True)
    monkeypatch.setattr(home_processing.client_gate, 'client_seen_cached', lambda uid: True)
    owner = {'id': 'live', 'status': 'live', 'conversation_ids': ['c1']}
    read = Mock(return_value=owner)
    monkeypatch.setattr(home_processing.episodes, 'get_current_episode', read)
    assert home_processing.live_owner(UID) == owner
    read.assert_called_once_with(UID, firestore_client=None)


@pytest.mark.parametrize('flag', ['HOME_PROCESSING_OWNERSHIP_ENABLED', 'HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED'])
def test_home_kill_switches_are_independent_and_keep_optional_cohort(monkeypatch, flag):
    from config.home_processing import ownership_enabled, live_member_notes_enabled

    readers = {
        'HOME_PROCESSING_OWNERSHIP_ENABLED': ownership_enabled,
        'HOME_LIVE_MEMBER_NOTES_DEFERRED_ENABLED': live_member_notes_enabled,
    }
    for key in readers:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.delenv('HOME_PROCESSING_OWNERSHIP_UIDS', raising=False)
    assert all(read(UID) for read in readers.values())
    monkeypatch.setenv(flag, 'false')
    assert not readers[flag](UID)
    assert all(read(UID) for key, read in readers.items() if key != flag)
    monkeypatch.setenv(flag, ' TRUE ')
    monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_UIDS', ' owner, internal ')
    assert all(read(UID) for read in readers.values())
    assert not any(read('outside') for read in readers.values())


def test_pending_work_endpoint_dedupes_live_and_listed_owners(http_client, monkeypatch):
    from database import sync_jobs
    from utils.episodes import home_processing

    monkeypatch.setattr(home_processing.conversations, 'get_conversations_by_id_without_photos', lambda *a: [])
    monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_ENABLED', 'true')
    monkeypatch.setattr(store, 'list_items', lambda *args, **kwargs: [])
    monkeypatch.setattr(
        home_processing,
        'live_owner',
        lambda *args, **kwargs: {
            'id': 'live',
            'status': 'live',
            'conversation_ids': ['c1'],
        },
    )
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    query = Mock()
    query.where.return_value = query
    query.limit.return_value = query
    query.stream.return_value = [
        SimpleNamespace(id=cid, to_dict=lambda: dict(ROW, status='processing', finalization_status='queued'))
        for cid in ['c1', 'outside']
    ]
    client = Mock()
    client.collection.return_value.document.return_value.collection.return_value = query
    monkeypatch.setattr(store, 'db', client)
    redis = Mock()
    redis.zrevrange.return_value = ['live', 'listed', 'unowned']
    monkeypatch.setattr(sync_jobs, 'r', redis)
    monkeypatch.setattr(
        sync_jobs,
        'get_sync_job',
        lambda jid: {
            'uid': UID,
            'status': 'processing',
            'created_at': NOW.timestamp(),
            'updated_at': NOW.timestamp(),
            'result': {'new_memories': {'live': ['c1'], 'listed': ['outside'], 'unowned': ['new']}[jid]},
        },
    )
    response = http_client.get('/v1/pending-work', headers={'X-Omi-App-Channel': 'beta', 'X-Omi-Home-Ownership': '1'})
    assert response.status_code == 200
    assert [item['id'] for item in response.json()['items']] == ['conv:outside', 'sync:unowned']


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('metadata', ['present', 'empty', 'missing'])
def test_inflight_sync_uses_admission_target_and_recording_count(monkeypatch, enabled, metadata):
    from database import sync_jobs
    from utils.episodes import home_processing

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_ENABLED', str(enabled).lower())
    monkeypatch.setattr(home_processing, 'live_owner', lambda uid: None)
    redis = Mock()
    redis.zrevrange.return_value = ['job']
    monkeypatch.setattr(sync_jobs, 'r', redis)
    monkeypatch.setattr(
        sync_jobs,
        'get_sync_job',
        lambda jid: {
            'uid': UID,
            'status': 'processing',
            'created_at': NOW.timestamp(),
            'updated_at': NOW.timestamp(),
            'result': None,
            **(
                {'target_conversation_id': 'c1', 'recording_ids': ['r1', 'r2', 'r3']}
                if metadata == 'present'
                else {'target_conversation_id': None, 'recording_ids': []} if metadata == 'empty' else {}
            ),
        },
    )
    enabled = enabled and metadata == 'present'
    items = sync_jobs.pending_sync_jobs(UID)
    assert items[0]['conversation_ids'] == (['c1'] if enabled else [])
    assert items[0].get('recording_count', 1) == (3 if enabled else 1)
    assert len(sync_jobs.pending_sync_jobs(UID, listed_conversation_ids={'c1'})) == (0 if enabled else 1)


def test_pending_conversations_fills_visible_page_after_owned_page(monkeypatch):
    query = Mock()
    query.where.return_value = query
    query.limit.return_value = query
    query.start_after.return_value = query
    owned = [SimpleNamespace(id=str(i), to_dict=lambda: dict(ROW, status='processing')) for i in range(store.LIMIT)]
    outside = SimpleNamespace(id='outside', to_dict=lambda: dict(ROW, status='processing'))
    query.stream.side_effect = [owned, [outside]]
    client = Mock()
    client.collection.return_value.document.return_value.collection.return_value = query
    monkeypatch.setattr(store, 'db', client)
    result = store.pending_conversations(UID, exclude=lambda row: row['id'] != 'outside')
    assert [item['id'] for item in result] == ['conv:outside']
    query.start_after.assert_called_once_with(owned[-1])


def test_pending_sync_default_reader_retains_live_writer_jobs(monkeypatch):
    from database import sync_jobs

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_ENABLED', 'true')
    redis = Mock()
    redis.zrevrange.return_value = ['job']
    monkeypatch.setattr(sync_jobs, 'r', redis)
    monkeypatch.setattr(
        sync_jobs,
        'get_sync_job',
        lambda _: {
            'uid': UID,
            'status': 'processing',
            'created_at': NOW.timestamp(),
            'updated_at': NOW.timestamp(),
            'target_conversation_id': 'c1',
            'result': None,
        },
    )
    assert len(sync_jobs.pending_sync_jobs(UID)) == 1  # Rehome lease probes must see writers.
    assert sync_jobs.pending_sync_jobs(UID, listed_conversation_ids={'c1'}) == []


def test_unlinked_sync_target_inside_live_window_never_reappears_as_a_job(monkeypatch, caplog):
    from utils.episodes import home_processing

    caplog.set_level('INFO')
    owner = {'id': 'e', 'started_at': NOW, 'last_activity_at': NOW + timedelta(minutes=10), 'conversation_ids': []}
    row = {'id': 'gap', 'recorded_start': NOW + timedelta(minutes=1), 'recorded_end': NOW + timedelta(minutes=2)}
    monkeypatch.setattr(home_processing.conversations, 'get_conversations_by_id_without_photos', lambda *a: [row])
    item = {'id': 'sync:job', 'conversation_ids': ['gap']}
    assert home_processing.suppress_owned_syncs(UID, [item], owner, set()) == []
    assert 'event=episode_attach_gap' in caplog.text


@pytest.mark.parametrize('enabled', [False, True])
@pytest.mark.parametrize('presentation', [False, True])
@pytest.mark.parametrize('recording_ids', [False, True])
def test_chunk_jobs_count_unique_recordings_without_hiding_raw_writers(
    monkeypatch, enabled, presentation, recording_ids
):
    from database import sync_jobs

    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_ENABLED', str(enabled).lower())
    memberships = {'newest': ['1', '2'], 'overlap': ['2', '3'], 'duplicate': ['1'], 'unknown': []}
    redis = Mock()
    redis.zrevrange.return_value = list(memberships)
    monkeypatch.setattr(sync_jobs, 'r', redis)
    monkeypatch.setattr(
        sync_jobs,
        'get_sync_job',
        lambda jid: {
            'uid': UID,
            'status': 'processing',
            'created_at': NOW.timestamp(),
            'updated_at': NOW.timestamp(),
            'recording_ids': ['r' + value for value in memberships[jid]] if recording_ids else [],
            'result': {'new_memories': ['c' + value for value in memberships[jid]]},
        },
    )
    items = (
        sync_jobs.pending_sync_jobs(UID, listed_conversation_ids=set())
        if presentation
        else sync_jobs.pending_sync_jobs(UID)
    )
    deduped = enabled and presentation
    assert [item['id'] for item in items] == ['sync:' + jid for jid in memberships if not deduped or jid != 'duplicate']
    # Three known recordings plus one job whose recording is not known yet.
    assert sum(item.get('recording_count', 1) for item in items) == (4 if deduped or not enabled else 6)
    redis.zrem.assert_not_called()
