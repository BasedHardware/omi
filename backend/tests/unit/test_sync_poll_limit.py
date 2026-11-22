"""HTTP cap and wire contract; isolate the unchanged Redis Lua transport."""

import time
from collections import OrderedDict
from collections.abc import Iterator
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.repeat_work import poll_backoff_cohort
from database import redis_db, sync_jobs
from routers import sync as sync_router
from utils.metrics import (
    OMI_SYNC_JOB_COMPLETION_TO_FIRST_TERMINAL_READ_SECONDS,
    OMI_SYNC_JOB_POLL_ACTIVE_UPLOADERS,
    OMI_SYNC_JOB_POLL_COHORT_REQUESTS_TOTAL,
)
from utils.sync import poll_limit, poll_metrics


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
    monkeypatch.setenv('SYNC_POLL_BACKOFF_PERCENT', '100')
    monkeypatch.setattr(sync_router, 'get_sync_job', lambda *_: {'job_id': 'j', 'uid': 'owner', 'status': 'queued'})
    response = poll_client.get('/v2/sync-local-files/j')
    assert response.status_code == 200 and response.json()['poll_after_ms'] == 60000
    response = poll_client.get('/v2/sync-local-files/j?surface_open=true')
    assert response.json()['poll_after_ms'] == 20000
    monkeypatch.setattr(sync_router, 'get_durable_job_status', lambda *_: {'job_id': 'j', 'status': 'completed'})
    assert poll_client.get('/v2/sync-local-files/j').json()['poll_after_ms'] == 0


def _active_uploaders() -> dict[str, float]:
    (metric,) = OMI_SYNC_JOB_POLL_ACTIVE_UPLOADERS.collect()
    return {sample.labels['cohort']: sample.value for sample in metric.samples}


def test_partial_backoff_http_uses_uid_and_reports_rollout_metrics(poll_client, monkeypatch):
    monkeypatch.setenv('SYNC_POLL_BACKOFF_ENABLED', 'true')
    monkeypatch.setenv('SYNC_POLL_BACKOFF_PERCENT', '5')
    seed = uuid4().hex
    uid_in = next(f'{seed}-{index}' for index in range(1000) if poll_backoff_cohort(f'{seed}-{index}') == 'in')
    uid_out = next(
        f'{seed}-out-{index}' for index in range(1000) if poll_backoff_cohort(f'{seed}-out-{index}') == 'out'
    )
    active_uid = {'value': uid_out}
    poll_client.app.dependency_overrides[sync_router.auth.get_current_user_uid] = lambda: active_uid['value']
    monkeypatch.setattr(sync_router, 'get_durable_job_status', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        sync_router,
        'get_sync_job',
        lambda job_id: {'job_id': job_id, 'uid': active_uid['value'], 'status': 'queued'},
    )

    requests_in = OMI_SYNC_JOB_POLL_COHORT_REQUESTS_TOTAL.labels(cohort='in')._value.get()
    requests_out = OMI_SYNC_JOB_POLL_COHORT_REQUESTS_TOTAL.labels(cohort='out')._value.get()
    before_active = _active_uploaders()

    excluded = poll_client.get('/v2/sync-local-files/excluded')
    assert excluded.status_code == 200 and 'poll_after_ms' not in excluded.json()
    active_uid['value'] = uid_in
    admitted = poll_client.get('/v2/sync-local-files/admitted')
    assert admitted.status_code == 200 and admitted.json()['poll_after_ms'] == 60000
    assert OMI_SYNC_JOB_POLL_COHORT_REQUESTS_TOTAL.labels(cohort='in')._value.get() == requests_in + 1
    assert OMI_SYNC_JOB_POLL_COHORT_REQUESTS_TOTAL.labels(cohort='out')._value.get() == requests_out + 1
    assert _active_uploaders() == {'in': before_active['in'] + 1, 'out': before_active['out'] + 1}

    terminal_job_id = f'terminal-{uuid4().hex}'
    completed_at = datetime.fromtimestamp(time.time() - 10, timezone.utc)

    def durable_status(job_id, *_args, **_kwargs):
        if job_id == terminal_job_id:
            return {'job_id': job_id, 'status': 'completed', 'completed_at': completed_at}
        return None

    monkeypatch.setattr(sync_router, 'get_durable_job_status', durable_status)
    histogram = OMI_SYNC_JOB_COMPLETION_TO_FIRST_TERMINAL_READ_SECONDS.labels(cohort='in')
    before = histogram._sum.get()
    first_response = poll_client.get(f'/v2/sync-local-files/{terminal_job_id}')
    assert first_response.json()['poll_after_ms'] == 0
    assert 'completed_at' not in first_response.json()
    first_read_sum = histogram._sum.get()
    assert first_read_sum >= before + 9
    assert poll_client.get(f'/v2/sync-local-files/{terminal_job_id}').json()['poll_after_ms'] == 0
    assert histogram._sum.get() == first_read_sum


def test_active_uploader_scrape_expires_uids_without_another_poll(monkeypatch):
    monotonic = MagicMock(return_value=1000.0)
    monkeypatch.setattr(poll_metrics, 'time', SimpleNamespace(monotonic=monotonic))
    monkeypatch.setattr(poll_metrics, '_ACTIVE_UIDS', OrderedDict())
    monkeypatch.setattr(poll_metrics, '_ACTIVE_UID_COUNTS', {'in': 0, 'out': 0})
    monkeypatch.setenv('SYNC_POLL_BACKOFF_ENABLED', 'true')
    monkeypatch.setenv('SYNC_POLL_BACKOFF_PERCENT', '100')

    poll_metrics.record_active_sync_uploader('owner', {'status': 'queued'})
    assert _active_uploaders() == {'in': 1, 'out': 0}
    monotonic.return_value += poll_metrics.ACTIVE_UID_WINDOW_SECONDS + 1
    assert _active_uploaders() == {'in': 0, 'out': 0}


@pytest.mark.parametrize('surface_open', [False, True])
@pytest.mark.parametrize('backoff', ['true', 'false'])
def test_held_custody_poll_is_paced_even_with_open_surface_or_generic_backoff_off(monkeypatch, surface_open, backoff):
    monkeypatch.setenv('SYNC_POLL_BACKOFF_ENABLED', backoff)
    status = {'status': 'processing', 'reason_code': 'batch_unit_held', 'poll_after_ms': 300000}
    assert poll_limit.with_poll_hint(status, surface_open=surface_open)['poll_after_ms'] == 300000
