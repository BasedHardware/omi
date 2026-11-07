"""Required wipe fencing, failure propagation and real cell/directory purge."""

from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import threading
from unittest.mock import Mock

import pytest
import fakeredis

from database.directory import router, wipe
from database.cells import CellStore
from database.cells.errors import CellSpaceUnavailable
from database.jobstore.connection import Pool
from testing.cells_fixtures import cells_dsn
from testing.cells_fixtures import make_cell_store, make_directory


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'new_owners')
    monkeypatch.setenv('CELL_WIPE_WRITER_DRAIN_SECONDS', '0')
    monkeypatch.setenv('CELL_DIRECTORY_WIPE_ENABLED', 'true')
    monkeypatch.setattr(wipe.users_db, 'get_user_deletion_wipe_status', lambda uid: 'running')
    monkeypatch.setattr(router, '_cache', {})
    monkeypatch.setattr(router.redis_db, 'r', fakeredis.FakeRedis())
    monkeypatch.setattr(router.redis_db, 'get_generic_cache', lambda key: None)
    monkeypatch.setattr(router.redis_db, 'delete_generic_cache', lambda key: None)


def test_off_constructs_nothing(monkeypatch):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'off')
    monkeypatch.setattr(router, 'directory_store', Mock(side_effect=AssertionError('pool')))
    monkeypatch.setattr(wipe, 'cell_store', Mock(side_effect=AssertionError('pool')))
    monkeypatch.setattr(wipe.users_db, 'get_user_deletion_wipe_status', Mock(side_effect=AssertionError('marker')))
    assert wipe.purge_owner_planes('owner') == {'status': 'noop'}


@pytest.mark.parametrize('marker', ['pending', 'failed', None, RuntimeError('unreadable')])
def test_requires_running_marker(monkeypatch, marker):
    monkeypatch.setattr(
        wipe.users_db,
        'get_user_deletion_wipe_status',
        Mock(side_effect=marker if isinstance(marker, Exception) else None, return_value=marker),
    )
    monkeypatch.setattr(router, 'directory_store', Mock(side_effect=AssertionError('pool')))
    with pytest.raises(RuntimeError):
        wipe.purge_owner_planes('owner')


def test_directory_outage_propagates(monkeypatch):
    monkeypatch.setattr(router, 'directory_store', Mock(side_effect=ConnectionError('down')))
    with pytest.raises(ConnectionError):
        wipe.purge_owner_planes('owner')


@pytest.mark.parametrize('crash', [False, True])
def test_real_purge_fence_drain_and_retry(monkeypatch, crash):
    directory = make_directory()
    cell = make_cell_store()
    uid = directory.uid()
    cell.seeded.add(uid)
    try:
        directory.store.get_or_create_personal_space(uid, cell='cell1', now=1)
        cell.store.enroll_space(uid, now=1)
        cell.store.run(uid, lambda tx: tx.put('memories', 'm1', {'text': 'synthetic'}), actor_uid=uid, now=1)
        monkeypatch.setattr(router, 'directory_store', lambda: directory.store)
        events = []
        monkeypatch.setattr(wipe, 'cell_store', lambda: cell.store)
        real_purge = cell.store.purge_space

        def purge(owner):
            space = directory.store.get_space(owner)
            assert space.cell == 'disabled'
            assert space.epoch >= 2
            assert owner not in router._cache
            with cell.store.pool.connection() as conn:
                assert conn.execute('SELECT tombstoned FROM space_heads WHERE space_id=%s', (owner,)).fetchone() == (
                    True,
                )
            with pytest.raises(CellSpaceUnavailable):
                cell.store.run(owner, lambda tx: tx.put('memories', 'late', {}), actor_uid=owner, now=2)
            with pytest.raises(router.DirectoryRoutingUnavailable):
                router.resolve(owner)
            events.append('purge')
            if crash and events.count('purge') == 1:
                raise RuntimeError('crash after fencing')
            return real_purge(owner)

        monkeypatch.setattr(cell.store, 'purge_space', purge)
        monkeypatch.setattr(wipe.time, 'sleep', lambda delay: events.append('drain'))
        if crash:
            with pytest.raises(RuntimeError, match='crash'):
                wipe.purge_owner_planes(uid, now=2)
            assert directory.store.get_space(uid).cell == 'disabled'
        assert wipe.purge_owner_planes(uid, now=3) == {'status': 'purged'}
        assert events[-2:] == ['drain', 'purge']
        assert directory.store.get_space(uid) is None
        assert wipe.purge_owner_planes(uid, now=4) == {'status': 'absent'}
        with cell.store.pool.connection() as conn:
            assert conn.execute('SELECT count(*) FROM cell_docs WHERE space_id=%s', (uid,)).fetchone()[0] == 0
        monkeypatch.setattr(cell.store, 'purge_space', real_purge)
    finally:
        monkeypatch.undo()
        directory.close()
        cell.close()


def test_stale_route_writer_cannot_recreate_after_purge(monkeypatch):
    directory, cell = make_directory(), make_cell_store()
    uid = directory.uid()
    cell.seeded.add(uid)
    other_pool = Pool(cells_dsn(), size=1)
    stale_writer = CellStore(other_pool)
    try:
        directory.store.get_or_create_personal_space(uid, cell='cell1', now=1)
        cell.store.enroll_space(uid, now=1)
        monkeypatch.setattr(router, 'directory_store', lambda: directory.store)
        monkeypatch.setattr(wipe, 'cell_store', lambda: cell.store)
        # An independent worker keeps this route even when the wiping worker
        # invalidates its own process cache. It outlives the drain and purge.
        other_worker_cache = {uid: 'cell'}
        assert wipe.purge_owner_planes(uid, now=2) == {'status': 'purged'}
        assert other_worker_cache[uid] == 'cell'
        with pytest.raises(CellSpaceUnavailable) as error:
            stale_writer.run(uid, lambda tx: tx.put('memories', 'late', {}), actor_uid=uid, now=3)
        assert error.value.retryable is True
        with pytest.raises(CellSpaceUnavailable):
            stale_writer.enroll_space(uid, now=3)
        # The cell authority must work in a separate interpreter too; it has
        # neither the wiping worker's process cache nor its invalidation calls.
        child = subprocess.run(
            [
                sys.executable,
                '-c',
                'import sys; from database.cells import CellStore; '
                'from database.cells.errors import CellSpaceUnavailable; '
                'from database.jobstore.connection import Pool; '
                'pool = Pool(sys.argv[1], size=1); store = CellStore(pool)\n'
                'try:\n'
                '    store.run(sys.argv[2], lambda tx: tx.put("memories", "child", {}), '
                'actor_uid=sys.argv[2], now=3)\n'
                'except CellSpaceUnavailable as error:\n'
                '    assert error.retryable\n'
                'else:\n'
                '    raise AssertionError("stale child route reopened wiped space")\n'
                'finally:\n'
                '    pool.close()\n',
                cells_dsn(),
                uid,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert child.returncode == 0, child.stderr
        with stale_writer.pool.connection() as conn:
            for table in ('cell_docs', 'change_log', 'sync_cursors', 'mutation_receipts'):
                assert conn.execute(f'SELECT count(*) FROM {table} WHERE space_id=%s', (uid,)).fetchone()[0] == 0
        assert wipe.purge_owner_planes(uid, now=4) == {'status': 'absent'}
    finally:
        other_pool.close()
        directory.close()
        cell.close()


def test_resolver_read_before_fence_cannot_enroll_after_purge(monkeypatch):
    directory, cell = make_directory(), make_cell_store()
    uid = directory.uid()
    cell.seeded.add(uid)
    read, resume = threading.Event(), threading.Event()
    real_get = directory.store.get_space
    try:
        directory.store.get_or_create_personal_space(uid, cell='cell1', now=1)
        cell.store.enroll_space(uid, now=1)
        monkeypatch.setattr(router, 'directory_store', lambda: directory.store)
        monkeypatch.setattr(router, 'cell_store', lambda: cell.store)
        monkeypatch.setattr(wipe, 'cell_store', lambda: cell.store)

        def old_row(owner):
            row = real_get(owner)
            if threading.current_thread() is not threading.main_thread():
                read.set()
                assert resume.wait(timeout=10)
            return row

        monkeypatch.setattr(directory.store, 'get_space', old_row)
        with ThreadPoolExecutor(max_workers=1) as executor:
            resolving = executor.submit(router.resolve, uid)
            try:
                assert read.wait(timeout=10)
                assert wipe.purge_owner_planes(uid, now=2) == {'status': 'purged'}
            finally:
                resume.set()
            with pytest.raises(router.DirectoryRoutingUnavailable):
                resolving.result(timeout=10)
        assert uid not in router._cache
        with pytest.raises(CellSpaceUnavailable):
            cell.store.run(uid, lambda tx: tx.put('memories', 'late', {}), actor_uid=uid, now=3)
    finally:
        resume.set()
        directory.close()
        cell.close()


@pytest.mark.parametrize('switch', [None, 'false', 'off', 'garbage'])
def test_wipe_kill_switch_blocks_before_io(monkeypatch, switch):
    if switch is None:
        monkeypatch.delenv('CELL_DIRECTORY_WIPE_ENABLED', raising=False)
    else:
        monkeypatch.setenv('CELL_DIRECTORY_WIPE_ENABLED', switch)
    monkeypatch.setattr(router, 'directory_store', Mock(side_effect=AssertionError('pool')))
    monkeypatch.setattr(wipe.users_db, 'get_user_deletion_wipe_status', Mock(side_effect=AssertionError('marker')))
    with pytest.raises(RuntimeError, match='wipe is disabled'):
        wipe.purge_owner_planes('owner')


@pytest.mark.parametrize(
    'route,enrolled',
    [('firestore', False), ('firestore', True), ('cell1', False), ('disabled', False), ('disabled', True)],
)
def test_no_destructive_work_without_explicit_enrollment(monkeypatch, route, enrolled):
    directory, cell = make_directory(), make_cell_store()
    uid = directory.uid()
    cell.seeded.add(uid)
    try:
        directory.store.get_or_create_personal_space(uid, cell=route, now=1)
        if enrolled:
            cell.store.enroll_space(uid, now=1)
        monkeypatch.setattr(router, 'directory_store', lambda: directory.store)
        monkeypatch.setattr(wipe, 'cell_store', lambda: cell.store)
        for name in ('tombstone_space', 'purge_space'):
            monkeypatch.setattr(cell.store, name, Mock(side_effect=AssertionError('destructive cell call')))
        monkeypatch.setattr(directory.store, 'set_routing', Mock(side_effect=AssertionError('route write')))
        monkeypatch.setattr(directory.store, 'purge_owner', Mock(side_effect=AssertionError('directory purge')))
        with pytest.raises(RuntimeError, match='requires .*enrollment'):
            wipe.purge_owner_planes(uid)
    finally:
        monkeypatch.undo()
        directory.close()
        cell.close()
