from __future__ import annotations

import threading

import pytest

from utils.executors import posthog_flag_executor
from utils.posthog_flags import PostHogPairedFlagProvider, TriState


@pytest.mark.asyncio
async def test_paired_flags_use_bounded_posthog_executor():
    calls = {}

    class Client:
        def get_feature_variants(self, uid):
            calls['uid'] = uid
            calls['thread'] = threading.current_thread().name
            return {'rollout': True, 'kill': False}

    provider = PostHogPairedFlagProvider(
        rollout_flag_key='rollout',
        kill_switch_flag_key='kill',
        client_factory=Client,
    )

    result = await provider('owner-1')

    assert result.rollout is TriState.ENABLED
    assert result.kill_switch is TriState.DISABLED
    assert calls['uid'] == 'owner-1'
    assert calls['thread'].startswith('posthog-flag')
    assert posthog_flag_executor.max_queue_size == 16


@pytest.mark.asyncio
async def test_lookup_errors_fail_closed():
    class Client:
        def get_feature_variants(self, _uid):
            raise RuntimeError('provider unavailable')

    provider = PostHogPairedFlagProvider(
        rollout_flag_key='rollout',
        kill_switch_flag_key='kill',
        client_factory=Client,
    )

    result = await provider('owner-1')

    assert result.rollout is TriState.UNKNOWN
    assert result.kill_switch is TriState.UNKNOWN
