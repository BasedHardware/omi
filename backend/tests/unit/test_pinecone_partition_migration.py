"""Migration failure cases with strict state transactions and deterministic LSNs."""

from collections import defaultdict
from contextlib import nullcontext
from copy import deepcopy
import json

import httpx
import pytest

from database import pinecone_partition_index as adapter
from database import pinecone_partition_migration as migration
from database import pinecone_partition_state as state
from database.pinecone_provider_errors import BARRIER_ID, barrier_record
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreTransaction


class Provider(migration.PartitionTransport):
    def __init__(self):
        self.records = defaultdict(dict)
        self.lsns = defaultdict(int)
        self.indexed = defaultdict(int)
        self.calls = []
        self.read_units = 0
        self.write_units = 0
        self.before_write = None
        self.corrupt_namespace = None
        self.reverse_namespace = None
        self.lag_namespace = None
        self.fail_namespace = None
        self.foreign_page = False
        self.repeated_page = False
        self.missing_query_lsn = False
        self.stale_fetch_records = {}
        self.page_size = 2

    @staticmethod
    def _predicate(where):
        clauses = []
        for field, expected in where.items():
            if field == '$and':
                predicates = [Provider._predicate(item) for item in expected]
                clauses.append(lambda metadata, ps=predicates: all(p(metadata) for p in ps))
            elif field == '$or':
                # Compile exact identity selectors once, so the large-owner
                # case exercises all proof batches without an O(N²) fake.
                fields = tuple(sorted(expected[0]))
                if all(
                    tuple(sorted(item)) == fields and all(set(v) == {'$eq'} for v in item.values()) for item in expected
                ):
                    identities = {tuple(item[name]['$eq'] for name in fields) for item in expected}
                    clauses.append(
                        lambda metadata, fs=fields, ids=identities: tuple(metadata.get(f) for f in fs) in ids
                    )
                else:
                    predicates = [Provider._predicate(item) for item in expected]
                    clauses.append(lambda metadata, ps=predicates: any(p(metadata) for p in ps))
            elif set(expected) == {'$eq'}:
                clauses.append(lambda metadata, f=field, value=expected['$eq']: metadata.get(f) == value)
            elif set(expected) == {'$exists'}:
                clauses.append(lambda metadata, f=field, exists=expected['$exists']: (f in metadata) is exists)
            elif set(expected) == {'$nin'}:
                values = set(expected['$nin'])
                clauses.append(lambda metadata, f=field, values=values: f in metadata and metadata[f] not in values)
            else:
                raise AssertionError(f'Unmodeled filter operation: {expected}')
        return lambda metadata: all(check(metadata) for check in clauses)

    def call(self, path, payload):
        self.calls.append((path, deepcopy(payload)))
        namespace = payload['namespace']
        if path in {'vectors/upsert', 'vectors/delete'}:
            if self.before_write:
                self.before_write(path, payload)
            if path == 'vectors/upsert':
                for record in payload['vectors']:
                    self.records[namespace][record['id']] = deepcopy(record)
                    if namespace == self.corrupt_namespace:
                        self.records[namespace][record['id']]['values'][0] += 0.125
            else:
                changed = any(id in self.records[namespace] for id in payload['ids'])
                for id in payload['ids']:
                    self.records[namespace].pop(id, None)
            self.lsns[namespace] += 1
            if path == 'vectors/upsert' or changed:
                self.indexed[namespace] = self.lsns[namespace]
            self.write_units += 1
            if namespace == self.fail_namespace:
                raise TimeoutError('request applied but acknowledgement lost')
            return {}, {'x-pinecone-request-lsn': str(self.lsns[namespace])}
        available = self.records[namespace]
        if path == 'vectors/fetch_by_metadata':
            available = self.stale_fetch_records.get(namespace, available)
        matches_filter = self._predicate(payload['filter'])
        rows = [row for row in available.values() if matches_filter(row['metadata'])]
        self.read_units += 1
        if path == 'vectors/fetch_by_metadata':
            rows.sort(key=lambda row: row['id'])
            offset = int(payload.get('paginationToken', '0'))
            page = deepcopy(rows[offset : offset + self.page_size])
            if self.foreign_page and page:
                page[0]['metadata']['uid'] = 'foreign-owner'
            next_token = str(offset + self.page_size) if offset + self.page_size < len(rows) else None
            if self.repeated_page:
                next_token = '2'
            return {'vectors': {row['id']: row for row in page}, 'pagination': {'next': next_token}}, {}
        assert path == 'query'
        rows.sort(key=lambda row: (-sum(a * b for a, b in zip(row['values'], payload['vector'])), row['id']))
        rows = rows[: payload['topK']]
        if namespace == self.reverse_namespace:
            rows.reverse()
        indexed = 0 if namespace == self.lag_namespace else self.indexed[namespace]
        headers = {} if self.missing_query_lsn else {'x-pinecone-max-indexed-lsn': str(indexed)}
        matches = []
        for row in rows:
            match = {'id': row['id'], 'score': 0.9}
            if payload.get('includeMetadata'):
                match['metadata'] = deepcopy(row['metadata'])
            if payload.get('includeValues'):
                match['values'] = deepcopy(row['values'])
            matches.append(match)
        return {'matches': matches}, headers


def record(id, *, uid='test-owner', values=None):
    return {'id': id, 'values': values or [1.0, 0.0], 'metadata': {'uid': uid, 'memory_id': id, 'revision': 1}}


def owned(provider, namespace, uid='test-owner'):
    return {id: row for id, row in provider.records[namespace].items() if row['metadata'].get('uid') == uid}


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv('PINECONE_PARTITIONS_ENABLED', 'true')
    monkeypatch.setattr(migration, 'external_write_fence', lambda *a, **kw: nullcontext())

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
    db = StrictFirestore()
    key = state.PartitionKey('test-index', 'ns2', 'test-owner')
    provider = Provider()
    provider.records[key.family] = {
        'a': record('a'),
        'b': record('b', values=[0.0, 1.0]),
        'c': record('c', values=[0.5, 0.5]),
    }
    runner = migration.OwnerMigration(key, provider, firestore_client=db)
    return key, db, provider, runner


def commit(key, db, receipt):
    return state.cutover(key, receipt['migration_token'], receipt['revision'], receipt, firestore_client=db)


def test_full_copy_preserves_values_metadata_and_source_until_explicit_cutover(setup):
    key, db, provider, runner = setup
    before = deepcopy(provider.records[key.family])
    receipt = runner.qualify('run', dimension=2)
    assert receipt['passed'] is True
    assert receipt['records'] == 3
    assert len(receipt['query_checks']) == 3
    assert owned(provider, key.partition_namespace) == before
    assert owned(provider, key.family) == before
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family
    assert commit(key, db, receipt).primary_namespace == key.partition_namespace
    assert all('deleteAll' not in payload and 'delete_all' not in payload for _, payload in provider.calls)


@pytest.mark.parametrize('source_empty', [False, True])
def test_reconciliation_removes_obsolete_target_records_including_last_record(setup, source_empty):
    key, db, provider, runner = setup
    provider.records[key.partition_namespace] = {'obsolete': record('obsolete')}
    if source_empty:
        provider.records[key.family].clear()
    receipt = runner.qualify('run', dimension=2)
    assert 'obsolete' not in provider.records[key.partition_namespace]
    assert owned(provider, key.partition_namespace) == owned(provider, key.family)
    assert receipt['records'] == (0 if source_empty else 3)
    commit(key, db, receipt)


def test_same_bucket_other_owner_is_never_copied_deleted_or_compared(setup):
    key, db, provider, runner = setup
    colliding = next(
        candidate
        for n in range(10000)
        if (candidate := state.PartitionKey(key.index_name, key.family, f'other-{n}')).partition_namespace
        == key.partition_namespace
    )
    foreign = record('foreign', uid=colliding.uid)
    provider.records[key.family]['foreign'] = deepcopy(foreign)
    provider.records[key.partition_namespace]['foreign'] = deepcopy(foreign)
    receipt = runner.qualify('run', dimension=2)
    assert receipt['records'] == 3
    assert provider.records[key.partition_namespace]['foreign'] == foreign
    assert provider.records[key.family]['foreign'] == foreign
    for path, payload in provider.calls:
        if path in {'query', 'vectors/fetch_by_metadata'}:
            where = payload['filter']
            assert where == {'uid': {'$eq': key.uid}} or where['$and'][0] == {'uid': {'$eq': key.uid}}
        elif path == 'vectors/upsert':
            assert all(
                row['metadata'].get('uid') == key.uid or (row['id'] == BARRIER_ID and 'uid' not in row['metadata'])
                for row in payload['vectors']
            )
        else:
            assert 'foreign' not in payload['ids']
    commit(key, db, receipt)


@pytest.mark.parametrize('failure', ['values', 'order', 'foreign', 'pagination'])
def test_parity_and_identity_failures_never_authorize_cutover(setup, failure):
    key, db, provider, runner = setup
    if failure == 'values':
        provider.corrupt_namespace = key.partition_namespace
    elif failure == 'order':
        provider.reverse_namespace = key.partition_namespace
    elif failure == 'foreign':
        provider.foreign_page = True
    else:
        provider.repeated_page = True
    with pytest.raises(migration.MigrationNotReady):
        runner.qualify('run', dimension=2)
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family


def test_indexing_lag_times_out_without_false_success(setup, monkeypatch):
    key, db, provider, runner = setup
    provider.lag_namespace = key.partition_namespace
    ticks = iter(range(0, 10000, 61))
    monkeypatch.setattr(migration.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(migration.time, 'sleep', lambda value: None)
    with pytest.raises(migration.MigrationNotReady, match='freshness'):
        runner.qualify('run', dimension=2)
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family


def test_missing_query_freshness_header_never_authorizes_cutover(setup):
    key, db, provider, runner = setup
    provider.missing_query_lsn = True
    with pytest.raises(migration.MigrationNotReady, match='freshness'):
        runner.qualify('run', dimension=2)
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family


def test_source_mutation_during_copy_invalidates_generation_then_retry_reconciles(setup):
    key, db, provider, runner = setup
    changed = False

    def concurrent_change(path, payload):
        nonlocal changed
        if path == 'vectors/upsert' and not changed:
            changed = True
            ticket = state.begin_mutation(key, affected_ids=['a'], firestore_client=db)
            provider.records[key.family].pop('a')
            provider.lsns[key.family] += 1
            state.finish_mutation(key, ticket, write_lsn=provider.lsns[key.family], firestore_client=db)

    provider.before_write = concurrent_change
    with pytest.raises(migration.MigrationNotReady):
        runner.qualify('run', dimension=2)
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family
    provider.before_write = None
    receipt = runner.qualify('run', dimension=2)
    assert 'a' not in provider.records[key.partition_namespace]
    commit(key, db, receipt)


def test_source_write_after_barrier_before_first_page_is_in_quiet_window(setup, monkeypatch):
    key, db, provider, runner = setup
    original_wait = provider.await_indexed
    changed = False

    def wait_then_change(namespace, uid, vector, lsn):
        nonlocal changed
        indexed = original_wait(namespace, uid, vector, lsn)
        if namespace == key.family and not changed:
            changed = True
            ticket = state.begin_mutation(key, affected_ids=['a'], firestore_client=db)
            provider.records[key.family]['a']['metadata']['revision'] = 2
            provider.lsns[key.family] += 1
            state.finish_mutation(key, ticket, firestore_client=db)
        return indexed

    monkeypatch.setattr(provider, 'await_indexed', wait_then_change)
    with pytest.raises(migration.MigrationNotReady, match='changed'):
        runner.qualify('run', dimension=2)
    # Both copies can happen to match perfectly; the provider visibility proof
    # still predates this change, so this attempt must not authorize cutover.
    assert owned(provider, key.family) == owned(provider, key.partition_namespace)
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family


def test_later_query_replica_cannot_regress_below_verified_barrier(setup, monkeypatch):
    key, db, provider, runner = setup
    original_query = provider.query

    def stale_final_query(namespace, uid, vector, top_k=10):
        body, indexed = original_query(namespace, uid, vector, top_k)
        return body, 0 if top_k == 10 else indexed

    monkeypatch.setattr(provider, 'query', stale_final_query)
    with pytest.raises(migration.MigrationNotReady, match='replica'):
        runner.qualify('run', dimension=2)
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family


def test_resume_cannot_qualify_while_uncertain_mutation_is_unresolved(setup):
    key, db, _, runner = setup
    state.begin_migration(key, 'run', firestore_client=db)
    ticket = state.begin_mutation(key, affected_ids=['a'], firestore_client=db)
    state.mark_mutation_uncertain(key, ticket, firestore_client=db)
    with pytest.raises(migration.MigrationNotReady, match='unfinished'):
        runner.qualify('run', dimension=2)
    route = state.get_route(key, firestore_client=db)
    assert route.primary_namespace == key.family
    assert route.uncertain_count == 1


def test_missing_fresh_target_id_is_detected_even_if_count_was_previously_equal(setup, monkeypatch):
    key, db, provider, runner = setup
    original_wait = provider.await_indexed

    def wait_then_lose_record(namespace, uid, vector, lsn):
        indexed = original_wait(namespace, uid, vector, lsn)
        if namespace == key.partition_namespace:
            provider.records[namespace].pop('a')
            provider.records[namespace]['wrong'] = record('wrong')
        return indexed

    monkeypatch.setattr(provider, 'await_indexed', wait_then_lose_record)
    with pytest.raises(migration.MigrationNotReady, match='IDs'):
        runner.qualify('run', dimension=2)
    assert len(provider.records[key.family]) == len(provider.records[key.partition_namespace])
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family


@pytest.mark.parametrize('changed_field', ['values', 'metadata'])
def test_stale_fetch_with_same_ids_cannot_pass_fresh_payload_proof(setup, changed_field):
    key, db, provider, runner = setup
    provider.stale_fetch_records[key.family] = deepcopy(provider.records[key.family])
    if changed_field == 'values':
        provider.records[key.family]['a']['values'] = [0.75, 0.25]
    else:
        provider.records[key.family]['a']['metadata']['revision'] = 2
    with pytest.raises(migration.MigrationNotReady, match='Fresh vector values or metadata'):
        runner.qualify('run', dimension=2)
    # Metadata fetch and the copied target agree on IDs and old contents. Only
    # the LSN-gated query exposes the current source payload and blocks cutover.
    assert set(provider.records[key.family]) == set(provider.records[key.partition_namespace])
    assert owned(provider, key.partition_namespace) == provider.stale_fetch_records[key.family]
    assert any(path == 'query' and payload.get('includeValues') for path, payload in provider.calls)
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family


def test_stale_fetch_missing_record_cannot_pass_complete_inventory(setup):
    key, db, provider, runner = setup
    provider.stale_fetch_records[key.family] = deepcopy(provider.records[key.family])
    provider.records[key.family]['new'] = record('new', values=[0.1, 0.9])
    with pytest.raises(migration.MigrationNotReady, match='complete inventory'):
        runner.qualify('run', dimension=2)
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family


def test_inventory_at_query_cap_is_not_claimed_complete(setup, monkeypatch):
    key, _, provider, _ = setup
    monkeypatch.setattr(
        provider,
        'call',
        lambda path, payload: (
            {'matches': [{'id': str(i)} for i in range(10000)]},
            {'x-pinecone-max-indexed-lsn': '10'},
        ),
    )
    with pytest.raises(migration.MigrationNotReady, match='complete-query limit'):
        provider.fresh_inventory(key.family, key.uid, [1.0, 0.0], 10)


def test_inventory_duplicate_ids_are_not_claimed_complete(setup, monkeypatch):
    key, _, provider, _ = setup
    monkeypatch.setattr(
        provider,
        'call',
        lambda path, payload: ({'matches': [{'id': 'a'}, {'id': 'a'}]}, {'x-pinecone-max-indexed-lsn': '10'}),
    )
    with pytest.raises(migration.MigrationNotReady, match='repeated an ID'):
        provider.fresh_inventory(key.family, key.uid, [1.0, 0.0], 10)


def identity_groups(records, fields=('memory_id',)):
    groups = {}
    for row in records.values():
        selector = json.dumps({field: {'$eq': row['metadata'][field]} for field in fields}, sort_keys=True)
        groups.setdefault(selector, {})[row['id']] = migration.record_digest(row)
    return groups


def test_large_owner_qualifies_complete_inventory_and_every_payload_group(setup):
    key, db, provider, runner = setup
    provider.page_size = 100
    provider.records[key.family] = {f'{i:05d}': record(f'{i:05d}') for i in range(10001)}
    receipt = runner.qualify('large', dimension=2)
    assert receipt['records'] == 10001
    assert owned(provider, key.family) == owned(provider, key.partition_namespace)
    for namespace in (key.family, key.partition_namespace):
        proofs = [
            payload
            for path, payload in provider.calls
            if path == 'query' and payload['namespace'] == namespace and payload.get('includeValues')
        ]
        assert len(proofs) == 334
        identities = {
            selector['memory_id']['$eq'] for payload in proofs for selector in payload['filter']['$and'][1]['$or']
        }
        assert identities == set(owned(provider, namespace))
        exclusions = [
            payload
            for path, payload in provider.calls
            if path == 'query'
            and payload['namespace'] == namespace
            and '$and' in payload['filter']
            and any('$nin' in clause.get('memory_id', {}) for clause in payload['filter']['$and'])
        ]
        assert len(exclusions) == 1
        lengths = [
            len(clause['memory_id']['$nin'])
            for clause in exclusions[0]['filter']['$and']
            if '$nin' in clause.get('memory_id', {})
        ]
        assert lengths == [10000, 1]
    commit(key, db, receipt)


def wide_record(id):
    row = record(id, values=[0.1234567890123456] * 3072)
    row['metadata']['context'] = '日本語"\\\n' * 1000
    return row


def test_wide_page_splits_by_complete_serialized_payload_without_losing_records():
    records = [wide_record(str(i)) for i in range(100)]
    before = deepcopy(records)
    namespace = 'ns2-p1-00'
    assert len(json.dumps({'namespace': namespace, 'vectors': records}).encode()) > 1_800_000
    batches = list(migration.bounded_upsert_batches(records, namespace))
    assert len(batches) > 1
    assert [row for batch in batches for row in batch] == before
    assert records == before
    assert all(len(json.dumps({'namespace': namespace, 'vectors': batch}).encode()) <= 1_800_000 for batch in batches)
    assert all(0 < len(batch) <= 1000 for batch in batches)


def test_upsert_batch_record_limit_applies_even_when_bytes_are_small():
    rows = [record(str(i)) for i in range(1001)]
    namespace = 'ns2-p1-00'
    assert len(json.dumps({'namespace': namespace, 'vectors': rows}).encode()) < 1_800_000
    batches = list(migration.bounded_upsert_batches(rows, namespace))
    assert [len(batch) for batch in batches] == [1000, 1]
    assert [row['id'] for batch in batches for row in batch] == [row['id'] for row in rows]
    assert list(migration.bounded_upsert_batches([], namespace)) == []


def test_one_oversize_record_is_rejected_before_customer_write_admission(setup):
    key, db, provider, runner = setup
    row = record('oversize')
    row['metadata']['context'] = 'x' * 1_800_000
    provider.records[key.family] = {'oversize': row}
    with pytest.raises(migration.MigrationNotReady):
        runner.qualify('oversize', dimension=2)
    route = state.get_route(key, firestore_client=db)
    assert route.pending_count == route.uncertain_count == 0
    assert route.primary_namespace == key.family
    customer_upserts = [
        payload
        for path, payload in provider.calls
        if path == 'vectors/upsert' and any('uid' in item['metadata'] for item in payload['vectors'])
    ]
    assert customer_upserts == []
    assert owned(provider, key.partition_namespace) == {}


def test_qualify_counts_every_split_upsert_in_generation_and_can_commit(setup):
    key, db, provider, runner = setup
    provider.page_size = 100
    provider.records[key.family] = {str(i): wide_record(str(i)) for i in range(40)}
    receipt = runner.qualify('split-page', dimension=3072)
    copies = [
        payload
        for path, payload in provider.calls
        if path == 'vectors/upsert'
        and payload['namespace'] == key.partition_namespace
        and any('uid' in row['metadata'] for row in payload['vectors'])
    ]
    assert len(copies) > 1
    assert all(len(json.dumps(payload).encode()) <= 1_800_000 for payload in copies)
    assert sorted(row['id'] for payload in copies for row in payload['vectors']) == sorted(owned(provider, key.family))
    assert receipt['revision'] == 1 + 2 * (len(copies) + 2)
    assert receipt['records'] == 40
    assert owned(provider, key.partition_namespace) == owned(provider, key.family)
    assert commit(key, db, receipt).primary_namespace == key.partition_namespace


@pytest.mark.parametrize('missing_field', [False, True])
def test_large_inventory_rejects_unknown_identity_and_missing_metadata(setup, missing_field):
    key, _, provider, _ = setup
    provider.records[key.family] = {str(i): record(str(i)) for i in range(10000)}
    groups = identity_groups(provider.records[key.family])
    extra = record('outside-snapshot')
    if missing_field:
        del extra['metadata']['memory_id']
    provider.records[key.family]['outside-snapshot'] = extra
    with pytest.raises(migration.MigrationNotReady, match='unknown identity'):
        provider.fresh_inventory(key.family, key.uid, [1.0, 0.0], 0, groups)


def test_large_compound_inventory_rejects_unknown_combination_of_known_values(setup):
    key, _, provider, _ = setup
    provider.records[key.family] = {str(i): record(str(i)) for i in range(10000)}
    for i, row in enumerate(provider.records[key.family].values()):
        row['metadata'].update(conversation_id=f'conversation-{i}', chunk_index=i % 2)
    groups = identity_groups(provider.records[key.family], ('conversation_id', 'chunk_index'))
    extra = record('unknown-combination')
    # Both values exist individually, but conversation-0 only owns chunk 0.
    extra['metadata'].update(conversation_id='conversation-0', chunk_index=1)
    provider.records[key.family]['unknown-combination'] = extra
    with pytest.raises(migration.MigrationNotReady, match='unknown identity'):
        provider.fresh_inventory(key.family, key.uid, [1.0, 0.0], 0, groups)


def test_large_known_identity_with_unexpected_extra_vector_is_rejected_by_payload_proof(setup):
    key, _, provider, _ = setup
    provider.records[key.family] = {str(i): record(str(i)) for i in range(10000)}
    groups = identity_groups(provider.records[key.family])
    expected_ids = set(provider.records[key.family])
    extra = record('unknown-alias')
    extra['metadata']['memory_id'] = '0'
    provider.records[key.family]['unknown-alias'] = extra
    # Identity-complement queries alone cannot establish the vector-ID set.
    assert provider.fresh_inventory(key.family, key.uid, [1.0, 0.0], 0, groups) == expected_ids
    with pytest.raises(migration.MigrationNotReady, match='Fresh vector values or metadata'):
        provider.verify_payloads(key.family, key.uid, [1.0, 0.0], 0, groups)


def test_large_complement_query_requires_fresh_replica(setup, monkeypatch):
    key, _, provider, _ = setup
    provider.records[key.family] = {str(i): record(str(i)) for i in range(10000)}
    provider.indexed[key.family] = 12
    groups = identity_groups(provider.records[key.family])
    original_call = provider.call

    def stale_complement(path, payload):
        body, headers = original_call(path, payload)
        if '$and' in payload.get('filter', {}):
            headers['x-pinecone-max-indexed-lsn'] = '11'
        return body, headers

    monkeypatch.setattr(provider, 'call', stale_complement)
    with pytest.raises(migration.MigrationNotReady, match='replica is stale'):
        provider.fresh_inventory(key.family, key.uid, [1.0, 0.0], 12, groups)


def test_identity_filter_is_required_before_claiming_payload_parity(setup):
    key, db, provider, runner = setup
    del provider.records[key.family]['a']['metadata']['memory_id']
    with pytest.raises(migration.MigrationNotReady, match='identity filter'):
        runner.qualify('run', dimension=2)
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family


def test_payload_queries_are_bounded_and_cover_every_record(setup):
    key, db, provider, runner = setup
    provider.records[key.family] = {str(i): record(str(i)) for i in range(65)}
    receipt = runner.qualify('run', dimension=2)
    payload_proofs = [payload for path, payload in provider.calls if path == 'query' and payload.get('includeValues')]
    assert len(payload_proofs) == 6
    assert all(payload['topK'] <= 31 for payload in payload_proofs)
    for namespace in (key.family, key.partition_namespace):
        selectors = [
            selector
            for payload in payload_proofs
            if payload['namespace'] == namespace
            for selector in payload['filter']['$and'][1]['$or']
        ]
        assert {selector['memory_id']['$eq'] for selector in selectors} == set(owned(provider, key.family))
    commit(key, db, receipt)


def test_too_many_aliases_for_one_identity_fail_payload_proof(setup):
    key, db, provider, runner = setup
    provider.records[key.family] = {str(i): record(str(i)) for i in range(31)}
    for row in provider.records[key.family].values():
        row['metadata']['memory_id'] = 'shared-source'
    with pytest.raises(migration.MigrationNotReady, match='identities share'):
        runner.qualify('run', dimension=2)
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family


def test_record_digest_ignores_scores_and_normalizes_equivalent_numeric_encoding():
    integer = {'id': 'a', 'values': [1, 0], 'metadata': {'uid': 'owner', 'revision': 1}}
    floating = {'id': 'a', 'values': [1.0, 0.0], 'metadata': {'uid': 'owner', 'revision': 1.0}, 'score': 0.97}
    assert migration.record_digest(integer) == migration.record_digest(floating)
    floating['metadata']['revision'] = 2.0
    assert migration.record_digest(integer) != migration.record_digest(floating)


def test_sparse_values_are_not_silently_discarded_by_digest():
    value = {**record('a'), 'sparseValues': {'indices': [1], 'values': [0.5]}}
    with pytest.raises(migration.MigrationNotReady, match='Sparse'):
        migration.record_digest(value)


def test_noop_delete_lsn_is_not_a_freshness_barrier_but_real_internal_upsert_is(setup):
    key, _, provider, _ = setup
    namespace = key.partition_namespace
    delete_lsn = provider.write('vectors/delete', namespace, ids=['absent-id'])
    _, indexed = provider.query(namespace, key.uid, [1.0, 0.0])
    assert indexed < delete_lsn
    barrier_lsn = provider.write('vectors/upsert', namespace, vectors=[barrier_record(2)])
    assert provider.await_indexed(namespace, key.uid, [1.0, 0.0], barrier_lsn) >= barrier_lsn
    assert provider.fresh_inventory(namespace, key.uid, [1.0, 0.0], barrier_lsn) == set()
    assert list(provider.owned_pages(namespace, key.uid)) == [[]]


def test_internal_barriers_have_fresh_nonce_and_never_enter_owner_results(setup):
    key, _, provider, runner = setup
    receipt = runner.qualify('run', dimension=2)
    source_marker = provider.records[key.family][BARRIER_ID]
    target_marker = provider.records[key.partition_namespace][BARRIER_ID]
    assert 'uid' not in source_marker['metadata']
    assert 'uid' not in target_marker['metadata']
    assert source_marker['metadata']['nonce'] != target_marker['metadata']['nonce']
    assert receipt['records'] == 3
    for namespace in (key.family, key.partition_namespace):
        results, _ = provider.query(namespace, key.uid, [1.0, 0.0])
        assert BARRIER_ID not in {row['id'] for row in results['matches']}
        assert all(row['id'] != BARRIER_ID for page in provider.owned_pages(namespace, key.uid) for row in page)


@pytest.mark.parametrize('which', ['source', 'target'])
def test_internal_barrier_failure_is_retryable_without_customer_uncertainty(setup, which):
    key, db, provider, runner = setup
    failing_namespace = key.family if which == 'source' else key.partition_namespace

    def fail_internal_barrier(path, payload):
        if (
            path == 'vectors/upsert'
            and payload['namespace'] == failing_namespace
            and [row['id'] for row in payload['vectors']] == [BARRIER_ID]
        ):
            raise TimeoutError('internal-only barrier outcome unknown')

    provider.before_write = fail_internal_barrier
    with pytest.raises(TimeoutError):
        runner.qualify('run', dimension=2)
    route = state.get_route(key, firestore_client=db)
    assert route.pending_count == route.uncertain_count == 0
    assert route.primary_namespace == key.family
    provider.before_write = None
    commit(key, db, runner.qualify('run', dimension=2))


def test_http_exact_missing_namespace_is_only_a_delete_or_initial_inventory_noop():
    def missing(request):
        return httpx.Response(404, json={'code': 5, 'message': 'Namespace not found'})

    with httpx.Client(transport=httpx.MockTransport(missing)) as client:
        transport = migration.PartitionTransport('test.pinecone.io', 'test-only-key', client=client)
        assert transport.write('vectors/delete', 'missing', ids=['id']) == 0
        assert list(transport.owned_pages('missing', 'owner')) == [[]]
        with pytest.raises(httpx.HTTPStatusError):
            transport.write('vectors/upsert', 'missing', vectors=[record('id')])


@pytest.mark.parametrize(
    'status,message', [(403, 'Namespace not found'), (500, 'Namespace not found'), (404, 'Index not found')]
)
def test_http_other_failures_never_become_successful_delete(status, message):
    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(status, json={'code': 5, 'message': message}))
    ) as client:
        transport = migration.PartitionTransport('test.pinecone.io', 'test-only-key', client=client)
        with pytest.raises(httpx.HTTPStatusError):
            transport.write('vectors/delete', 'missing', ids=['id'])


def test_namespace_disappearing_after_first_inventory_page_is_not_complete_inventory():
    def disappearing(request):
        payload = json.loads(request.content)
        if 'paginationToken' not in payload:
            return httpx.Response(200, json={'vectors': {'a': record('a')}, 'pagination': {'next': 'more'}})
        return httpx.Response(404, json={'code': 5, 'message': 'Namespace not found'})

    with httpx.Client(transport=httpx.MockTransport(disappearing)) as client:
        transport = migration.PartitionTransport('test.pinecone.io', 'test-only-key', client=client)
        with pytest.raises(httpx.HTTPStatusError):
            list(transport.owned_pages('namespace', 'test-owner'))


def test_same_token_can_retry_failed_parity_without_exposing_partial_copy(setup):
    key, db, provider, runner = setup
    provider.corrupt_namespace = key.partition_namespace
    with pytest.raises(migration.MigrationNotReady):
        runner.qualify('run', dimension=2)
    provider.corrupt_namespace = None
    receipt = runner.qualify('run', dimension=2)
    assert owned(provider, key.family) == owned(provider, key.partition_namespace)
    commit(key, db, receipt)


def test_mutation_after_qualification_invalidates_receipt_at_atomic_cutover(setup):
    key, db, _, runner = setup
    receipt = runner.qualify('run', dimension=2)
    ticket = state.begin_mutation(key, affected_ids=['a'], firestore_client=db)
    state.finish_mutation(key, ticket, write_lsn=100, firestore_client=db)
    with pytest.raises(state.PartitionConflict):
        commit(key, db, receipt)
    assert state.get_route(key, firestore_client=db).primary_namespace == key.family


def test_pending_copy_blocks_account_purge_and_cancellation(setup):
    key, db, provider, runner = setup
    scoped = adapter.owner_index(None, key.uid, index_name=key.index_name, firestore_client=db)
    checks = []

    def while_copying(path, payload):
        if path == 'vectors/upsert':
            checks.append(True)
            assert state.get_route(key, firestore_client=db).pending_count == 1
            with pytest.raises(state.PartitionBusy):
                state.cancel_migration(key, 'run', firestore_client=db)
            with pytest.raises(state.PartitionBusy):
                scoped.verify_empty_all_copies(namespace=key.family, filter={'uid': key.uid})

    provider.before_write = while_copying
    runner.qualify('run', dimension=2)
    assert checks


def test_copy_timeout_keeps_unknown_outcome_blocking_cutover(setup):
    key, db, provider, runner = setup
    provider.fail_namespace = key.partition_namespace
    with pytest.raises(TimeoutError):
        runner.qualify('run', dimension=2)
    route = state.get_route(key, firestore_client=db)
    assert route.primary_namespace == key.family
    assert route.pending_count + route.uncertain_count > 0


def test_rollback_reconciles_from_current_primary_instead_of_restoring_stale_copy(setup):
    key, db, provider, runner = setup
    commit(key, db, runner.qualify('forward', dimension=2))
    ticket = state.begin_mutation(key, full_owner=True, firestore_client=db)
    provider.records[key.partition_namespace].pop('a')
    provider.records[key.partition_namespace]['new'] = record('new', values=[0.25, 0.75])
    provider.lsns[key.partition_namespace] += 1
    state.finish_mutation(key, ticket, write_lsn=provider.lsns[key.partition_namespace], firestore_client=db)
    receipt = runner.qualify('rollback', dimension=2, rollback=True)
    assert owned(provider, key.family) == owned(provider, key.partition_namespace)
    assert 'a' not in provider.records[key.family]
    assert 'new' in provider.records[key.family]
    assert state.get_route(key, firestore_client=db).primary_namespace == key.partition_namespace
    assert commit(key, db, receipt).primary_namespace == key.family
