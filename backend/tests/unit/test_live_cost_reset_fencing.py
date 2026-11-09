"""Reset epochs fence actual settlements and dials across evidence-key expiry."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from config import live_stt_state
from config.live_stt_registry import DEFAULT_TARGETS
from tests.unit.test_live_cost_router import controls
from utils.stt import live_chain, live_health, live_session, streaming as st
from utils.stt.live_cost_reset import reset_cost_target
from utils.stt.live_outcome import LiveLegOutcome


@pytest.mark.asyncio
@pytest.mark.parametrize('target', DEFAULT_TARGETS, ids=lambda target: target.id)
@pytest.mark.parametrize('connect', [False, True])
@pytest.mark.parametrize('expire', [False, True])
async def test_old_generation_zero_settlements_stay_fenced_after_reset_and_idle_expiry(
    monkeypatch, target, connect, expire
):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    async with fakeredis.aioredis.FakeRedis(decode_responses=True) as redis:
        pod = live_health.FleetHealth(redis_client=redis)
        pending = []
        monkeypatch.setattr(pod, 'schedule', lambda coroutine, **_labels: pending.append(coroutine))
        old = [LiveLegOutcome(target.id, 'en', f'old-{i}', {'all': 0, 'en': 0}, pod.record_session) for i in range(8)]
        receipt = await reset_cost_target(redis, target=target.id, environment='offline', reason='fence', apply=True)
        floor = receipt['scopes'][0]['generation']
        if expire:
            for language in ('all', 'en'):
                key = live_stt_state.cost_key(target, language)
                await redis.expire(key, 0)  # Real Redis expiry semantics, without a 15-minute sleep.
                assert await redis.get(key) is None
        reset_key = live_stt_state.cost_reset_key(target)
        assert await redis.get(reset_key) == str(floor) and await redis.ttl(reset_key) == -1
        await pod.refresh_cost_once()
        for outcome in old:
            outcome.claim('timeout', connect=connect)
            assert outcome.generations == {'all': 0, 'en': 0}
            assert outcome.settle()
        # Missing generation evidence is not permission to cross a reset either.
        pod.record_session(target.id, 'en', 'connect_failure', uid='unknown-old', reason='timeout')
        for coroutine in pending:
            await coroutine
        pending.clear()
        await pod.refresh_cost_once()
        for language in ('all', 'en'):
            state = pod._cost_cached[(target.id, language)]
            assert state.stage == 100 and state.n == 0 and state.generation == floor
        # New post-reset failures remain live provider evidence and can bench.
        for i in range(8):
            outcome = LiveLegOutcome(
                target.id, 'en', f'new-{i}', pod.cost_generations(target.id, 'en'), pod.record_session
            )
            outcome.claim('timeout', connect=True)
            assert outcome.settle()
            for coroutine in pending:
                await coroutine
            pending.clear()
        await pod.refresh_cost_once()
        assert pod.cost_stage(target.id, 'en') == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('recovery', ['true', 'false'])
async def test_raw_connect_failure_captures_epoch_before_a_reset_during_handshake(monkeypatch, recovery):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', recovery)
    monkeypatch.setenv('LISTEN_STT_SAME_TARGET_RETRY_ENABLED', 'false')
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    target = DEFAULT_TARGETS[1]
    async with fakeredis.aioredis.FakeRedis(decode_responses=True) as redis:
        pod = live_health.FleetHealth(redis_client=redis)
        pending = []
        monkeypatch.setattr(pod, 'schedule', lambda coroutine, **_labels: pending.append(coroutine))
        monkeypatch.setattr(live_chain, 'health', pod)
        monkeypatch.setattr(live_session, 'health', pod)
        await pod.refresh_cost_once()

        async def reset_during_dial():
            await reset_cost_target(redis, target=target.id, environment='offline', reason='in-flight', apply=True)
            await pod.refresh_cost_once()
            raise TimeoutError('synthetic pre-reset dial failure')

        _, service = await live_chain.connect_configured_chain(
            primary_service=st.STTService.modulate,
            connect_primary=reset_during_dial,
            callbacks={st.STTService.soniox: AsyncMock(return_value=SimpleNamespace(is_connection_dead=False))},
            failed=set(),
            models=['modulate-velma-2', 'soniox'],
            routing_uid='synthetic',
            routing_language='en',
        )
        assert service == st.STTService.soniox
        for coroutine in pending:
            await coroutine
        for language in ('all', 'en'):
            state = pod._cost_cached[(target.id, language)]
            assert state.stage == 100 and state.n == 0 and state.generation > 0
