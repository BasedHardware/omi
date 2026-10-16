"""HTTP cap and wire contract; isolate the unchanged Redis Lua transport."""

from collections.abc import Iterator
from unittest.mock import MagicMock

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import redis_db, sync_jobs
from routers import sync as sync_router
from utils.sync import poll_limit


@pytest.fixture
def poll_lua(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    lua = MagicMock(return_value=[1, 1, 20])
    monkeypatch.setattr(redis_db, '_RATE_LIMIT_RESERVE_LUA', lua)
    return lua


@pytest.fixture
def poll_redis(monkeypatch: pytest.MonkeyPatch, poll_lua: MagicMock) -> fakeredis.FakeRedis:
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    redis = fakeredis.FakeRedis()
    # The generic atomic Lua transport is unchanged by this fix. Mock its reply,
    # while exercising reserve_rate_limit, the direct policy, and the real route.
    monkeypatch.setattr(sync_jobs, 'r', redis)
    return redis


@pytest.fixture
def poll_client(poll_redis: fakeredis.FakeRedis) -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(sync_router.router)
    app.dependency_overrides[sync_router.auth.get_current_user_uid] = lambda: 'owner'
    with TestClient(app) as client:
        yield client


def test_http_boundary_blocks_before_lookup_and_counts_requests(
    poll_client: TestClient, monkeypatch: pytest.MonkeyPatch, poll_lua: MagicMock
) -> None:
    poll_lua.side_effect = [[1, count, 20] for count in range(1, 41)] + [[0, 40, 20]]
    lookup = MagicMock(return_value={'job_id': 'job-1', 'uid': 'owner', 'status': 'queued'})
    monkeypatch.setattr(sync_router, 'get_sync_job', lookup)
    requests_before = sync_router.OMI_SYNC_JOB_POLL_REQUESTS_TOTAL._value.get()
    throttles_before = sync_router.OMI_SYNC_JOB_POLL_THROTTLED_TOTAL._value.get()
    for index in range(poll_limit.SYNC_POLL_MAX_REQUESTS):
        response = poll_client.get(f'/v2/sync-local-files/job-{index}')
        assert response.status_code == 200
        assert response.json()['status'] == 'queued'
        assert response.json()['job_id'] == 'job-1'
    response = poll_client.get('/v2/sync-local-files/unknown')
    assert response.status_code == 429
    assert response.headers['Retry-After'] == '20'
    assert response.json() == {'detail': 'Sync job polling too frequent; retry later'}
    assert lookup.call_count == 40
    for call in poll_lua.call_args_list:
        assert call.kwargs == {'keys': ['rl:sync_job_poll:owner'], 'args': [20, 40], 'client': None}
    assert sync_router.OMI_SYNC_JOB_POLL_REQUESTS_TOTAL._value.get() - requests_before == 41
    assert sync_router.OMI_SYNC_JOB_POLL_THROTTLED_TOTAL._value.get() - throttles_before == 1


def test_two_sane_client_bursts_fit_direct_ceiling(
    poll_client: TestClient,
    poll_redis: fakeredis.FakeRedis,
    poll_lua: MagicMock,
) -> None:
    redis = poll_redis
    sync_jobs.create_sync_job('owner', 1, 1, job_id='job-1')
    # Worst-case bursts: each instance uses its entire 18/min allowance at once.
    # Both instances' worst burst fits strictly below the directly enforced cap.
    assert 2 * 18 < poll_limit.SYNC_POLL_MAX_REQUESTS
    for _ in range(36):
        assert poll_client.get('/v2/sync-local-files/job-1').status_code == 200
    assert poll_lua.call_count == 36
    assert all(call.kwargs['args'] == [20, 40] for call in poll_lua.call_args_list)
    # Redis TTL expiry preserves the existing terminal HTTP response.
    redis.expire('sync_job:job-1', 0)
    response = poll_client.get('/v2/sync-local-files/job-1')
    assert response.status_code == 404
    assert response.json() == {'detail': 'Sync job not found or expired'}


def test_direct_cap_ignores_boost_shadow_and_separates_uids(
    poll_redis: fakeredis.FakeRedis, monkeypatch: pytest.MonkeyPatch, poll_lua: MagicMock
) -> None:
    monkeypatch.setenv('RATE_LIMIT_BOOST', '1000')
    monkeypatch.setenv('RATE_LIMIT_SHADOW_MODE', 'true')
    poll_lua.side_effect = [[1, 40, 1], [0, 40, 1], [1, 1, 20], [1, 1, 20]]
    assert poll_limit.admit_sync_job_poll('owner')
    assert not poll_limit.admit_sync_job_poll('owner')
    assert poll_limit.admit_sync_job_poll('other-owner')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    assert poll_limit.admit_sync_job_poll('owner')
    calls = poll_lua.call_args_list
    assert [call.kwargs['keys'] for call in calls] == [
        ['rl:sync_job_poll:owner'],
        ['rl:sync_job_poll:owner'],
        ['rl:sync_job_poll:other-owner'],
        ['rl:dev:sync_job_poll:owner'],
    ]
    assert all(call.kwargs['args'] == [20, 40] for call in calls)


def test_unknown_and_foreign_job_contract(poll_client: TestClient) -> None:
    response = poll_client.get('/v2/sync-local-files/unknown')
    assert response.status_code == 404
    assert response.json() == {'detail': 'Sync job not found or expired'}
    sync_jobs.create_sync_job('other-owner', 1, 1, job_id='foreign')
    assert poll_client.get('/v2/sync-local-files/foreign').status_code == 403


def test_redis_failure_preserves_poll_and_emits_fallback(
    poll_client: TestClient, monkeypatch: pytest.MonkeyPatch, poll_lua: MagicMock
) -> None:
    monkeypatch.setattr(redis_db, 'reserve_rate_limit', MagicMock(side_effect=RuntimeError('unavailable')))
    fallback = MagicMock()
    monkeypatch.setattr(poll_limit, 'record_fallback', fallback)
    sync_jobs.create_sync_job('owner', 1, 1, job_id='job-1')
    assert poll_client.get('/v2/sync-local-files/job-1').status_code == 200
    fallback.assert_called_once_with(
        component='redis_ratelimit',
        from_mode='sync_job_poll',
        to_mode='unlimited',
        reason='gate_unavailable',
        outcome='degraded',
    )


def test_server_backoff_http_wire_and_open_surface(poll_client, monkeypatch):
    monkeypatch.setenv('SYNC_POLL_BACKOFF_ENABLED', 'true')
    monkeypatch.setattr(sync_router, 'get_sync_job', lambda *_: {'job_id': 'j', 'uid': 'owner', 'status': 'queued'})
    response = poll_client.get('/v2/sync-local-files/j')
    assert response.status_code == 200 and response.json()['poll_after_ms'] == 60000
    response = poll_client.get('/v2/sync-local-files/j?surface_open=true')
    assert response.json()['poll_after_ms'] == 20000
    monkeypatch.setattr(sync_router, 'get_durable_job_status', lambda *_: {'job_id': 'j', 'status': 'completed'})
    assert poll_client.get('/v2/sync-local-files/j').json()['poll_after_ms'] == 0
