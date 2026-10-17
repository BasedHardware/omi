"""Read-count and snapshot proof for the capped sequencer telemetry query.

The query semantics here are also checked against the local Firestore emulator
in the S6 report. No production document/query/count call is used.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import threading

import pytest

from database import sync_backfill_sequencer as registry
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreTransaction

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)


class ReadOnlyTransaction(StrictFirestoreTransaction):
    def __init__(self, store):
        super().__init__(store)
        self._read_only = True

    def _begin(self, retry_id=None):
        super()._begin(retry_id)
        self.snapshot = deepcopy(self._database.rows)

    def _commit(self):
        assert not self.has_written
        super()._commit()


class Query:
    def __init__(self, store, uid=None, maximum=None, ordered=False):
        self.store, self.uid, self.maximum, self.ordered = store, uid, maximum, ordered

    def where(self, field, op, uid):
        assert (field, op) == ('uid', '==')
        return Query(self.store, uid, self.maximum, self.ordered)

    def order_by(self, field):
        assert field == 'accepted_at'
        return Query(self.store, self.uid, self.maximum, True)

    def limit(self, maximum):
        return Query(self.store, self.uid, maximum, self.ordered)

    def _rows(self, transaction):
        if transaction is not None:
            transaction._assert_read_allowed()
            assert transaction._read_only and transaction._id is not None
        data = transaction.snapshot if transaction is not None else self.store.rows
        rows = [(key, row) for key, row in data.items() if row.get('uid') == self.uid]
        assert self.ordered
        rows = [(key, row) for key, row in rows if 'accepted_at' in row]
        rows.sort(key=lambda pair: (pair[1]['accepted_at'], pair[0]))
        return rows[: self.maximum]

    def stream(self, transaction=None):
        rows = self._rows(transaction)
        self.store.reads += max(1, len(rows))
        if self.store.after_head:
            self.store.after_head(self.store)
        return [SimpleNamespace(id=key, exists=True, to_dict=lambda row=row: deepcopy(row)) for key, row in rows]

    def count(self):
        query = self

        class Count:
            def get(self, transaction=None):
                assert transaction is not None  # no independent head/count race
                rows = query._rows(transaction)
                query.store.reads += max(1, (len(rows) + 999) // 1000)
                query.store.counts += 1
                return [[SimpleNamespace(value=len(rows))]]

        return Count()


class Store:
    def __init__(self, size):
        self.rows = {f'job-{i:03}': {'uid': 'u', 'accepted_at': NOW - timedelta(seconds=1000 - i)} for i in range(size)}
        self.rows['missing-order-field'] = {'uid': 'u'}
        self.rows['other-uid'] = {'uid': 'v', 'accepted_at': NOW - timedelta(days=1)}
        self.lock = threading.RLock()
        self.reads = self.counts = self.transactions = 0
        self.after_head = None

    def collection(self, name):
        assert name == registry.PENDING_COLLECTION
        return Query(self)

    def transaction(self, *, read_only):
        assert read_only is True
        self.transactions += 1
        return ReadOnlyTransaction(self)


@pytest.fixture(autouse=True)
def production(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')


@pytest.mark.parametrize('size', [0, 1, 2, 3, 4, 99, 100, 120, 2000])
def test_read_count_and_byte_equal_sample(monkeypatch, size):
    samples, reads = [], []
    for enabled in (False, True):
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"backfill_task_reads":100}' if enabled else '')
        store = Store(size)
        before = deepcopy(store.rows)
        samples.append(registry.waiting_sample('u', firestore_client=store, now=NOW))
        reads.append(store.reads)
        assert store.rows == before
        assert store.transactions == int(enabled)
    assert samples[0] == samples[1]
    assert samples[1] == {
        'depth': min(100, size),
        'age_seconds': 1000.0 if size else 0.0,
        'job_id': 'job-000' if size else '',
    }
    assert reads == [max(1, min(100, size)), 3 if size >= 2 else 1]


def test_ten_full_queue_samples_remove_970_document_reads(monkeypatch):
    reads = []
    for enabled in (False, True):
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"backfill_task_reads":100}' if enabled else '')
        store = Store(150)
        for _ in range(10):
            assert registry.waiting_sample('u', firestore_client=store, now=NOW)['depth'] == 100
        reads.append(store.reads)
    assert reads == [1000, 30]


def test_count_and_head_share_snapshot_during_pending_mutation(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"backfill_task_reads":100}')
    store = Store(80)
    store.after_head = lambda store: store.rows.clear()
    sample = registry.waiting_sample('u', firestore_client=store, now=NOW)
    assert sample == {'depth': 80, 'age_seconds': 1000.0, 'job_id': 'job-000'}
    assert store.rows == {}


def test_rollback_does_not_construct_transaction_or_aggregation(monkeypatch):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    store = Store(80)
    store.transaction = lambda **kw: pytest.fail('new read-only transaction on flag-off path')
    registry.waiting_sample('u', firestore_client=store, now=NOW)
    assert store.counts == 0 and store.reads == 80


def test_sample_is_uid_keyed(monkeypatch):
    seen = []
    monkeypatch.setattr(registry, 'lever_enabled', lambda name, uid: seen.append((name, uid)) or False)
    registry.waiting_sample('u', firestore_client=Store(2), now=NOW)
    assert seen == [('backfill_task_reads', 'u')]


def test_nonprod_refuses_before_client_or_transaction(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"backfill_task_reads":100}')
    store = Store(2)
    with pytest.raises(RuntimeError, match='production-only'):
        registry.waiting_sample('u', firestore_client=store, now=NOW)
    assert store.transactions == 0 and store.reads == 0


def test_read_error_propagates_without_fabricating_empty_queue(monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"backfill_task_reads":100}')
    store = Store(2)
    store.collection = lambda *a: (_ for _ in ()).throw(RuntimeError('read unavailable'))
    with pytest.raises(RuntimeError, match='read unavailable'):
        registry.waiting_sample('u', firestore_client=store, now=NOW)


@pytest.mark.integration
def test_local_emulator_sdk_queries_and_read_only_transaction(monkeypatch):
    """Run explicitly with a local emulator; never select a remote project."""
    import os
    import uuid
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import firestore

    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host:
        pytest.skip('requires a local Firestore emulator')
    assert host.startswith('127.0.0.1:') or host.startswith('localhost:')
    client = firestore.Client(project='demo-fsr-s6', credentials=AnonymousCredentials())
    prefix = 's6-' + uuid.uuid4().hex
    sizes = [0, 1, 2, 100, 120]
    batch = client.batch()
    for size in sizes:
        uid = f'{prefix}-{size}'
        for i in range(size):
            batch.set(
                client.collection(registry.PENDING_COLLECTION).document(f'{uid}-{i:03}'),
                {'uid': uid, 'accepted_at': NOW - timedelta(seconds=1000 - i)},
            )
        batch.set(client.collection(registry.PENDING_COLLECTION).document(f'{uid}-missing'), {'uid': uid})
    batch.commit()
    api = client._firestore_api
    query_reads, aggregation_reads, read_only_begins = [], [], []
    run_query, run_count, begin, commit = api.run_query, api.run_aggregation_query, api.begin_transaction, api.commit

    def counted_query(*args, **kwargs):
        rows = list(run_query(*args, **kwargs))
        query_reads.append(max(1, sum(bool(row.document.name) for row in rows)))
        return iter(rows)

    def counted_count(*args, **kwargs):
        rows = list(run_count(*args, **kwargs))
        aggregation_reads.append(1)  # capped 100-index-entry COUNT, including the minimum charge
        return iter(rows)

    def read_only_begin(*args, **kwargs):
        request = kwargs['request']
        options = request['options']
        assert options._pb.WhichOneof('mode') == 'read_only'
        read_only_begins.append(True)
        return begin(*args, **kwargs)

    def no_write_commit(*args, **kwargs):
        assert not kwargs['request']['writes']
        return commit(*args, **kwargs)

    monkeypatch.setattr(api, 'run_query', counted_query)
    monkeypatch.setattr(api, 'run_aggregation_query', counted_count)
    monkeypatch.setattr(api, 'begin_transaction', read_only_begin)
    monkeypatch.setattr(api, 'commit', no_write_commit)
    for size in sizes:
        uid = f'{prefix}-{size}'
        samples = []
        for enabled in (False, True):
            monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"backfill_task_reads":100}' if enabled else '')
            samples.append(registry.waiting_sample(uid, firestore_client=client, now=NOW))
        assert samples[0] == samples[1]
        assert samples[0]['depth'] == min(100, size)
        assert samples[0]['age_seconds'] == (1000.0 if size else 0.0)
    assert query_reads == [1, 1, 1, 1, 2, 2, 100, 2, 100, 2]
    assert aggregation_reads == [1, 1, 1]
    assert len(read_only_begins) == len(sizes)
    client.close()
