"""Transient Soniox rate limits, bounded reconnects, and provider socket gauge leases."""

import asyncio

import pytest

from utils.stt import live_chain
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
from utils.stt import streaming
from utils.stt.streaming import STTService, _classify_provider_account_rejection, _fallback_failure_reason


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
    from utils.stt.live_failure import note_typed_provider_death

    assert not note_typed_provider_death(
        type('Socket', (), {'typed_death_reason': 'provider_rate_limited'})(), 'soniox'
    )


@pytest.mark.asyncio
async def test_connect_rate_limit_uses_short_selection_failure_not_account_bench(monkeypatch):
    class Circuit:
        account_failures = 0
        selection_failures = 0

        def allow_request(self, **kwargs):
            return True

        def record_account_failure(self, *_args, **_kwargs):
            self.account_failures += 1

        def record_failure(self):
            self.selection_failures += 1

        def record_success(self, **_kwargs):
            pass

        def deferred_result_callbacks(self):
            return (lambda: None), (lambda: None)

    circuit = Circuit()
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
    assert circuit.selection_failures == 1


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
    from types import SimpleNamespace

    from utils.metrics import OMI_LIVE_STT_OPEN_STREAMS

    gauge = OMI_LIVE_STT_OPEN_STREAMS.labels(provider='soniox')
    before = gauge._value.get()
    socket = FakeSocket(fail_drain=True)
    receiver = ListenReceiver.__new__(ListenReceiver)
    receiver.host = SimpleNamespace(is_multi_channel=False, stt_service=STTService.soniox)
    receiver.channel_configs = []
    receiver.stt_socket = socket
    receiver.stt_sockets_multi = []
    track_live_stt_socket(socket, 'soniox')
    assert gauge._value.get() == before + 1
    await receiver._drain_stt_sockets()
    assert gauge._value.get() == before
