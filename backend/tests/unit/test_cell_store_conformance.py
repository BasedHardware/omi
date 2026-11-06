"""Real Postgres conformance for the cell foundation (private unix sockets)."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import threading
import time

import pytest

from config import cell_store
from database.cells import CellStore
from database.cells.adapters import AdapterRegistry
from database.cells.errors import BaseRevisionMismatch, CellContentionExhausted, MutationIdReused
from database.cells.feed import DEVICE_STALE_S, FEED_RETENTION_S, ResyncRequired
from database.cells import store as store_module
from database.jobstore.connection import Pool, dial
from database.jobstore.migrate import current_version, migrate
from testing.cells_fixtures import cells_dsn, make_cell_store

NOW = 2_000_000_000.0


@pytest.fixture(scope='module')
def harness():
    harness = make_cell_store()
    yield harness
    harness.close()


@pytest.fixture
def space(harness, request):
    return harness.uid(request.node.name)


def write(store, space, key, *, now=NOW, **kwargs):
    return store.run(space, lambda tx: tx.put('notes', key, {'key': key}, **kwargs), actor_uid=space, now=now)


def test_concurrent_commit_order_and_no_skip(harness, space):
    store = harness.store
    start = threading.Barrier(3)
    done = threading.Event()
    observed = []

    def writer(label):
        start.wait(timeout=5)
        for index in range(4):
            key = f'{label}-{index}'
            write(store, space, key, client_mutation_id=key, fingerprint=key)

    def reader():
        start.wait(timeout=5)
        cursor = 0
        deadline = time.monotonic() + 10
        while not done.is_set() and time.monotonic() < deadline:
            page = store.pull(space, cursor=cursor, limit=2, now=NOW)
            observed.extend(e.seq for e in page.entries)
            cursor = page.next_cursor
        return cursor

    with ThreadPoolExecutor(max_workers=3) as executor:
        first = executor.submit(writer, 'a')
        second = executor.submit(writer, 'b')
        reading = executor.submit(reader)
        try:
            first.result(timeout=15)
            second.result(timeout=15)
        finally:
            done.set()
        cursor = reading.result(timeout=15)
    page = store.pull(space, cursor=cursor, now=NOW)
    observed.extend(e.seq for e in page.entries)
    assert observed == list(range(1, 9))
    assert store.head(space) == (8, 1)
    page = store.pull(space, cursor=0, now=NOW)
    assert all(page.rows[(e.entity, e.entity_id)]['rev'] == e.seq for e in page.entries)


def test_uncommitted_lower_seq_cannot_be_skipped(harness, space, monkeypatch):
    store = harness.store
    allocated = threading.Event()
    release = threading.Event()
    entered_second = threading.Event()
    flush = store_module.CellTransaction.flush

    def pause(tx):
        result = flush(tx)
        if tx.mutations[0].entity_id == 'first':
            allocated.set()
            assert release.wait(timeout=5)
        return result

    monkeypatch.setattr(store_module.CellTransaction, 'flush', pause)
    # Independent reader pool permits a pull while both writers own connections.
    reader_pool = Pool(cells_dsn(), size=1)
    reader = CellStore(reader_pool)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(write, store, space, 'first')
            try:
                assert allocated.wait(timeout=5)

                def second_body(tx):
                    entered_second.set()
                    tx.put('notes', 'second', {})

                second = executor.submit(store.run, space, second_body, actor_uid=space, now=NOW)
                assert entered_second.wait(timeout=5)
                assert reader.pull(space, cursor=0, now=NOW).entries == []
            finally:
                release.set()
            first.result(timeout=10)
            second.result(timeout=10)
        assert [e.entity_id for e in reader.pull(space, cursor=0, now=NOW).entries] == ['first', 'second']
    finally:
        reader_pool.close()


def test_paging_with_interleaved_commit(harness, space):
    store = harness.store
    for index in range(7):
        write(store, space, str(index))
    cursor = 0
    seen = []
    for index in range(5):
        page = store.pull(space, cursor=cursor, limit=2, now=NOW)
        assert page.next_cursor >= cursor
        cursor = page.next_cursor
        seen.extend(e.seq for e in page.entries)
        if index == 0:
            write(store, space, 'late')
    assert seen == list(range(1, 9))
    assert cursor == 8


def test_replay_cas_and_reuse(harness, space):
    store = harness.store
    first = write(store, space, 'a', client_mutation_id='mid', fingerprint='fp')
    assert first.replayed == {}
    before = store.read_doc(space, 'notes', 'a')
    replay = write(store, space, 'a', client_mutation_id='mid', fingerprint='fp', expected_rev=999)
    assert replay.replayed == {'mid': 1}
    assert store.head(space) == (1, 1)
    assert store.read_doc(space, 'notes', 'a') == before
    for key, fingerprint in [('a', 'other'), ('b', 'fp')]:
        with pytest.raises(MutationIdReused) as error:
            write(store, space, key, client_mutation_id='mid', fingerprint=fingerprint)
        assert error.value.client_mutation_id == 'mid'
    with pytest.raises(MutationIdReused):
        store.run(
            space,
            lambda tx: tx.delete('notes', 'a', client_mutation_id='mid', fingerprint='fp'),
            actor_uid=space,
            now=NOW,
        )
    assert store.head(space) == (1, 1)
    write(store, space, 'a', expected_rev=1)
    with pytest.raises(BaseRevisionMismatch) as error:
        write(store, space, 'a', expected_rev=1)
    assert error.value.current_rev == 2
    with pytest.raises(BaseRevisionMismatch) as error:
        write(store, space, 'missing', expected_rev=1)
    assert error.value.current_rev is None
    assert store.head(space) == (2, 1)


def test_concurrent_duplicate_mutation(harness, space):
    start = threading.Barrier(2)

    def duplicate():
        start.wait(timeout=5)
        return write(harness.store, space, 'a', client_mutation_id='mid', fingerprint='fp')

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: duplicate(), range(2)))
    assert sorted(len(r.replayed) for r in results) == [0, 1]
    assert harness.store.head(space) == (1, 1)


def test_coalescing_feed_and_page_dedup(harness, space):
    store = harness.store

    def body(tx):
        tx.put('notes', 'a', {'v': 1})
        tx.put('notes', 'a', {'v': 2})
        tx.delete('notes', 'b')
        tx.put('notes', 'b', {'v': 3}, author_uid='other-author')

    store.run(space, body, actor_uid=space, now=NOW)
    page = store.pull(space, cursor=0, now=NOW)
    assert [(e.entity_id, e.op) for e in page.entries] == [('a', 'upsert'), ('b', 'upsert')]
    assert page.rows[('notes', 'b')]['author_id'] == 'other-author'
    assert store.read_doc(space, 'notes', 'a') == {'v': 2}
    write(store, space, 'hidden', feed=False)
    assert store.pull(space, cursor=2, now=NOW).next_cursor == 2
    with store.pool.connection() as conn:
        assert conn.execute('SELECT feed, rev FROM change_log WHERE space_id=%s AND seq=3', (space,)).fetchone() == (
            False,
            3,
        )
    write(store, space, 'hidden')
    store.run(space, lambda tx: tx.delete('notes', 'a'), actor_uid=space, now=NOW)
    page = store.pull(space, cursor=0, now=NOW)
    assert [(e.seq, e.entity_id, e.op) for e in page.entries] == [
        (2, 'b', 'upsert'),
        (4, 'hidden', 'upsert'),
        (5, 'a', 'delete'),
    ]
    assert page.rows[('notes', 'a')] is None
    assert page.next_cursor == 5


def test_current_state_read_set(harness, space):
    store = harness.store
    write(store, space, 'a')
    write(store, space, 'a')
    page = store.pull(space, cursor=0, limit=1, now=NOW)
    assert page.entries[0].rev == 1
    assert page.rows[('notes', 'a')]['rev'] == 2


def test_compaction_floor_and_tombstone(harness, space):
    store = harness.store
    old = NOW - 40 * 86400
    for i in range(4):
        write(store, space, str(i), now=old)
    store.run(space, lambda tx: tx.delete('notes', 'missing'), actor_uid=space, now=old)
    write(store, space, 'recent')
    store.set_cursor(space, 'device', last_seq=5, now=NOW)
    assert store.floor(space, now=NOW) == 5
    assert store.compact(space, now=NOW) == 4
    with pytest.raises(ResyncRequired) as error:
        store.pull(space, cursor=3, now=NOW)
    assert (error.value.floor, error.value.epoch) == (5, 1)
    assert store.pull(space, cursor=5, now=NOW).entries[0].seq == 6
    with store.pool.connection() as conn:
        assert conn.execute('SELECT seq, op FROM change_log WHERE space_id=%s ORDER BY seq', (space,)).fetchall() == [
            (5, 'delete'),
            (6, 'upsert'),
        ]
    assert store.compact(space, now=NOW) == 0
    with pytest.raises(ResyncRequired):
        store.set_cursor(space, 'new-device', last_seq=0, now=NOW)


def test_cursor_retention_and_monotonicity(harness, space):
    store = harness.store
    write(store, space, 'old', now=NOW - FEED_RETENTION_S - 1)
    # A known device can hold the log before its time cap expires.
    store.set_cursor(space, 'device', last_seq=0, now=NOW - FEED_RETENTION_S - 1)
    write(store, space, 'new')
    assert store.floor(space, now=NOW) == 0
    store.set_cursor(space, 'device', last_seq=1, now=NOW)
    store.set_cursor(space, 'device', last_seq=0, now=NOW - FEED_RETENTION_S - 1)
    assert store.floor(space, now=NOW) == 1
    assert store.floor(space, now=NOW + DEVICE_STALE_S + 1) == 2


def test_purge_is_complete_and_isolated(harness, space):
    store = harness.store
    other = harness.uid('purge-neighbor')
    for sid in (space, other):
        write(store, sid, 'a')
        store.set_cursor(sid, 'device', last_seq=1, now=NOW)
    assert store.purge_space(space) == 4
    with store.pool.connection() as conn:
        for table in ('space_heads', 'cell_docs', 'change_log', 'sync_cursors'):
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE space_id=%s', (space,)).fetchone()[0] == 0
    assert store.read_doc(other, 'notes', 'a')
    assert store.purge_space(space) == 0


def test_doc_semantics_and_rollback(harness, space):
    store = harness.store
    assert store.read_doc(space, 'notes', 'a') == {}
    assert store.run(space, lambda tx: tx.get('notes', 'a'), actor_uid=space, now=NOW).value == {}
    assert store.head(space) == (0, 0)
    doc = {'nested': [{'when': datetime(2026, 1, 1, tzinfo=timezone.utc), 'bytes': b'\x00\xff'}]}

    def body(tx):
        assert tx.get('notes', 'a') == {}
        tx.put('notes', 'a', doc)
        assert tx.get('notes', 'a') == doc
        tx.delete('notes', 'a')
        assert tx.get('notes', 'a') == {}
        tx.put('notes', 'a', doc)
        tx.get('notes', 'a')['nested'].clear()
        return 'body-result'

    assert store.run(space, body, actor_uid=space, now=NOW).value == 'body-result'
    assert store.read_doc(space, 'notes', 'a') == doc

    def failing(tx):
        tx.put('notes', 'a', {'bad': True})
        raise RuntimeError('body failed')

    with pytest.raises(RuntimeError, match='body failed'):
        store.run(space, failing, actor_uid=space, now=NOW)
    assert store.read_doc(space, 'notes', 'a') == doc
    assert store.head(space) == (1, 1)
    assert store.read_doc(harness.uid('isolated'), 'notes', 'a') == {}


def test_head_epoch_and_migrations(harness, space):
    store = harness.store
    assert store.head(space) == (0, 0)
    assert store.pull(space, cursor=0, now=NOW).epoch == 0
    write(store, space, 'a')
    assert store.head(space) == (1, 1)
    assert store.bump_epoch(space, now=NOW) == 2
    assert store.pull(space, cursor=0, now=NOW).epoch == 2
    with dial(cells_dsn()) as conn:
        path = Path(store_module.__file__).parent / 'migrations'
        assert migrate(conn, directory=path) == []
        assert migrate(conn, directory=path) == []
        assert current_version(conn) == 1


def test_validation_and_adapter_registration(harness, space, monkeypatch):
    monkeypatch.delenv('CELL_STORE_MODE', raising=False)
    assert cell_store.mode() == 'off'
    for value in cell_store.MODES:
        monkeypatch.setenv('CELL_STORE_MODE', value)
        assert cell_store.mode() == value
    monkeypatch.setenv('CELL_STORE_MODE', 'typo')
    with pytest.raises(ValueError):
        cell_store.mode()
    for entity, key in [('Notes', 'a'), ('a' * 41, 'a'), ('notes', ''), ('notes', 'a\x00'), ('notes', 'a' * 257)]:
        with pytest.raises(ValueError):
            harness.store.read_doc(space, entity, key)
    for uid in ('', 'has space', 'a' * 129):
        with pytest.raises(ValueError):
            write(harness.store, uid, 'a')
    with pytest.raises(ValueError):
        write(harness.store, space, 'a', client_mutation_id='missing-fingerprint')
    registry = AdapterRegistry()
    registry.register('notes', lambda tx: tx)
    with pytest.raises(ValueError):
        registry.register('notes', lambda tx: tx)

    def body(tx):
        assert registry.bind('notes', tx) is tx

    harness.store.run(space, body, actor_uid=space, now=NOW)


def test_retry_and_exhaustion(harness, space, monkeypatch):
    class RetryError(Exception):
        sqlstate = '40001'

    count = 0

    def body(tx):
        nonlocal count
        count += 1
        tx.put('notes', 'a', {'attempt': count})
        if count == 1:
            raise RetryError()

    monkeypatch.setattr(store_module.time, 'sleep', lambda delay: None)
    harness.store.run(space, body, actor_uid=space, now=NOW)
    assert count == 2
    assert harness.store.read_doc(space, 'notes', 'a') == {'attempt': 2}

    def fail(tx):
        tx.put('notes', 'a', {})
        raise RetryError()

    with pytest.raises(CellContentionExhausted):
        harness.store.run(space, fail, actor_uid=space, now=NOW)
    assert harness.store.head(space) == (1, 1)


def test_purge_rollback(harness, space, monkeypatch):
    store = harness.store
    write(store, space, 'a')
    original = store.pool.connection

    class Proxy:
        def __init__(self, conn):
            self.conn = conn

        def transaction(self):
            return self.conn.transaction()

        def execute(self, sql, args=None):
            if sql.startswith('DELETE FROM change_log'):
                raise RuntimeError('injected deletion failure')
            return self.conn.execute(sql, args)

    @contextmanager
    def connection():
        with original() as conn:
            yield Proxy(conn)

    with monkeypatch.context() as patch:
        patch.setattr(store.pool, 'connection', connection)
        with pytest.raises(RuntimeError, match='injected'):
            store.purge_space(space)
    assert store.head(space) == (1, 1)
    assert store.read_doc(space, 'notes', 'a')
    assert len(store.pull(space, cursor=0, now=NOW).entries) == 1
