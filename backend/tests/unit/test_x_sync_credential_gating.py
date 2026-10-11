"""Credential gating for the X-connector periodic sweep.

The sweep runs as its own Cloud Run Job (``x-connector-sync-job``) with
Scheduler owning the 6h cadence (#9298 / #11183). It must not walk the
connected-user registry when no X OAuth app is configured, and must not burn
RapidAPI retries when that fallback's credentials are unset.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from utils import social, x_connector

ENTRY_PATH = Path(__file__).resolve().parents[2] / 'modal' / 'x_connector_sync_job.py'


@pytest.fixture
def sync_job(monkeypatch):
    spec = importlib.util.spec_from_file_location('_x_sync_credential_gating_entry', ENTRY_PATH)
    assert spec is not None and spec.loader is not None
    job = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(job)
    monkeypatch.setattr(job, '_init_firebase', lambda: None)
    return job


async def _inline_run_blocking(_executor, func, *args, **kwargs):
    return func(*args, **kwargs)


def test_sweep_skipped_when_oauth_not_configured(monkeypatch, sync_job):
    monkeypatch.setattr(sync_job, 'is_oauth_configured', lambda: False)

    async def must_not_sweep():
        raise AssertionError('unconfigured deployments must not walk the registry')

    monkeypatch.setattr(sync_job, 'run_x_sync_job', must_not_sweep)

    # An unconfigured deployment is a healthy no-op, not a job failure.
    sync_job.main()


def test_sweep_runs_when_oauth_configured(monkeypatch, sync_job):
    sweep_calls = []

    monkeypatch.setattr(sync_job, 'is_oauth_configured', lambda: True)

    async def record_sweep():
        sweep_calls.append(True)
        return {'users': 0, 'synced': 0, 'new_posts': 0, 'failed': 0, 'errors': []}

    monkeypatch.setattr(sync_job, 'run_x_sync_job', record_sweep)

    sync_job.main()

    assert sweep_calls == [True]


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
