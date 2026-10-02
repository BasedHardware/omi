"""Exercise bounded attribution through the serving leg, not only the classifier."""

import math
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from prometheus_client import CollectorRegistry, Gauge

from config.live_stt_registry import DEFAULT_TARGETS
from utils.metrics import OMI_FALLBACK_TOTAL
from utils.observability.fallback import ALLOWED_REASONS
from utils.stt import live_chain, live_cost_health, live_failure, live_session, streaming as st
from utils.stt.live_metrics import COST_OBSERVATIONS
from utils.stt.parakeet_window import WindowedParakeetSocket
from utils.stt.live_reason import LIVE_STT_REASONS, normalize_live_stt_reason
from utils.stt.live_signal import provider_observation
from tests.unit.test_live_cost_router import controls, MemoryRedis
from tests.unit.test_live_routing_health import SpeechGate

PCM = b'\x01\x00' * 16000


class ServingSocket:
    is_connection_dead = False
    typed_death_reason = None
    death_reason = None

    def __init__(self):
        self.on_send = lambda: None

    def send(self, _audio):
        self.on_send()
        return not self.is_connection_dead

    def die(self, typed=None, raw=None):
        self.typed_death_reason, self.death_reason = typed, raw
        self.is_connection_dead = True

    def finalize(self):
        pass

    def finish(self):
        pass


def serving_leg(raw=None, family='modulate'):
    receiver = SimpleNamespace(
        host=SimpleNamespace(language='en', request=SimpleNamespace(uid='synthetic')),
        _telemetry_platform=lambda: 'ios',
    )
    session = SimpleNamespace(receiver=receiver, audio_seconds=0.0, speech_ms=0, total_speech_ms=0)
    leg = live_session.LiveLegSocket(
        raw or ServingSocket(), SpeechGate(), session, st.STTService(family), 16000, family == 'parakeet', False
    )
    assert leg.send(PCM)
    return leg


def observed(target, outcome, reason):
    return COST_OBSERVATIONS.labels(target=target, outcome=outcome, reason=reason)._value.get()


CASES = [
    ('modulate', 'modulate_serve_error', 'vendor diagnostic', 'modulate_serve_error', 'provider_failure'),
    ('modulate', None, 'send returned False', 'connection_lost', 'provider_failure'),
    ('modulate', None, 'keep_alive ConnectionClosed: x', 'connection_lost', 'provider_failure'),
    ('modulate', None, 'send ConnectionError: x', 'connection_lost', 'provider_failure'),
    ('parakeet', 'first_text_deadline', 'first_text_deadline', 'first_text_deadline', 'censored'),
    ('parakeet', 'empty_streak', 'empty_streak', 'empty_streak', 'censored'),
    ('parakeet', 'capacity_full', 'capacity_full', 'capacity_full', 'censored'),
    ('soniox', 'provider_budget_exhausted', 'vendor diagnostic', 'provider_budget_exhausted', 'censored'),
    ('soniox', 'provider_auth_rejected', 'vendor diagnostic', 'provider_auth_rejected', 'censored'),
    ('soniox', 'soniox_rotation', 'vendor diagnostic', 'soniox_rotation', 'censored'),
    ('soniox', 'soniox_idle_timeout', 'vendor diagnostic', 'soniox_idle_timeout', 'censored'),
    ('soniox', 'soniox_no_audio_teardown', 'vendor diagnostic', 'soniox_no_audio_teardown', 'censored'),
    ('modulate', 'client_disconnect', None, 'client_disconnect', 'censored'),
    ('modulate', 'normal_close', None, 'normal_close', 'censored'),
]


@pytest.mark.parametrize('family,typed,raw_reason,reason,outcome', CASES)
@pytest.mark.parametrize('observer', ['monitor', 'send_false', 'send_exception'])
def test_serving_death_is_attributed_once_and_reconciles_fallback(family, typed, raw_reason, reason, outcome, observer):
    leg = serving_leg(family=family)
    before = observed(leg.routing_target, outcome, reason)
    if observer == 'monitor':
        leg.raw.die(typed, raw_reason)
        assert leg.is_connection_dead
    else:

        def fail_on_send():
            leg.raw.die(typed, raw_reason)
            if observer == 'send_exception':
                raise ConnectionError('synthetic transport symptom')

        leg.raw.on_send = fail_on_send
        # Untyped send symptoms use send_failed rather than monitor connection_lost.
        if typed is None:
            reason = 'send_failed'
            before = observed(leg.routing_target, outcome, reason)
        assert not leg.send(PCM)
    assert observed(leg.routing_target, outcome, reason) == before + 1
    assert leg.normalized_death_reason == reason
    assert leg.death_reason == leg.typed_death_reason == reason
    # All observer vantage points see the same cause after the first observation.
    assert live_failure.live_stt_terminal_reason(leg, 'send_failed') == reason
    assert live_failure.live_stt_terminal_reason(leg, 'connection_lost') == reason
    for recovered in (True, False):
        hop = live_failure.PendingLiveFailover.from_socket(leg, family, 'soniox')
        assert hop.reason == reason
        hop.to_mode = 'modulate'  # PTT's connect fallback changes the successor, not the source.
        fallback = OMI_FALLBACK_TOTAL.labels(
            component='stt_live_session',
            from_mode=family,
            to_mode='modulate',
            reason=reason,
            outcome='recovered' if recovered else 'exhausted',
        )
        baseline = fallback._value.get()
        if recovered:
            hop.note_transcript([{'text': 'synthetic'}])
        else:
            # A successor's different cause must not overwrite source attribution.
            hop.note_failure('provider_auth_rejected')
        hop.note_failure('connection_lost')
        assert fallback._value.get() == baseline + 1
    leg.finish()
    leg.finish()
    assert leg.is_connection_dead
    assert not leg.send(PCM)
    assert observed(leg.routing_target, outcome, reason) == before + 1
    if outcome == 'provider_failure':
        state = live_chain.health._cost_local[(leg.routing_target, 'all')]
        assert state.n == state.failures == 1
    else:
        assert not live_chain.health._cost_local


@pytest.mark.parametrize('cause', ['first_text_deadline', 'empty_streak', 'capacity_full'])
def test_window_bounded_raw_reason_wins_even_without_typed_proxy(cause):
    leg = serving_leg(family='parakeet')
    before = observed(leg.routing_target, 'censored', cause)
    leg.raw.on_send = lambda: leg.raw.die(raw=cause)
    assert not leg.send(PCM)
    leg.finish()
    assert observed(leg.routing_target, 'censored', cause) == before + 1
    assert not live_chain.health._cost_local


@pytest.mark.parametrize('text', [False, True])
def test_normal_client_close_records_no_provider_failure(text):
    leg = serving_leg()
    outcome, reason = ('success', 'text') if text else ('censored', 'no_text')
    before = observed(leg.routing_target, outcome, reason)
    leg._first_speech_at -= 60  # Completed session, beyond early-client-teardown censor.
    if text:
        leg.note_selection_transcript([{'text': 'synthetic'}])
    leg.finish()
    leg.finish()
    assert observed(leg.routing_target, outcome, reason) == before + 1
    assert all(state.failures == 0 for state in live_chain.health._cost_local.values())


def test_early_teardown_flag_cannot_censor_a_later_attributable_death():
    leg = serving_leg()
    leg._cost_censored_no_text = True
    leg.raw.die('modulate_serve_error', 'vendor diagnostic')
    baseline = observed(leg.routing_target, 'provider_failure', 'modulate_serve_error')
    assert leg.is_connection_dead
    assert observed(leg.routing_target, 'provider_failure', 'modulate_serve_error') == baseline + 1


@pytest.mark.parametrize('observe_at', ['_dead', '_death_reason'])
def test_modulate_publishes_typed_cause_before_the_dead_latch(observe_at):
    class ObservedModulate(st.SafeModulateSocket):
        def __init__(self):
            self._dead, self._closed = False, False
            self._death_reason = self._typed_death_reason = None
            self._lock = threading.Lock()
            self.observer = lambda: None

        def __setattr__(self, name, value):
            super().__setattr__(name, value)
            if name == observe_at and self._dead:
                self.observer()

        def send(self, _audio):
            return not self._dead

        def finish(self):
            pass

    raw = ObservedModulate()
    leg = serving_leg(raw)
    raw.observer = lambda: leg.is_connection_dead
    baseline = observed(leg.routing_target, 'provider_failure', 'modulate_serve_error')
    raw._mark_dead('vendor diagnostic', typed_reason='modulate_serve_error')
    assert leg.is_connection_dead
    assert leg.normalized_death_reason == 'modulate_serve_error'
    assert observed(leg.routing_target, 'provider_failure', 'modulate_serve_error') == baseline + 1


def test_vocabulary_is_closed_and_classifier_cannot_accept_free_text():
    assert LIVE_STT_REASONS <= ALLOWED_REASONS
    assert len(LIVE_STT_REASONS) == 27
    assert normalize_live_stt_reason('send ConnectionError: private') == 'connection_lost'
    assert normalize_live_stt_reason('first_text_deadline', 'send_failed') == 'first_text_deadline'
    with pytest.raises(ValueError, match='bounded'):
        provider_observation('failover', 'send ConnectionError: private')


@pytest.mark.asyncio
async def test_never_refreshed_snapshot_is_distinct_from_stale_and_idle_refreshes(monkeypatch):
    # Fresh process metric, isolated from other tests' completed snapshots.
    timestamp = Gauge('snapshot', 'test snapshot', registry=CollectorRegistry())
    timestamp.set(float('nan'))
    monkeypatch.setattr(live_cost_health, 'COST_SNAPSHOT_AT', timestamp)
    now = [1000]
    redis = MemoryRedis(clock=lambda: now[0])
    pod = live_chain.health.__class__(redis_client=redis, clock=lambda: now[0])
    assert math.isnan(timestamp._value.get())
    assert not pod._cost_interests
    await pod.refresh_cost_once()
    assert timestamp._value.get() == 1000
    now[0] += 19

    async def down():
        raise ConnectionError('synthetic')

    monkeypatch.setattr(redis, 'time', down)
    await pod.refresh_cost_once()
    assert timestamp._value.get() == 1000  # Stale is finite, never-refreshed is NaN.


@pytest.mark.asyncio
@pytest.mark.parametrize('cause', ['first_text_deadline', 'empty_streak', 'capacity_full'])
async def test_real_window_publishes_cause_before_latch_and_next_send_is_censored(cause):
    class ObservedWindow(WindowedParakeetSocket):
        def __setattr__(self, name, value):
            super().__setattr__(name, value)
            if name == '_dead' and value:
                self.observer()

    raw = ObservedWindow(lambda _: None, 'http://unused.invalid', 16000, lambda: None)
    leg = serving_leg(raw, family='parakeet')
    raw.observer = lambda: leg.is_connection_dead
    baseline = observed(leg.routing_target, 'censored', cause)
    raw.fail(cause)
    assert not leg.send(PCM)
    leg.finish()
    assert leg.normalized_death_reason == cause
    assert observed(leg.routing_target, 'censored', cause) == baseline + 1
    assert not live_chain.health._cost_local


def test_early_client_disconnect_is_not_a_provider_observation():
    leg = serving_leg()
    leg.finish()
    assert leg._cost_censored_no_text
    assert not live_chain.health._cost_local


def test_local_vad_failure_is_censored_rather_than_transport_failure(monkeypatch):
    leg = serving_leg(family='parakeet')

    def broken_gate(*args, **kwargs):
        raise RuntimeError('synthetic VAD fault')

    monkeypatch.setattr(leg.gate, 'process_audio', broken_gate)
    baseline = observed(leg.routing_target, 'censored', 'vad_failed')
    assert not leg.send(PCM)
    leg.finish()
    assert leg.normalized_death_reason == 'vad_failed'
    assert observed(leg.routing_target, 'censored', 'vad_failed') == baseline + 1
    assert not live_chain.health._cost_local


@pytest.mark.asyncio
async def test_vad_attribution_preserves_legacy_terminal_local_protection(monkeypatch):
    opened = []
    monkeypatch.setattr(
        live_failure, '_open_serving_provider_circuit', lambda reason, provider: opened.append((reason, provider))
    )
    state = SimpleNamespace(stt_terminal_failure=False, active=True, close_code=1000)
    client = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
    await live_failure.terminate_live_stt_session(
        client, state, failure=live_failure.live_stt_upstream_failure('parakeet'), reason='vad_failed', platform='ios'
    )
    assert opened == [('vad_failed', 'parakeet')]
    assert provider_observation('failover', 'vad_failed') is None
    client.close.assert_awaited_once_with(code=1011, reason='transcription_service_unavailable')
