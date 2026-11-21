"""Required wipe fencing, failure propagation and real cell/directory purge."""

from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import threading
from unittest.mock import Mock

import pytest
import fakeredis

from database.directory import router, wipe
from database.directory.store import OwnerTombstoned
from database.cells import CellStore
from database.cells.errors import CellSpaceUnavailable
from database.jobstore.connection import Pool
from testing.cells_fixtures import cells_dsn
from testing.cells_fixtures import make_cell_store, make_directory


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'new_owners')
    monkeypatch.setenv('DIRECTORY_PG_DSN', 'synthetic-configured-directory')
    monkeypatch.setenv('CELL_WIPE_WRITER_DRAIN_SECONDS', '0')
    monkeypatch.setenv('CELL_DIRECTORY_WIPE_ENABLED', 'true')
    monkeypatch.setattr(wipe.users_db, 'get_user_deletion_wipe_status', lambda uid: 'running')
    monkeypatch.setattr(router, '_cache', {})
    monkeypatch.setattr(router.redis_db, 'r', fakeredis.FakeRedis())
    monkeypatch.setattr(router.redis_db, 'get_generic_cache', lambda key: None)
    monkeypatch.setattr(router.redis_db, 'delete_generic_cache', lambda key: None)


@pytest.mark.parametrize('routing_mode', ['off', 'new_owners'])
def test_unconfigured_constructs_nothing(monkeypatch, routing_mode):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', routing_mode)
    for name in ('DSN', 'HOST', 'DATABASE', 'USER'):
        monkeypatch.delenv(f'DIRECTORY_PG_{name}', raising=False)
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
        monkeypatch.setattr(router, 'directory_store', lambda **kwargs: directory.store)
        events = []
        monkeypatch.setattr(wipe, 'cell_store', lambda **kwargs: cell.store)
        real_purge = cell.store.purge_space

        def purge(owner):
            space = directory.store.get_space(owner)
            # A retry after a completed wipe re-purges from the retained tombstone route.
            if space is not None:
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
        assert wipe.purge_owner_planes(uid, now=4) == {'status': 'purged'}
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
        monkeypatch.setattr(router, 'directory_store', lambda **kwargs: directory.store)
        monkeypatch.setattr(wipe, 'cell_store', lambda **kwargs: cell.store)
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
        assert wipe.purge_owner_planes(uid, now=4) == {'status': 'purged'}
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
        monkeypatch.setattr(router, 'directory_store', lambda **kwargs: directory.store)
        monkeypatch.setattr(router, 'cell_store', lambda **kwargs: cell.store)
        monkeypatch.setattr(wipe, 'cell_store', lambda **kwargs: cell.store)

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
    [('disabled', False), ('disabled', True)],
)
def test_no_destructive_work_without_explicit_enrollment(monkeypatch, route, enrolled):
    directory, cell = make_directory(), make_cell_store()
    uid = directory.uid()
    cell.seeded.add(uid)
    try:
        directory.store.get_or_create_personal_space(uid, cell=route, now=1)
        if enrolled:
            cell.store.enroll_space(uid, now=1)
        monkeypatch.setattr(router, 'directory_store', lambda **kwargs: directory.store)
        monkeypatch.setattr(wipe, 'cell_store', lambda **kwargs: cell.store)
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


def test_interrupted_wipe_with_disabled_route_resumes_from_cell_tombstone(monkeypatch):
    directory, cell = make_directory(), make_cell_store()
    uid = directory.uid()
    cell.seeded.add(uid)
    try:
        directory.store.get_or_create_personal_space(uid, cell='cell1', now=1)
        cell.store.enroll_space(uid, now=1)
        cell.store.run(uid, lambda tx: tx.put('memories', 'm1', {'text': 'synthetic'}), actor_uid=uid, now=1)
        # An earlier wipe fenced the cell and disabled the route, then stopped before any owner tombstone row.
        cell.store.tombstone_space(uid)
        directory.store.set_routing(uid, cell='disabled', bump_epoch=True, now=2)
        monkeypatch.setattr(router, 'directory_store', lambda **kwargs: directory.store)
        monkeypatch.setattr(wipe, 'cell_store', lambda **kwargs: cell.store)
        assert wipe.purge_owner_planes(uid, now=3) == {'status': 'purged'}
        assert directory.store.get_space(uid) is None
        with cell.store.pool.connection() as conn:
            assert conn.execute('SELECT count(*) FROM cell_docs WHERE space_id=%s', (uid,)).fetchone()[0] == 0
        assert wipe.purge_owner_planes(uid, now=4) == {'status': 'purged'}
    finally:
        directory.close()
        cell.close()


@pytest.mark.parametrize('routing_mode', ['off', 'new_owners'])
def test_configured_directory_outage_fails_in_every_mode(monkeypatch, routing_mode):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', routing_mode)
    monkeypatch.setattr(router, 'directory_store', Mock(side_effect=ConnectionError('down')))
    with pytest.raises(ConnectionError, match='down'):
        wipe.purge_owner_planes('owner')


@pytest.mark.parametrize('routing_mode', ['off', 'new_owners'])
def test_configured_wipe_purges_cell_in_every_mode(monkeypatch, routing_mode):
    directory, cell = make_directory(), make_cell_store()
    uid = directory.uid()
    cell.seeded.add(uid)
    try:
        directory.store.get_or_create_personal_space(uid, cell='cell1', now=1)
        cell.store.enroll_space(uid, now=1)
        cell.store.run(uid, lambda tx: tx.put('memories', 'm1', {'text': 'synthetic'}), actor_uid=uid, now=1)
        monkeypatch.setenv('DIRECTORY_ROUTING_MODE', routing_mode)
        monkeypatch.setattr(router, '_store', directory.store)
        monkeypatch.setattr(wipe, 'cell_store', lambda **kwargs: cell.store)
        assert wipe.purge_owner_planes(uid, now=2) == {'status': 'purged'}
        assert directory.store.get_space(uid) is None
        assert cell.store.read_doc(uid, 'memories', 'm1') == {}
        with cell.store.pool.connection() as conn:
            assert conn.execute('SELECT tombstoned FROM space_heads WHERE space_id=%s', (uid,)).fetchone() == (True,)
    finally:
        directory.close()
        cell.close()


def test_firestore_owner_wipe_tombstones_without_cell_io(monkeypatch):
    directory = make_directory()
    uid = directory.uid()
    try:
        directory.store.get_or_create_personal_space(uid, cell='firestore', now=1)
        directory.store.upsert_token(uid, 'phone', uid + ':token', now=1)
        monkeypatch.setattr(router, 'directory_store', lambda **kwargs: directory.store)
        monkeypatch.setattr(wipe, 'cell_store', Mock(side_effect=AssertionError('cell IO')))
        assert wipe.purge_owner_planes(uid, now=2) == {'status': 'purged'}
        assert directory.store.get_space(uid) is None
        assert directory.store.tokens_for_uid(uid) == []
        fence = directory.store.tombstone_owner(uid, now=3)
        assert (fence.wipe_epoch, fence.cell, fence.created_at) == (2, 'firestore', 2)
        with pytest.raises(OwnerTombstoned):
            directory.store.get_or_create_personal_space(uid, cell='cell1', now=3)
        assert wipe.purge_owner_planes(uid, now=4) == {'status': 'purged'}
    finally:
        directory.close()


def test_absent_owner_old_epoch_request_cannot_enroll_after_wipe(monkeypatch):
    directory, cell = make_directory(), make_cell_store()
    uid = directory.uid()
    cell.seeded.add(uid)
    read, resume = threading.Event(), threading.Event()
    real_get = directory.store.get_space
    try:
        monkeypatch.setattr(router, 'directory_store', lambda **kwargs: directory.store)
        monkeypatch.setattr(router, 'cell_store', lambda: cell.store)
        monkeypatch.setattr(wipe, 'cell_store', Mock(side_effect=AssertionError('absent owner cell IO')))
        monkeypatch.setattr(router.users_db, 'is_exists_user', lambda uid: False)
        monkeypatch.setattr(router.rollout_cohorts, 'runtime_percent', lambda *args, **kwargs: 100)

        def old_absence(owner):
            row = real_get(owner)
            assert row is None
            read.set()
            assert resume.wait(timeout=10)
            return row

        monkeypatch.setattr(directory.store, 'get_space', old_absence)
        with ThreadPoolExecutor(max_workers=1) as executor:
            resolving = executor.submit(router.resolve, uid)
            try:
                assert read.wait(timeout=10)
                old_epoch = router._route_epoch(uid)
                assert wipe.purge_owner_planes(uid, now=2) == {'status': 'absent'}
                assert router._route_epoch(uid) != old_epoch
            finally:
                resume.set()
            with pytest.raises(router.DirectoryRoutingUnavailable):
                resolving.result(timeout=10)
        assert uid not in router._cache
        assert real_get(uid) is None
        fence = directory.store.tombstone_owner(uid, now=3)
        assert (fence.wipe_epoch, fence.cell, fence.created_at) == (1, None, 2)
        with pytest.raises(OwnerTombstoned):
            directory.store.get_or_create_personal_space(uid, cell='firestore', now=3)
        with cell.store.pool.connection() as conn:
            assert conn.execute('SELECT 1 FROM space_heads WHERE space_id=%s', (uid,)).fetchone() is None
    finally:
        resume.set()
        directory.close()
        cell.close()


def test_directory_create_before_first_cell_enrollment_is_wipeable(monkeypatch):
    directory, cell = make_directory(), make_cell_store()
    uid = directory.uid()
    cell.seeded.add(uid)
    try:
        directory.store.get_or_create_personal_space(uid, cell='cell1', now=1)
        monkeypatch.setattr(router, 'directory_store', lambda **kwargs: directory.store)
        monkeypatch.setattr(wipe, 'cell_store', lambda **kwargs: cell.store)
        assert wipe.purge_owner_planes(uid, now=2) == {'status': 'purged'}
        enroll = Mock()
        with pytest.raises(OwnerTombstoned):
            directory.store.enroll_cell(uid, enroll)
        enroll.assert_not_called()
        with pytest.raises(CellSpaceUnavailable):
            cell.store.enroll_space(uid, now=3)
    finally:
        directory.close()
        cell.close()
