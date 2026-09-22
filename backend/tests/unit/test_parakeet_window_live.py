"""Live TDT runs through real admission, socket, VAD and receiver seams; no network."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import numpy as np
import pytest

from utils.stt import parakeet_window as window, provider_resilience, streaming as st, vad_gate
from utils.stt.live_metrics import WINDOW_FORCED_CUTS, WINDOW_POSTS
from utils.stt.live_session import (
    WINDOW_VAD_CONTINUE_THRESHOLD,
    WINDOW_VAD_HANGOVER_MS,
    WINDOW_VAD_SPEECH_THRESHOLD,
    LiveChainSession,
    LiveLegSocket,
)
from routers.listen.receiver import ListenReceiver

_REAL_SLEEP = asyncio.sleep


@pytest.fixture(autouse=True)
def runtime(monkeypatch):
    monkeypatch.setenv('STT_CONNECT_ORDER_FROM_CONFIG', 'true')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_SESSIONS', '1')
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://tdt.invalid')
    monkeypatch.setenv('SONIOX_API_KEY', 'test')
    monkeypatch.setenv('MODULATE_API_KEY', 'test')
    monkeypatch.setenv('HOSTED_SPEAKER_EMBEDDING_API_URL', 'http://embedding.invalid')
    monkeypatch.setattr(window, 'admission', window.WindowAdmission())
    monkeypatch.setattr(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0)
    for provider in ('parakeet', 'modulate', 'deepgram', 'soniox'):
        monkeypatch.setattr(
            st,
            f'_{provider}_circuit',
            provider_resilience.ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30),
        )
    monkeypatch.setattr(st, '_deepgram_is_available', lambda: True)
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    # Keep the production VAD state machine/remapper; supply a deterministic
    # speech detector (nonzero PCM=speech) instead of downloading a model.
    # Ingest AGC scales the 0x01 marker, so a byte-literal test would drop speech.
    monkeypatch.setattr(vad_gate, '_get_ort_session', lambda: None)

    def _vad_nonzero(_self, data: bytes) -> bool:
        if len(data) < 2:
            return False
        aligned = data[: len(data) - (len(data) % 2)]
        return bool(np.any(np.frombuffer(aligned, dtype=np.int16)))

    monkeypatch.setattr(vad_gate.VADStreamingGate, '_run_vad', _vad_nonzero)

    @asynccontextmanager
    async def semaphore():
        yield

    monkeypatch.setattr(window, 'get_stt_semaphore', semaphore)


class Client:
    def __init__(self, status=200, data=None, error=None):
        self.status, self.data, self.error = status, data or {'text': 'hello'}, error
        self.requests = []
        self.called = asyncio.Event()

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        self.called.set()
        if self.error:
            raise self.error
        return httpx.Response(self.status, json=self.data, request=httpx.Request('POST', url))


class SeqClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests = []

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        data = self.payloads[min(len(self.requests) - 1, len(self.payloads) - 1)]
        if callable(data):
            data = data(len(self.requests), kwargs)
        return httpx.Response(200, json=data, request=httpx.Request('POST', url))


async def _wait_requests(client, count: int) -> None:
    deadline = asyncio.get_running_loop().time() + 2
    while len(client.requests) < count:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f'expected {count} POSTs, got {len(client.requests)}')
        await _REAL_SLEEP(0)


def receiver():
    emitted = []
    host = SimpleNamespace(
        request=SimpleNamespace(uid='user'),
        language='en',
        stt_language='multi',
        multi_lang_enabled=True,
        stt_model='parakeet-window',
        stt_service=st.STTService.parakeet,
        vocabulary=[],
        state=SimpleNamespace(active=True),
        is_multi_channel=False,
        use_custom_stt=False,
    )
    return SimpleNamespace(
        host=host,
        _stt_failed_providers=set(),
        vad_gate=None,
        _enqueue_stt_segments=lambda segments, **kwargs: emitted.extend(segments),
        _telemetry_platform=lambda: 'ios',
        emitted=emitted,
    )


@pytest.mark.asyncio
async def test_speech_only_post_silence_flush_tail_timestamps_and_usage(monkeypatch):
    client = Client()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    from utils.stt import live_session

    usage = []
    monkeypatch.setattr(live_session, 'record_live_stt_audio_seconds', lambda **kw: usage.append(kw))
    recv = receiver()
    session = LiveChainSession(recv)
    socket = await session.connect(16000)
    assert isinstance(socket.raw, st.ParakeetStreamingSocket)
    # Pure noise/silence never receives a POST, including at teardown.
    assert socket.send(bytes(32000))
    assert not socket.raw._buf
    assert client.requests == []
    assert socket.send(b'\x01\x00' * 16000)
    assert socket.send(bytes(16000))
    assert socket.send(bytes(16000))
    await socket.drain_and_close()
    assert len(client.requests) == 1
    url, kwargs = client.requests[0]
    assert url.endswith('/v1/transcribe')
    assert list(kwargs) == ['files']  # the batch endpoint takes no language parameter
    assert kwargs['files']['file'][1].startswith(b'RIFF')
    assert recv.emitted[0]['text'] == 'hello'
    assert recv.emitted[0]['start'] >= 1.0
    assert usage == [{'provider': 'parakeet', 'platform': 'ios', 'seconds': 1.0}]
    assert session.consume_speech_ms_delta() == 1000
    assert session.consume_speech_ms_delta() == 0
    assert window.admission.active == 0


@pytest.mark.asyncio
async def test_pure_noise_close_posts_nothing(monkeypatch):
    client = Client()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    socket = await LiveChainSession(receiver()).connect(16000)
    for _ in range(12):
        assert socket.send(bytes(32000))
    await socket.drain_and_close()
    assert not client.requests
    assert window.admission.active == 0


@pytest.mark.asyncio
async def test_windowed_gate_keeps_the_billed_threshold_with_a_short_tail(monkeypatch):
    """The windowed leg differs from the billed Deepgram gate in its tail, not its
    threshold. Quiet far-field speech is admitted by the level-corrected copy the gate
    scores, not by a lower threshold, so the start value tracks VAD_GATE_SPEECH_THRESHOLD
    and there is no hysteresis gap for borderline audio to slip through."""
    client = Client()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    socket = await LiveChainSession(receiver()).connect(16000)
    gate = socket.gate
    assert gate is not None
    assert gate.mode == 'active'
    assert gate._hangover_ms == WINDOW_VAD_HANGOVER_MS == 300
    assert gate._speech_threshold == WINDOW_VAD_SPEECH_THRESHOLD == vad_gate.VAD_GATE_SPEECH_THRESHOLD
    assert gate._continue_threshold == WINDOW_VAD_CONTINUE_THRESHOLD == gate._speech_threshold
    await socket.drain_and_close()
    assert window.admission.active == 0


@pytest.mark.asyncio
async def test_overflow_moves_to_soniox_and_releases_on_finish(monkeypatch):
    first = await LiveChainSession(receiver()).connect(16000)
    tail = SimpleNamespace(is_connection_dead=False, finish=lambda: None)
    soniox = AsyncMock(return_value=tail)
    monkeypatch.setattr(st, 'process_audio_soniox', soniox)
    recv = receiver()
    second = await LiveChainSession(recv).connect(16000)
    assert second.raw is tail
    assert recv.host.stt_service == st.STTService.soniox
    assert st._parakeet_circuit.state == 'closed'  # local admission isn't GPU failure
    first.finish()
    first.finish()
    assert window.admission.active == 0
    await asyncio.gather(first.raw._pump_task, return_exceptions=True)
    second.finish()


@pytest.mark.parametrize('fault', ['503', 'timeout'])
@pytest.mark.asyncio
async def test_post_failure_benches_leg_and_releases_slot(monkeypatch, fault):
    client = Client(status=503 if fault == '503' else 200, error=TimeoutError() if fault == 'timeout' else None)
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(lambda _: None, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000)
    sock.finalize()
    await sock._pump_task
    assert sock.is_connection_dead
    assert st._parakeet_circuit.state == 'open'
    assert window.admission.active == 0
    assert len(client.requests) == 1
    await sock.drain_and_close()
    assert len(client.requests) == 1  # no retry of a failed window during teardown


@pytest.mark.asyncio
async def test_one_post_in_flight_buffer_bounded_and_cancel_releases(monkeypatch):
    started = asyncio.Event()
    calls = []

    async def blocked(*args, **kwargs):
        calls.append(1)
        started.set()
        await asyncio.Future()

    monkeypatch.setattr(window, 'get_stt_client', lambda: SimpleNamespace(post=blocked))
    sock = window.connect_window(lambda _: None, 16000)
    sock.mark_speech()
    assert sock.send(b'\x01\x00' * 16000 * 6)
    await started.wait()
    room = sock._buffer_cap() - len(sock._buf)
    assert sock.send(b'\x01\x00' * (room // 2))
    assert not sock.send(b'\x01\x00')
    assert len(calls) == 1
    assert sock.is_connection_dead
    assert sock.death_reason == 'capacity_full'
    assert st._parakeet_circuit.state == 'open'
    assert window.admission.active == 0
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancellation_before_pump_start_and_during_drain_release(monkeypatch):
    sock = window.connect_window(lambda _: None, 16000)
    sock._pump_task.cancel()
    await asyncio.gather(sock._pump_task, return_exceptions=True)
    assert window.admission.active == 0
    assert sock.is_connection_dead
    sock = window.connect_window(lambda _: None, 16000)
    started = asyncio.Event()

    async def blocked(*args, **kwargs):
        started.set()
        await asyncio.Future()

    monkeypatch.setattr(window, 'get_stt_client', lambda: SimpleNamespace(post=blocked))
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000)
    drain = asyncio.create_task(sock.drain_and_close())
    await started.wait()
    assert window.admission.active == 0
    drain.cancel()
    with pytest.raises(asyncio.CancelledError):
        await drain
    assert window.admission.active == 0


@pytest.mark.asyncio
async def test_connect_failure_releases_lease(monkeypatch):
    monkeypatch.setattr(window.WindowedParakeetSocket, 'start', lambda self: (_ for _ in ()).throw(RuntimeError()))
    with pytest.raises(RuntimeError):
        window.connect_window(lambda _: None, 16000)
    assert window.admission.active == 0


@pytest.mark.asyncio
async def test_vad_initialization_and_inference_never_fail_open_to_tdt(monkeypatch):
    from utils.stt import live_session

    recv = receiver()
    session = LiveChainSession(recv)
    sock = await session.connect(16000)
    monkeypatch.setattr(sock.gate, 'process_audio', lambda *a: (_ for _ in ()).throw(RuntimeError()))
    assert not sock.send(b'\x01\x00' * 16000)
    assert sock.is_connection_dead
    assert window.admission.active == 0
    await asyncio.gather(sock.raw._pump_task, return_exceptions=True)
    monkeypatch.setattr(live_session, 'VADStreamingGate', lambda **kw: (_ for _ in ()).throw(RuntimeError()))
    tail = SimpleNamespace(is_connection_dead=False, finish=lambda: None)
    monkeypatch.setattr(st, 'process_audio_soniox', AsyncMock(return_value=tail))
    recv = receiver()
    result = await LiveChainSession(recv).connect(16000)
    assert result.raw is tail
    assert window.admission.active == 0


@pytest.mark.asyncio
async def test_speaker_embedding_optional_and_at_most_once_per_window(monkeypatch):
    sock = window.connect_window(lambda _: None, 16000)
    assign = AsyncMock(return_value=2)
    monkeypatch.setattr(st.ParakeetStreamingSocket, '_assign_speaker', assign)
    assert sock._diarize is False
    sock._diarize = True
    await sock._assign_speaker(b'\x01\x00' * 16000)
    await sock._assign_speaker(b'\x01\x00' * 16000)
    assign.assert_awaited_once()
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_soniox_primary_can_reach_window_and_old_callbacks_are_fenced(monkeypatch):
    recv = receiver()
    recv.host.stt_service, recv.host.stt_model = st.STTService.soniox, 'soniox'
    monkeypatch.setattr(st, 'process_audio_soniox', AsyncMock(side_effect=RuntimeError()))
    session = LiveChainSession(recv)
    first = await session.connect(16000)
    assert isinstance(first.raw, window.WindowedParakeetSocket)
    assert recv.host.stt_service == st.STTService.parakeet
    first.send(b'\x01\x00' * 16000)
    first.raw._stream_transcript([{'start': 0, 'end': 1, 'text': 'one'}])
    first.finish()
    await asyncio.gather(first.raw._pump_task, return_exceptions=True)
    callbacks = []

    async def soniox(callback, *args):
        callbacks.append(callback)
        return SimpleNamespace(is_connection_dead=False, finish=lambda: None)

    recv._stt_failed_providers = {'parakeet'}
    recv.host.stt_service = st.STTService.soniox
    monkeypatch.setattr(st, 'process_audio_soniox', soniox)
    st._soniox_circuit.record_success()
    second = await session.connect(16000)
    first.raw._stream_transcript([{'start': 100, 'end': 101, 'text': 'stale'}])
    callbacks[0]([{'start': 0, 'end': 1, 'text': 'two'}])
    assert [s['text'] for s in recv.emitted] == ['one', 'two']
    assert recv.emitted[1]['start'] >= recv.emitted[0]['end']
    assert recv.emitted[1]['start'] == 1
    second.finish()


@pytest.mark.parametrize('primary', list(st.STTService))
@pytest.mark.asyncio
async def test_receiver_dispatches_all_primary_branches_through_managed_chain(monkeypatch, primary):

    recv = receiver()
    recv.host.stt_service = primary
    sentinel = SimpleNamespace(manages_vad=True)
    connect = AsyncMock(return_value=sentinel)
    monkeypatch.setattr(LiveChainSession, 'connect', connect)
    assert await ListenReceiver._create_stt_socket(recv, lambda _: None, 16000) is sentinel
    connect.assert_awaited_once_with(16000)


@pytest.mark.asyncio
async def test_growing_windows_hold_then_emit_on_drain(monkeypatch):
    posted = []
    delays = []

    async def pacing(delay):
        delays.append(delay)

    monkeypatch.setattr(window.asyncio, 'sleep', pacing)
    payloads = [
        {
            'segments': [
                {'text': 'One.', 'start': 0.0, 'end': 2.4},
                {'text': 'Two', 'start': 2.4, 'end': 5.8},
            ]
        },
        {
            'segments': [
                {'text': 'Two.', 'start': 0.0, 'end': 3.6},
                {'text': 'Three.', 'start': 3.6, 'end': 9.0},
            ]
        },
    ]
    client = SeqClient(payloads)
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    first, second = b'\x01\x00' * 16000 * 6, b'\x02\x00' * 16000 * 6
    assert sock.send(first)
    await _wait_requests(client, 1)
    sock.mark_speech()
    assert sock.send(second)
    await sock.drain_and_close()  # one POST of the whole remaining context, not one per pace step
    assert len(client.requests) == 2
    assert client.requests[0][1]['files']['file'][1].endswith(_agc(first))
    assert len(client.requests[1][1]['files']['file'][1]) > len(client.requests[0][1]['files']['file'][1])
    assert [s['text'] for s in posted] == ['One.', 'Two.', 'Three.']
    for earlier, later in zip(posted, posted[1:]):
        assert later['start'] >= earlier['end']
    assert delays == []  # drain skips pacing so teardown does not hold the slot


@pytest.mark.asyncio
async def test_real_receiver_initializes_window_and_survives_post_failure(monkeypatch):

    base = receiver()
    host = base.host
    host.request.sample_rate = 16000
    host.request.websocket = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
    host.state.stt_terminal_failure = False
    host.client_device_context = SimpleNamespace(platform='ios')
    host.transcripts = SimpleNamespace(enqueue=base.emitted.extend)
    # Exercise initialize/rebuild directly, without running its background monitor.
    host.spawn = lambda coro, **kw: coro.close()
    actual = ListenReceiver(host, [], {})
    client = Client(status=503)
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    callbacks = []

    async def tail(callback, *args):
        callbacks.append(callback)
        return SimpleNamespace(
            is_connection_dead=False, send=lambda _: True, finalize=lambda: None, finish=lambda: None
        )

    monkeypatch.setattr(st, 'process_audio_soniox', tail)
    assert await actual.initialize_stt()
    previous = actual.stt_socket
    assert isinstance(previous, LiveLegSocket)  # no double VAD wrapper/remapping
    previous.send(b'\x01\x00' * 16000)
    previous.finalize()
    await previous.raw._pump_task
    assert previous.is_connection_dead
    assert await actual._failover_stt_socket()
    assert host.stt_service == st.STTService.soniox
    assert host.stt_model == 'soniox'
    assert actual._stt_failed_providers == {'parakeet'}
    assert actual.stt_socket.send(b'\x01\x00' * 16000)
    callbacks[0]([{'speaker': 'speaker_0', 'text': 'tail', 'start': 0, 'end': 1}])
    assert base.emitted[0]['start'] == 1
    assert base.emitted[0]['speaker_id_scope']
    assert window.admission.active == 0
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_hangover_only_tail_after_full_window_is_not_posted(monkeypatch):
    client = Client()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)

    async def pacing(_delay):
        pass

    monkeypatch.setattr(window.asyncio, 'sleep', pacing)
    sock = window.connect_window(lambda _: None, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 6)
    await _wait_requests(client, 1)
    sock.send(bytes(16000))  # admitted hangover has no speech of its own
    await _REAL_SLEEP(0)
    assert len(client.requests) == 1
    await sock.drain_and_close()
    for _url, kwargs in client.requests:
        assert _agc(b'\x01\x00' * 8)[:2] in _posted_pcm(kwargs)
    assert window.admission.active == 0


@pytest.mark.asyncio
async def test_cancelled_connection_liveness_check_releases_window_admission(monkeypatch):
    from utils.stt import live_chain

    entered = asyncio.Event()

    async def check(_socket):
        entered.set()
        await asyncio.Future()

    monkeypatch.setattr(live_chain, 'fallback_socket_is_serving', check)
    task = asyncio.create_task(LiveChainSession(receiver()).connect(16000))
    await entered.wait()
    assert window.admission.active == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert window.admission.active == 0


@pytest.mark.asyncio
async def test_half_open_window_probe_waits_for_real_post_health(monkeypatch):
    now = [0.0]
    cb = provider_resilience.ProviderCircuitBreaker(
        failure_threshold=1, cooldown_seconds=1, serve_error_cooldown_seconds=1, clock=lambda: now[0]
    )
    cb.record_serve_failure()
    now[0] = 1
    monkeypatch.setattr(st, '_parakeet_circuit', cb)
    client = Client()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = await LiveChainSession(receiver()).connect(16000)
    assert cb.state == 'half_open'
    assert not cb.allow_request()
    sock.send(b'\x01\x00' * 16000)
    await sock.drain_and_close()
    assert len(client.requests) == 1
    assert cb.allow_request()  # first real success released its probe
    cb.release_probe()


@pytest.mark.parametrize('dies_before_transcript', [False, True])
@pytest.mark.asyncio
async def test_rebuilt_window_recovers_only_on_text_not_empty_post(monkeypatch, dies_before_transcript):
    from utils.stt import live_failure

    events = []
    monkeypatch.setattr(live_failure, 'record_fallback', lambda **kw: events.append(kw))
    monkeypatch.setattr(st, 'stt_service_models', ['soniox', 'parakeet-window'])
    monkeypatch.setattr(st, 'process_audio_soniox', AsyncMock(side_effect=RuntimeError('unavailable')))
    base = receiver()
    host = base.host
    host.stt_service, host.stt_model = st.STTService.modulate, 'velma-2'
    host.state.stt_terminal_failure = False
    host.client_device_context = SimpleNamespace(platform='ios')
    host.transcripts = SimpleNamespace(enqueue=base.emitted.extend)
    actual = ListenReceiver(host, [], {})
    actual.stt_socket = SimpleNamespace(is_connection_dead=True, typed_death_reason=None, finish=lambda: None)
    actual._stt_rebuild = (lambda _: None, lambda _: None, 16000)
    now = [0.0]
    cb = provider_resilience.ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=1, clock=lambda: now[0])
    cb.record_failure()
    now[0] = 1
    monkeypatch.setattr(st, '_parakeet_circuit', cb)
    client = Client(data={'text': ''})
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)

    assert await actual._failover_stt_socket()
    assert host.stt_service == st.STTService.parakeet  # selected Soniox, adopted TDT
    assert cb.state == 'half_open'
    assert not any(e['outcome'] == 'recovered' for e in events)
    leg = actual.stt_socket
    pcm = b'\x01\x00' * 16000
    assert await leg.raw._transcribe_chunk(pcm, 0, 1) == []
    assert cb.state == 'closed'  # HTTP health is distinct from transcript recovery
    assert not any(e['outcome'] == 'recovered' for e in events)

    client.data = {'text': 'hello'}
    client.status = 503 if dies_before_transcript else 200
    assert leg.send(pcm)
    await leg.drain_and_close()
    if dies_before_transcript:
        assert not await actual._failover_stt_socket()
        assert not any(e['outcome'] == 'recovered' for e in events)
        exhausted = [e for e in events if e['outcome'] == 'exhausted']
        assert {'stt_selection', 'stt_live_session'} <= {e['component'] for e in exhausted}
        assert any(e['component'] == 'stt_selection' and e['to_mode'] == 'parakeet' for e in exhausted)
        assert any(e['component'] == 'stt_live_session' and e['to_mode'] == 'parakeet' for e in exhausted)
    else:
        recovered = [e for e in events if e['outcome'] == 'recovered']
        assert len(recovered) == 2
        assert {e['component'] for e in recovered} == {'stt_selection', 'stt_live_session'}
        assert all(e['to_mode'] == 'parakeet' for e in recovered)
        leg.raw._stream_transcript([{'start': 1, 'end': 2, 'text': 'again'}])
        assert len([e for e in events if e['outcome'] == 'recovered']) == 2
    assert window.admission.active == 0


class GateFirstClient:
    """Block only the first POST so a burst can land while one request is in flight."""

    def __init__(self, payloads=None):
        self.payloads = list(payloads) if payloads is not None else [{'text': 'ok'}]
        self.requests = []
        self.started = asyncio.Event()
        self.gate: asyncio.Future[None] | None = None

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        data = self.payloads[min(len(self.requests) - 1, len(self.payloads) - 1)]
        if callable(data):
            data = data(len(self.requests), kwargs)
        if self.gate is None:
            self.gate = asyncio.get_running_loop().create_future()
            self.started.set()
            await self.gate
        return httpx.Response(200, json=data, request=httpx.Request('POST', url))


class HoldClient:
    def __init__(self):
        self.gates: list[asyncio.Future[None]] = []
        self.requests = []

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        gate: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.gates.append(gate)
        await gate
        return httpx.Response(200, json={'text': 'ok'}, request=httpx.Request('POST', url))


async def _wait_gate(client: HoldClient) -> asyncio.Future[None]:
    deadline = asyncio.get_running_loop().time() + 2
    while not client.gates:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError('window POST never started')
        await _REAL_SLEEP(0)
    return client.gates[-1]


async def _release_after_audio(sock, client: HoldClient, during_seconds: int) -> bool:
    gate = await _wait_gate(client)
    client.gates.pop()
    sock.mark_speech()
    accepted = sock.send(b'\x01\x00' * 16000 * during_seconds)
    if not gate.done():
        gate.set_result(None)
    await asyncio.sleep(0)
    return accepted


@pytest.mark.asyncio
async def test_repeated_slow_posts_stay_up(monkeypatch):
    monkeypatch.setattr(window.WindowedParakeetSocket, '_assign_speaker', AsyncMock(return_value=0))
    for _ in range(5):
        client = HoldClient()
        monkeypatch.setattr(window, 'get_stt_client', lambda current=client: current)
        sock = window.connect_window(lambda _: None, 16000)
        sock.mark_speech()
        assert sock.send(b'\x01\x00' * 16000 * 6)
        assert await _release_after_audio(sock, client, 8)
        assert not sock.is_connection_dead
        assert st._parakeet_circuit.state == 'closed'
        sock.finish()
        await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_buffer_overflow_sheds_and_opens_circuit(monkeypatch):
    started = asyncio.Event()

    async def blocked(*args, **kwargs):
        started.set()
        await asyncio.Future()

    monkeypatch.setattr(window, 'get_stt_client', lambda: SimpleNamespace(post=blocked))
    sock = window.connect_window(lambda _: None, 16000)
    sock.mark_speech()
    assert sock.send(b'\x01\x00' * 16000 * 6)
    await started.wait()
    sock.mark_speech()
    room = sock._buffer_cap() - len(sock._buf)
    assert sock.send(b'\x01\x00' * (room // 2))
    assert not sock.send(b'\x01\x00')
    assert sock.is_connection_dead
    assert sock.death_reason == 'capacity_full'
    assert st._parakeet_circuit.state == 'open'
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_single_slow_post_never_kills_window(monkeypatch):
    client = HoldClient()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    monkeypatch.setattr(window.WindowedParakeetSocket, '_assign_speaker', AsyncMock(return_value=0))
    sock = window.connect_window(lambda _: None, 16000)
    sock.mark_speech()
    assert sock.send(b'\x01\x00' * 16000 * 6)
    assert await _release_after_audio(sock, client, 8)
    assert not sock.is_connection_dead
    assert st._parakeet_circuit.state == 'closed'
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.parametrize(
    'status,data,error',
    [
        (413, {'detail': 'too large'}, None),
        (200, {'unexpected': True}, None),
    ],
)
@pytest.mark.asyncio
async def test_malformed_or_413_is_session_local(monkeypatch, status, data, error):
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client(status=status, data=data, error=error))
    sock = window.connect_window(lambda _: None, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000)
    sock.finalize()
    await sock._pump_task
    assert sock.is_connection_dead
    assert st._parakeet_circuit.state == 'closed'
    assert window.admission.active == 0


@pytest.mark.asyncio
async def test_semaphore_queue_timeout_is_session_local(monkeypatch):
    from contextlib import asynccontextmanager

    monkeypatch.setenv('PARAKEET_WINDOW_POST_TIMEOUT_SECONDS', '0.05')

    @asynccontextmanager
    async def stuck():
        await asyncio.Future()
        yield

    monkeypatch.setattr(window, 'get_stt_semaphore', stuck)
    sock = window.connect_window(lambda _: None, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000)
    sock.finalize()
    await sock._pump_task
    assert sock.is_connection_dead
    assert st._parakeet_circuit.state == 'closed'
    assert WINDOW_POSTS.labels(outcome='queue_timeout')._value.get() >= 1
    assert window.admission.active == 0


@pytest.mark.asyncio
async def test_non_window_vad_fails_open_and_honours_override(monkeypatch):
    from utils.stt import live_session

    sent = []
    raw = SimpleNamespace(
        is_connection_dead=False,
        send=lambda data: sent.append(data) or True,
        finish=lambda: sent.append(b'FIN'),
        finalize=lambda: None,
    )
    gate = SimpleNamespace(process_audio=lambda *a: (_ for _ in ()).throw(RuntimeError('onnx')))
    session = LiveChainSession(receiver())
    sock = LiveLegSocket(raw, gate, session, st.STTService.soniox, 16000, False, False)
    audio = b'\x01\x00' * 16
    assert sock.send(audio)
    assert sent == [audio]
    assert not sock.is_connection_dead
    assert sock.gate is None

    monkeypatch.setattr(live_session, 'is_gate_enabled', lambda: True)
    monkeypatch.setattr(live_session, 'VAD_GATE_MODE', 'active')
    recv = receiver()
    recv.host.request.vad_gate_override = 'disabled'
    recv.host.stt_service, recv.host.stt_model = st.STTService.soniox, 'soniox'
    monkeypatch.setattr(st, 'stt_service_models', ['soniox'])
    monkeypatch.setattr(st, 'process_audio_soniox', AsyncMock(return_value=raw))
    managed = await LiveChainSession(recv).connect(16000)
    assert managed.gate is None
    assert managed.window is False


def _wav_duration(kwargs: dict, sample_rate: int = 16000) -> float:
    wav = kwargs['files']['file'][1]
    return max(0.0, (len(wav) - 44) / (2 * sample_rate))


def _posted_pcm(kwargs: dict) -> bytes:
    return kwargs['files']['file'][1][44:]


def _agc(pcm: bytes, peak: float | None = None) -> bytes:
    return window.bounded_agc_pcm16(pcm, peak=peak)[0]


def test_bounded_agc_caps_gain_skips_silence_and_does_not_attenuate():
    silence = bytes(1600)
    out, gain = window.bounded_agc_pcm16(silence)
    assert out == silence
    assert gain == 1.0

    loud = (np.int16(30000) * np.ones(200, dtype=np.int16)).tobytes()
    out, gain = window.bounded_agc_pcm16(loud)
    assert out == loud
    assert gain == 1.0

    quiet = (np.int16(1000) * np.ones(200, dtype=np.int16)).tobytes()
    out, gain = window.bounded_agc_pcm16(quiet)
    assert gain == window.WINDOW_AGC_MAX_GAIN == 4.0
    assert int(np.frombuffer(out, dtype=np.int16)[0]) == 4000

    # Session envelope from loud speech must not lift a later quiet window
    # by more than target/peak — here peak is already above target, so 1×.
    held, held_gain = window.bounded_agc_pcm16(quiet, peak=30000)
    assert held == quiet
    assert held_gain == 1.0

    # Cap binds for a very quiet peak: nearby targets all hit 4×.
    _, low = window.bounded_agc_pcm16(quiet, target=0.7)
    _, high = window.bounded_agc_pcm16(quiet, target=0.9)
    assert low == high == 4.0


def test_posted_agc_deadband_spares_already_levelled_sessions_but_not_admission():
    """Gain rescues quiet audio; on a session that is already loud it only costs accuracy.

    The deadband is on the POSTED (decode) stage alone. Admission keeps gaining the copy
    Silero scores unconditionally — that copy is what admits quiet far-field, and Silero
    is not the thing the distortion hurts.
    """
    pcm = (np.int16(6000) * np.ones(320, dtype=np.int16)).tobytes()

    # Measured peaks from the qualification clips.
    assert window.window_needs_gain(8598.0)  # far-field, 0.26 of full scale
    assert not window.window_needs_gain(17712.0)  # dense speech loud passage, 0.54
    assert not window.window_needs_gain(22405.0)  # clean, 0.68

    # Quiet passages *inside* that loud dense-speech clip. Judged on the session
    # envelope (0.54) these are denied gain and go missing entirely; judged on
    # their own peak they are rescued. This is the whole reason the rule is
    # per-window rather than per-session.
    assert window.window_needs_gain(12121.0)  # 0.370
    assert window.window_needs_gain(12921.0)  # 0.394
    assert not window.window_needs_gain(13828.0)  # 0.422, captured without gain

    # The boundary belongs to the gained side; one count above it does not.
    edge = window.WINDOW_AGC_DEADBAND_PEAK * 32767.0
    assert window.window_needs_gain(edge)
    assert not window.window_needs_gain(edge + 1.0)

    # Equivalently: never apply less than 2x. Anything the deadband admits is
    # boosted by at least that much, so the rule cannot silently become a no-op.
    assert window.bounded_agc_pcm16(pcm, peak=edge)[1] >= 2.0

    # A growing window spanning a level change: loud prefix, quiet tail. Judged on
    # the whole window's peak (0.431) this reads "not quiet" and the tail is lost —
    # measured on dev, that swung earnings WER between 0.155 and 0.262 depending
    # only on where the anchor fell. Judged on the tail it is rescued, and the
    # boost is capped so the loud prefix cannot clip.
    rate = 16000
    tail_bytes = int(window.WINDOW_AGC_TAIL_SECONDS * rate) * 2
    loud = (np.int16(14120) * np.ones(rate * 30, dtype=np.int16)).tobytes()  # 0.431
    quiet = (np.int16(12121) * np.ones(rate * 10, dtype=np.int16)).tobytes()  # 0.370
    g = window.posted_window_gain(loud + quiet, tail_bytes)
    assert g > 1.0, 'a quiet tail behind a loud prefix must still be boosted'
    assert 14120 * g <= 32767, 'the boost must not clip the louder prefix'

    # An all-loud window is still left alone — this is what keeps substitutions down.
    assert window.posted_window_gain(loud, tail_bytes) == 1.0

    # Admission is NOT deadbanded: a loud envelope still gains the scored copy.
    ingest = window.SessionPcmGain()
    ingest.peak = 17712.0
    assert ingest.apply(pcm) != pcm
    assert ingest.last_gain > 1.0


def test_farfield_like_peak_gain_moves_smoothly_with_target():
    # Clip peak from the public far-field file. Not a WER-fitted constant: it
    # only shows that 0.7 / 0.8 / 0.9 all boost and all stay under the 4× cap.
    peak = 8598
    pcm = (np.int16(peak) * np.ones(32, dtype=np.int16)).tobytes()
    g07 = window.bounded_agc_pcm16(pcm, target=0.7)[1]
    g08 = window.bounded_agc_pcm16(pcm, target=0.8)[1]
    g09 = window.bounded_agc_pcm16(pcm, target=0.9)[1]
    assert 1.0 < g07 < g08 < g09 < window.WINDOW_AGC_MAX_GAIN
    assert g09 / g07 < 1.4


@pytest.mark.asyncio
async def test_posted_pcm_is_agc_scaled_buffer_is_not(monkeypatch):
    client = Client()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    sock = window.connect_window(lambda _: None, 16000)
    quiet = (np.int16(1000) * np.ones(16000 * 6, dtype=np.int16)).tobytes()
    sock.mark_speech()
    sock.send(quiet)
    await _wait_requests(client, 1)
    posted = _posted_pcm(client.requests[0][1])
    assert posted == _agc(quiet)
    assert posted != quiet
    assert sock._agc_last_gain == 4.0
    assert sock._agc_peak == 1000.0
    if sock._buf:
        assert int(np.frombuffer(bytes(sock._buf), dtype=np.int16).max()) == 1000
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


def test_session_pcm_gain_silence_and_ceiling():
    gain = window.SessionPcmGain()
    silence = bytes(1600)
    assert gain.apply(silence) == silence
    assert gain.last_gain == 1.0
    assert gain.peak == 0.0

    faint100 = (np.int16(100) * np.ones(200, dtype=np.int16)).tobytes()
    out100 = gain.apply(faint100)
    assert gain.last_gain == window.WINDOW_AGC_MAX_GAIN == 4.0
    assert int(np.frombuffer(out100, dtype=np.int16)[0]) == 400
    assert gain.peak == 100.0

    gain30 = window.SessionPcmGain()
    faint30 = (np.int16(30) * np.ones(200, dtype=np.int16)).tobytes()
    out30 = gain30.apply(faint30)
    assert gain30.last_gain == 4.0
    assert int(np.frombuffer(out30, dtype=np.int16)[0]) == 120


def test_session_pcm_gain_fast_attack_then_holds_running_max():
    gain = window.SessionPcmGain()
    quiet = (np.int16(1000) * np.ones(32, dtype=np.int16)).tobytes()
    loud = (np.int16(30000) * np.ones(32, dtype=np.int16)).tobytes()
    assert gain.apply(quiet) == _agc(quiet)
    assert gain.last_gain == 4.0
    assert gain.apply(loud) == loud
    assert gain.last_gain == 1.0
    held = gain.apply(quiet)
    assert held == quiet
    assert gain.last_gain == 1.0


@pytest.mark.asyncio
async def test_ingest_agc_does_not_compound_posted_agc(monkeypatch):
    client = Client()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    monkeypatch.setattr(window, 'WINDOW_INGEST_AGC', True)
    sock = await LiveChainSession(receiver()).connect(16000)
    quiet = (np.int16(1000) * np.ones(16000 * 6, dtype=np.int16)).tobytes()
    once = _agc(quiet)
    twice, _ = window.bounded_agc_pcm16(once)
    assert sock.send(quiet)
    await _wait_requests(client, 1)
    posted = _posted_pcm(client.requests[0][1])
    assert posted == once
    assert posted != quiet
    assert posted != twice
    assert sock.raw._agc_last_gain == 4.0
    assert sock.raw._agc_peak == 1000.0
    if sock.raw._buf:
        # Buffer stays original; posted AGC is the only 4× the model sees.
        assert int(np.frombuffer(bytes(sock.raw._buf), dtype=np.int16).max()) == 1000
    await sock.drain_and_close()


@pytest.mark.asyncio
async def test_ingest_agc_at_ceiling_on_silence_is_not_posted(monkeypatch):
    client = Client()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    monkeypatch.setattr(window, 'WINDOW_INGEST_AGC', True)
    seen: list[float] = []

    def _reject_and_record(_self, data: bytes) -> bool:
        seen.append(window.pcm16_peak(data))
        return False

    monkeypatch.setattr(vad_gate.VADStreamingGate, '_run_vad', _reject_and_record)
    sock = await LiveChainSession(receiver()).connect(16000)
    # Digital silence stays identity; faint floors hit the 4× ceiling into VAD.
    assert sock.send(bytes(32000))
    faint100 = (np.int16(100) * np.ones(16000, dtype=np.int16)).tobytes()
    faint30 = (np.int16(30) * np.ones(16000, dtype=np.int16)).tobytes()
    assert sock.send(faint100)
    assert sock.send(faint30)
    await sock.drain_and_close()
    assert not client.requests
    assert seen[0] == 0.0
    assert seen[1] == 400.0
    assert seen[2] == 120.0


@pytest.mark.asyncio
async def test_posted_agc_still_runs_when_ingest_is_disabled(monkeypatch):
    client = Client()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    monkeypatch.setattr(window, 'WINDOW_INGEST_AGC', False)
    sock = await LiveChainSession(receiver()).connect(16000)
    quiet = (np.int16(1000) * np.ones(16000 * 6, dtype=np.int16)).tobytes()
    assert sock.send(quiet)
    await _wait_requests(client, 1)
    posted = _posted_pcm(client.requests[0][1])
    assert posted == _agc(quiet)
    if sock.raw._buf:
        assert int(np.frombuffer(bytes(sock.raw._buf), dtype=np.int16).max()) == 1000
    await sock.drain_and_close()


@pytest.mark.asyncio
async def test_posted_window_is_uniform_when_ingest_gain_moves(monkeypatch):
    """Quiet then loud chunks must not store a ramp; POST is one scale."""
    client = Client()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    monkeypatch.setattr(window, 'WINDOW_INGEST_AGC', True)
    sock = await LiveChainSession(receiver()).connect(16000)
    quiet = (np.int16(1000) * np.ones(16000 * 3, dtype=np.int16)).tobytes()
    loud = (np.int16(8000) * np.ones(16000 * 3, dtype=np.int16)).tobytes()
    ingest = window.SessionPcmGain()
    first_gain_chunk = ingest.apply(quiet[:640])
    assert window.pcm16_peak(first_gain_chunk) == 4000.0
    assert sock.send(quiet)
    assert sock.send(loud)
    await _wait_requests(client, 1)
    posted = np.frombuffer(_posted_pcm(client.requests[0][1]), dtype=np.int16)
    half = 16000 * 3
    assert posted.size >= 2 * half
    first_half, second_half = posted[:half], posted[half : 2 * half]
    # Uniform scale preserves the original 8:1 ratio. A stored ingest ramp
    # would be 4000 then ~26214 (ratio ~6.55) because the quiet half was
    # already 4× when the envelope was still at the cap.
    orig_ratio = 8000 / 1000
    posted_ratio = float(second_half[0]) / float(first_half[0])
    assert abs(posted_ratio - orig_ratio) < 0.02
    assert len(set(int(x) for x in first_half[::1600])) == 1
    assert len(set(int(x) for x in second_half[::1600])) == 1
    expected, gain = window.bounded_agc_pcm16(quiet + loud, peak=8000.0)
    assert bytes(posted[: 2 * half]) == expected
    assert gain == pytest.approx(window.WINDOW_AGC_TARGET_PEAK * 32767.0 / 8000.0)
    if sock.raw._buf:
        buf = np.frombuffer(bytes(sock.raw._buf), dtype=np.int16)
        assert int(buf.max()) == 8000
        assert int(buf[0]) == 1000
    await sock.drain_and_close()


def test_decide_window_hold_empty_trailing_complete_and_forced_cut():
    from utils.stt.window_anchor import RawSegment, decide_window, is_trailing_complete

    first, held = RawSegment('One.', 0.0, 2.0), RawSegment('Two', 2.0, 5.0)
    held_decision = decide_window([first, held], 6.0, 24.0, force=False)
    assert held_decision.emit == (first,)
    assert held_decision.new_anchor == 2.0
    assert held_decision.forced_cut is False

    done = RawSegment('Done.', 0.0, 4.5)
    assert is_trailing_complete(done, 6.0)
    complete = decide_window([done], 6.0, 24.0, force=False)
    assert complete.emit == (done,)
    assert complete.new_anchor == 4.5

    empty_keep = decide_window([], 6.0, 24.0, force=False)
    assert empty_keep.emit == ()
    assert empty_keep.new_anchor is None
    empty_cut = decide_window([], 24.0, 24.0, force=False, empty_cap_slide=6.0)
    assert empty_cut.emit == ()
    assert empty_cut.new_anchor == 6.0
    assert empty_cut.forced_cut is True
    cap_two = decide_window([first, held], 24.0, 24.0, force=False)
    assert cap_two.emit == (first,)
    assert cap_two.new_anchor == 2.0
    assert cap_two.forced_cut is False
    forced = decide_window([held], 24.0, 24.0, force=False)
    assert forced.emit == (held,)
    assert forced.new_anchor == 5.0
    assert forced.forced_cut is True
    force_all = decide_window([held], 24.0, 24.0, force=True)
    assert force_all.emit == (held,)
    assert force_all.new_anchor == 24.0
    assert force_all.forced_cut is False

    paused_mid = decide_window([held], 2.0, 24.0, force=False, pause=True)
    assert paused_mid.emit == ()
    assert paused_mid.new_anchor is None
    short_done = RawSegment('Done.', 0.0, 1.8)
    assert not is_trailing_complete(short_done, 2.0)
    assert decide_window([short_done], 2.0, 24.0, force=False).emit == ()
    paused_done = decide_window([short_done], 2.0, 24.0, force=False, pause=True)
    assert paused_done.emit == (short_done,)
    assert paused_done.new_anchor == 1.8


def test_default_buffer_cap_fits_documented_memory():
    from utils.stt.window_anchor import buffer_cap_seconds

    assert buffer_cap_seconds(6.0, 24.0) == 60.0
    assert int(60.0 * 16000 * 2) <= 1_920_000


def test_pace_and_max_context_env_clamps(monkeypatch):
    from utils.stt.window_anchor import read_max_context_seconds, read_pace_seconds

    monkeypatch.setenv('PARAKEET_WINDOW_PACE_SECONDS', '0')
    assert read_pace_seconds() == 1.0
    monkeypatch.setenv('PARAKEET_WINDOW_PACE_SECONDS', '99')
    assert read_pace_seconds() == 15.0
    monkeypatch.setenv('PARAKEET_WINDOW_PACE_SECONDS', 'nope')
    assert read_pace_seconds() == 6.0
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_CONTEXT_SECONDS', '1')
    assert read_max_context_seconds() == 6.0
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_CONTEXT_SECONDS', '100')
    assert read_max_context_seconds() == 30.0
    monkeypatch.delenv('PARAKEET_WINDOW_MAX_CONTEXT_SECONDS', raising=False)
    assert read_max_context_seconds() == 24.0


@pytest.mark.asyncio
async def test_socket_reads_clamped_window_env(monkeypatch):
    monkeypatch.setenv('PARAKEET_WINDOW_PACE_SECONDS', '100')
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_CONTEXT_SECONDS', '2')
    sock = window.connect_window(lambda _: None, 16000)
    assert sock._pace_seconds == 15.0
    assert sock._max_context_seconds == 6.0
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_trailing_complete_emits_last_sentence(monkeypatch):
    posted = []
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    client = SeqClient(
        [
            {'segments': [{'text': 'Done.', 'start': 0.0, 'end': 4.5}]},
            {'text': ''},
        ]
    )
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 6)
    deadline = asyncio.get_running_loop().time() + 2
    while not posted:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError('trailing-complete sentence was not emitted')
        await _REAL_SLEEP(0)
    assert [s['text'] for s in posted] == ['Done.']
    assert sock._anchor_bytes > 0
    await sock.drain_and_close()
    assert [s['text'] for s in posted] == ['Done.']


@pytest.mark.asyncio
async def test_empty_response_keeps_anchor_and_later_post_recovers(monkeypatch):
    posted = []
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    client = SeqClient([{'text': ''}, {'segments': [{'text': 'Recovered.', 'start': 0.0, 'end': 5.0}]}])
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 6)
    await _wait_requests(client, 1)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 6)
    await sock.drain_and_close()
    assert len(client.requests) >= 2
    assert len(client.requests[1][1]['files']['file'][1]) > len(client.requests[0][1]['files']['file'][1])
    assert [s['text'] for s in posted] == ['Recovered.']


@pytest.mark.asyncio
async def test_max_context_run_on_sentence_reanchors_at_sentence_end(monkeypatch):
    """A run-on sentence at the cap is the one case that must cut: emit it and re-anchor at its
    END, not at `now`. Anchoring at `now` would start the next context mid-utterance, which is the
    empty-output failure mode. The session stays open so this takes the cap path; a closing session
    force-flushes instead and is covered by the drain tests."""
    posted = []
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_CONTEXT_SECONDS', '6')
    monkeypatch.setenv('PARAKEET_WINDOW_PACE_SECONDS', '6')
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    before = WINDOW_FORCED_CUTS._value.get()
    client = Client(data={'segments': [{'text': 'Still going', 'start': 0.0, 'end': 5.8}]})
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 6)
    await _wait_requests(client, 1)
    deadline = asyncio.get_running_loop().time() + 2
    while not posted:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError('run-on sentence was never emitted at the cap')
        await _REAL_SLEEP(0)
    assert [s['text'] for s in posted] == ['Still going']
    assert WINDOW_FORCED_CUTS._value.get() >= before + 1
    # 5.8 s (the sentence end), not 6.0 s (`now`).
    assert 5.0 * 16000 * 2 < sock._anchor_bytes < 6.0 * 16000 * 2
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_silence_flush_reanchors_at_next_speech_onset(monkeypatch):
    posted = []
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    client = SeqClient(
        [
            {'segments': [{'text': 'First.', 'start': 0.0, 'end': 1.8}]},
            {'segments': [{'text': 'Second.', 'start': 0.0, 'end': 1.6}]},
        ]
    )
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    first, second = b'\x01\x00' * 16000 * 2, b'\x02\x00' * 16000 * 2
    sock.mark_speech()
    sock.send(first)
    sock.send(bytes(16000 * 2 * 2))
    await _wait_requests(client, 1)
    sock.mark_speech()
    sock.send(second)
    await sock.drain_and_close()
    assert len(client.requests) == 2
    assert client.requests[0][1]['files']['file'][1].endswith(_agc(first + bytes(16000 * 2 * 2)))
    assert _agc(second)[:2] in _posted_pcm(client.requests[1][1])
    assert [s['text'] for s in posted] == ['First.', 'Second.']
    assert posted[1]['start'] >= posted[0]['end']


@pytest.mark.asyncio
async def test_finalize_mid_sentence_holds_and_keeps_anchor(monkeypatch):
    posted = []
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    client = Client(data={'segments': [{'text': 'Held', 'start': 0.0, 'end': 1.6}]})
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 2)
    sock.finalize()
    await _wait_requests(client, 1)
    deadline = asyncio.get_running_loop().time() + 2
    while sock._now_bytes == 0:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError('pause POST did not commit')
        await _REAL_SLEEP(0)
    assert posted == []
    assert sock._anchor_bytes == 0
    sock.finalize()
    for _ in range(8):
        sock._wake.set()
        await _REAL_SLEEP(0)
    assert len(client.requests) == 1
    assert posted == []
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_finalize_after_terminal_emits_and_reanchors(monkeypatch):
    posted = []
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    client = Client(data={'segments': [{'text': 'Done.', 'start': 0.0, 'end': 1.6}]})
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 2)
    sock.finalize()
    deadline = asyncio.get_running_loop().time() + 2
    while not posted:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError('pause POST did not emit the completed sentence')
        await _REAL_SLEEP(0)
    assert [s['text'] for s in posted] == ['Done.']
    assert sock._anchor_bytes > 0
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_idle_flush_emits_held_sentence_once(monkeypatch):
    from utils.stt.window_anchor import IDLE_FLUSH_SECONDS

    posted = []
    clock = {'now': 1000.0}
    monkeypatch.setattr(window.time, 'monotonic', lambda: clock['now'])
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    client = Client(data={'segments': [{'text': 'Held', 'start': 0.0, 'end': 1.0}]})
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 6)
    await _wait_requests(client, 1)
    deadline = asyncio.get_running_loop().time() + 2
    while sock._now_bytes == 0:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError('first POST did not commit')
        await _REAL_SLEEP(0)
    assert posted == []
    clock['now'] += IDLE_FLUSH_SECONDS
    sock._wake.set()
    deadline = asyncio.get_running_loop().time() + 2
    while not posted:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError('idle flush did not emit the held sentence')
        await _REAL_SLEEP(0)
    assert [s['text'] for s in posted] == ['Held']
    n_posts = len(client.requests)
    clock['now'] += IDLE_FLUSH_SECONDS
    for _ in range(8):
        sock._wake.set()
        await _REAL_SLEEP(0)
    assert len(client.requests) == n_posts
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_unchanged_context_is_not_reposted(monkeypatch):
    posted = []
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    client = Client(data={'segments': [{'text': 'Held', 'start': 0.0, 'end': 1.6}]})
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 2)
    sock.finalize()
    await _wait_requests(client, 1)
    first_len = len(client.requests[0][1]['files']['file'][1])
    for _ in range(5):
        sock.finalize()
        sock._wake.set()
        await _REAL_SLEEP(0)
    assert len(client.requests) == 1
    assert len(client.requests[0][1]['files']['file'][1]) == first_len
    assert posted == []
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_many_posts_stay_monotonic_without_duplicates(monkeypatch):
    posted = []
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))

    def payload(n, kwargs):
        dur = _wav_duration(kwargs)
        held_start = max(0.4, dur - 1.0)
        return {
            'segments': [
                {'text': f'S{n}.', 'start': 0.0, 'end': held_start},
                {'text': f'H{n}', 'start': held_start, 'end': dur},
            ]
        }

    client = SeqClient([payload])
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    for step in range(12):
        sock.mark_speech()
        assert sock.send(b'\x01\x00' * 16000 * 6)
        await _wait_requests(client, step + 1)
    await sock.drain_and_close()
    assert len(client.requests) >= 12
    texts = [s['text'] for s in posted]
    assert len(texts) == len(set(texts))
    for earlier, later in zip(posted, posted[1:]):
        assert later['start'] >= earlier['end']
        assert later['start'] >= earlier['start']


@pytest.mark.asyncio
async def test_speaker_assignment_only_for_emitted_segments(monkeypatch):
    posted = []
    assign = AsyncMock(return_value=0)
    monkeypatch.setattr(window.WindowedParakeetSocket, '_assign_speaker', assign)
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    client = SeqClient(
        [
            {
                'segments': [
                    {'text': 'One.', 'start': 0.0, 'end': 2.0},
                    {'text': 'Two', 'start': 2.0, 'end': 5.0},
                ]
            },
            {'segments': [{'text': 'Two', 'start': 0.0, 'end': 3.0}]},
        ]
    )
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 6)
    deadline = asyncio.get_running_loop().time() + 2
    while not posted:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError('held window did not emit the completed sentence')
        await _REAL_SLEEP(0)
    assert [s['text'] for s in posted] == ['One.']
    assert assign.await_count == 1
    await sock.drain_and_close()
    assert [s['text'] for s in posted] == ['One.', 'Two']
    assert assign.await_count == 2


@pytest.mark.asyncio
async def test_live_posts_are_paced_and_single_flight(monkeypatch):
    delays = []

    async def pacing(delay):
        delays.append(delay)

    monkeypatch.setattr(window.asyncio, 'sleep', pacing)
    client = Client(data={'segments': [{'text': 'Go.', 'start': 0.0, 'end': 4.5}]})
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(lambda _: None, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 6)
    await _wait_requests(client, 1)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 6)
    await _wait_requests(client, 2)
    assert delays and delays[0] >= 0
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_nonspeech_audio_is_never_posted(monkeypatch):
    client = Client()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(lambda _: None, 16000)
    assert sock.send(bytes(16000 * 2 * 12))
    await sock.drain_and_close()
    assert client.requests == []
    assert window.admission.active == 0


@pytest.mark.asyncio
async def test_cap_cut_next_post_starts_at_emitted_sentence_end(monkeypatch):
    posted = []
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_CONTEXT_SECONDS', '6')
    monkeypatch.setenv('PARAKEET_WINDOW_PACE_SECONDS', '6')
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    first, second = b'\x01\x00' * 16000 * 6, b'\x02\x00' * 16000 * 6
    client = SeqClient(
        [
            {
                'segments': [
                    {'text': 'One.', 'start': 0.0, 'end': 2.0},
                    {'text': 'Two', 'start': 2.0, 'end': 5.8},
                ]
            },
            {
                'segments': [
                    {'text': 'Two.', 'start': 0.0, 'end': 4.0},
                    {'text': 'Three', 'start': 4.0, 'end': 9.0},
                ]
            },
        ]
    )
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    sock.send(first)
    await _wait_requests(client, 1)
    sock.mark_speech()
    sock.send(second)
    await _wait_requests(client, 2)
    anchor = 2 * 16000 * 2
    body1 = _posted_pcm(client.requests[0][1])
    body2 = _posted_pcm(client.requests[1][1])
    assert body1 == _agc(first)
    assert body2.startswith(_agc(first[anchor:], peak=2))
    assert [s['text'] for s in posted][0] == 'One.'
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_empty_at_cap_slides_pace_and_later_post_recovers(monkeypatch):
    posted = []
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    empty, later = b'\x01\x00' * 16000 * 24, b'\x02\x00' * 16000 * 6
    before = WINDOW_FORCED_CUTS._value.get()
    client = SeqClient([{'text': ''}, {'segments': [{'text': 'Recovered.', 'start': 0.0, 'end': 4.0}]}])
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    sock.send(empty)
    await _wait_requests(client, 1)
    sock.mark_speech()
    sock.send(later)
    await sock.drain_and_close()
    slide = 6 * 16000 * 2
    body1 = _posted_pcm(client.requests[0][1])
    body2 = _posted_pcm(client.requests[1][1])
    assert body1 == _agc(empty)
    assert body2.startswith(_agc(empty[slide:], peak=2))
    assert _agc(later)[:2] in body2
    assert [s['text'] for s in posted] == ['Recovered.']
    assert WINDOW_FORCED_CUTS._value.get() >= before + 1


@pytest.mark.asyncio
async def test_catchup_burst_does_not_shed_and_posts_max_context_jobs(monkeypatch):
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    client = GateFirstClient()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(lambda _: None, 16000)
    head, tail = b'\x01\x00' * 16000 * 6, b'\x02\x00' * 16000 * 34
    sock.mark_speech()
    assert sock.send(head)
    await client.started.wait()
    sock.mark_speech()
    assert sock.send(tail)
    assert not sock.is_connection_dead
    assert st._parakeet_circuit.state == 'closed'
    assert client.gate is not None
    client.gate.set_result(None)
    await sock.drain_and_close()
    assert st._parakeet_circuit.state == 'closed'
    assert client.requests
    assert all(_wav_duration(kw) <= 24.0 + 1e-6 for _, kw in client.requests)
    last_body = _posted_pcm(client.requests[-1][1])
    assert _agc(head + tail).endswith(last_body)
    assert _agc(tail[:2], peak=2) in last_body


@pytest.mark.asyncio
async def test_idle_remainder_posts_without_close(monkeypatch):
    from utils.stt.window_anchor import IDLE_FLUSH_SECONDS

    posted = []
    clock = {'now': 1000.0}
    monkeypatch.setattr(window.time, 'monotonic', lambda: clock['now'])
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    client = GateFirstClient()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 6)
    await client.started.wait()
    sock.mark_speech()
    sock.send(b'\x02\x00' * 16000 * 21)
    clock['now'] += IDLE_FLUSH_SECONDS
    assert client.gate is not None
    client.gate.set_result(None)
    deadline = asyncio.get_running_loop().time() + 2
    while len(client.requests) < 3:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f'idle remainder never posted, got {len(client.requests)} POSTs')
        await _REAL_SLEEP(0)
    durs = [_wav_duration(kw) for _, kw in client.requests]
    assert durs[-1] < 6.0
    assert durs[-1] > 0.0
    n_posts = len(client.requests)
    clock['now'] += IDLE_FLUSH_SECONDS
    for _ in range(8):
        sock._wake.set()
        await _REAL_SLEEP(0)
    assert len(client.requests) == n_posts
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)
