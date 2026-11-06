"""Required wipe fencing, failure propagation and real cell/directory purge."""

from unittest.mock import Mock

import pytest

from database.directory import router, wipe
from testing.cells_fixtures import make_cell_store, make_directory


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'new_owners')
    monkeypatch.setenv('CELL_WIPE_WRITER_DRAIN_SECONDS', '0')
    monkeypatch.setattr(wipe.users_db, 'get_user_deletion_wipe_status', lambda uid: 'running')
    monkeypatch.setattr(router, '_cache', {})
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
        directory.store.get_or_create_personal_space(uid, now=1)
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
