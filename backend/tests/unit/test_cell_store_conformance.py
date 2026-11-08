"""Real Postgres conformance for the cell foundation (private unix sockets)."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import base64
import json
import subprocess
import sys
import threading
import time

import pytest

from config import cell_store
from database.cells import AdapterRegistry, CellStore
from database.cells.errors import BaseRevisionMismatch, CellContentionExhausted, CellSpaceUnavailable, MutationIdReused
from database.cells.feed import CursorAhead, DEVICE_STALE_S, FEED_RETENTION_S, ResyncRequired
from database.cells.receipts import MUTATION_RECEIPT_RETENTION_SECONDS
from database.cells import store as store_module
from database.jobstore.connection import Pool, dial
from database.jobstore.migrate import current_version, migrate
from testing import cells_fixtures
from testing.cells_fixtures import cells_dsn, make_cell_store

NOW = 2_000_000_000.0


@pytest.fixture(scope='module')
def harness():
    harness = make_cell_store()
    yield harness
    harness.close()


@pytest.fixture
def space(harness, request):
    uid = harness.uid(request.node.name.replace('[', '-').replace(']', ''))
    harness.store.enroll_space(uid, now=NOW)
    return uid


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
    with pytest.raises(BaseRevisionMismatch) as error:
        write(store, space, 'missing', expected_rev=0)
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
    assert store.pull(space, cursor=2, now=NOW).next_cursor == 3
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
    for i in range(2):
        write(store, space, str(i), now=old)
    store.run(space, lambda tx: tx.delete('notes', 'missing'), actor_uid=space, now=old)
    for i in range(2, 4):
        write(store, space, str(i), now=old)
    write(store, space, 'recent')
    store.set_cursor(space, 'device', last_seq=5, now=NOW)
    assert store.floor(space, now=NOW) == 5
    assert store.compact(space, now=NOW) == 3
    with pytest.raises(ResyncRequired) as error:
        store.pull(space, cursor=3, now=NOW)
    assert (error.value.floor, error.value.epoch) == (5, 1)
    assert store.pull(space, cursor=5, now=NOW).entries[0].seq == 6
    with store.pool.connection() as conn:
        assert conn.execute('SELECT seq, op FROM change_log WHERE space_id=%s ORDER BY seq', (space,)).fetchall() == [
            (3, 'delete'),
            (5, 'upsert'),
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


@pytest.mark.parametrize('head', [0, 1])
def test_future_cursors_rejected_and_head_accepted(harness, space, head):
    store = harness.store
    if head:
        write(store, space, 'a')
    for cursor in (head + 1, head + 100):
        with pytest.raises(CursorAhead) as error:
            store.pull(space, cursor=cursor, now=NOW)
        assert (error.value.space_id, error.value.head, error.value.epoch) == (space, head, 1)
        with pytest.raises(CursorAhead):
            store.set_cursor(space, 'device', last_seq=cursor, now=NOW)
    with store.pool.connection() as conn:
        assert conn.execute('SELECT count(*) FROM sync_cursors WHERE space_id=%s', (space,)).fetchone()[0] == 0
    page = store.pull(space, cursor=head, now=NOW)
    assert (page.next_cursor, page.head, page.entries) == (head, head, [])
    store.set_cursor(space, 'device', last_seq=head, now=NOW)
    with store.pool.connection() as conn:
        assert conn.execute('SELECT last_seq FROM sync_cursors WHERE space_id=%s', (space,)).fetchone() == (head,)


@pytest.mark.parametrize('op,feed', [('upsert', True), ('upsert', False), ('delete', True)])
def test_replay_survives_feed_compaction(harness, space, op, feed):
    store = harness.store
    old = NOW - 40 * 86400

    def original(tx):
        if op == 'upsert':
            tx.put('notes', 'a', {'old': True}, client_mutation_id='mid', fingerprint='fp', feed=feed)
        else:
            tx.delete('notes', 'a', client_mutation_id='mid', fingerprint='fp', feed=feed)

    store.run(space, original, actor_uid=space, now=old)
    write(store, space, 'filler', now=old)
    write(store, space, 'a')
    assert store.compact(space, now=NOW) == int(op == 'upsert')
    before = store.read_doc(space, 'notes', 'a')
    assert store.run(space, original, actor_uid=space, now=NOW).replayed == {'mid': 1}
    assert store.head(space) == (3, 1)
    assert store.read_doc(space, 'notes', 'a') == before
    with store.pool.connection() as conn:
        assert conn.execute(
            'SELECT seq, created_at FROM mutation_receipts WHERE space_id=%s AND client_mutation_id=%s',
            (space, 'mid'),
        ).fetchone() == (1, old)
    with pytest.raises(MutationIdReused):
        write(store, space, 'other', client_mutation_id='mid', fingerprint='fp')


def test_receipt_purge_is_bounded_and_independent_of_feed(harness, space):
    store = harness.store
    cutoff = NOW - MUTATION_RECEIPT_RETENTION_SECONDS
    other = harness.uid('receipt-neighbor')
    store.enroll_space(other, now=NOW)
    write(store, other, 'a', now=cutoff - 1, client_mutation_id='neighbor', fingerprint='fp')
    for key, ts in [('expired-1', cutoff - 2), ('expired-2', cutoff - 1), ('boundary', cutoff), ('recent', NOW)]:
        write(store, space, key, now=ts, client_mutation_id=key, fingerprint='fp')
    with store.pool.connection() as conn:
        before = conn.execute('SELECT * FROM change_log WHERE space_id=%s ORDER BY seq', (space,)).fetchall()
    assert store.purge_mutation_receipts(space, now=NOW, limit=1) == 1
    assert store.purge_mutation_receipts(space, now=NOW, limit=1) == 1
    assert store.purge_mutation_receipts(space, now=NOW) == 0
    with store.pool.connection() as conn:
        assert conn.execute('SELECT * FROM change_log WHERE space_id=%s ORDER BY seq', (space,)).fetchall() == before
        assert conn.execute(
            'SELECT client_mutation_id FROM mutation_receipts WHERE space_id=%s ORDER BY client_mutation_id', (space,)
        ).fetchall() == [('boundary',), ('recent',)]
        assert conn.execute('SELECT count(*) FROM mutation_receipts WHERE space_id=%s', (other,)).fetchone()[0] == 1
    # After independent receipt expiry, the retained log must not impose replay uniqueness.
    assert write(store, space, 'expired-1', client_mutation_id='expired-1', fingerprint='fp').replayed == {}
    assert store.head(space) == (5, 1)


def test_receipt_insert_failure_rolls_back_whole_write(harness, space, monkeypatch):
    store = harness.store
    original = store.pool.connection

    class Proxy:
        def __init__(self, conn):
            self.conn = conn

        def transaction(self):
            return self.conn.transaction()

        def execute(self, sql, args=None):
            result = self.conn.execute(sql, args)
            if sql.startswith('INSERT INTO mutation_receipts'):
                raise RuntimeError('injected receipt failure')
            return result

    @contextmanager
    def connection():
        with original() as conn:
            yield Proxy(conn)

    with monkeypatch.context() as patch:
        patch.setattr(store.pool, 'connection', connection)
        with pytest.raises(RuntimeError, match='injected receipt failure'):
            write(store, space, 'a', client_mutation_id='mid', fingerprint='fp')
    assert store.head(space) == (0, 1)
    assert store.read_doc(space, 'notes', 'a') == {}
    with store.pool.connection() as conn:
        for table in ('change_log', 'mutation_receipts'):
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE space_id=%s', (space,)).fetchone()[0] == 0


def test_purge_is_complete_and_isolated(harness, space):
    store = harness.store
    other = harness.uid('purge-neighbor')
    store.enroll_space(other, now=NOW)
    for sid in (space, other):
        write(store, sid, 'a', client_mutation_id='mid', fingerprint='fp')
        store.set_cursor(sid, 'device', last_seq=1, now=NOW)
    assert store.purge_space(space) == 4
    with store.pool.connection() as conn:
        assert conn.execute('SELECT tombstoned FROM space_heads WHERE space_id=%s', (space,)).fetchone() == (True,)
        for table in ('cell_docs', 'change_log', 'sync_cursors', 'mutation_receipts'):
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE space_id=%s', (space,)).fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM mutation_receipts WHERE space_id=%s', (other,)).fetchone()[0] == 1
    assert store.read_doc(other, 'notes', 'a')
    assert store.purge_space(space) == 0


@pytest.mark.parametrize('state', ['missing', 'tombstoned'])
def test_every_creating_write_requires_live_enrollment(harness, state):
    store = harness.store
    uid = harness.uid(f'write-fence-{state}')
    if state == 'tombstoned':
        store.enroll_space(uid, now=NOW)
        store.tombstone_space(uid)
    with pytest.raises(CellSpaceUnavailable) as error:
        write(store, uid, 'late', client_mutation_id='mid', fingerprint='fp')
    assert error.value.retryable is True
    with pytest.raises(CellSpaceUnavailable):
        store.set_cursor(uid, 'late-device', last_seq=0, now=NOW)
    with pytest.raises(CellSpaceUnavailable):
        store.bump_epoch(uid, now=NOW)
    if state == 'tombstoned':
        with pytest.raises(CellSpaceUnavailable):
            store.enroll_space(uid, now=NOW)
    with store.pool.connection() as conn:
        for table in ('cell_docs', 'change_log', 'sync_cursors', 'mutation_receipts'):
            assert conn.execute(f'SELECT count(*) FROM {table} WHERE space_id=%s', (uid,)).fetchone()[0] == 0
        assert conn.execute('SELECT tombstoned FROM space_heads WHERE space_id=%s', (uid,)).fetchone() == (
            (True,) if state == 'tombstoned' else None
        )


def test_fence_waits_for_admitted_commit_then_rejects_late_writer(harness, space, monkeypatch):
    allocated, release = threading.Event(), threading.Event()
    original = store_module.CellTransaction.flush

    def held_commit(tx):
        result = original(tx)
        allocated.set()
        assert release.wait(timeout=10)
        return result

    with monkeypatch.context() as patch:
        patch.setattr(store_module.CellTransaction, 'flush', held_commit)
        with ThreadPoolExecutor(max_workers=2) as executor:
            writer = executor.submit(write, harness.store, space, 'admitted')
            try:
                assert allocated.wait(timeout=10)
                fence = executor.submit(harness.store.tombstone_space, space)
            finally:
                release.set()
            writer.result(timeout=10)
            fence.result(timeout=10)
    assert harness.store.read_doc(space, 'notes', 'admitted')
    with pytest.raises(CellSpaceUnavailable):
        write(harness.store, space, 'late')
    assert harness.store.purge_space(space) == 2
    assert harness.store.read_doc(space, 'notes', 'admitted') == {}


def test_doc_semantics_and_rollback(harness, space):
    store = harness.store
    assert store.read_doc(space, 'notes', 'a') == {}
    assert store.run(space, lambda tx: tx.get('notes', 'a'), actor_uid=space, now=NOW).value == {}
    assert store.head(space) == (0, 1)
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
    assert store.head(space) == (0, 1)
    assert store.pull(space, cursor=0, now=NOW).epoch == 1
    write(store, space, 'a')
    assert store.head(space) == (1, 1)
    assert store.bump_epoch(space, now=NOW) == 2
    assert store.pull(space, cursor=0, now=NOW).epoch == 2
    with dial(cells_dsn()) as conn:
        path = Path(store_module.__file__).parent / 'migrations'
        assert migrate(conn, directory=path) == []
        assert migrate(conn, directory=path) == []
        assert current_version(conn) == 4  # B2 fence, B3 revision timestamps, A2b typed query promotion


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


def test_mutation_receipts_cannot_be_lost_during_coalescing(harness, space):
    store = harness.store

    def overwritten(tx):
        tx.put('notes', 'a', {}, client_mutation_id='first', fingerprint='fp')
        tx.put('notes', 'a', {'new': True}, client_mutation_id='second', fingerprint='fp2')

    with pytest.raises(ValueError, match='discard a client mutation receipt'):
        store.run(space, overwritten, actor_uid=space, now=NOW)

    def reused(tx):
        tx.put('notes', 'a', {}, client_mutation_id='same', fingerprint='fp')
        tx.put('notes', 'b', {}, client_mutation_id='same', fingerprint='fp')

    with pytest.raises(MutationIdReused):
        store.run(space, reused, actor_uid=space, now=NOW)
    assert store.head(space) == (0, 1)
    assert store.read_doc(space, 'notes', 'a') == {}


def test_imports_are_driver_and_connection_lazy():
    # A clean process proves import purity independently of this suite's PG setup.
    import_result = subprocess.run(
        [
            sys.executable,
            '-c',
            'import sys; import database.cells, database.directory, config.cell_store; '
            'assert "psycopg" not in sys.modules',
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert import_result.returncode == 0, import_result.stderr


def test_iam_fixture_refuses_before_contacting_postgres(monkeypatch):
    monkeypatch.setenv('OMI_TEST_POSTGRES_IAM', 'not-a-real-target')

    def forbidden():
        raise AssertionError('IAM refusal must precede discovery')

    monkeypatch.setattr(cells_fixtures, 'postgres_dsn', forbidden)
    with pytest.raises(cells_fixtures.BackendUnavailable, match='do not support IAM'):
        cells_fixtures.cells_dsn()
    with pytest.raises(cells_fixtures.BackendUnavailable, match='do not support IAM'):
        cells_fixtures.directory_dsn()


@pytest.mark.parametrize('tombstoned', [False, True])
def test_feed_enrollment_fence(harness, tombstoned):
    space = harness.uid('feed-fence-' + str(tombstoned))
    if tombstoned:
        harness.store.purge_space(space)
    for read in [harness.store.pull, harness.store.snapshot]:
        kwargs = {'cursor': 0} if read.__name__ == 'pull' else {}
        with pytest.raises(CellSpaceUnavailable):
            read(space, now=NOW, **kwargs)
    assert harness.store.compact(space, now=NOW) == 0


def test_feed_tail_and_truncation(harness, space):
    store = harness.store
    write(store, space, 'a')
    write(store, space, 'b')
    write(store, space, 'hidden', feed=False)
    assert store.pull(space, cursor=0, limit=1, now=NOW).next_cursor == 1
    assert store.pull(space, cursor=1, limit=2, now=NOW).next_cursor == 3
    assert store.pull(space, cursor=2, now=NOW).next_cursor == 3


def test_snapshot_keyset_since_and_page_one_head(harness, space):
    store = harness.store
    # Entity IDs need not be ASCII; PostgreSQL C ordering defines the keyset.
    for key in ['a', 'z', 'é']:
        write(store, space, key)
    page = store.snapshot(space, limit=1, now=NOW)
    first_head = page.head
    assert page.rows[0]['entity_id'] == 'a'
    write(store, space, 'a')
    rows = list(page.rows)
    while page.next_page_token:
        after = tuple(json.loads(base64.b64decode(page.next_page_token)))
        page = store.snapshot(space, after=after, limit=1, now=NOW)
        rows.extend(page.rows)
    assert [row['entity_id'] for row in rows] == ['a', 'z', 'é']
    assert [row['entity_id'] for row in store.snapshot(space, since=first_head, now=NOW).rows] == ['a']
    assert [e.entity_id for e in store.pull(space, cursor=first_head, now=NOW).entries] == ['a']
    assert store.bump_epoch(space, now=NOW) != page.epoch


def test_snapshot_since_pages_rows_and_latest_tombstones(harness, space):
    store = harness.store
    for key in ['a', 'b', 'é', 'old']:
        write(store, space, key)
    store.run(space, lambda tx: tx.delete('notes', 'old'), actor_uid=space, now=NOW)
    since = store.head(space)[0]
    for key in ['a', 'é', 'a']:
        store.run(space, lambda tx: tx.delete('notes', key, feed=False), actor_uid=space, now=NOW)
    write(store, space, 'b')
    write(store, space, 'é')  # Recreated rows suppress older deletion records.
    store.compact(space, now=NOW + FEED_RETENTION_S + 1)

    after, addresses, rows, entries = None, [], [], []
    while True:
        page = store.snapshot(space, since=since, after=after, limit=1, now=NOW)
        assert len(page.rows) + len(page.entries) <= 1
        rows.extend(page.rows)
        entries.extend(page.entries)
        addresses.extend(r['entity_id'] for r in page.rows)
        addresses.extend(e.entity_id for e in page.entries)
        if page.next_page_token is None:
            break
        after = tuple(json.loads(base64.b64decode(page.next_page_token)))
    assert addresses == ['a', 'b', 'é']
    assert [r['entity_id'] for r in rows] == ['b', 'é']
    assert [(e.entity_id, e.op, e.seq) for e in entries] == [('a', 'delete', 8)]
    assert all(e.rev == e.seq for e in entries)
    assert store.snapshot(space, since=store.head(space)[0], now=NOW).entries == []


def test_protocol_transaction_reads(harness, space):
    store = harness.store
    write(store, space, 'a', now=NOW - 2, client_mutation_id='read-mid', fingerprint='fp')
    write(store, space, 'a', now=NOW - 1)
    write(store, space, 'a', now=NOW - 1, feed=False)
    with store.pool.connection() as conn:
        stamps = [
            r[0]
            for r in conn.execute(
                'SELECT committed_at FROM change_log WHERE space_id=%s ORDER BY seq', (space,)
            ).fetchall()
        ]

    def read(tx):
        assert tx.get_with_rev('notes', 'absent') is None
        row = tx.get_with_rev('notes', 'a')
        assert row == (3, {'key': 'a'})
        row[1]['key'] = 'must not mutate the cached row'
        assert tx.get_with_rev('notes', 'a') == (3, {'key': 'a'})
        assert tx.receipt_seq('missing') is None
        assert tx.receipt_seq('read-mid') == 1
        assert tx.seq_as_of('notes', 'a', stamps[0] - 1) is None
        assert tx.seq_as_of('notes', 'a', stamps[0]) == 1
        assert tx.seq_as_of('notes', 'a', stamps[1]) == 2
        assert tx.seq_as_of('notes', 'a', stamps[2]) == 3  # includes feed=false
        for invalid in ['', 'bad\x00']:
            with pytest.raises(ValueError):
                tx.receipt_seq(invalid)

    store.run(space, read, actor_uid=space, now=NOW)
    store.compact(space, now=NOW + FEED_RETENTION_S + 1)
    assert store.run(space, lambda tx: tx.seq_as_of('notes', 'a', stamps[0]), actor_uid=space, now=NOW).value is None


@pytest.mark.parametrize('read_kind', ['pull', 'snapshot'])
def test_read_head_cannot_advance_past_its_data_snapshot(harness, space, monkeypatch, read_kind):
    store = harness.store
    write(store, space, 'a')
    original = store.pool.connection
    injected = False

    class Result:
        def __init__(self, cursor):
            self.cursor = cursor

        def fetchall(self):
            nonlocal injected
            rows = self.cursor.fetchall()
            if not injected:
                injected = True
                write(store, space, 'late')
            return rows

    class Proxy:
        def __init__(self, conn):
            self.conn = conn

        def transaction(self):
            return self.conn.transaction()

        def execute(self, sql, args=None):
            result = self.conn.execute(sql, args)
            trigger = 'SELECT seq, entity' if read_kind == 'pull' else 'SELECT entity, entity_id, author_id'
            return Result(result) if sql.startswith(trigger) else result

    @contextmanager
    def connection():
        with original() as conn:
            yield Proxy(conn)

    with monkeypatch.context() as patch:
        patch.setattr(store.pool, 'connection', connection)
        kwargs = {'cursor': 0} if read_kind == 'pull' else {}
        page = getattr(store, read_kind)(space, now=NOW, **kwargs)
    assert injected
    assert page.head == 1
    if read_kind == 'pull':
        assert page.next_cursor == 1
    assert [e.entity_id for e in store.pull(space, cursor=page.head, now=NOW).entries] == ['late']
