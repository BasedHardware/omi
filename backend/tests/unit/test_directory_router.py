"""Serving enrollment against isolated Postgres; no cloud identities or data."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
import time

import pytest
from fastapi import HTTPException, WebSocketException

from config import directory_routing
from database.directory import router
from database.cells import serving as cells_serving
from testing.cells_fixtures import make_directory
from utils.other import endpoints, plane_routing


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'new_owners')
    monkeypatch.setenv('DIRECTORY_ROUTING_NEW_OWNER_PERCENT', '0')
    monkeypatch.setattr(router, '_cache', {})
    cache = {}
    monkeypatch.setattr(router.redis_db, 'get_generic_cache', lambda key: cache.get(key))
    monkeypatch.setattr(router.redis_db, 'set_generic_cache', lambda key, value, ttl: cache.update({key: value}))
    monkeypatch.setattr(router.redis_db, 'delete_generic_cache', lambda key: cache.pop(key, None))
    monkeypatch.setattr(router.users_db, 'is_exists_user', lambda uid: False)
    monkeypatch.setattr(router.rollout_cohorts, 'runtime_percent', lambda name, env_default: env_default)
    monkeypatch.setattr(router, 'ramp_snapshot', lambda: SimpleNamespace(revision=7))
    return cache


@pytest.fixture
def harness(monkeypatch):
    harness = make_directory()
    monkeypatch.setattr(router, 'directory_store', lambda: harness.store)
    yield harness
    harness.close()


def fail(*args, **kwargs):
    raise AssertionError('unexpected IO')


def test_off_has_no_io_even_with_cached_route(monkeypatch):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'off')
    monkeypatch.setattr(router, 'Pool', fail)
    monkeypatch.setattr(cells_serving, 'Pool', fail)
    monkeypatch.setattr(router.redis_db, 'get_generic_cache', fail)
    router._remember('owner', 'cell')
    assert router.resolve('owner') == router.cached_plane('owner') == 'firestore'
    assert plane_routing.plane_for('owner') == 'firestore'
    assert not plane_routing.has_cell_plane()
    with pytest.raises(RuntimeError, match='off'):
        router.directory_store()
    with pytest.raises(RuntimeError, match='off'):
        cells_serving.cell_store()


@pytest.mark.parametrize('percent,plane,cell', [(0, 'firestore', 'firestore'), (100, 'cell', 'cell1')])
def test_sticky_new_owner(harness, monkeypatch, percent, plane, cell):
    uid = harness.uid()
    monkeypatch.setenv('DIRECTORY_ROUTING_NEW_OWNER_PERCENT', str(percent))
    assert router.resolve(uid, signup_platform='ios') == plane
    space = harness.store.get_space(uid)
    assert space.cell == cell
    assert space.ramp_bucket == router.cohort_bucket(uid, 'new-owner-cell1')
    assert space.ramp_revision == 7
    assert (space.signup_platform, space.signup_os) == ('mobile', 'ios')
    monkeypatch.setenv('DIRECTORY_ROUTING_NEW_OWNER_PERCENT', str(100 - percent))
    router.invalidate(uid)
    assert router.resolve(uid) == plane
    assert harness.store.get_space(uid) == space


def test_existing_owner_never_enrolls_cell(harness, monkeypatch):
    monkeypatch.setenv('DIRECTORY_ROUTING_NEW_OWNER_PERCENT', '100')
    monkeypatch.setattr(router.users_db, 'is_exists_user', lambda uid: True)
    uid = harness.uid()
    assert router.resolve(uid) == 'firestore'
    assert harness.store.get_space(uid).cell == 'firestore'


def test_concurrent_first_requests_share_winner(harness, monkeypatch):
    uid = harness.uid()
    monkeypatch.setenv('DIRECTORY_ROUTING_NEW_OWNER_PERCENT', '100')
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert list(executor.map(router.resolve, [uid, uid])) == ['cell', 'cell']
    with harness.store.pool.connection() as conn:
        assert conn.execute('SELECT count(*) FROM spaces WHERE space_id=%s', (uid,)).fetchone()[0] == 1


def test_process_hit_does_not_touch_redis_or_pg(monkeypatch):
    router._remember('owner', 'cell')
    monkeypatch.setattr(router.redis_db, 'get_generic_cache', fail)
    monkeypatch.setattr(router, 'directory_store', fail)
    assert router.resolve('owner') == router.cached_plane('owner') == 'cell'


def test_redis_hit_skips_pg(isolated, monkeypatch):
    isolated['plane:v1:owner'] = 'cell'
    monkeypatch.setattr(router, 'directory_store', fail)
    assert router.resolve('owner') == 'cell'
    assert router.cached_plane('owner') == 'cell'


def test_redis_outage_uses_pg(harness, monkeypatch):
    uid = harness.uid()
    harness.store.get_or_create_personal_space(uid, cell='cell1', now=1)
    monkeypatch.setattr(router.redis_db, 'get_generic_cache', Mock(side_effect=ConnectionError()))
    monkeypatch.setattr(router.redis_db, 'set_generic_cache', Mock(side_effect=ConnectionError()))
    assert router.resolve(uid) == 'cell'


def test_pg_outage_is_retryable_at_http_and_ws_boundary(monkeypatch):
    monkeypatch.setattr(router, 'directory_store', Mock(side_effect=ConnectionError()))
    with pytest.raises(router.DirectoryRoutingUnavailable):
        router.resolve('owner')
    with pytest.raises(HTTPException) as error:
        endpoints._resolve_request_plane_or_503('owner')
    assert error.value.status_code == 503
    assert error.value.detail == {'code': 'directory_routing_unavailable', 'retryable': True}
    with pytest.raises(WebSocketException) as error:
        endpoints._resolve_request_plane_ws('owner')
    assert error.value.code == 1013


def test_disabled_and_malformed_fail_closed(harness):
    uid = harness.uid()
    harness.store.get_or_create_personal_space(uid, cell='disabled', now=1)
    with pytest.raises(router.DirectoryRoutingUnavailable):
        router.resolve(uid)
    with pytest.raises(router.DirectoryRoutingUnavailable):
        router._plane_of(SimpleNamespace(cell=None))


def test_invalid_uid_does_not_enroll(harness):
    assert router.resolve('_ramp_reserved') == 'firestore'
    assert harness.store.get_space('_ramp_reserved') is None


def test_invalidate_both_tiers(isolated):
    router._remember('owner', 'cell')
    isolated['plane:v1:owner'] = 'cell'
    router.invalidate('owner')
    assert 'owner' not in router._cache
    assert 'plane:v1:owner' not in isolated


def test_cache_expiry_and_bound(monkeypatch):
    monkeypatch.setattr(router, 'PROCESS_MAX_ENTRIES', 2)
    for uid in ('a', 'b', 'c'):
        router._remember(uid, 'cell')
    assert len(router._cache) == 2
    assert router.cached_plane('a') == 'firestore'
    router._cache['b'] = (time.monotonic() - 1, 'cell')
    assert router.cached_plane('b') == 'firestore'


@pytest.mark.parametrize(
    'module,accessor,prefix', [(router, 'directory_store', 'DIRECTORY'), (cells_serving, 'cell_store', 'CELLS')]
)
def test_pool_lazy_singleton_and_clamp(monkeypatch, module, accessor, prefix):
    monkeypatch.setattr(module, '_store', None)
    monkeypatch.setenv(f'{prefix}_PG_DSN', 'local-test-dsn')
    monkeypatch.setenv(f'{prefix}_PG_POOL_SIZE', '99')
    pool = Mock()
    monkeypatch.setattr(module, 'Pool', pool)
    assert not pool.called
    first = getattr(module, accessor)()
    assert first is getattr(module, accessor)()
    pool.assert_called_once_with('local-test-dsn', size=2, connect=None)


def test_config_validates_and_clamps(monkeypatch):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'all')
    with pytest.raises(ValueError):
        directory_routing.mode()
    monkeypatch.setenv('DIRECTORY_PG_POOL_SIZE', '0')
    monkeypatch.setenv('CELLS_PG_POOL_SIZE', '99')
    monkeypatch.setenv('DIRECTORY_ROUTING_NEW_OWNER_PERCENT', '110')
    monkeypatch.setenv('CELL_WIPE_WRITER_DRAIN_SECONDS', '-1')
    assert directory_routing.directory_pool_size() == 1
    assert directory_routing.cell_pool_size() == 2
    assert directory_routing.new_owner_percent_env() == 100
    assert directory_routing.wipe_writer_drain_seconds() == 0


@pytest.mark.parametrize('name', ['get_current_user_uid', 'get_current_user_uid_no_byok_validation'])
def test_http_enrollment_precedes_platform_record(monkeypatch, name):
    calls = []
    monkeypatch.setattr(endpoints, 'verify_token', lambda token: 'owner')
    monkeypatch.setattr(endpoints, 'enforce_account_deletion_http_access', lambda uid: None)
    monkeypatch.setattr(endpoints, '_enforce_cutover_http_if_request', lambda *args: None)
    monkeypatch.setattr(endpoints, '_resolve_request_plane_or_503', lambda *args, **kwargs: calls.append('resolve'))
    monkeypatch.setattr(endpoints, 'record_user_platform', lambda *args: calls.append('record'))
    monkeypatch.setattr(endpoints, 'record_client_device', lambda *args, **kwargs: None)
    monkeypatch.setattr(endpoints, 'validate_byok_request', lambda uid: None)
    monkeypatch.setattr(endpoints, '_recover_locked_content_if_request', lambda *args: None)
    monkeypatch.setattr(endpoints, 'load_rollout_cohorts', lambda uid: None)
    assert getattr(endpoints, name)(authorization='Bearer token', x_app_platform='ios') == 'owner'
    assert calls == ['resolve', 'record']


@pytest.mark.parametrize(
    'module,accessor,prefix', [(router, 'directory_store', 'DIRECTORY'), (cells_serving, 'cell_store', 'CELLS')]
)
def test_iam_pool_uses_explicit_bindings(monkeypatch, module, accessor, prefix):
    monkeypatch.setattr(module, '_store', None)
    monkeypatch.delenv(f'{prefix}_PG_DSN', raising=False)
    for suffix, value in [('HOST', 'localhost'), ('DATABASE', 'synthetic'), ('USER', 'synthetic-user')]:
        monkeypatch.setenv(f'{prefix}_PG_{suffix}', value)
    connect = Mock()
    factory = Mock(return_value=connect)
    pool = Mock()
    monkeypatch.setattr(module, 'iam_connector', factory)
    monkeypatch.setattr(module, 'Pool', pool)
    getattr(module, accessor)()
    factory.assert_called_once_with('localhost', 'synthetic', 'synthetic-user')
    pool.assert_called_once_with('', size=2, connect=connect)
