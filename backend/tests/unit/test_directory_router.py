"""Serving enrollment against isolated Postgres; no cloud identities or data."""

import asyncio
import dependencies
import importlib.util
import fakeredis
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock
import time

import pytest
from fastapi import HTTPException, WebSocketException

from config import directory_routing
from database.directory import router
from database.cells import serving as cells_serving
from testing.cells_fixtures import make_cell_store, make_directory
from utils.other import endpoints, plane_routing


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'new_owners')
    monkeypatch.setenv('DIRECTORY_ROUTING_NEW_OWNER_PERCENT', '0')
    monkeypatch.setattr(router, '_cache', {})
    monkeypatch.setattr(router.redis_db, 'r', fakeredis.FakeRedis())
    monkeypatch.setattr(router, 'cell_store', lambda: Mock())
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
    cell = make_cell_store()
    monkeypatch.setattr(router, 'cell_store', lambda: cell.store)
    yield harness
    cell.seeded.update(harness.seeded)
    cell.close()
    harness.close()


def fail(*args, **kwargs):
    raise AssertionError('unexpected IO')


@pytest.mark.parametrize('plane', ['cells', 'directory'])
@pytest.mark.parametrize('use_dsn', [False, True], ids=['iam', 'dsn'])
@pytest.mark.parametrize('pool_size', [1, 2])
def test_runtime_keeps_lazy_singleton_pool(monkeypatch, plane, use_dsn, pool_size):
    module = cells_serving if plane == 'cells' else router
    get_store = module.cell_store if plane == 'cells' else module.directory_store
    prefix = 'CELLS' if plane == 'cells' else 'DIRECTORY'
    dsn = 'postgresql://runtime-pooler/runtime-db' if use_dsn else ''
    monkeypatch.setattr(module, '_store', None)
    monkeypatch.setenv(f'{prefix}_PG_DSN', dsn)
    monkeypatch.setenv(f'{prefix}_PG_HOST', 'runtime-pooler')
    monkeypatch.setenv(f'{prefix}_PG_DATABASE', 'runtime-db')
    monkeypatch.setenv(f'{prefix}_PG_USER', 'runtime-data-only@project.iam')
    monkeypatch.setenv(f'{prefix}_PG_POOL_SIZE', str(pool_size))
    dial = Mock(side_effect=AssertionError('runtime must not dial before pool checkout'))
    connector = Mock(return_value=dial)
    pool = Mock()
    pool_factory = Mock(return_value=pool)
    monkeypatch.setattr(module, 'iam_connector', connector)
    monkeypatch.setattr(module, 'Pool', pool_factory)

    store = get_store()

    assert get_store() is store
    assert store.pool is pool
    pool_factory.assert_called_once_with(dsn, size=pool_size, connect=None if use_dsn else dial)
    if use_dsn:
        connector.assert_not_called()
    else:
        connector.assert_called_once_with('runtime-pooler', 'runtime-db', 'runtime-data-only@project.iam')
    dial.assert_not_called()


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


def test_process_hit_checks_one_epoch_get_without_pg(monkeypatch):
    router.redis_db.r.set(router._epoch_key('owner'), 'epoch')
    router._remember('owner', 'cell', 'epoch')
    get = Mock(wraps=router.redis_db.r.get)
    monkeypatch.setattr(router.redis_db.r, 'get', get)
    monkeypatch.setattr(router.redis_db, 'get_generic_cache', fail)
    monkeypatch.setattr(router, 'directory_store', fail)
    assert router.resolve('owner') == router.cached_plane('owner') == 'cell'
    get.assert_called_once_with(router._epoch_key('owner'))


def test_redis_hit_skips_pg(isolated, monkeypatch):
    router.redis_db.r.set(router._epoch_key('owner'), 'epoch')
    isolated['plane:v1:owner'] = {'plane': 'cell', 'epoch': 'epoch'}
    monkeypatch.setattr(router, 'directory_store', fail)
    assert router.resolve('owner') == 'cell'
    assert router.cached_plane('owner') == 'cell'


def test_redis_outage_fails_closed(harness, monkeypatch):
    uid = harness.uid()
    harness.store.get_or_create_personal_space(uid, cell='cell1', now=1)
    monkeypatch.setattr(router.redis_db.r, 'get', Mock(side_effect=ConnectionError()))
    monkeypatch.setattr(router, 'directory_store', fail)
    with pytest.raises(router.DirectoryRoutingUnavailable):
        router.resolve(uid)


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


def test_invalid_mode_is_retryable_at_http_and_ws_boundary(monkeypatch):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'typo')
    with pytest.raises(HTTPException) as error:
        endpoints._resolve_request_plane_or_503('owner')
    assert error.value.status_code == 503
    assert error.value.detail == {'code': 'directory_routing_unavailable', 'retryable': True}
    with pytest.raises(WebSocketException) as error:
        endpoints._resolve_request_plane_ws('owner')
    assert error.value.code == 1013
    assert error.value.reason == 'directory_routing_unavailable'


@pytest.mark.parametrize('routing_mode', ['off', 'new_owners', 'typo'])
@pytest.mark.parametrize(
    'name', ['get_current_user_id', 'get_uid_from_mcp_api_key', 'get_mcp_api_key_auth', 'get_api_key_auth']
)
def test_async_http_routing_submits_only_when_on(monkeypatch, routing_mode, name):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', routing_mode)
    submitted = []

    async def run(pool, fn, *args, **kwargs):
        submitted.append(fn)
        if fn is dependencies.auth.verify_id_token:
            return {'uid': 'owner'}
        if fn in (
            dependencies.mcp_api_key_db.get_api_key_auth_result,
            dependencies.dev_api_key_db.get_api_key_auth_result,
        ):
            return SimpleNamespace(context={'user_id': 'owner'}, repairs=())
        if fn is endpoints._resolve_request_plane_or_503 and routing_mode == 'typo':
            return fn(*args, **kwargs)
        return None

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(dependencies, 'run_blocking', run)
    for helper in (
        '_enforce_account_deletion_access',
        '_enforce_cutover_access',
        '_enforce_ladder_api',
        '_check_api_key_rate_limit_async',
    ):
        monkeypatch.setattr(dependencies, helper, noop)
    monkeypatch.setattr(dependencies, 'wrong_key_family_detail', lambda *args: None)
    monkeypatch.setattr(dependencies, 'malformed_api_key_detail', lambda *args: None)
    monkeypatch.setattr(dependencies, 'record_api_key_repairs', lambda **kwargs: None)
    kwargs = (
        {'credentials': SimpleNamespace(credentials='synthetic')}
        if name == 'get_current_user_id'
        else {'api_key': 'Bearer synthetic'}
    )
    if routing_mode == 'typo':
        with pytest.raises(HTTPException) as error:
            asyncio.run(getattr(dependencies, name)(**kwargs))
        assert error.value.status_code == 503
        assert error.value.detail == {'code': 'directory_routing_unavailable', 'retryable': True}
    else:
        result = asyncio.run(getattr(dependencies, name)(**kwargs))
        assert (result if isinstance(result, str) else result.uid) == 'owner'
    resolver = endpoints._resolve_request_plane_or_503
    assert submitted.count(resolver) == int(routing_mode != 'off')
    assert len(submitted) == 1 + int(routing_mode != 'off')


@pytest.mark.parametrize('routing_mode', ['off', 'new_owners', 'typo'])
@pytest.mark.parametrize('name', ['get_current_user_uid_ws_listen', 'get_current_user_uid_from_ws_message'])
def test_async_ws_routing_submits_only_when_on(monkeypatch, routing_mode, name):
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', routing_mode)
    submitted = []

    async def run(pool, fn, *args, **kwargs):
        submitted.append(fn)
        if fn is endpoints._resolve_request_plane_ws and routing_mode == 'typo':
            return fn(*args, **kwargs)
        return None

    async def verified(*args, **kwargs):
        return 'owner'

    monkeypatch.setattr(endpoints, 'run_blocking', run)
    monkeypatch.setattr(endpoints, 'run_critical_ws', verified)
    monkeypatch.setattr(endpoints, 'cutover_enforcement_enabled', lambda: False)
    kwargs = (
        {'message': {'type': 'auth', 'token': 'synthetic'}}
        if name.endswith('message')
        else {'authorization': 'Bearer synthetic'}
    )
    if routing_mode == 'typo':
        with pytest.raises(WebSocketException) as error:
            asyncio.run(getattr(endpoints, name)(**kwargs))
        assert error.value.code == 1013
        assert error.value.reason == 'directory_routing_unavailable'
    else:
        assert asyncio.run(getattr(endpoints, name)(**kwargs)) == 'owner'
    assert submitted == [endpoints.enforce_account_deletion_ws_access] + (
        [endpoints._resolve_request_plane_ws] if routing_mode != 'off' else []
    )


@pytest.fixture
def peer_resolver(monkeypatch, harness):
    # A second loaded resolver has its own globals/cache, like another worker.
    spec = importlib.util.spec_from_file_location('peer_directory_router', router.__file__)
    peer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(peer)
    monkeypatch.setattr(peer, 'directory_store', lambda: harness.store)
    monkeypatch.setattr(peer, 'cell_store', lambda: Mock())
    return peer


@pytest.mark.parametrize('destination', ['cell1', 'disabled'])
def test_route_flip_reaches_two_warm_resolvers(harness, peer_resolver, destination):
    uid = harness.uid()
    harness.store.get_or_create_personal_space(uid, cell='firestore', now=1)
    assert router.resolve(uid) == peer_resolver.resolve(uid) == 'firestore'
    old_epoch = peer_resolver._cache[uid][2]
    harness.store.set_routing(uid, cell=destination, bump_epoch=True, now=2)
    router.invalidate(uid)
    assert peer_resolver._cache[uid][2] == old_epoch
    for resolver in (router, peer_resolver):
        if destination == 'disabled':
            with pytest.raises(resolver.DirectoryRoutingUnavailable):
                resolver.resolve(uid)
        else:
            assert resolver.resolve(uid) == 'cell'
            assert resolver._cache[uid][2] != old_epoch


def test_stale_read_cannot_poison_post_flip_cache(harness, peer_resolver, monkeypatch):
    uid = harness.uid()
    harness.store.get_or_create_personal_space(uid, cell='firestore', now=1)
    original = harness.store.get_space

    def flip_after_read(owner):
        stale = original(owner)
        harness.store.set_routing(owner, cell='cell1', bump_epoch=True, now=2)
        router.invalidate(owner)
        return stale

    with monkeypatch.context() as patch:
        patch.setattr(harness.store, 'get_space', flip_after_read)
        assert peer_resolver.resolve(uid) == 'firestore'  # Already-admitted request.
    assert peer_resolver.resolve(uid) == router.resolve(uid) == 'cell'


def test_epoch_loss_rejects_both_stale_cache_tiers(harness, isolated):
    uid = harness.uid()
    harness.store.get_or_create_personal_space(uid, cell='firestore', now=1)
    assert router.resolve(uid) == 'firestore'
    stale = isolated[f'plane:v1:{uid}']
    harness.store.set_routing(uid, cell='cell1', bump_epoch=True, now=2)
    router.redis_db.r.delete(router._epoch_key(uid))
    assert router.resolve(uid) == 'cell'
    assert isolated[f'plane:v1:{uid}']['epoch'] != stale['epoch']


def test_warm_resolver_and_invalidation_fail_closed_on_redis_loss(monkeypatch):
    router.redis_db.r.set(router._epoch_key('owner'), 'epoch')
    router._remember('owner', 'cell', 'epoch')
    monkeypatch.setattr(router.redis_db.r, 'get', Mock(side_effect=ConnectionError()))
    with pytest.raises(router.DirectoryRoutingUnavailable):
        router.resolve('owner')
    with pytest.raises(HTTPException) as error:
        endpoints._resolve_request_plane_or_503('owner')
    assert error.value.status_code == 503
    with pytest.raises(WebSocketException) as error:
        endpoints._resolve_request_plane_ws('owner')
    assert error.value.code == 1013
    monkeypatch.setattr(router.redis_db.r, 'set', Mock(side_effect=ConnectionError()))
    with pytest.raises(router.DirectoryRoutingUnavailable):
        router.invalidate('owner')


@pytest.mark.parametrize('prefix', ['DIRECTORY', 'CELLS'])
def test_wipe_accessor_available_when_routing_off(monkeypatch, prefix):
    module = router if prefix == 'DIRECTORY' else cells_serving
    accessor = module.directory_store if prefix == 'DIRECTORY' else module.cell_store
    monkeypatch.setenv('DIRECTORY_ROUTING_MODE', 'off')
    monkeypatch.setenv(f'{prefix}_PG_DSN', 'synthetic-local-dsn')
    monkeypatch.setattr(module, '_store', None)
    pool = Mock()
    monkeypatch.setattr(module, 'Pool', pool)
    with pytest.raises(RuntimeError, match='off'):
        accessor()
    pool.assert_not_called()
    assert accessor(for_wipe=True) is accessor(for_wipe=True)
    pool.assert_called_once_with('synthetic-local-dsn', size=2, connect=None)


@pytest.mark.parametrize('suffix', ['DSN', 'HOST', 'DATABASE', 'USER'])
def test_partial_directory_binding_requires_erasure(monkeypatch, suffix):
    for name in ('DSN', 'HOST', 'DATABASE', 'USER'):
        monkeypatch.delenv(f'DIRECTORY_PG_{name}', raising=False)
    assert not directory_routing.directory_configured()
    monkeypatch.setenv(f'DIRECTORY_PG_{suffix}', 'synthetic-binding')
    assert directory_routing.directory_configured()


@pytest.mark.parametrize(
    'path',
    [
        '/v1/account/cutover/control',
        '/v1/auth/refresh',
        '/v1/users/delete-account',
        '/v2/desktop/update-policy',
        '/v1/updates/check',
        '/health',
        '/v1/health',
    ],
)
@pytest.mark.parametrize(
    'name',
    [
        'get_current_user_uid',
        'get_current_user_uid_readonly',
        'get_current_user_uid_no_byok_validation',
    ],
)
def test_cutover_exempt_auth_does_not_resolve_product_plane(monkeypatch, name, path):
    monkeypatch.setattr(endpoints, 'verify_token', lambda token: 'owner')
    monkeypatch.setattr(endpoints, 'enforce_account_deletion_http_access', lambda uid: None)
    monkeypatch.setattr(endpoints, '_enforce_cutover_http_if_request', lambda *args: None)
    monkeypatch.setattr(endpoints, 'record_user_platform', lambda *args: None)
    monkeypatch.setattr(endpoints, 'record_client_device', lambda *args, **kwargs: None)
    monkeypatch.setattr(endpoints, 'validate_byok_request', lambda uid: None)
    monkeypatch.setattr(endpoints, '_recover_locked_content_if_request', lambda *args: None)
    monkeypatch.setattr(endpoints, 'load_rollout_cohorts', lambda uid: None)
    resolver = Mock(side_effect=router.DirectoryRoutingUnavailable('directory down'))
    monkeypatch.setattr(router, 'resolve', resolver)
    request = SimpleNamespace(method='GET', url=SimpleNamespace(path=path))
    assert getattr(endpoints, name)(authorization='Bearer token', request=request) == 'owner'
    resolver.assert_not_called()
    # The exemption must not extend to a product route or lookalike prefix.
    for product_path in ('/v1/memories', '/v1/account/cutover-unsafe'):
        request.url.path = product_path
        with pytest.raises(HTTPException) as error:
            getattr(endpoints, name)(authorization='Bearer token', request=request)
        assert error.value.status_code == 503


@pytest.mark.parametrize(
    'name',
    [
        'get_current_user_id',
        'get_uid_from_mcp_api_key',
        'get_mcp_api_key_auth',
        'get_api_key_auth',
    ],
)
def test_async_cutover_exempt_auth_reaches_control_during_directory_outage(monkeypatch, name):
    async def run(pool, fn, *args, **kwargs):
        if fn is dependencies.auth.verify_id_token:
            return {'uid': 'owner'}
        if fn in (
            dependencies.mcp_api_key_db.get_api_key_auth_result,
            dependencies.dev_api_key_db.get_api_key_auth_result,
        ):
            return SimpleNamespace(context={'user_id': 'owner'}, repairs=())
        return fn(*args, **kwargs)

    async def noop(*args, **kwargs):
        return None

    monkeypatch.setattr(dependencies, 'run_blocking', run)
    for helper in (
        '_enforce_account_deletion_access',
        '_enforce_cutover_access',
        '_enforce_ladder_api',
        '_check_api_key_rate_limit_async',
    ):
        monkeypatch.setattr(dependencies, helper, noop)
    for helper in ('wrong_key_family_detail', 'malformed_api_key_detail'):
        monkeypatch.setattr(dependencies, helper, lambda *args: None)
    monkeypatch.setattr(dependencies, 'record_api_key_repairs', lambda **kwargs: None)
    resolver = Mock(side_effect=router.DirectoryRoutingUnavailable('directory down'))
    monkeypatch.setattr(router, 'resolve', resolver)
    kwargs = (
        {'credentials': SimpleNamespace(credentials='synthetic')}
        if name == 'get_current_user_id'
        else {'api_key': 'Bearer synthetic'}
    )
    kwargs['request'] = SimpleNamespace(url=SimpleNamespace(path='/v1/account/cutover/control'))
    result = asyncio.run(getattr(dependencies, name)(**kwargs))
    assert (result if isinstance(result, str) else result.uid) == 'owner'
    resolver.assert_not_called()
