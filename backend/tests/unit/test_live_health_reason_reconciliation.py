"""Exercise bounded attribution through the serving leg, not only the classifier."""

import asyncio
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
from utils.stt.live_metrics import (
    COST_EMISSION_ACK_ERRORS,
    COST_OBSERVATIONS,
    COST_SETTLEMENTS,
    WINDOW_SESSION_OUTCOME,
)
from utils.stt import parakeet_window
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
    ('soniox', 'no_text_rescue_complete', 'vendor diagnostic', 'no_text_rescue_complete', 'censored'),
    ('modulate', 'client_disconnect', None, 'client_disconnect', 'censored'),
    ('modulate', 'normal_close', None, 'normal_close', 'censored'),
    # Listen-cancelled Parakeet window: censored, never connection_lost.
    ('parakeet', None, 'cancelled', 'cancelled', 'censored'),
    # Unknown free-text deaths still default to the conservative provider failure.
    ('parakeet', None, 'parakeet pump crashed: x', 'connection_lost', 'provider_failure'),
    ('parakeet', None, 'connection_lost', 'connection_lost', 'provider_failure'),
]


@pytest.mark.parametrize('family,typed,raw_reason,reason,outcome', CASES)
@pytest.mark.parametrize('observer', ['monitor', 'send_false', 'send_exception'])
@pytest.mark.parametrize('settlement', ['recovered', 'degraded', 'exhausted'])
def test_serving_death_is_attributed_once_and_reconciles_fallback(
    family, typed, raw_reason, reason, outcome, observer, settlement
):
    reconciliation_before = COST_EMISSION_ACK_ERRORS._value.get()
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
        assert not leg.send(PCM)
    # Death discovery is not a serving decision and emits nothing.
    assert observed(leg.routing_target, outcome, reason) == before
    assert leg.normalized_death_reason == reason
    hop = live_failure.PendingLiveFailover.from_socket(leg, family, 'soniox')
    assert hop.reason == reason
    hop.to_mode = 'modulate'
    fallback_reason = {'provider_budget_exhausted': 'quota', 'provider_auth_rejected': 'auth'}.get(reason, reason)
    fallback = OMI_FALLBACK_TOTAL.labels(
        component='stt_live_session',
        from_mode=family,
        to_mode='modulate',
        reason=fallback_reason,
        outcome=settlement,
    )
    decision = COST_SETTLEMENTS.labels(target=leg.routing_target, outcome=outcome, reason=reason, path='failover')
    baseline, decision_before = fallback._value.get(), decision._value.get()
    if settlement == 'recovered':
        hop.note_transcript([{'text': 'synthetic'}])
    else:
        hop.note_failure('provider_auth_rejected', continuing=settlement == 'degraded')
    hop.note_failure('connection_lost')
    # Even a second decision object cannot settle the same source twice.
    live_failure.PendingLiveFailover.from_socket(leg, family, 'modulate').note_failure(None)
    assert fallback._value.get() == baseline + 1
    assert decision._value.get() == decision_before + 1
    assert COST_EMISSION_ACK_ERRORS._value.get() == reconciliation_before
    assert observed(leg.routing_target, outcome, reason) == before + 1
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


@pytest.mark.parametrize('cause', ['first_text_deadline', 'empty_streak', 'capacity_full', 'replay_ring_overflow'])
def test_window_bounded_raw_reason_wins_even_without_typed_proxy(cause):
    leg = serving_leg(family='parakeet')
    before = observed(leg.routing_target, 'censored', cause)
    leg.raw.on_send = lambda: leg.raw.die(raw=cause)
    assert not leg.send(PCM)
    live_failure.settle_terminal_socket(leg, leg.service.value, 'connection_lost')
    leg.finish()
    assert observed(leg.routing_target, 'censored', cause) == before + 1
    assert not live_chain.health._cost_local


def test_false_send_while_raw_socket_is_alive_is_send_failed():
    class FalseSendSocket(ServingSocket):
        fail_send = False

        def send(self, _audio):
            return not self.fail_send

    raw = FalseSendSocket()
    leg = serving_leg(raw)
    raw.fail_send = True
    before = observed(leg.routing_target, 'provider_failure', 'send_failed')
    assert not leg.send(PCM)
    live_failure.settle_terminal_socket(leg, leg.service.value, 'connection_lost')
    leg.finish()
    assert leg.normalized_death_reason == 'send_failed'
    assert observed(leg.routing_target, 'provider_failure', 'send_failed') == before + 1
    assert live_chain.health._cost_local[(leg.routing_target, 'all')].failures == 1


@pytest.mark.parametrize(
    'source_reason,metric_reason',
    [
        ('provider_budget_exhausted', 'quota'),
        ('provider_auth_rejected', 'auth'),
        ('modulate_serve_error', 'modulate_serve_error'),
        ('connection_lost', 'connection_lost'),
        ('first_text_deadline', 'first_text_deadline'),
        ('capacity_full', 'capacity_full'),
        ('replay_ring_overflow', 'replay_ring_overflow'),
    ],
)
def test_pending_failover_emits_stable_fallback_reason_labels(monkeypatch, source_reason, metric_reason):
    events = []
    monkeypatch.setattr(live_failure, 'record_fallback', lambda **kw: events.append(kw))
    hop = live_failure.PendingLiveFailover(
        component='stt_live_session', from_mode='soniox', to_mode='modulate', reason=source_reason
    )
    hop.note_failure('send_failed')
    assert len(events) == 1
    assert events[0]['reason'] == metric_reason


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


def test_discovery_cannot_consume_later_serving_decision():
    leg = serving_leg()
    leg.raw.die('modulate_serve_error', 'vendor diagnostic')
    baseline = observed(leg.routing_target, 'provider_failure', 'modulate_serve_error')
    assert leg.is_connection_dead
    assert observed(leg.routing_target, 'provider_failure', 'modulate_serve_error') == baseline
    live_failure.settle_terminal_socket(leg, 'modulate', 'connection_lost')
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
    live_failure.settle_terminal_socket(leg, 'modulate', 'connection_lost')
    assert observed(leg.routing_target, 'provider_failure', 'modulate_serve_error') == baseline + 1


def test_vocabulary_is_closed_and_classifier_cannot_accept_free_text():
    assert LIVE_STT_REASONS <= ALLOWED_REASONS
    # 33 + the three local delivery deaths split out of capacity_full (P34).
    assert len(LIVE_STT_REASONS) == 36
    assert provider_observation('failover', 'no_text_rescue_complete') is None
    assert provider_observation('failover', 'cancelled') is None
    assert provider_observation('failover', 'replay_ring_overflow') is None  # session-local, never provider failure
    for local_bound in ('send_queue_full', 'replay_send_stalled', 'delivery_expired'):
        assert provider_observation('failover', local_bound) is None  # our send path, never provider failure
    assert normalize_live_stt_reason('cancelled') == 'cancelled'
    assert normalize_live_stt_reason(None, 'unknown free text') == 'connection_lost'
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
@pytest.mark.parametrize(
    'cause', ['first_text_deadline', 'empty_streak', 'capacity_full', 'replay_ring_overflow', 'replay_send_stalled']
)
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
    live_failure.settle_terminal_socket(leg, leg.service.value, 'connection_lost')
    leg.finish()
    assert leg.normalized_death_reason == cause
    assert observed(leg.routing_target, 'censored', cause) == baseline + 1
    assert not live_chain.health._cost_local


@pytest.mark.asyncio
async def test_real_window_failure_survives_raising_send_with_one_censored_observation():
    class RaisingWindow(WindowedParakeetSocket):
        raise_after_fail = False

        def send(self, data):
            if self.raise_after_fail:
                self.fail('first_text_deadline')
                raise ConnectionError('synthetic send race')
            return super().send(data)

    raw = RaisingWindow(lambda _: None, 'http://unused.invalid', 16000, lambda: None)
    leg = serving_leg(raw, family='parakeet')
    baseline = observed(leg.routing_target, 'censored', 'first_text_deadline')
    raw.raise_after_fail = True
    assert not leg.send(PCM)
    live_failure.settle_terminal_socket(leg, leg.service.value, 'connection_lost')
    leg.finish()
    assert leg.normalized_death_reason == 'first_text_deadline'
    assert observed(leg.routing_target, 'censored', 'first_text_deadline') == baseline + 1
    assert not live_chain.health._cost_local


def test_early_client_disconnect_is_not_a_provider_observation():
    leg = serving_leg()
    leg.finish()
    assert leg.leg_outcome.settled
    assert not live_chain.health._cost_local


def test_local_vad_failure_is_censored_rather_than_transport_failure(monkeypatch):
    leg = serving_leg(family='parakeet')

    def broken_gate(*args, **kwargs):
        raise RuntimeError('synthetic VAD fault')

    monkeypatch.setattr(leg.gate, 'process_audio', broken_gate)
    baseline = observed(leg.routing_target, 'censored', 'vad_failed')
    assert not leg.send(PCM)
    live_failure.settle_terminal_socket(leg, leg.service.value, 'connection_lost')
    leg.finish()
    assert leg.normalized_death_reason == 'vad_failed'
    assert observed(leg.routing_target, 'censored', 'vad_failed') == baseline + 1
    assert not live_chain.health._cost_local


@pytest.mark.asyncio
async def test_vad_failure_never_opens_a_provider_circuit(monkeypatch):
    opened = []
    monkeypatch.setattr(
        live_failure, '_open_serving_provider_circuit', lambda reason, provider: opened.append((reason, provider))
    )
    state = SimpleNamespace(stt_terminal_failure=False, active=True, close_code=1000)
    client = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
    await live_failure.terminate_live_stt_session(
        client, state, failure=live_failure.live_stt_upstream_failure('parakeet'), reason='vad_failed', platform='ios'
    )
    assert opened == []
    assert provider_observation('failover', 'vad_failed') is None
    client.close.assert_awaited_once_with(code=1011, reason='transcription_service_unavailable')


def _real_window_leg():
    raw = WindowedParakeetSocket(lambda _: None, 'http://unused.invalid', 16000, lambda: None)
    raw.start()
    return raw, serving_leg(raw, family='parakeet')


async def _settle_failover(leg):
    hop = live_failure.PendingLiveFailover.from_socket(leg, 'parakeet', 'soniox')
    hop.note_failure(None, continuing=True)
    return hop


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel', ['task_cancel', 'transport_finish'])
async def test_listen_cancelled_real_window_is_censored_not_connection_lost(monkeypatch, cancel):
    started = asyncio.Event()

    async def blocked(*args, **kwargs):
        started.set()
        await asyncio.Future()

    monkeypatch.setattr(parakeet_window, 'get_stt_client', lambda: SimpleNamespace(post=blocked))
    raw, leg = _real_window_leg()
    raw.mark_speech()
    assert leg.send(PCM)
    raw.finalize()
    await asyncio.wait_for(started.wait(), 5)  # A POST is in flight.
    target = leg.routing_target
    censored = observed(target, 'censored', 'cancelled')
    lost = observed(target, 'provider_failure', 'connection_lost')
    settled = COST_SETTLEMENTS.labels(target=target, outcome='censored', reason='cancelled', path='failover')
    settled_before = settled._value.get()
    outcome = WINDOW_SESSION_OUTCOME.labels(outcome='no_text', reason='cancelled')
    outcome_before = outcome._value.get()
    # Listen cancels the leg (recovery switch / teardown); the provider did nothing.
    if cancel == 'task_cancel':
        raw._pump_task.cancel()
    else:
        raw.finish()
    await asyncio.gather(raw._pump_task, return_exceptions=True)
    assert raw.is_connection_dead and raw.death_reason == 'cancelled'
    assert outcome._value.get() == outcome_before + 1
    assert leg.is_connection_dead
    assert leg.normalized_death_reason == 'cancelled'
    hop = await _settle_failover(leg)
    assert hop.reason == 'cancelled'
    leg.finish()
    assert observed(target, 'censored', 'cancelled') == censored + 1
    assert observed(target, 'provider_failure', 'connection_lost') == lost
    assert settled._value.get() == settled_before + 1
    # Censored: neither the gate numerator nor its denominator moves.
    assert not live_chain.health._cost_local


@pytest.mark.asyncio
async def test_window_pump_ending_on_its_own_is_still_connection_lost():
    raw, leg = _real_window_leg()
    target = leg.routing_target
    lost = observed(target, 'provider_failure', 'connection_lost')
    # The pump ended without listen closing or cancelling it.
    raw._on_pump_done(SimpleNamespace(cancelled=lambda: False))
    assert raw.death_reason == 'connection_lost'
    assert leg.normalized_death_reason == 'connection_lost'
    await _settle_failover(leg)
    leg.finish()
    await asyncio.gather(raw._pump_task, return_exceptions=True)
    assert observed(target, 'provider_failure', 'connection_lost') == lost + 1
    state = live_chain.health._cost_local[(target, 'all')]
    assert state.n == state.failures == 1


def test_cancelled_failovers_cannot_trip_the_disruption_gate():
    pod = live_chain.health
    target = 'parakeet-window'
    for i in range(400):
        uid = f'synthetic-cancel-{i}'
        if i % 2:
            assert pod.record_session(target, 'en', 'failover', None, uid, 'cancelled')
        else:
            assert pod.record_session(target, 'en', 'text', None, uid, 'text')
    state = pod._cost_local[(target, 'all')]
    # 50% cancelled is far above the 0.08 gate, yet only text sessions count.
    assert state.threshold == 0.08
    assert state.n == 200 and state.failures == 0
    assert state.stage == 100


def test_connection_lost_failovers_still_trip_the_disruption_gate():
    pod = live_chain.health
    target = 'parakeet-window'
    for i in range(400):
        uid = f'synthetic-lost-{i}'
        if i % 2:
            pod.record_session(target, 'en', 'failover', None, uid, 'connection_lost')
        else:
            pod.record_session(target, 'en', 'text', None, uid, 'text')
        if pod._cost_local[(target, 'all')].stage == 0:
            break
    assert pod._cost_local[(target, 'all')].stage == 0


@pytest.mark.parametrize('reason', [None, 'unknown free text'])
def test_unknown_failover_reason_still_counts_against_the_provider(reason):
    pod = live_chain.health
    target = 'parakeet-window'
    before = observed(target, 'provider_failure', 'connection_lost')
    assert pod.record_session(target, 'en', 'failover', None, 'synthetic-unknown', reason)
    assert observed(target, 'provider_failure', 'connection_lost') == before + 1
    assert pod._cost_local[(target, 'all')].failures == 1
