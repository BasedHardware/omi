"""Credential and window gating for the X-connector periodic sweep.

The notifications job fires every minute; the X sweep must not walk the
connected-user registry when no X OAuth app is configured, must run at most
once per 6h window, and must not burn RapidAPI retries when that fallback's
credentials are unset.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from database import redis_db
from utils import social, x_connector
from utils.other import jobs


async def _inline_run_blocking(_executor, func, *args, **kwargs):
    return func(*args, **kwargs)


def _patch_start_job_neighbors(monkeypatch):
    monkeypatch.setattr(jobs, 'should_run_daily_notification_job', lambda: False)
    monkeypatch.setattr(jobs, 'run_scheduled_check', lambda: None)
    monkeypatch.setattr(jobs, 'run_redis_memory_check', lambda: None)
    monkeypatch.setattr(jobs, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(jobs, 'should_run_x_sync_job', lambda: True)


async def test_sweep_skipped_when_oauth_not_configured(monkeypatch):
    sweep_calls = []

    _patch_start_job_neighbors(monkeypatch)
    monkeypatch.setattr(jobs.x_connector, 'is_oauth_configured', lambda: False)

    async def record_sweep(**kwargs):
        sweep_calls.append(kwargs)

    monkeypatch.setattr(jobs, 'run_x_sync_job', record_sweep)

    await jobs.start_job()

    assert sweep_calls == []


async def test_sweep_runs_when_oauth_configured(monkeypatch):
    sweep_calls = []

    _patch_start_job_neighbors(monkeypatch)
    monkeypatch.setattr(jobs.x_connector, 'is_oauth_configured', lambda: True)

    async def record_sweep(**kwargs):
        sweep_calls.append(kwargs)

    monkeypatch.setattr(jobs, 'run_x_sync_job', record_sweep)

    await jobs.start_job()

    assert len(sweep_calls) == 1
    assert 'job_started_at' in sweep_calls[0]


class FakeRedis:
    """Dict-backed stand-in for the redis client covering SET with NX/EX."""

    def __init__(self):
        self.store: dict = {}

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = (value, ex)
        return True


class _Registry:
    def __init__(self, ids):
        self._ids = ids

    def stream(self):
        return [SimpleNamespace(id=uid) for uid in self._ids]


class _FakeDb:
    def __init__(self, ids):
        self._ids = ids

    def collection(self, _name):
        return _Registry(self._ids)


def _patch_sweep_internals(monkeypatch, uids):
    monkeypatch.setattr(x_connector, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(x_connector, 'db', _FakeDb(uids))
    monkeypatch.setattr(x_connector, 'PromotionFlexRunRouter', lambda **_kwargs: None)
    monkeypatch.setattr(x_connector, '_SYNC_JOB_USER_SPACING_SEC', 0)
    synced = []

    async def fake_sync(uid, **_kwargs):
        synced.append(uid)
        return {'success': True, 'new_posts': 2}

    monkeypatch.setattr(x_connector, 'sync_x_for_user', fake_sync)
    return synced


async def test_window_lock_admits_a_single_sweep_per_window(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(redis_db, 'r', fake_redis)
    synced = _patch_sweep_internals(monkeypatch, ['uid-1'])

    first = await x_connector.run_x_sync_job()
    second = await x_connector.run_x_sync_job()

    assert first == {'users': 1, 'synced': 1, 'new_posts': 2}
    assert second['skipped'] == 'window_lock'
    assert second['users'] == 0
    assert synced == ['uid-1']


def test_x_sync_window_lock_redis_semantics(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(redis_db, 'r', fake_redis)

    assert redis_db.try_acquire_x_sync_window_lock('2026-09-18', 0) is True
    assert redis_db.try_acquire_x_sync_window_lock('2026-09-18', 0) is False
    # A different window or day is a different lock.
    assert redis_db.try_acquire_x_sync_window_lock('2026-09-18', 1) is True
    assert redis_db.try_acquire_x_sync_window_lock('2026-09-19', 0) is True

    value, ttl = fake_redis.store['notifications_job:x_sync_lock:2026-09-18:0']
    assert value == '1'
    # TTL slightly over one 6h window: bounds a crashed holder's blackout.
    assert ttl == 6 * 60 * 60 + 10 * 60


def test_x_sync_window_lock_fails_open_when_redis_is_unavailable(monkeypatch):
    class BrokenRedis:
        def set(self, *_args, **_kwargs):
            raise ConnectionError('redis unreachable')

    monkeypatch.setattr(redis_db, 'r', BrokenRedis())

    assert redis_db.try_acquire_x_sync_window_lock('2026-09-18', 0) is True


async def test_rapidapi_fallback_skipped_when_key_unset(monkeypatch):
    integration_updates = []

    monkeypatch.setattr(x_connector, 'run_blocking', _inline_run_blocking)
    monkeypatch.setattr(x_connector.users_db, 'get_integration', lambda *_args: {'handle': 'somebody'})
    monkeypatch.setattr(
        x_connector.users_db,
        'set_integration',
        lambda _uid, _key, payload: integration_updates.append(payload),
    )
    monkeypatch.setattr(x_connector.x_posts_db, 'get_newest_tweet_id', lambda _uid: None)

    async def no_token(_uid):
        return None

    monkeypatch.setattr(x_connector, 'get_valid_access_token', no_token)
    monkeypatch.setattr(social, 'is_rapid_api_configured', lambda: False)

    async def must_not_fetch(_handle):
        raise AssertionError('RapidAPI fallback must not be attempted without credentials')

    monkeypatch.setattr(social, 'get_twitter_timeline', must_not_fetch)

    result = await x_connector.sync_x_for_user('uid-1')

    assert result == {'success': False, 'error': 'rapidapi_not_configured', 'new_posts': 0, 'memories_created': 0}
    # The syncing flag must be cleared on the skip path, not left dangling.
    assert integration_updates[-1] == {'syncing': False}


async def test_get_twitter_timeline_fails_fast_without_credentials(monkeypatch):
    monkeypatch.setattr(social, 'rapid_api_host', 'rapid-host')
    monkeypatch.setattr(social, 'rapid_api_key', None)

    async def must_not_retry(*_args, **_kwargs):
        raise AssertionError('unset credentials must fail before the retry loop')

    monkeypatch.setattr(social, 'async_with_retry', must_not_retry)

    with pytest.raises(social.SocialCredentialsError):
        await social.get_twitter_timeline('somebody')


async def test_get_twitter_profile_fails_fast_without_credentials(monkeypatch):
    monkeypatch.setattr(social, 'rapid_api_host', None)
    monkeypatch.setattr(social, 'rapid_api_key', 'some-key')

    async def must_not_retry(*_args, **_kwargs):
        raise AssertionError('unset credentials must fail before the retry loop')

    monkeypatch.setattr(social, 'async_with_retry', must_not_retry)

    with pytest.raises(social.SocialCredentialsError):
        await social.get_twitter_profile('somebody')
