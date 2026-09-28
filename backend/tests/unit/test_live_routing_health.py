"""Fleet routing: bounded Redis, transcript proof, probe floor and account benches."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock

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
    started = time.monotonic()
    states = await health.snapshot(['soniox'], 'en')
    assert time.monotonic() - started < 0.2
    assert states['soniox'].score == pytest.approx(2 / 3)
    # Ten-second local fallback avoids repeating the timeout for every listen.
    started = time.monotonic()
    assert (await health.snapshot(['soniox'], 'en'))['soniox'].score == pytest.approx(2 / 3)
    assert time.monotonic() - started < 0.02


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
    states = await health.snapshot(['soniox'], 'en')
    assert states['soniox'].bench == 'account'
    assert states['soniox'].excluded
    assert states['soniox'].bench_until == now + 60.0


def test_language_key_has_closed_vocabulary():
    assert live_health.bounded_language('pt-BR') == 'pt'
    assert live_health.bounded_language('ar') == 'ar'
    assert live_health.bounded_language('user-12345') == 'other'


@pytest.mark.asyncio
async def test_on_reorders_only_eligible_legs_and_shadow_keeps_config_order(monkeypatch):
    from utils.stt import live_chain

    monkeypatch.setattr(st, 'stt_service_models', ['modulate-velma-2', 'soniox', 'dg-nova-3'])
    states = {
        'modulate': live_health.ProviderState(score=0.2, samples=20),
        'soniox': live_health.ProviderState(score=0.9, samples=20),
    }
    seen_languages = []

    async def snapshot(providers, language):
        assert providers == ['modulate', 'soniox']  # Deepgram has no eligible callback.
        seen_languages.append(language)
        return states

    monkeypatch.setattr(live_chain.health, 'snapshot', snapshot)
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

    async def snapshot(_providers, _language):
        return {
            'modulate': live_health.ProviderState(score=0.2, samples=20),
            'soniox': live_health.ProviderState(score=0.9, samples=20, bench='account', bench_until=time.time() + 60),
        }

    monkeypatch.setattr(live_chain.health, 'snapshot', snapshot)
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

    def process_audio(self, audio, _wall, _score=None, start_sample=None):
        return SimpleNamespace(audio_to_send=audio, is_speech=True, should_finalize=False, send_spans=())

    def consume_speech_ms_delta(self):
        return 1000


def _leg():
    receiver = SimpleNamespace(host=SimpleNamespace(language='en'), _telemetry_platform=lambda: 'ios')
    session = SimpleNamespace(receiver=receiver, audio_seconds=0.0, speech_ms=0, total_speech_ms=0)
    return live_session.LiveLegSocket(RawSocket(), SpeechGate(), session, st.STTService.modulate, 16000, False, False)


def test_no_text_and_text_are_classified_from_vad_speech(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'shadow')
    observed = []
    monkeypatch.setattr(
        live_session.health,
        'record',
        lambda provider, language, outcome: observed.append((provider, language, outcome)),
    )
    silent = _leg()
    assert silent.send(b'\x01\x00' * 16000)
    silent.finish()
    silent.finish()
    assert observed == [('modulate', 'en', 'no_text')]
    text = _leg()
    assert text.send(b'\x01\x00' * 16000)
    text.note_selection_transcript([{'text': 'hello'}])
    text.finish()
    assert observed[-1] == ('modulate', 'en', 'text')


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
