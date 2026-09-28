"""Fleet routing: bounded Redis, transcript proof, probe floor and account benches."""

from __future__ import annotations

import asyncio
from contextlib import suppress
import statistics
import time
from collections import deque
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock, Mock

from utils.stt import live_health, live_session, streaming as st


class SlowRedis:
    async def mget(self, _keys):
        await asyncio.sleep(1)


class DownRedis:
    async def mget(self, _keys):
        raise ConnectionError('Redis unavailable')


@pytest.mark.asyncio
@pytest.mark.parametrize('redis_client', [SlowRedis(), DownRedis()])
async def test_redis_slow_or_down_uses_local_score_without_blocking_session(monkeypatch, redis_client):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_REDIS_TIMEOUT_SECONDS', '0.01')
    health = live_health.FleetHealth(redis_client=redis_client)
    health._local[('soniox', 'en')] = deque([(time.time(), True)])
    states = health.cached_snapshot(['soniox'], 'en')
    assert states['soniox'].score == pytest.approx(2 / 3)
    await health.refresh_once()  # This bounded Redis wait runs only in the background.
    started = time.monotonic()
    assert health.cached_snapshot(['soniox'], 'en')['soniox'].score == pytest.approx(2 / 3)
    assert time.monotonic() - started < 0.005


def test_health_order_probe_floor_and_account_override():
    states = {
        'modulate': live_health.ProviderState(score=0.2, samples=20),
        'soniox': live_health.ProviderState(score=0.9, samples=20),
        'parakeet': live_health.ProviderState(score=0.1, samples=20),
    }
    configured = ['modulate', 'soniox', 'parakeet']
    assert live_health.ordered_providers(configured, states, 'uid', probe_percent=0) == [
        'soniox',
        'modulate',
        'parakeet',
    ]
    # At the bounded probe floor a weaker provider is tried; a spent account is never probed.
    uid = next(
        str(index)
        for index in range(10000)
        if live_health.ordered_providers(configured, states, str(index), probe_percent=10)[0] == 'parakeet'
    )
    assert live_health.ordered_providers(configured, states, uid, probe_percent=10)[0] == 'parakeet'
    states['parakeet'] = live_health.ProviderState(score=0.1, samples=20, bench='account', bench_until=time.time() + 60)
    assert 'parakeet' not in live_health.ordered_providers(configured, states, uid, probe_percent=10)


@pytest.mark.asyncio
async def test_local_account_bench_applies_before_redis_write_finishes(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    now = time.time()
    clock = lambda: now

    class EmptyRedis:
        async def mget(self, keys):
            return [None] * len(keys)

    health = live_health.FleetHealth(clock=clock, redis_client=EmptyRedis())
    # Simulate a just-observed 402 while Redis still reports its old state.
    health._benches['soniox'] = ('account', now + 60.0)
    health.cached_snapshot(['soniox'], 'en')
    await health.refresh_once()
    states = health.cached_snapshot(['soniox'], 'en')
    assert states['soniox'].bench == 'account'
    assert states['soniox'].excluded
    assert states['soniox'].bench_until == now + 60.0


def test_language_key_has_closed_vocabulary():
    assert live_health.bounded_language('pt-BR') == 'pt'
    assert live_health.bounded_language('ar') == 'ar'
    assert live_health.bounded_language('user-12345') == 'other'


@pytest.mark.asyncio
async def test_stale_scores_keep_known_fleet_account_bench(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    now = [time.time()]
    bench_until = now[0] + 600

    class BenchedRedis:
        async def mget(self, keys):
            return [
                (
                    f'account:{bench_until}'
                    if key.endswith(':state:soniox')
                    else 9 if ':score:soniox:' in key and key.endswith(':text') else None
                )
                for key in keys
            ]

    health = live_health.FleetHealth(clock=lambda: now[0], redis_client=BenchedRedis())
    health.cached_snapshot(['soniox'], 'en')
    await health.refresh_once()
    assert health.cached_snapshot(['soniox'], 'en')['soniox'].score == pytest.approx(28 / 29)
    now[0] += live_health.CACHE_STALE_SECONDS + 1
    state = health.cached_snapshot(['soniox'], 'en')['soniox']
    assert state.score == 0.5  # Fleet score expired; the known account bench did not.
    assert state.bench == 'account'
    assert state.bench_until == bench_until
    assert state.excluded
    assert live_health.ordered_providers(['soniox'], {'soniox': state}, 'uid') == []
    health._benches['soniox'] = ('selection', bench_until + 30)
    assert health.cached_snapshot(['soniox'], 'en')['soniox'].bench == 'account'
    health._client = DownRedis()
    await health.refresh_once()
    assert health._cache_at is None
    assert health.cached_snapshot(['soniox'], 'en')['soniox'].bench == 'account'


@pytest.mark.asyncio
async def test_fleet_cache_refreshes_off_path_and_stale_data_uses_local_score(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    now = [time.time()]

    class ScoredRedis:
        async def mget(self, keys):
            return [9 if ':score:soniox:' in key and key.endswith(':text') else None for key in keys]

    health = live_health.FleetHealth(clock=lambda: now[0], redis_client=ScoredRedis())
    assert health.cached_snapshot(['soniox'], 'en')['soniox'].score == 0.5
    await health.refresh_once()
    assert health.cached_snapshot(['soniox'], 'en')['soniox'].score == pytest.approx(28 / 29)
    now[0] += live_health.CACHE_STALE_SECONDS + 1
    assert health.cached_snapshot(['soniox'], 'en')['soniox'].score == 0.5


@pytest.mark.asyncio
async def test_redis_blackhole_bounds_background_outcome_writes(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_REDIS_TIMEOUT_SECONDS', '0.1')
    dropped = live_health.FLEET_HEALTH_WRITE_DROPPED.labels(kind='result')._value.get()
    bench_dropped = live_health.FLEET_HEALTH_WRITE_DROPPED.labels(kind='bench')._value.get()

    class BlackholeRedis:
        def __init__(self):
            self.active = 0
            self.maximum = 0

        def pipeline(self, *, transaction):
            assert transaction is False
            return self

        def incr(self, _key):
            return self

        def expire(self, _key, _seconds):
            return self

        async def execute(self):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            try:
                await asyncio.sleep(1)
            finally:
                self.active -= 1

        async def set(self, *_args, **_kwargs):
            await asyncio.sleep(1)

    redis = BlackholeRedis()
    health = live_health.FleetHealth(redis_client=redis)
    for _ in range(1000):
        health.record('soniox', 'en', 'no_text')
    assert health._writes_in_flight['result'] == live_health.WRITE_IN_FLIGHT_LIMITS['result']
    assert live_health.FLEET_HEALTH_WRITE_DROPPED.labels(kind='result')._value.get() - dropped == 992
    for _ in range(100):
        health.quarantine('soniox', 'account', 60)
    assert health._writes_in_flight['bench'] == 1
    assert len(health._pending_benches) == 1
    assert live_health.FLEET_HEALTH_WRITE_DROPPED.labels(kind='bench')._value.get() == bench_dropped
    # Outcome burst cannot starve the account-quarantine writer.
    await asyncio.sleep(0.01)
    assert redis.maximum <= live_health.WRITE_IN_FLIGHT_LIMITS['result']
    deadline = asyncio.get_running_loop().time() + 1.0
    while any(health._writes_in_flight.values()) and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.01)
    assert health._writes_in_flight == {'result': 0, 'bench': 0}
    assert ('soniox', 'account') in health._pending_benches  # Redis timed out; deadline is retained.
    assert live_health.FLEET_HEALTH_WRITE_DROPPED.labels(kind='result')._value.get() - dropped == 1000


@pytest.mark.asyncio
async def test_full_bench_slots_flush_longer_pending_deadline(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    gate = asyncio.Event()

    class SlotRedis:
        def __init__(self):
            self.writes = []

        async def set(self, key, value, **_kwargs):
            self.writes.append((key, value))
            if len(self.writes) <= live_health.WRITE_IN_FLIGHT_LIMITS['bench']:
                await gate.wait()
            return True

    redis = SlotRedis()
    health = live_health.FleetHealth(redis_client=redis)
    for provider in sorted(live_health.PROVIDERS):
        health.quarantine(provider, 'account', 30)
    assert health._writes_in_flight['bench'] == live_health.WRITE_IN_FLIGHT_LIMITS['bench']
    health.quarantine('soniox', 'account', 60)
    assert len(health._pending_benches) == len(live_health.PROVIDERS)
    gate.set()
    deadline = asyncio.get_running_loop().time() + 1.0
    while (
        health._pending_benches or health._writes_in_flight['bench']
    ) and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.01)
    assert health._pending_benches == {}
    assert health._writes_in_flight['bench'] == 0
    soniox_writes = [value for key, value in redis.writes if key.endswith(':state:soniox')]
    assert len(soniox_writes) == 2
    assert float(soniox_writes[-1].split(':', 1)[1]) > float(soniox_writes[0].split(':', 1)[1])


@pytest.mark.asyncio
async def test_bench_write_retries_after_redis_backoff(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setattr(live_health, 'CACHE_REFRESH_SECONDS', 0.01)

    class RecoveringRedis:
        def __init__(self):
            self.writes = 0

        async def set(self, *_args, **_kwargs):
            self.writes += 1
            if self.writes == 1:
                raise ConnectionError('Redis unavailable')
            return True

        async def mget(self, keys):
            return [None] * len(keys)

    redis = RecoveringRedis()
    health = live_health.FleetHealth(redis_client=redis)
    health.quarantine('soniox', 'account', 60)
    deadline = asyncio.get_running_loop().time() + 1.0
    while health._writes_in_flight['bench'] and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.01)
    assert redis.writes == 1
    assert ('soniox', 'account') in health._pending_benches
    assert health._redis_retry_at > time.time()
    health._redis_retry_at = time.time() + 0.03  # Shorten the production backoff for the test.
    refresh = asyncio.create_task(health.refresh_forever())
    try:
        deadline = asyncio.get_running_loop().time() + 1.0
        while health._pending_benches and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
    finally:
        refresh.cancel()
        with suppress(asyncio.CancelledError):
            await refresh
    assert redis.writes == 2
    assert health._pending_benches == {}


@pytest.mark.asyncio
async def test_expired_pending_bench_is_not_written(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    now = [time.time()]

    class SpyRedis:
        def __init__(self):
            self.writes = 0

        async def set(self, *_args, **_kwargs):
            self.writes += 1
            return True

        async def mget(self, keys):
            return [None] * len(keys)

    redis = SpyRedis()
    health = live_health.FleetHealth(clock=lambda: now[0], redis_client=redis)
    health._redis_retry_at = now[0] + 10
    health.quarantine('soniox', 'account', 1)
    assert ('soniox', 'account') in health._pending_benches
    now[0] += 11
    await health.refresh_once()
    assert health._pending_benches == {}
    assert redis.writes == 0


@pytest.mark.asyncio
async def test_redis_outage_uses_jittered_one_probe_per_provider_per_pod(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    now = [time.time()]
    health = live_health.FleetHealth(clock=lambda: now[0], redis_client=DownRedis(), probe_jitter=lambda _provider: 2.0)
    health.cached_snapshot(['soniox'], 'en')
    await health.refresh_once()
    assert not health.try_admit_recovery_probe('soniox')
    now[0] += 2.0
    assert health.try_admit_recovery_probe('soniox')
    assert not health.try_admit_recovery_probe('soniox')
    now[0] += live_health.LOCAL_PROBE_INTERVAL_SECONDS + 1.0
    assert not health.try_admit_recovery_probe('soniox')
    now[0] += 1.0
    assert health.try_admit_recovery_probe('soniox')
    assert not health.try_admit_recovery_probe('soniox')


@pytest.mark.asyncio
async def test_background_fleet_probe_lease_is_consumed_once(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')

    class LeaseRedis:
        def __init__(self):
            self.claims = 0

        async def mget(self, keys):
            return [f'account:{time.time() - 1}' if key.endswith(':state:soniox') else None for key in keys]

        async def set(self, *_args, **_kwargs):
            self.claims += 1
            return self.claims == 1

    redis = LeaseRedis()
    health = live_health.FleetHealth(redis_client=redis, probe_jitter=lambda _provider: 0.0)
    health.cached_snapshot(['soniox'], 'en')
    await health.refresh_once()
    assert health.try_admit_recovery_probe('soniox')
    assert not health.try_admit_recovery_probe('soniox')
    await health.refresh_once()
    assert not health.try_admit_recovery_probe('soniox')
    assert redis.claims == 2


@pytest.mark.asyncio
async def test_hanging_redis_adds_under_five_ms_to_connection_decision(monkeypatch):
    from utils.stt import live_chain
    from utils.stt.live_metrics import ROUTING_DECISION_LATENCY

    class HangingRedis:
        def __init__(self):
            self.started = asyncio.Event()

        async def mget(self, _keys):
            self.started.set()
            await asyncio.sleep(1.0)

    class Circuit:
        def allow_request(self, **_kwargs):
            return True

        def deferred_result_callbacks(self):
            return (lambda: None), (lambda: None)

        def release_probe(self):
            pass

    async def connect():
        return RawSocket()

    async def serving(_socket):
        return True

    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', serving)
    monkeypatch.setattr(st, '_circuit_for_primary', lambda _service: Circuit())
    redis = HangingRedis()
    health = live_health.FleetHealth(redis_client=redis)
    monkeypatch.setattr(live_chain, 'health', health)
    monkeypatch.setenv('STT_ROUTING_REDIS_TIMEOUT_SECONDS', '0.1')

    async def dial():
        started = time.perf_counter()
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.soniox,
            connect_primary=connect,
            callbacks={st.STTService.soniox: connect},
            failed=set(),
            models=['soniox'],
            routing_uid='test-user',
            routing_language='en',
        )
        return (time.perf_counter() - started) * 1000

    monkeypatch.setenv('STT_ROUTING_MODE', 'off')
    baseline = [await dial() for _ in range(40)]
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    health.cached_snapshot(['soniox'], 'en')
    refresh = asyncio.create_task(health.refresh_once())
    try:
        await redis.started.wait()
        routed = [await dial() for _ in range(40)]
    finally:
        refresh.cancel()
        with suppress(asyncio.CancelledError):
            await refresh
    added_ms = statistics.median(routed) - statistics.median(baseline)
    print(f'routing added median latency with hanging Redis: {added_ms:.3f} ms')
    assert added_ms < 5.0
    assert ROUTING_DECISION_LATENCY._labelnames == ()


@pytest.mark.asyncio
async def test_hanging_recovery_lease_is_not_awaited_by_connection(monkeypatch):
    from utils.stt import live_chain

    class SlowLeaseRedis:
        def __init__(self):
            self.started = asyncio.Event()

        async def mget(self, keys):
            return [
                f'selection:{time.time() - 1}' if key.endswith((':state:modulate', ':state:soniox')) else None
                for key in keys
            ]

        async def set(self, *_args, **_kwargs):
            self.started.set()
            await asyncio.sleep(1.0)

    class Circuit:
        def allow_request(self, **_kwargs):
            return True

        def deferred_result_callbacks(self):
            return (lambda: None), (lambda: None)

        def release_probe(self):
            pass

    async def connect():
        return RawSocket()

    async def serving(_socket):
        return True

    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', serving)
    monkeypatch.setattr(st, '_circuit_for_primary', lambda _service: Circuit())
    monkeypatch.setenv('STT_ROUTING_PROBE_PERCENT', '0')
    monkeypatch.setenv('STT_ROUTING_REDIS_TIMEOUT_SECONDS', '0.1')
    redis = SlowLeaseRedis()
    health = live_health.FleetHealth(redis_client=redis, probe_jitter=lambda _provider: 0.0)
    monkeypatch.setattr(live_chain, 'health', health)

    async def dial():
        health._local_probe_next.clear()  # Isolate the latency measurement from the probe interval.
        started = time.perf_counter()
        _, actual = await live_chain.connect_configured_chain(
            primary_service=st.STTService.modulate,
            connect_primary=connect,
            callbacks={st.STTService.modulate: connect, st.STTService.soniox: connect},
            failed=set(),
            models=['modulate-velma-2', 'soniox'],
            routing_uid='test-user',
            routing_language='en',
        )
        assert actual == st.STTService.modulate
        return (time.perf_counter() - started) * 1000

    monkeypatch.setenv('STT_ROUTING_MODE', 'off')
    baseline = [await dial() for _ in range(30)]
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    health.cached_snapshot(['modulate', 'soniox'], 'en')
    refresh = asyncio.create_task(health.refresh_once())
    try:
        await redis.started.wait()
        assert 'modulate' in health._probe_pending
        routed = [await dial() for _ in range(30)]
    finally:
        refresh.cancel()
        with suppress(asyncio.CancelledError):
            await refresh
    added_ms = statistics.median(routed) - statistics.median(baseline)
    print(f'routing added median latency with hanging recovery lease: {added_ms:.3f} ms')
    assert added_ms < 5.0


@pytest.mark.asyncio
async def test_on_reorders_only_eligible_legs_and_shadow_keeps_config_order(monkeypatch):
    from utils.stt import live_chain

    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox', 'dg-nova-3'])
    states = {
        'modulate': live_health.ProviderState(score=0.2, samples=20),
        'soniox': live_health.ProviderState(score=0.9, samples=20),
    }
    seen_languages = []

    def snapshot(providers, language):
        assert providers == ['modulate', 'soniox']  # Deepgram has no eligible callback.
        seen_languages.append(language)
        return states

    monkeypatch.setattr(live_chain.health, 'cached_snapshot', snapshot)
    monkeypatch.setenv('STT_ROUTING_PROBE_PERCENT', '0')
    modulate = AsyncMock(return_value=RawSocket())
    soniox = AsyncMock(return_value=RawSocket())
    for mode, expected in [('shadow', 'modulate'), ('on', 'soniox')]:
        monkeypatch.setenv('STT_ROUTING_MODE', mode)
        _, actual = await st.connect_stt_socket_with_fallback(
            primary_service=st.STTService.modulate,
            connect_primary=modulate,
            connect_soniox=soniox,
            connect_deepgram=None,
            use_config=True,
            routing_uid='test-user',
            routing_language='fr',
        )
        assert actual.value == expected
    assert seen_languages == ['fr', 'fr']


@pytest.mark.asyncio
async def test_on_account_bench_overrides_better_score(monkeypatch):
    from utils.stt import live_chain

    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox'])

    def snapshot(_providers, _language):
        return {
            'modulate': live_health.ProviderState(score=0.2, samples=20),
            'soniox': live_health.ProviderState(score=0.9, samples=20, bench='account', bench_until=time.time() + 60),
        }

    monkeypatch.setattr(live_chain.health, 'cached_snapshot', snapshot)
    soniox = AsyncMock(return_value=RawSocket())
    _, actual = await st.connect_stt_socket_with_fallback(
        primary_service=st.STTService.modulate,
        connect_primary=AsyncMock(return_value=RawSocket()),
        connect_soniox=soniox,
        use_config=True,
        routing_uid='test-user',
        routing_language='en',
    )
    assert actual == st.STTService.modulate
    soniox.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('local_allowed,claims,releases', [(False, 0, 0), (True, 1, 1)])
async def test_local_probe_is_checked_before_fleet_lease_and_released_on_denial(
    monkeypatch, local_allowed, claims, releases
):
    from utils.stt import live_chain

    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_PROBE_PERCENT', '0')
    monkeypatch.setattr(
        live_chain.health,
        'cached_snapshot',
        lambda _providers, _language: {
            'soniox': live_health.ProviderState(bench='account', bench_until=time.time() - 1),
            'modulate': live_health.ProviderState(),
        },
    )
    admit = Mock(return_value=False)
    monkeypatch.setattr(live_chain.health, 'try_admit_recovery_probe', admit)

    class Circuit:
        def __init__(self, allowed):
            self.allowed = allowed
            self.releases = 0

        def allow_request(self, **_kwargs):
            return self.allowed

        def deferred_result_callbacks(self):
            return (lambda: None), (lambda: None)

        def release_probe(self):
            self.releases += 1

    circuits = {'soniox': Circuit(local_allowed), 'modulate': Circuit(True)}
    monkeypatch.setattr(st, '_circuit_for_primary', lambda service: circuits[service.value])
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    soniox = AsyncMock(return_value=RawSocket())
    modulate = AsyncMock(return_value=RawSocket())
    _, chosen = await live_chain.connect_configured_chain(
        primary_service=st.STTService.soniox,
        connect_primary=soniox,
        callbacks={st.STTService.soniox: soniox, st.STTService.modulate: modulate},
        failed=set(),
        models=['soniox', 'modulate-velma-2'],
        routing_uid='test-user',
        routing_language='en',
    )
    assert chosen == st.STTService.modulate
    soniox.assert_not_awaited()
    assert admit.call_count == claims
    assert circuits['soniox'].releases == releases


class RawSocket:
    is_connection_dead = False
    death_reason = None

    def send(self, _audio):
        return True

    def finish(self):
        return None

    def finalize(self):
        return None


class SpeechGate:
    mode = 'active'

    def __init__(self, is_speech=True):
        self.is_speech = is_speech

    def process_audio(self, audio, _wall, _score=None, start_sample=None):
        return SimpleNamespace(
            audio_to_send=audio if self.is_speech else b'',
            is_speech=self.is_speech,
            should_finalize=False,
            send_spans=(),
        )

    def consume_speech_ms_delta(self):
        return 1000 if self.is_speech else 0


def _leg(gate=None):
    receiver = SimpleNamespace(host=SimpleNamespace(language='en'), _telemetry_platform=lambda: 'ios')
    session = SimpleNamespace(receiver=receiver, audio_seconds=0.0, speech_ms=0, total_speech_ms=0)
    return live_session.LiveLegSocket(
        RawSocket(), gate or SpeechGate(), session, st.STTService.modulate, 16000, False, False
    )


def test_no_text_and_text_are_classified_from_vad_speech(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    observed = []
    monkeypatch.setattr(
        live_session.health,
        'record',
        lambda provider, language, outcome: observed.append((provider, language, outcome)),
    )
    silent = _leg(SpeechGate(is_speech=False))
    assert silent.send(b'\x00\x00' * 16000)
    silent.finish()
    assert observed == []
    speech_without_text = _leg()
    assert speech_without_text.send(b'\x01\x00' * 16000)
    speech_without_text.finish()
    speech_without_text.finish()
    assert observed == [('modulate', 'en', 'no_text')]
    text = _leg()
    assert text.send(b'\x01\x00' * 16000)
    text.note_selection_transcript([{'text': 'hello'}])
    text.finish()
    assert observed[-1] == ('modulate', 'en', 'text')


def test_speech_then_silence_past_deadline_yields_no_text_once(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    monkeypatch.setenv('STT_NO_TEXT_SECONDS', '3')
    observed = []
    monkeypatch.setattr(live_session.health, 'record', lambda *args: observed.append(args))
    gate = SpeechGate()
    leg = _leg(gate)
    assert leg.send(b'\x01\x00' * 1600)
    assert observed == []
    leg._first_speech_at = time.monotonic() - 4.0
    gate.is_speech = False
    assert leg.send(b'\x00\x00' * 1600)
    leg.finish()
    assert observed == [('modulate', 'en', 'no_text')]


def test_on_mode_waits_for_text_and_no_text_opens_breaker(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setattr(live_session.health, 'record', lambda *_: None)
    quarantines = []
    monkeypatch.setattr(live_session.health, 'quarantine', lambda *args: quarantines.append(args))
    breaker = SimpleNamespace(record_serve_failure=lambda: None, serve_error_bench_seconds=180.0)
    monkeypatch.setattr(st, '_circuit_for_primary', lambda _service: breaker)
    success = []
    closed = []
    leg = _leg()
    assert leg.defers_selection_success
    leg.set_health_callbacks(lambda: success.append(True), lambda: closed.append(True))
    assert leg.send(b'\x01\x00' * 16000)
    assert success == []
    leg.finish()
    assert closed == [True]
    assert quarantines == [('modulate', 'selection', 180.0)]
