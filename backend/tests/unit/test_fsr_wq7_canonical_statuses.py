"""WQ7: billed missing-pair reads and suppression parity on all four callers."""

import json
from math import ceil
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from config import firestore_read_levers as levers
from tests.unit.test_memory_service_parity import _load_memory_service, _sample_memory_dict
from utils.other.list_budget import ListReadBudget, ListReadBudgetExhausted

UID = 'uid-test'
LEVER = 'canonical_statuses_dedupe'


class CountingStore:
    """Model billed documents, including one read for an empty query.

    This is deliberately not an RPC counter: get_all bills every requested
    missing document; an IN query bills returned documents, with a floor of one.
    """

    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.reads = 0
        self.get_all_calls = []
        self.queries = []
        self.query_kwargs = []
        self.fail_collection = None
        self.extra_snapshot = None

    def document(self, path):
        return SimpleNamespace(path=path)

    def snapshot(self, path):
        return SimpleNamespace(
            reference=self.document(path),
            exists=path in self.docs,
            to_dict=lambda: self.docs.get(path),
        )

    def get_all(self, refs, **kwargs):
        paths = [ref.path for ref in refs]
        self.get_all_calls.append(paths)
        self.reads += len(paths)
        return [self.snapshot(path) for path in reversed(paths)]

    def collection(self, path):
        store = self

        class Query:
            def where(self, *, filter):
                assert filter.field_path == '__name__'
                assert filter.op_string == 'in'
                self.paths = [ref.path for ref in filter.value]
                assert 1 <= len(self.paths) <= 30
                assert all(p.rsplit('/', 1)[0] == path for p in self.paths)
                return self

            def stream(self, **kwargs):
                store.queries.append((path, self.paths))
                store.query_kwargs.append(kwargs)
                if store.fail_collection == path:
                    raise RuntimeError('unavailable')
                found = [store.snapshot(p) for p in reversed(self.paths) if p in store.docs]
                store.reads += max(1, len(found))
                if store.extra_snapshot is not None:
                    found.append(store.extra_snapshot)
                return iter(found)

        return Query()


@pytest.fixture
def service_mod(monkeypatch):
    monkeypatch.setenv('MEMORY_ENABLED', 'on')
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    module = _load_memory_service(monkeypatch)
    from utils.memory import read_resilience

    monkeypatch.setenv('OMI_MEMORY_READ_RETRY_BURST', '64')
    monkeypatch.setattr(read_resilience, '_retry_allowance', read_resilience.RetryAllowance())
    return module


def enable(monkeypatch, on):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', json.dumps({LEVER: 100 if on else 0}))


def budget(*, max_documents=1000, clock=lambda: 0):
    return ListReadBudget(deadline_monotonic=24, max_documents=max_documents, clock=clock)


@pytest.mark.parametrize('count', [2, 30, 31, 100, 501])
def test_missing_pair_billed_reads_off_vs_on(service_mod, monkeypatch, count):
    ids = [f'm-{i}' for i in range(count)]
    off, on = CountingStore(), CountingStore()
    enable(monkeypatch, False)
    assert service_mod.MemoryService(db_client=off).canonical_statuses(UID, ids) == {}
    enable(monkeypatch, True)
    assert service_mod.MemoryService(db_client=on).canonical_statuses(UID, ids) == {}
    assert off.reads == 2 * count
    assert on.reads == 2 * ceil(count / 30)
    assert on.reads <= count
    assert not off.queries
    assert not on.get_all_calls


def test_unset_lever_preserves_exact_batch_lookup_path(service_mod):
    store = CountingStore({'users/uid-test/memory_items/a': {'status': 'active'}})
    service = service_mod.MemoryService(db_client=store)
    assert service.canonical_statuses(UID, ['a', '', 'a', 'b']) == {'a': service_mod.MemoryItemStatus.active}
    assert store.get_all_calls == [
        ['users/uid-test/memory_items/a', 'users/uid-test/memory_items/b'],
        ['users/uid-test/memory_historical_overrides/b'],
    ]
    assert store.reads == 3
    assert not store.queries


def test_singleton_still_checks_both_independent_authorities(service_mod, monkeypatch):
    enable(monkeypatch, True)
    store = CountingStore()
    service = service_mod.MemoryService(db_client=store)
    assert service.canonical_statuses(UID, ['', 'a', 'a']) == {}
    assert store.reads == 2  # No claim of a one-read guarantee for isolated IDs.
    assert service.canonical_statuses(UID, ['', '']) == {}
    assert store.reads == 2


def suppression_docs():
    docs = {}
    for status in ('active', 'hidden', 'tombstoned', 'superseded'):
        docs[f'users/{UID}/memory_items/item-{status}'] = {'status': status}
        docs[f'users/{UID}/memory_historical_overrides/item-{status}'] = {'status': 'hidden'}
        docs[f'users/{UID}/memory_historical_overrides/override-{status}'] = {'suppression': status}
    # A body ID is not identity, and another owner's matching ID is not authority.
    docs[f'users/{UID}/memory_items/item-active']['memory_id'] = 'visible-a'
    docs['users/another-user/memory_items/visible-a'] = {'status': 'tombstoned'}
    return docs


def records(module):
    ids = [
        f'{source}-{status}'
        for source in ('item', 'override')
        for status in ('active', 'hidden', 'tombstoned', 'superseded')
    ]
    return [
        module.HistoricalMemoryRecord(
            memory=module.MemoryDB.model_validate(_sample_memory_dict(memory_id)),
            locator=module.MemoryLocator(UID, 'legacy', memory_id),
        )
        for memory_id in [*ids, 'visible-a', 'visible-b']
    ]


def consume(module, service, rows, caller):
    if caller == 'list':
        service._canonical.read = MagicMock(return_value=[])
        service.history.read = MagicMock(return_value=rows)
        return [memory.id for memory in service.read(UID, limit=100)]
    if caller == 'search':
        service._canonical.search = MagicMock(return_value=[])
        service.history.search = MagicMock(
            return_value=[module.MemorySearchMatch(memory=row.memory, score=1) for row in rows]
        )
        return [match.memory.id for match in service.search(UID, 'hiking', limit=20)]
    if caller == 'export':
        service.history.iter_all_live = MagicMock(return_value=iter(rows))
        return [
            memory.id
            for memory in service._iter_export_memories(
                UID, include_archive=True, page_size=100, include_ledger_history=True
            )
        ]
    assert caller == 'cursor'
    service.history.read_updated_scan_page = MagicMock(
        return_value=([(row, (row.memory.updated_at, row.memory.id)) for row in rows], True)
    )
    stream = module._HistoricalRawStream(
        service=service,
        uid=UID,
        kind='updated',
        scan=None,
        exhausted=False,
        device_scope_request=None,
        page_limit=100,
    )
    visible = []
    while (memory := stream.peek()) is not None:
        visible.append(memory.id)
        stream.consume()
    return visible


@pytest.mark.parametrize('caller', ['list', 'search', 'export', 'cursor'])
def test_every_caller_preserves_visible_decisions(service_mod, monkeypatch, caller):
    monkeypatch.setattr(service_mod, 'iter_authoritative_product_memory_items', lambda **kwargs: iter(()))
    rows = records(service_mod)
    observed = []
    billed_reads = []
    for on in (False, True):
        enable(monkeypatch, on)
        store = CountingStore(suppression_docs())
        service = service_mod.MemoryService(db_client=store)
        observed.append(consume(service_mod, service, rows, caller))
        billed_reads.append(store.reads)
        if on:
            # Present items are authoritative: their overrides are never queried.
            assert all(
                '/item-' not in path
                for collection, paths in store.queries
                if collection.endswith('overrides')
                for path in paths
            )
    assert observed == [['visible-a', 'visible-b'], ['visible-a', 'visible-b']]
    assert billed_reads == [16, 8]


@pytest.mark.parametrize('collection', ['memory_items', 'memory_historical_overrides'])
@pytest.mark.parametrize('on', [False, True])
def test_malformed_present_authority_remains_503(service_mod, monkeypatch, collection, on):
    enable(monkeypatch, on)
    docs = {f'users/{UID}/{collection}/bad': {'status': 'invalid'}}
    if collection == 'memory_items':
        docs[f'users/{UID}/memory_historical_overrides/bad'] = {'status': 'tombstoned'}
    store = CountingStore(docs)
    with pytest.raises(service_mod.HTTPException) as error:
        service_mod.MemoryService(db_client=store).canonical_statuses(UID, ['bad', 'absent'])
    assert error.value.status_code == 503
    if collection == 'memory_items':
        assert len(store.queries if on else store.get_all_calls) == 1


def test_no_negative_state_survives_call_or_crosses_uid(service_mod, monkeypatch):
    enable(monkeypatch, True)
    store = CountingStore()
    service = service_mod.MemoryService(db_client=store)
    assert service.canonical_statuses(UID, ['a', 'b']) == {}
    store.docs[f'users/{UID}/memory_historical_overrides/a'] = {'status': 'tombstoned'}
    assert service.canonical_statuses(UID, ['a', 'b']) == {'a': service_mod.MemoryItemStatus.tombstoned}
    store.docs[f'users/{UID}/memory_items/a'] = {'status': 'active'}
    assert service.canonical_statuses(UID, ['a', 'b']) == {'a': service_mod.MemoryItemStatus.active}
    assert service.canonical_statuses('other', ['a', 'b']) == {}
    del store.docs[f'users/{UID}/memory_items/a']
    del store.docs[f'users/{UID}/memory_historical_overrides/a']
    assert service.canonical_statuses(UID, ['a', 'b']) == {}


@pytest.mark.parametrize('collection', ['memory_items', 'memory_historical_overrides'])
def test_query_failure_never_admits_historical(service_mod, monkeypatch, collection):
    enable(monkeypatch, True)
    store = CountingStore()
    store.fail_collection = f'users/{UID}/{collection}'
    with pytest.raises(service_mod.HTTPException) as error:
        service_mod.MemoryService(db_client=store).canonical_statuses(UID, ['a', 'b'])
    assert error.value.status_code == 503


def test_unmappable_query_result_never_admits_historical(service_mod, monkeypatch):
    enable(monkeypatch, True)
    store = CountingStore()
    store.extra_snapshot = store.snapshot('users/other/memory_items/a')
    with pytest.raises(service_mod.HTTPException) as error:
        service_mod.MemoryService(db_client=store).canonical_statuses(UID, ['a', 'b'])
    assert error.value.status_code == 503


def test_query_budget_accounts_for_hits_and_empty_floors(service_mod, monkeypatch):
    enable(monkeypatch, True)
    store = CountingStore({f'users/{UID}/memory_items/a': {'status': 'active'}})
    request_budget = budget()
    assert service_mod.MemoryService(db_client=store).canonical_statuses(UID, ['a', 'b'], budget=request_budget) == {
        'a': service_mod.MemoryItemStatus.active,
    }
    assert request_budget.docs_scanned == store.reads == 2
    assert all(0 < kwargs['timeout'] <= 24 and kwargs['retry'] is not None for kwargs in store.query_kwargs)


def test_query_document_budget_exhaustion_propagates(service_mod, monkeypatch):
    enable(monkeypatch, True)
    store = CountingStore()
    with pytest.raises(ListReadBudgetExhausted) as error:
        service_mod.MemoryService(db_client=store).canonical_statuses(UID, ['a', 'b'], budget=budget(max_documents=0))
    assert error.value.reason == 'documents'
    assert len(store.queries) == 1


def test_query_expired_budget_starts_no_rpc(service_mod, monkeypatch):
    enable(monkeypatch, True)
    store = CountingStore()
    with pytest.raises(ListReadBudgetExhausted) as error:
        service_mod.MemoryService(db_client=store).canonical_statuses(UID, ['a', 'b'], budget=budget(clock=lambda: 25))
    assert error.value.reason == 'deadline'
    assert not store.queries


def test_real_sdk_builds_owner_scoped_name_in_queries(service_mod, monkeypatch):
    from google.auth.credentials import AnonymousCredentials
    from google.cloud.firestore_v1 import Client, Query

    enable(monkeypatch, True)
    client = Client(project='wq7-hermetic', credentials=AnonymousCredentials())
    queries = []

    def empty_stream(query):
        queries.append(('/'.join(query._parent._path), query._to_protobuf()))
        return iter(())

    monkeypatch.setattr(Query, 'stream', empty_stream)
    ids = [f'm-{i}' for i in range(31)]
    assert service_mod.MemoryService(db_client=client).canonical_statuses(UID, ids) == {}
    assert len(queries) == 4
    for collection, query in queries:
        assert collection.startswith(f'users/{UID}/')
        assert len(query.from_) == 1
        clause = query.where.field_filter
        assert clause.field.field_path == '__name__'
        assert clause.op == 8  # StructuredQuery.FieldFilter.Operator.IN
        values = clause.value.array_value.values
        assert 1 <= len(values) <= 30
        assert {value.reference_value for value in values} <= {
            f'projects/wq7-hermetic/databases/(default)/documents/{collection}/{memory_id}' for memory_id in ids
        }


def test_new_lever_registered_and_default_off(service_mod):
    assert LEVER in levers.KNOWN_LEVERS
    assert not levers.lever_enabled(LEVER, UID)
