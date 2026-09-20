"""Live TDT runs through real admission, socket, VAD and receiver seams; no network."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from utils.stt import parakeet_window as window, provider_resilience, streaming as st, vad_gate
from utils.stt.live_session import LiveChainSession, LiveLegSocket
from routers.listen.receiver import ListenReceiver


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
    # speech detector (positive PCM=speech) instead of downloading a model.
    monkeypatch.setattr(vad_gate, '_get_ort_session', lambda: None)
    monkeypatch.setattr(vad_gate.VADStreamingGate, '_run_vad', lambda self, data: b'\x01' in data)

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
    assert sock.send(b'\x01\x00' * 16000 * 12)
    assert not sock.send(b'\x01\x00')
    assert len(calls) == 1
    assert sock.is_connection_dead
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
async def test_multiple_windows_are_paced_ordered_and_not_overlapped(monkeypatch):
    posted = []
    delays = []

    async def pacing(delay):
        delays.append(delay)

    monkeypatch.setattr(window.asyncio, 'sleep', pacing)
    data = {'segments': [{'text': 'one', 'start': -1, 'end': 100}]}
    client = Client(data=data)
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    first, second = b'\x01\x00' * 16000 * 6, b'\x02\x00' * 16000 * 6
    assert sock.send(first + second)
    await sock.drain_and_close()
    assert len(client.requests) == 2
    assert client.requests[0][1]['files']['file'][1].endswith(first)
    assert client.requests[1][1]['files']['file'][1].endswith(second)
    assert len(delays) == 1 and 5 < delays[0] <= 6
    assert [(s['start'], s['end']) for s in posted] == [(0, 6), (6, 12)]


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
    sock.send(bytes(16000))  # admitted hangover has no speech of its own
    await sock.drain_and_close()
    assert len(client.requests) == 1
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
        assert {e['component'] for e in exhausted} == {'stt_selection', 'stt_live_session'}
        assert all(e['to_mode'] == 'parakeet' for e in exhausted)
    else:
        recovered = [e for e in events if e['outcome'] == 'recovered']
        assert len(recovered) == 2
        assert {e['component'] for e in recovered} == {'stt_selection', 'stt_live_session'}
        assert all(e['to_mode'] == 'parakeet' for e in recovered)
        leg.raw._stream_transcript([{'start': 1, 'end': 2, 'text': 'again'}])
        assert len([e for e in events if e['outcome'] == 'recovered']) == 2
    assert window.admission.active == 0
