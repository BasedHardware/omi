"""Provider-boundary and tenant-isolation checks for partition routing."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from threading import Event
from uuid import uuid4

import pytest
from pinecone.db_data.dataclasses import FetchResponse, Vector
from pinecone.db_data.index import Index
from pinecone.exceptions import PineconeApiException

from database import pinecone_partition_index as adapter
from database import pinecone_partition_state as state
from database.legal_holds import DestructiveOperationInProgress
from database.pinecone_provider_errors import BARRIER_ID
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction


class RecordingIndex:
    def __init__(self):
        self.calls = []
        self.fetch_records = {}
        self.fetch_by_namespace = {}
        self.matches = []
        self.failure = None
        self.lsn = 17
        self.before_write = None
        self.indexed_lsn = 17

    def query(self, **kwargs):
        self.calls.append(('query', (), deepcopy(kwargs)))
        if self.failure:
            raise self.failure
        return {'matches': self.matches, 'usage': {'read_units': 1}}

    def fetch(self, **kwargs):
        self.calls.append(('fetch', (), deepcopy(kwargs)))
        available = self.fetch_by_namespace.get(kwargs['namespace'], self.fetch_records)
        records = {k: v for k, v in available.items() if k in kwargs['ids']}
        return FetchResponse(namespace=kwargs['namespace'], vectors=records, usage={'read_units': 1})

    def _query(self, **kwargs):
        return self.query(**kwargs), 200, {'x-pinecone-max-indexed-lsn': str(self.indexed_lsn)}

    def list(self, **kwargs):
        self.calls.append(('list', (), deepcopy(kwargs)))
        return iter([['owner-a-record']])

    def describe_index_stats(self):
        return {'dimension': 2}

    def _write(self, method, args, kwargs):
        self.calls.append((method, args, deepcopy(kwargs)))
        if self.before_write:
            self.before_write()
        if self.failure:
            raise self.failure
        body = {'upserted_count': len(kwargs.get('vectors', []))} if method == 'upsert' else {}
        if kwargs.get('_return_http_data_only') is False:
            return body, 200, {'X-Pinecone-Request-Lsn': str(self.lsn)}
        return body

    def upsert(self, **kwargs):
        return self._write('upsert', (), kwargs)

    def update(self, *args, **kwargs):
        return self._write('update', args, kwargs)

    def delete(self, **kwargs):
        return self._write('delete', (), kwargs)


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.setenv('PINECONE_PARTITIONS_ENABLED', 'true')
    db = StrictFirestore()

    def delete(transaction, ref):
        transaction._assert_reference_belongs(ref)
        transaction.has_written = True
        transaction._database.rows.pop(ref.path, None)

    monkeypatch.setattr(StrictFirestoreTransaction, 'delete', delete)
    for name in (
        '_begin_mutation',
        '_finish_mutation',
        '_mark_mutation_uncertain',
        '_begin_migration',
        '_cancel_migration',
        '_cutover',
    ):
        monkeypatch.setattr(state, name, getattr(state, name).to_wrap)
    index = RecordingIndex()
    key = state.PartitionKey('test-index', 'ns1', 'owner-a')
    scoped = adapter.owner_index(index, key.uid, index_name=key.index_name, firestore_client=db)
    return scoped, index, key, db


def partition(key, db):
    route = state.begin_migration(key, uuid4().hex, firestore_client=db)
    state.cutover(
        key,
        route.migration_token,
        route.revision,
        {
            'passed': True,
            'freshness_verified': True,
            'key_id': key.document_id,
            'migration_token': route.migration_token,
            'revision': route.revision,
            'source_namespace': route.source_namespace,
            'target_namespace': route.target_namespace,
            'receipt_id': uuid4().hex,
            'source_indexed_lsn': max(100, route.latest_write_lsn),
            'source_barrier_lsn': max(100, route.latest_write_lsn),
            'target_write_lsn': 7,
            'target_indexed_lsn': 7,
        },
        firestore_client=db,
    )


def record(uid='owner-a', id='owner-a-record'):
    return {'id': id, 'values': [0.5, 0.5], 'metadata': {'uid': uid, 'memory_id': 'record'}}


def test_reads_switch_primary_without_cache_and_preserve_complete_filter(harness):
    scoped, raw, key, db = harness
    where = {'$and': [{'uid': {'$eq': key.uid}}, {'created_at': {'$gte': 100}}, {'private': {'$ne': True}}]}
    original = deepcopy(where)
    scoped.query(namespace=key.family, vector=[1.0, 0.0], filter=where, top_k=3)
    partition(key, db)
    for _ in range(3):
        scoped.query(namespace=key.family, vector=[1.0, 0.0], filter=where, top_k=3)
    assert [call[2]['namespace'] for call in raw.calls] == [key.family] + [key.partition_namespace] * 3
    assert all(call[2]['filter'] == original for call in raw.calls)
    assert where == original


@pytest.mark.parametrize('filter', [None, {}, {'uid': 'other'}, {'$or': [{'uid': 'owner-a'}, {'public': True}]}])
def test_unscoped_or_cross_owner_query_is_rejected_before_provider(harness, filter):
    scoped, raw, _, _ = harness
    with pytest.raises(ValueError, match='owner'):
        scoped.query(namespace='ns1', vector=[1.0, 0.0], filter=filter, top_k=3)
    assert raw.calls == []


def test_colliding_buckets_retain_distinct_owner_constraints(harness):
    scoped, raw, key, db = harness
    collision = next(
        candidate
        for n in range(10000)
        if (candidate := state.PartitionKey(key.index_name, key.family, f'other-{n}')).partition_namespace
        == key.partition_namespace
    )
    partition(key, db)
    partition(collision, db)
    other = adapter.owner_index(raw, collision.uid, index_name=key.index_name, firestore_client=db)
    scoped.query(namespace=key.family, vector=[1.0, 0.0], filter={'uid': key.uid}, top_k=1)
    other.query(namespace=key.family, vector=[1.0, 0.0], filter={'uid': collision.uid}, top_k=1)
    assert raw.calls[0][2]['namespace'] == raw.calls[1][2]['namespace']
    assert [call[2]['filter'] for call in raw.calls] == [{'uid': key.uid}, {'uid': collision.uid}]


def test_empty_result_and_provider_error_never_fall_back_to_legacy(harness):
    scoped, raw, key, db = harness
    partition(key, db)
    assert scoped.query(namespace=key.family, vector=[1.0, 0.0], filter={'uid': key.uid}, top_k=3)['matches'] == []
    raw.failure = TimeoutError('provider timeout')
    with pytest.raises(TimeoutError):
        scoped.query(namespace=key.family, vector=[1.0, 0.0], filter={'uid': key.uid}, top_k=3)
    assert len(raw.calls) == 2
    assert all(call[2]['namespace'] == key.partition_namespace for call in raw.calls)


def test_successful_upsert_has_durable_admission_and_unwraps_sdk_headers(harness):
    scoped, raw, key, db = harness
    partition(key, db)
    raw.before_write = lambda: assert_pending(key, db)
    response = scoped.upsert(namespace=key.family, vectors=[record()])
    assert response == {'upserted_count': 1}
    assert raw.calls[0][2]['namespace'] == key.partition_namespace
    route = state.get_route(key, firestore_client=db)
    assert route.pending_count == 0
    assert route.latest_write_lsn == 17


def assert_pending(key, db):
    assert state.get_route(key, firestore_client=db).pending_count == 1


def test_unknown_provider_outcome_permanently_blocks_migration(harness):
    scoped, raw, key, db = harness
    raw.failure = TimeoutError('provider may have accepted this request')
    with pytest.raises(TimeoutError):
        scoped.upsert(namespace=key.family, vectors=[record()])
    for _ in range(3):
        route = state.get_route(key, firestore_client=db)
        assert route.pending_count == 0
        assert route.uncertain_count == 1
        with pytest.raises(state.PartitionBusy):
            state.begin_migration(key, uuid4().hex, firestore_client=db)
    raw.failure = None
    scoped.upsert(namespace=key.family, vectors=[record()])
    assert state.get_route(key, firestore_client=db).uncertain_count == 1


def test_upsert_cannot_route_record_for_other_owner(harness):
    scoped, raw, _, _ = harness
    with pytest.raises(ValueError, match='owner'):
        scoped.upsert(namespace='ns1', vectors=[record(uid='other')])
    assert raw.calls == []


def test_fetch_accepts_real_sdk_dataclass_and_rejects_cross_owner_record(harness):
    scoped, raw, key, db = harness
    partition(key, db)
    raw.fetch_records['owner-a-record'] = Vector(**record())
    result = scoped.fetch(namespace=key.family, ids=['owner-a-record'])
    assert isinstance(result, FetchResponse)
    assert result.vectors['owner-a-record'].metadata['uid'] == key.uid
    raw.fetch_records['other-record'] = Vector(**record(uid='other', id='other-record'))
    with pytest.raises(ValueError, match='owner'):
        scoped.fetch(namespace=key.family, ids=['other-record'])


def test_update_uses_sdk_fetch_response_and_cannot_change_owner(harness):
    scoped, raw, key, db = harness
    partition(key, db)
    raw.fetch_records['owner-a-record'] = Vector(**record())
    scoped.update('owner-a-record', namespace=key.family, set_metadata={'category': 'work'})
    assert raw.calls[-1][0] == 'update'
    assert raw.calls[-1][2]['namespace'] == key.partition_namespace
    count = len(raw.calls)
    with pytest.raises(ValueError, match='ownership'):
        scoped.update('owner-a-record', namespace=key.family, set_metadata={'uid': 'other'})
    assert len(raw.calls) == count


def test_delete_by_id_checks_existing_owner_before_mutating(harness):
    scoped, raw, key, db = harness
    raw.fetch_records['other-record'] = Vector(**record(uid='other', id='other-record'))
    with pytest.raises(ValueError, match='owner'):
        scoped.delete(namespace=key.family, ids=['other-record'])
    assert not any(method == 'delete' for method, _, _ in raw.calls)
    route = state.get_route(key, firestore_client=db)
    assert route.pending_count == route.uncertain_count == 0


def test_explicit_delete_removes_primary_and_retained_copy(harness):
    scoped, raw, key, db = harness
    partition(key, db)
    raw.fetch_records['owner-a-record'] = Vector(**record())
    scoped.delete(namespace=key.family, ids=['owner-a-record'])
    writes = [call for call in raw.calls if call[0] == 'delete']
    assert [call[2]['namespace'] for call in writes] == [key.partition_namespace, key.family]
    assert all(call[2]['ids'] == ['owner-a-record'] for call in writes)
    assert state.get_route(key, firestore_client=db).pending_count == 0


def test_retained_copy_delete_failure_keeps_mutation_uncertain(harness):
    scoped, raw, key, db = harness
    partition(key, db)

    def fail_second_write():
        if len([call for call in raw.calls if call[0] == 'delete']) == 2:
            raise TimeoutError('retained copy outcome unknown')

    raw.before_write = fail_second_write
    with pytest.raises(TimeoutError):
        scoped.delete(namespace=key.family, filter={'uid': key.uid})
    route = state.get_route(key, firestore_client=db)
    assert route.pending_count == 0
    assert route.uncertain_count == 1
    with pytest.raises(state.PartitionBusy):
        state.begin_rollback(key, uuid4().hex, firestore_client=db)


def test_account_purge_constrains_both_namespaces_to_owner(harness):
    scoped, raw, key, db = harness
    partition(key, db)
    scoped.delete_all_copies(namespace=key.family, filter={'uid': key.uid})
    deletes = [call for call in raw.calls if call[0] == 'delete']
    assert [call[2]['namespace'] for call in deletes] == [key.family, key.partition_namespace]
    assert all(call[2]['filter'] == {'uid': key.uid} for call in deletes)
    barriers = [call for call in raw.calls if call[0] == 'upsert']
    assert len(barriers) == 2
    assert all(call[2]['vectors'][0]['id'] == BARRIER_ID for call in barriers)
    assert all('uid' not in call[2]['vectors'][0]['metadata'] for call in barriers)
    scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})
    reads = [call for call in raw.calls if call[0] == 'query']
    assert [call[2]['namespace'] for call in reads] == [key.family, key.partition_namespace]
    assert all(call[2]['filter'] == {'uid': key.uid} for call in reads)


def test_account_purge_cannot_pass_while_migration_or_mutation_pending(harness):
    scoped, raw, key, db = harness
    state.begin_migration(key, uuid4().hex, firestore_client=db)
    with pytest.raises(state.PartitionBusy):
        scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})
    assert not raw.calls


def test_account_purge_does_not_hide_remaining_vectors(harness, monkeypatch):
    scoped, raw, key, _ = harness
    scoped.delete_all_copies(namespace=key.family, filter={'uid': key.uid})
    raw.matches = [{'id': 'retained-record'}]
    monkeypatch.setattr(adapter.time, 'sleep', lambda seconds: None)
    with pytest.raises(state.PartitionBusy):
        scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})
    assert len([call for call in raw.calls if call[0] == 'query']) == 6


@pytest.mark.parametrize('kwargs', [{'delete_all': True}, {'filter': {'uid': 'other'}}, {}])
def test_bucket_wide_or_unscoped_delete_is_rejected(harness, kwargs):
    scoped, raw, _, _ = harness
    with pytest.raises(ValueError):
        scoped.delete(namespace='ns1', **kwargs)
    assert raw.calls == []


def test_list_requires_owner_prefix_and_uses_selected_namespace(harness):
    scoped, raw, key, db = harness
    partition(key, db)
    assert list(scoped.list(namespace=key.family, prefix=key.uid + '-')) == [['owner-a-record']]
    assert raw.calls[-1][2]['namespace'] == key.partition_namespace
    with pytest.raises(ValueError):
        scoped.list(namespace=key.family, prefix='other-')


@pytest.mark.parametrize('flag', [None, 'false', '0'])
def test_environment_flag_cannot_bypass_committed_partition_route(harness, monkeypatch, flag):
    scoped, raw, key, db = harness
    partition(key, db)
    if flag is None:
        monkeypatch.delenv('PINECONE_PARTITIONS_ENABLED')
    else:
        monkeypatch.setenv('PINECONE_PARTITIONS_ENABLED', flag)
    scoped.query(namespace=key.family, filter={'uid': key.uid}, vector=[1.0, 0.0], top_k=5)
    scoped.upsert(namespace=key.family, vectors=[record()])
    assert all(call[2]['namespace'] == key.partition_namespace for call in raw.calls)
    assert raw.calls[-1][2]['_return_http_data_only'] is False


@pytest.mark.parametrize(
    'kwargs',
    [
        dict(async_req=True),
        dict(async_threadpool_executor=True),
        dict(batch_size=50),
        dict(_return_http_data_only=True),
    ],
)
def test_non_synchronous_mutation_options_rejected_before_admission(harness, kwargs):
    scoped, raw, key, db = harness
    with pytest.raises(ValueError, match='synchronous'):
        scoped.upsert(namespace=key.family, vectors=[record()], **kwargs)
    assert raw.calls == []
    assert state.get_route(key, firestore_client=db).revision == 0


def test_index_identity_is_required_even_with_old_flag_off(monkeypatch):
    monkeypatch.delenv('PINECONE_INDEX_NAME', raising=False)
    monkeypatch.setenv('PINECONE_PARTITIONS_ENABLED', 'false')
    with pytest.raises(ValueError, match='index identity'):
        adapter.owner_index(RecordingIndex(), 'owner-a')


def test_delete_rejects_cross_owner_id_in_retained_copy_before_any_write(harness):
    scoped, raw, key, db = harness
    partition(key, db)
    raw.fetch_by_namespace[key.partition_namespace] = {}
    raw.fetch_by_namespace[key.family] = {'collision': Vector(**record(uid='other', id='collision'))}
    with pytest.raises(ValueError, match='owner'):
        scoped.delete(namespace=key.family, ids=['collision'])
    assert not any(call[0] == 'delete' for call in raw.calls)
    route = state.get_route(key, firestore_client=db)
    assert route.pending_count == route.uncertain_count == 0


def test_empty_purge_query_cannot_pass_before_delete_lsn_is_indexed(harness, monkeypatch):
    scoped, raw, key, _ = harness
    scoped.delete_all_copies(namespace=key.family, filter={'uid': key.uid})
    raw.indexed_lsn = raw.lsn - 1
    monkeypatch.setattr(adapter.time, 'sleep', lambda value: None)
    with pytest.raises(state.PartitionBusy):
        scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})
    raw.indexed_lsn = raw.lsn
    scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})


def test_purge_verification_requires_its_own_deletion_receipt(harness):
    scoped, raw, key, _ = harness
    with pytest.raises(state.PartitionStateError, match='receipts'):
        scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})
    assert raw.calls == []


def test_account_purge_cancels_quiet_migration_before_deleting_both_copies(harness):
    scoped, raw, key, db = harness
    state.begin_migration(key, 'run', firestore_client=db)
    scoped.delete_all_copies(namespace=key.family, filter={'uid': key.uid})
    route = state.get_route(key, firestore_client=db)
    assert route.mode == 'legacy'
    assert route.migration_token is None
    assert {call[2]['namespace'] for call in raw.calls} == {key.family, key.partition_namespace}
    scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})


def provider_error(status=404, body=None):
    error = PineconeApiException(status=status, reason='provider error')
    error.body = json.dumps({'code': 5, 'message': 'Namespace not found'}) if body is None else body
    return error


def test_exact_missing_namespace_delete_is_successful_known_noop(harness):
    scoped, raw, key, db = harness
    raw.failure = provider_error()
    assert scoped.delete(namespace=key.family, filter={'uid': key.uid}) == {}
    assert len([call for call in raw.calls if call[0] == 'delete']) == 2
    route = state.get_route(key, firestore_client=db)
    assert route.pending_count == route.uncertain_count == 0


@pytest.mark.parametrize(
    'status,body',
    [
        (403, '{"code":5,"message":"Namespace not found"}'),
        (500, '{"code":5,"message":"Namespace not found"}'),
        (404, '{"code":7,"message":"Namespace not found"}'),
        (404, '{"code":5,"message":"Index not found"}'),
        (404, 'Namespace not found'),
    ],
)
def test_other_provider_errors_are_not_silently_successful_deletes(harness, status, body):
    scoped, raw, key, db = harness
    raw.failure = provider_error(status, body)
    with pytest.raises(PineconeApiException):
        scoped.delete(namespace=key.family, filter={'uid': key.uid})
    assert state.get_route(key, firestore_client=db).uncertain_count == 1


def test_namespace_absence_is_not_successful_upsert(harness):
    scoped, raw, key, db = harness
    raw.failure = provider_error()
    with pytest.raises(PineconeApiException):
        scoped.upsert(namespace=key.family, vectors=[record()])
    assert state.get_route(key, firestore_client=db).uncertain_count == 1


def test_purge_real_barrier_advances_after_noop_delete_lsn_stays_unindexed(harness):
    scoped, raw, key, _ = harness
    raw.indexed_lsn = 0
    receipts = []

    def provider_indexing():
        method, _, payload = raw.calls[-1]
        raw.lsn += 1
        if method == 'upsert':
            assert payload['vectors'][0]['id'] == BARRIER_ID
            assert 'uid' not in payload['vectors'][0]['metadata']
            raw.indexed_lsn = raw.lsn
        receipts.append((method, payload['namespace'], raw.lsn))

    raw.before_write = provider_indexing
    scoped.delete_all_copies(namespace=key.family, filter={'uid': key.uid})
    assert [method for method, _, _ in receipts] == ['delete', 'delete', 'upsert', 'upsert']
    assert scoped._deletion_lsns[key.family] == {
        namespace: lsn for method, namespace, lsn in receipts if method == 'upsert'
    }
    scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})


def test_internal_barrier_failure_does_not_poison_acknowledged_customer_deletion(harness):
    scoped, raw, key, db = harness

    def fail_internal_barrier():
        if raw.calls[-1][0] == 'upsert':
            raise TimeoutError('internal-only barrier acknowledgement lost')

    raw.before_write = fail_internal_barrier
    with pytest.raises(TimeoutError):
        scoped.delete_all_copies(namespace=key.family, filter={'uid': key.uid})
    route = state.get_route(key, firestore_client=db)
    assert route.pending_count == route.uncertain_count == 0
    with pytest.raises(state.PartitionStateError, match='receipts'):
        scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})


def test_failed_repeat_purge_cannot_reuse_old_freshness_receipt(harness):
    scoped, raw, key, db = harness
    scoped.delete_all_copies(namespace=key.family, filter={'uid': key.uid})
    scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})

    def fail_internal_barrier():
        if raw.calls[-1][0] == 'upsert':
            raise TimeoutError('new barrier acknowledgement lost')

    raw.before_write = fail_internal_barrier
    with pytest.raises(TimeoutError):
        scoped.delete_all_copies(namespace=key.family, filter={'uid': key.uid})
    with pytest.raises(state.PartitionStateError, match='receipts'):
        scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})
    assert state.get_route(key, firestore_client=db).uncertain_count == 0


def test_purge_attempts_known_erasures_despite_uncertainty_but_never_claims_done(harness):
    scoped, raw, key, db = harness
    ticket = state.begin_mutation(key, full_owner=True, firestore_client=db)
    state.mark_mutation_uncertain(key, ticket, firestore_client=db)
    scoped.delete_all_copies(namespace=key.family, filter={'uid': key.uid})
    assert len([call for call in raw.calls if call[0] == 'delete']) == 2
    assert state.get_route(key, firestore_client=db).uncertain_count == 1
    with pytest.raises(state.PartitionBusy):
        scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})


@pytest.mark.parametrize('method', ['upsert', 'update'])
def test_embedding_delayed_writer_resuming_after_account_purge_cannot_resurrect_data(harness, method):
    scoped, raw, key, db = harness
    embedding_started, resume_writer = Event(), Event()

    def delayed_writer():
        # This is the early writer fence used before a slow embedding call.
        # It passes while the account still exists, then the request stalls.
        with adapter.external_write_fence(key.uid, firestore_client=db):
            pass
        embedding_started.set()
        assert resume_writer.wait(5)
        if method == 'upsert':
            return scoped.upsert(namespace=key.family, vectors=[record()])
        return scoped.update('owner-a-record', namespace=key.family, set_metadata={'category': 'work'})

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(delayed_writer)
        try:
            assert embedding_started.wait(5)
            marker = db.collection('account_deletions').document(key.uid)
            db.rows[marker.path] = {'wipe_status': 'pending'}
            scoped.delete_all_copies(namespace=key.family, filter={'uid': key.uid})
            scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})
            db.rows[marker.path] = {'wipe_status': 'completed'}
            calls_before_resume = deepcopy(raw.calls)
        finally:
            resume_writer.set()
        with pytest.raises(DestructiveOperationInProgress):
            future.result(timeout=5)
    assert raw.calls == calls_before_resume
    route = state.get_route(key, firestore_client=db)
    assert route.pending_count == route.uncertain_count == 0


@pytest.mark.parametrize('method', ['upsert', 'update'])
def test_admission_is_visible_to_purge_during_fresh_writer_fence(harness, monkeypatch, method):
    scoped, raw, key, db = harness
    original_fence = adapter.external_write_fence
    checked = []

    @contextmanager
    def inspect_admission(uid, *, firestore_client):
        assert uid == key.uid
        assert firestore_client is db
        assert state.get_route(key, firestore_client=db).pending_count == 1
        assert raw.calls == []
        with pytest.raises(state.PartitionBusy):
            scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})
        with original_fence(uid, firestore_client=db):
            checked.append(True)
            yield

    monkeypatch.setattr(adapter, 'external_write_fence', inspect_admission)

    def check_pending_before_provider():
        assert checked == [True]
        assert state.get_route(key, firestore_client=db).pending_count == 1

    raw.before_write = check_pending_before_provider
    if method == 'upsert':
        scoped.upsert(namespace=key.family, vectors=[record()])
    else:
        scoped.update('owner-a-record', namespace=key.family, set_metadata={'category': 'work'})
    assert checked == [True]
    assert state.get_route(key, firestore_client=db).pending_count == 0


@pytest.mark.parametrize('copying', [False, True])
def test_purge_stats_failure_never_leaves_admitted_or_uncertain_mutation(harness, monkeypatch, copying):
    scoped, raw, key, db = harness
    if copying:
        state.begin_migration(key, 'run', firestore_client=db)

    def fail_stats():
        assert state.get_route(key, firestore_client=db).pending_count == 0
        raise TimeoutError('stats read failed before any provider mutation')

    monkeypatch.setattr(raw, 'describe_index_stats', fail_stats)
    with pytest.raises(TimeoutError, match='stats read'):
        scoped.delete_all_copies(namespace=key.family, filter={'uid': key.uid})
    route = state.get_route(key, firestore_client=db)
    assert route.pending_count == route.uncertain_count == 0
    assert route.mode == 'legacy'
    assert raw.calls == []
    assert not any('operations' in path for path in db.rows)


def test_pinned_sdk_upsert_really_preserves_http_headers(monkeypatch):
    index = Index(api_key='test-api-key', host='https://not-a-real-pinecone-host.invalid')
    expected = ({'upserted_count': 1}, 200, {'x-pinecone-request-lsn': '29'})
    calls = []

    def upsert_vectors(request, **kwargs):
        calls.append(kwargs)
        return expected

    monkeypatch.setattr(index._vector_api, 'upsert_vectors', upsert_vectors)
    response = index.upsert(vectors=[record()], namespace='ns1', _return_http_data_only=False)
    assert response == expected
    assert calls[0]['_return_http_data_only'] is False
    assert adapter._body_and_lsn(response) == ({'upserted_count': 1}, 29)
    index.close()
