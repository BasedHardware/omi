"""Transient Soniox rate limits, bounded reconnects, and provider socket gauge leases."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from utils.stt import connect_backoff, live_chain, live_router
from routers.listen.receiver import ListenReceiver
from utils.stt.soniox import (
    SONIOX_CONNECT_RETRY_DEADLINE_SECONDS,
    SONIOX_CONNECT_RETRY_DELAYS,
    SonioxRateLimitError,
    process_audio_soniox,
)
from utils.stt.socket import (
    STTSocket,
    record_live_stt_socket_closed,
    record_live_stt_socket_open,
    track_live_stt_socket,
)
from utils.stt.provider_resilience import ProviderCircuitBreaker
from utils.stt.recovery_state import LiveRecoveryController
from utils.stt import streaming
from utils.stt.streaming import STTService, _classify_provider_account_rejection, _fallback_failure_reason


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


@pytest.fixture(autouse=True)
def fresh_connect_backoff():
    connect_backoff.connect_backoff().reset()


class Fake429(Exception):
    status_code = 429


class FakeSocket(STTSocket):
    def __init__(self, *, dead=False, fail_finish=False, fail_drain=False):
        self.dead = dead
        self.fail_finish = fail_finish
        self.fail_drain = fail_drain

    def send(self, data, *args, **kwargs):
        return True

    def finish(self):
        if self.fail_finish:
            raise RuntimeError('finish failed')

    def finalize(self):
        pass

    @property
    def is_connection_dead(self):
        return self.dead

    @property
    def death_reason(self):
        return 'closed' if self.dead else None

    async def drain_and_close(self):
        if self.fail_drain:
            raise RuntimeError('drain failed')


@pytest.mark.asyncio
async def test_soniox_connect_429_retries_are_bounded_and_end_as_transient(monkeypatch):
    from utils.metrics import OMI_LIVE_STT_OPEN_STREAMS

    attempts = []
    sleeps = []
    gauge = OMI_LIVE_STT_OPEN_STREAMS.labels(provider='soniox')
    before_open = gauge._value.get()

    async def connect(*args, **kwargs):
        attempts.append(kwargs['open_timeout'])
        raise Fake429()

    async def sleep(delay):
        sleeps.append(delay)

    monkeypatch.setenv('SONIOX_API_KEY', 'test-key')
    monkeypatch.setattr('utils.stt.soniox.websockets.connect', connect)
    monkeypatch.setattr('utils.stt.soniox.asyncio.sleep', sleep)
    monkeypatch.setattr('utils.stt.soniox.random.uniform', lambda low, high: high)

    with pytest.raises(SonioxRateLimitError) as error:
        await process_audio_soniox(lambda _: None, 16000, 'en')

    assert error.value.reason == 'provider_rate_limited'
    assert len(attempts) == len(SONIOX_CONNECT_RETRY_DELAYS) + 1
    assert all(0 < timeout <= SONIOX_CONNECT_RETRY_DEADLINE_SECONDS for timeout in attempts)
    assert sleeps == [delay * 1.25 for delay in SONIOX_CONNECT_RETRY_DELAYS]
    assert all(0 <= delay <= base * 1.25 for delay, base in zip(sleeps, SONIOX_CONNECT_RETRY_DELAYS))
    assert sum(sleeps) <= SONIOX_CONNECT_RETRY_DEADLINE_SECONDS
    assert gauge._value.get() == before_open


def test_connect_rate_limit_does_not_enter_account_rejection_or_quota_path():
    error = SonioxRateLimitError('transient')
    assert _classify_provider_account_rejection('soniox', str(error)) is None
    assert _fallback_failure_reason(error) == 'provider_429'
    assert live_chain.failure_reason(error) == 'provider_429'
    assert live_chain.failure_reason(RuntimeError('unrelated failure containing request 429')) == 'provider_5xx'
    from utils.stt.live_failure import note_typed_provider_death

    assert not note_typed_provider_death(
        type('Socket', (), {'typed_death_reason': 'provider_rate_limited'})(), 'soniox'
    )


class FakeCircuit:
    def __init__(self):
        self.account_failures = 0
        self.selection_failures = 0
        self.probe_releases = 0
        self.closes = 0
        self.state = 'closed'

    def allow_request(self, **_kwargs):
        return True

    def account_cooldown_elapsed(self):
        return True

    def record_account_rejection(self):
        self.account_failures += 1

    def record_account_failure(self, *_args, **_kwargs):
        self.account_failures += 1

    def record_failure(self):
        self.selection_failures += 1

    def record_success(self, **_kwargs):
        pass

    def release_probe(self):
        self.probe_releases += 1

    def deferred_result_callbacks(self):
        return (lambda: None), self._close

    def _close(self):
        self.closes += 1


@pytest.mark.asyncio
async def test_legacy_primary_connect_preserves_typed_rate_limit_reason(monkeypatch):
    circuits = {service: FakeCircuit() for service in STTService}
    monkeypatch.setattr(streaming, '_circuit_for_primary', lambda service: circuits[service])
    monkeypatch.setattr(streaming, 'fallback_socket_is_serving', lambda _socket: _serving())
    recorded = []
    monkeypatch.setattr(streaming, 'record_stt_provider_connect', lambda **kwargs: recorded.append(kwargs))

    async def _serving():
        return True

    async def connect_primary():
        raise SonioxRateLimitError('transient')

    fallback = FakeSocket()
    socket, service = await streaming.connect_stt_socket_with_fallback(
        use_config=False,
        primary_service=STTService.soniox,
        connect_primary=connect_primary,
        connect_modulate=lambda: _connected(fallback),
    )

    assert (socket, service) == (fallback, STTService.modulate)
    assert any(
        event['provider'] == 'soniox' and event['outcome'] == 'failure' and event['reason'] == 'provider_429'
        for event in recorded
    )
    assert circuits[STTService.soniox].selection_failures == 0
    assert circuits[STTService.soniox].probe_releases == 1
    assert circuits[STTService.soniox].account_failures == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('circuit_state', ['closed', 'half_open'])
async def test_legacy_post_upgrade_rate_limit_releases_probe_not_failure(monkeypatch, circuit_state):
    """The primary accepts the upgrade then refuses with a typed 429 (the
    post-upgrade serving check is the modulate-shaped branch; half_open is
    the probe-death twin): the refusal releases the admission and keeps
    provider_429 classification instead of recording a connect failure."""
    circuits = {service: FakeCircuit() for service in STTService}
    circuits[STTService.modulate].state = circuit_state
    monkeypatch.setattr(streaming, '_circuit_for_primary', lambda service: circuits[service])

    async def _serve(socket):
        return not getattr(socket, 'dead', False)

    monkeypatch.setattr(streaming, 'fallback_socket_is_serving', _serve)
    recorded = []
    monkeypatch.setattr(streaming, 'record_stt_provider_connect', lambda **kwargs: recorded.append(kwargs))

    rejected = FakeSocket(dead=True)
    rejected.typed_death_reason = 'provider_rate_limited'

    async def connect_primary():
        return rejected

    fallback = FakeSocket()
    socket, service = await streaming.connect_stt_socket_with_fallback(
        use_config=False,
        primary_service=STTService.modulate,
        connect_primary=connect_primary,
        connect_deepgram=lambda: _connected(fallback),
    )

    assert (socket, service) == (fallback, STTService.deepgram)
    assert any(
        event['provider'] == 'modulate' and event['outcome'] == 'failure' and event['reason'] == 'provider_rate_limited'
        for event in recorded
    )
    assert circuits[STTService.modulate].selection_failures == 0
    assert circuits[STTService.modulate].probe_releases == 1


async def _connected(socket):
    return socket


@pytest.mark.asyncio
async def test_configured_rate_limit_releases_admission_without_selection_failure(monkeypatch):
    circuit = FakeCircuit()
    monkeypatch.setattr(streaming, '_circuit_for_primary', lambda _service: circuit)

    async def connect():
        raise SonioxRateLimitError('transient 429')

    with pytest.raises(RuntimeError, match='Configured STT chain exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=STTService.soniox,
            connect_primary=connect,
            callbacks={STTService.soniox: connect},
            failed=set(),
            models=['soniox'],
        )

    assert circuit.account_failures == 0
    assert circuit.selection_failures == 0
    assert circuit.closes == 1


@pytest.mark.asyncio
async def test_configured_burst_429_then_healthy_session_admitted(monkeypatch):
    """Repeated 429s never open the selection circuit: the next session
    connects the same provider and its connect-time success stands."""
    breaker = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30)
    monkeypatch.setattr(streaming, '_circuit_for_primary', lambda _service: breaker)
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    dials = []

    async def connect():
        dials.append(len(dials))
        if len(dials) <= 2:
            raise SonioxRateLimitError('transient 429')
        return FakeSocket()

    for _ in range(2):
        with pytest.raises(RuntimeError, match='Configured STT chain exhausted'):
            await live_chain.connect_configured_chain(
                primary_service=STTService.soniox,
                connect_primary=connect,
                callbacks={STTService.soniox: connect},
                failed=set(),
                models=['soniox'],
            )
        assert breaker.state == 'closed'

    socket, service = await live_chain.connect_configured_chain(
        primary_service=STTService.soniox,
        connect_primary=connect,
        callbacks={STTService.soniox: connect},
        failed=set(),
        models=['soniox'],
    )
    assert service == STTService.soniox
    assert len(dials) == 3
    assert breaker.state == 'closed'


@pytest.mark.asyncio
async def test_half_open_429_releases_probe_slot_without_extending_bench(monkeypatch):
    """A 429 on a recovery probe frees the slot for reuse: it neither
    re-opens/extends the prior bench nor closes the breaker as a success."""
    ticks = [1000.0]
    breaker = ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30, clock=lambda: ticks[0])
    monkeypatch.setattr(streaming, '_circuit_for_primary', lambda _service: breaker)
    breaker.record_failure()
    assert breaker.state == 'open'
    opened_at = breaker._opened_at
    ticks[0] += 31.0

    async def connect():
        raise SonioxRateLimitError('transient 429')

    with pytest.raises(RuntimeError, match='Configured STT chain exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=STTService.soniox,
            connect_primary=connect,
            callbacks={STTService.soniox: connect},
            failed=set(),
            models=['soniox'],
        )

    assert breaker.state == 'half_open'
    assert breaker._probes_in_flight == 0
    assert breaker._opened_at == opened_at
    assert breaker._account_cooldown is None
    assert breaker.allow_request()


@pytest.mark.asyncio
async def test_router_on_target_429_releases_target_probe_without_bench(monkeypatch):
    """Under an active router, a 429 against the selected target releases the
    target circuit's probe — no selection bench, no fleet quarantine."""
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setenv(
        'STT_ROUTING_TARGETS_JSON',
        json.dumps([{'id': 'soniox-b', 'family': 'soniox', 'cost_per_audio_hour': 0.05}]),
    )
    monkeypatch.setattr(live_router, '_target_circuits', {})
    monkeypatch.setattr(live_chain.health, 'cost_snapshot', lambda *_: {})
    monkeypatch.setattr(live_chain.health, 'cached_snapshot', lambda *_: {})
    quarantined = []
    monkeypatch.setattr(live_chain.health, 'quarantine', lambda *args: quarantined.append(args))
    monkeypatch.setattr(live_chain.health, 'quarantine_target', lambda *args: quarantined.append(args))
    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', AsyncMock(return_value=True))
    selected = live_chain.registry()[0]
    circuit = live_router.target_circuit(selected, streaming._soniox_circuit)
    assert circuit is streaming._soniox_circuit

    async def connect():
        raise SonioxRateLimitError('transient 429')

    with pytest.raises(RuntimeError, match='Configured STT chain exhausted'):
        await live_chain.connect_configured_chain(
            primary_service=STTService.soniox,
            connect_primary=connect,
            callbacks={STTService.soniox: connect},
            failed=set(),
            models=['soniox'],
            routing_uid='synthetic-uid',
            routing_language='en',
        )

    assert live_router.target_circuit(selected, streaming._soniox_circuit) is circuit
    assert circuit.state == 'closed'
    assert circuit._failures == 0
    assert circuit._probes_in_flight == 0
    assert streaming._soniox_circuit._probes_in_flight == 0
    assert quarantined == []


def test_provider_socket_gauge_open_close_helpers_balance():
    from utils.metrics import OMI_LIVE_STT_OPEN_STREAMS

    gauge = OMI_LIVE_STT_OPEN_STREAMS.labels(provider='soniox')
    before = gauge._value.get()
    record_live_stt_socket_open('soniox')
    assert gauge._value.get() == before + 1
    record_live_stt_socket_closed('soniox')
    assert gauge._value.get() == before


@pytest.mark.asyncio
async def test_receiver_drain_releases_gauge_when_close_raises():
    from utils.metrics import OMI_LIVE_STT_OPEN_STREAMS

    gauge = OMI_LIVE_STT_OPEN_STREAMS.labels(provider='soniox')
    before = gauge._value.get()
    socket = FakeSocket(fail_drain=True)
    receiver = ListenReceiver.__new__(ListenReceiver)
    receiver.host = SimpleNamespace(
        is_multi_channel=False,
        stt_service=STTService.soniox,
        state=SimpleNamespace(active=True, stt_terminal_failure=False),
        request=SimpleNamespace(),
    )
    receiver.recovery = LiveRecoveryController(receiver.host)
    receiver.channel_configs = []
    receiver.stt_socket = socket
    receiver.stt_sockets_multi = []
    receiver._resilient_audio = None
    receiver._replay_recovery_task = None
    receiver._replay_delivery = None
    receiver._pending_live_failover = None
    track_live_stt_socket(socket, 'soniox')
    assert gauge._value.get() == before + 1
    await receiver._drain_stt_sockets()
    assert gauge._value.get() == before


def test_managed_socket_gauge_tracks_physical_close_not_death_latch():
    from utils.metrics import OMI_LIVE_STT_OPEN_STREAMS
    from utils.stt.live_session import LiveLegSocket

    gauge = OMI_LIVE_STT_OPEN_STREAMS.labels(provider='soniox')
    before = gauge._value.get()
    record_live_stt_socket_open('soniox')
    socket = LiveLegSocket.__new__(LiveLegSocket)
    socket.raw = FakeSocket(dead=True)
    socket._dead = False
    socket._terminal_reason = None
    socket._local_death_reason = None
    socket._replay_failure_reason = None
    socket._closing_for_health = False
    socket._rescue_timer = None
    from utils.stt.live_outcome import LiveLegOutcome

    socket.leg_outcome = LiveLegOutcome('soniox', 'en', None, None, lambda *args: True)
    socket._cost_text_seen = False
    socket._routing_active = False
    socket._pending_selection = None
    socket._open_gauge_released = False
    socket._first_speech_at = None
    socket._speech_ms_for_health = 0
    socket._transcript_outcome = None
    socket.service = STTService.soniox

    assert socket.is_connection_dead
    assert gauge._value.get() == before + 1
    socket.finish()
    assert gauge._value.get() == before
