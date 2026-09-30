"""Live TDT runs through real admission, socket, VAD and receiver seams; no network."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import numpy as np
import pytest

from utils.stt import parakeet_window as window, provider_resilience, streaming as st, vad_gate
from utils.stt.resilient_stream import trim_window_replay_to_anchor
from utils.observability.fallback import record_fallback
from utils.stt.live_metrics import (
    WINDOW_ADMISSION,
    WINDOW_FIRST_TEXT,
    WINDOW_FORCED_CUTS,
    WINDOW_POSTS,
    WINDOW_PRESSURE_REFRESH,
    WINDOW_PRESSURE_REFUSAL,
    WINDOW_REPLAY_SAFE_TRIMS,
    WINDOW_SESSION_OUTCOME,
)
from utils.metrics import OMI_FALLBACK_TOTAL
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
    monkeypatch.setenv('PARAKEET_BATCH_PRESSURE_POOL_HOST', 'tdt-headless.invalid')
    monkeypatch.setenv('PARAKEET_BATCH_PRESSURE_MIN_REPLICAS', '2')
    # The scheduling tests below are written in 6 s steps (one 6 s send = one POST).
    # Pin that unit here so they test mechanics, not the shipped default, which
    # test_default_pace_waits_for_fifteen_seconds_of_speech pins on its own.
    monkeypatch.setenv('PARAKEET_WINDOW_PACE_SECONDS', '6')
    monkeypatch.setenv('PARAKEET_WINDOW_FIRST_TEXT_DEADLINE_SECONDS', '12')
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_EMPTY_STREAK', '4')
    monkeypatch.setenv('SONIOX_API_KEY', 'test')
    monkeypatch.setenv('MODULATE_API_KEY', 'test')
    monkeypatch.setenv('HOSTED_SPEAKER_EMBEDDING_API_URL', 'http://embedding.invalid')
    monkeypatch.setattr(window, 'admission', window.WindowAdmission())
    monkeypatch.setattr(window, 'batch_pressure', window.BatchPressure())
    window.batch_pressure._observed_at = window.time.monotonic()
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


@pytest.mark.asyncio
async def test_batch_pressure_cache_never_waits_at_admission_and_stands_down(monkeypatch):
    pressure = window.BatchPressure()
    began = asyncio.Event()
    release = asyncio.Event()
    missing_before = WINDOW_PRESSURE_REFUSAL.labels(reason='missing')._value.get()
    pressure_before = WINDOW_PRESSURE_REFUSAL.labels(reason='pressure')._value.get()
    stale_before = WINDOW_PRESSURE_REFUSAL.labels(reason='stale')._value.get()

    async def refresh(_host, _replicas, _client):
        began.set()
        await release.wait()
        pressure._busy = True
        pressure._observed_at = window.time.monotonic()

    monkeypatch.setattr(pressure, '_refresh', refresh)
    assert not pressure.allows('tdt-headless.invalid', 2)  # admission never starts a poll
    assert WINDOW_PRESSURE_REFUSAL.labels(reason='missing')._value.get() == missing_before + 1
    assert pressure._task is None
    pressure.start('tdt-headless.invalid', 2)
    try:
        await began.wait()
        assert not pressure.allows('tdt-headless.invalid', 2)
        release.set()
        await asyncio.sleep(0)
        assert not pressure.allows('tdt-headless.invalid', 2)
        assert WINDOW_PRESSURE_REFUSAL.labels(reason='pressure')._value.get() == pressure_before + 1
        pressure._observed_at -= pressure.STALE_SECONDS + 1
        assert not pressure.allows('tdt-headless.invalid', 2)  # stale signal: fleet stands down
        assert WINDOW_PRESSURE_REFUSAL.labels(reason='stale')._value.get() == stale_before + 1
    finally:
        await pressure.stop()


@pytest.mark.asyncio
async def test_batch_pressure_keeps_sample_fresh_between_rare_admissions(monkeypatch):
    pressure = window.BatchPressure()
    pressure.REFRESH_SECONDS = 0.01
    clock = [100.0]
    monkeypatch.setattr(window, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    refreshed = asyncio.Event()
    calls = 0

    async def refresh(_host, _replicas, _client):
        nonlocal calls
        calls += 1
        pressure._busy = False
        pressure._observed_at = clock[0]
        refreshed.set()

    monkeypatch.setattr(pressure, '_refresh', refresh)
    pressure.start('tdt-headless.invalid', 2)
    try:
        assert not pressure.allows('tdt-headless.invalid', 2)
        await refreshed.wait()
        assert pressure.allows('tdt-headless.invalid', 2)
        for _ in range(2):
            refreshed.clear()
            clock[0] += 16.0
            await asyncio.wait_for(refreshed.wait(), 1)
            assert pressure.allows('tdt-headless.invalid', 2)
        assert calls >= 3
    finally:
        await pressure.stop()


@pytest.mark.asyncio
async def test_batch_pressure_poller_retries_exception_starts_once_and_stops(monkeypatch):
    pressure = window.BatchPressure()
    pressure.REFRESH_SECONDS = 0.01
    recovered = asyncio.Event()
    calls = 0
    unavailable_before = WINDOW_PRESSURE_REFRESH.labels(outcome='unavailable')._value.get()

    async def refresh(_host, _replicas, _client):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError('transient poll failure')
        pressure._observed_at = window.time.monotonic()
        recovered.set()

    monkeypatch.setattr(pressure, '_refresh', refresh)
    pressure.start('tdt-headless.invalid', 2)
    task = pressure._task
    pressure.start('tdt-headless.invalid', 2)
    assert pressure._task is task
    try:
        await asyncio.wait_for(recovered.wait(), 1)
        assert pressure.allows('tdt-headless.invalid', 2)
        assert calls >= 2
        assert WINDOW_PRESSURE_REFRESH.labels(outcome='unavailable')._value.get() == unavailable_before + 1
    finally:
        await pressure.stop()
    assert task.done()
    assert pressure._task is None
    assert not pressure.allows('tdt-headless.invalid', 2)


@pytest.mark.asyncio
async def test_batch_pressure_poller_off_configuration_does_no_work(monkeypatch):
    pressure = window.BatchPressure()
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '0')
    pressure.start_from_env()
    assert pressure._task is None
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '1')
    monkeypatch.delenv('PARAKEET_BATCH_PRESSURE_POOL_HOST')
    pressure.start_from_env()
    assert pressure._task is None
    monkeypatch.setenv('PARAKEET_BATCH_PRESSURE_POOL_HOST', 'tdt-headless.invalid')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', 'nan')
    pressure.start_from_env()
    assert pressure._task is None
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '1')
    monkeypatch.setattr(pressure, '_refresh', AsyncMock())
    pressure.start_from_env()
    task = pressure._task
    assert task is not None
    pressure.start_from_env()
    assert pressure._task is task
    await pressure.stop()


@pytest.mark.asyncio
async def test_batch_pressure_reuses_bounded_client_until_shutdown(monkeypatch):
    pressure = window.BatchPressure()
    pressure.REFRESH_SECONDS = 0.01
    created = []
    used = []
    refreshed_twice = asyncio.Event()

    class Client:
        def __init__(self, **kwargs):
            self.options = kwargs
            self.closed = False
            created.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            self.closed = True

    async def refresh(_host, _replicas, client):
        used.append(client)
        if len(used) == 2:
            refreshed_twice.set()

    monkeypatch.setattr(window.httpx, 'AsyncClient', Client)
    monkeypatch.setattr(pressure, '_refresh', refresh)
    pressure.start('tdt-headless.invalid', 2)
    try:
        await asyncio.wait_for(refreshed_twice.wait(), 1)
        assert len(created) == 1
        assert used[:2] == [created[0], created[0]]
        assert created[0].options['timeout'] == 1.0
        assert created[0].options['trust_env'] is False
        limits = created[0].options['limits']
        assert limits.max_connections == pressure.MAX_REPLICAS
        assert limits.max_keepalive_connections == pressure.MAX_REPLICAS
        assert not created[0].closed
    finally:
        await pressure.stop()
    assert created[0].closed


def test_batch_pressure_poller_can_restart_on_a_new_event_loop(monkeypatch):
    pressure = window.BatchPressure()
    clients = []

    class Client:
        def __init__(self, **_kwargs):
            self.closed = False
            clients.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            self.closed = True

    monkeypatch.setattr(window.httpx, 'AsyncClient', Client)
    monkeypatch.setattr(pressure, '_refresh', AsyncMock())

    async def one_lifecycle():
        pressure.start('tdt-headless.invalid', 2)
        task = pressure._task
        await asyncio.sleep(0)
        await pressure.stop()
        assert task is not None and task.done()

    asyncio.run(one_lifecycle())
    asyncio.run(one_lifecycle())
    assert len(clients) == 2
    assert clients[0] is not clients[1]
    assert all(client.closed for client in clients)


@pytest.mark.asyncio
async def test_batch_pressure_endpoint_thresholds_and_unavailable_signal(monkeypatch):
    pressure = window.BatchPressure()
    loop = asyncio.get_running_loop()
    ips = ['10.0.0.1', '10.0.0.2']
    monkeypatch.setattr(
        loop,
        'getaddrinfo',
        AsyncMock(side_effect=lambda *_args, **_kwargs: [(None, None, None, None, (ip, 8080)) for ip in ips]),
    )
    payloads = {
        '10.0.0.1': {'pending_requests': 100, 'live_pending_requests': 3, 'live_oldest_pending_seconds': 0},
        '10.0.0.2': {'pending_requests': 100, 'live_pending_requests': 3, 'live_oldest_pending_seconds': 0},
    }

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class Client:
        def __init__(self):
            self.requests = []

        async def get(self, url):
            self.requests.append(url)
            return Response(payloads[url.split('/')[2].split(':')[0]])

    client = Client()
    await pressure._refresh('tdt-headless.invalid', 2, client)
    assert pressure.allows('tdt-headless.invalid', 2)  # Backfill and fleet sum do not trip the live gate.
    payloads['10.0.0.2']['live_pending_requests'] = 4
    await pressure._refresh('tdt-headless.invalid', 2, client)
    assert not pressure.allows('tdt-headless.invalid', 2)
    payloads['10.0.0.2']['live_pending_requests'] = 0
    payloads['10.0.0.2']['live_oldest_pending_seconds'] = 0.75
    await pressure._refresh('tdt-headless.invalid', 2, client)
    assert not pressure.allows('tdt-headless.invalid', 2)
    payloads['10.0.0.2']['live_oldest_pending_seconds'] = 0
    ips.pop()
    await pressure._refresh('tdt-headless.invalid', 2, client)
    assert not pressure.allows('tdt-headless.invalid', 2)  # incomplete DNS set
    ips.append('10.0.0.2')
    payloads['10.0.0.2']['live_pending_requests'] = float('nan')
    await pressure._refresh('tdt-headless.invalid', 2, client)
    assert not pressure.allows('tdt-headless.invalid', 2)  # invalid telemetry
    payloads['10.0.0.2']['live_pending_requests'] = 0
    await pressure._refresh('tdt-headless.invalid', 2, client)
    assert pressure.allows('tdt-headless.invalid', 2)
    del payloads['10.0.0.2']['live_oldest_pending_seconds']
    await pressure._refresh('tdt-headless.invalid', 2, client)
    assert not pressure.allows('tdt-headless.invalid', 2)  # Old GPU replica: fail closed.
    payloads['10.0.0.2']['live_oldest_pending_seconds'] = 0
    requests_before = len(client.requests)
    ips[:] = [f'10.0.0.{i}' for i in range(1, pressure.MAX_REPLICAS + 2)]
    await pressure._refresh('tdt-headless.invalid', 2, client)
    assert not pressure.allows('tdt-headless.invalid', 2)  # no partial sample of an oversized fleet
    assert pressure._observed_at == 0
    assert len(client.requests) == requests_before
    ips[:] = ['10.0.0.1', '10.0.0.2']
    await pressure._refresh('tdt-headless.invalid', 2, client)
    assert pressure.allows('tdt-headless.invalid', 2)
    pressure._observed_at -= pressure.STALE_SECONDS + 1
    assert not pressure.allows('tdt-headless.invalid', 2)


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
        language_profile=None,
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
    before_accepted = WINDOW_ADMISSION.labels(outcome='accepted')._value.get()
    before_text = WINDOW_SESSION_OUTCOME.labels(outcome='text', reason='none')._value.get()
    before_first = WINDOW_FIRST_TEXT._sum.get()
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
    assert list(kwargs) == ['files', 'headers']  # no language parameter; exclude live from prerecorded metrics
    assert kwargs['headers'] == {'X-Omi-STT-Surface': 'live-window'}
    assert kwargs['files']['file'][1].startswith(b'RIFF')
    assert recv.emitted[0]['text'] == 'hello'
    assert recv.emitted[0]['start'] >= 1.0
    assert usage == [{'provider': 'parakeet', 'platform': 'ios', 'seconds': 1.0}]
    assert session.consume_speech_ms_delta() == 1000
    assert session.consume_speech_ms_delta() == 0
    assert window.admission.active == 0
    assert WINDOW_ADMISSION.labels(outcome='accepted')._value.get() == before_accepted + 1
    assert WINDOW_SESSION_OUTCOME.labels(outcome='text', reason='none')._value.get() == before_text + 1
    assert WINDOW_FIRST_TEXT._sum.get() > before_first


@pytest.mark.asyncio
async def test_speech_with_empty_tdt_output_counts_no_text(monkeypatch):
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client(data={'text': ''}))
    before_accepted = WINDOW_ADMISSION.labels(outcome='accepted')._value.get()
    before = WINDOW_SESSION_OUTCOME.labels(outcome='no_text', reason='none')._value.get()
    sock = await LiveChainSession(receiver()).connect(16000)
    assert sock.send(b'\x01\x00' * 16000)
    await sock.drain_and_close()
    assert WINDOW_ADMISSION.labels(outcome='accepted')._value.get() == before_accepted + 1
    assert WINDOW_SESSION_OUTCOME.labels(outcome='no_text', reason='none')._value.get() == before + 1


@pytest.mark.asyncio
async def test_session_outcome_is_recorded_before_health_close_callback():
    sock = window.connect_window(lambda _: None, 16000)
    sock._first_speech_at = window.time.monotonic()
    before = WINDOW_SESSION_OUTCOME.labels(outcome='no_text', reason='none')._value.get()

    def fail_health_close():
        raise RuntimeError('health callback failed')

    sock._health_close = fail_health_close
    sock._on_pump_done(SimpleNamespace(cancelled=lambda: False))

    assert WINDOW_SESSION_OUTCOME.labels(outcome='no_text', reason='none')._value.get() == before + 1
    assert window.admission.active == 0

    # The real pump task is still running; close it through the normal async
    # lifecycle after restoring its callback so this test leaves no task behind.
    sock._health_close = lambda: None
    sock._closed = True
    sock._wake.set()
    assert sock._pump_task is not None
    await sock._pump_task
    sock.finish()


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal', ['finish', 'fail'])
async def test_terminal_callback_failure_releases_admission_once(terminal):
    sock = window.connect_window(lambda _: None, 16000)
    assert window.admission.active == 1

    def fail_health_close():
        raise RuntimeError('health callback failed')

    sock._health_close = fail_health_close
    if terminal == 'finish':
        sock.finish()
    else:
        sock.fail('test_failure')

    # The releasing call must not wait for the cancelled pump's done callback.
    assert window.admission.active == 0
    assert sock._pump_task is not None
    with pytest.raises(asyncio.CancelledError):
        await sock._pump_task
    await _REAL_SLEEP(0)
    # _on_pump_done may release again, but the admission lease is idempotent.
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
async def test_overflow_moves_to_soniox_and_releases_on_finish(monkeypatch, caplog):
    first = await LiveChainSession(receiver()).connect(16000)
    tail = SimpleNamespace(is_connection_dead=False, finish=lambda: None)
    soniox = AsyncMock(return_value=tail)
    monkeypatch.setattr(st, 'process_audio_soniox', soniox)
    recv = receiver()
    second = await LiveChainSession(recv).connect(16000)
    assert second.raw is tail
    assert recv.host.stt_service == st.STTService.soniox
    assert second._pending_selection.capacity_subtype == 'admission'
    second._pending_selection.note_transcript([{'text': 'test'}])
    assert 'reason=capacity_full outcome=recovered subtype=admission' in caplog.text
    assert st._parakeet_circuit.state == 'closed'  # local admission isn't GPU failure
    first.finish()
    first.finish()
    assert window.admission.active == 0
    await asyncio.gather(first.raw._pump_task, return_exceptions=True)
    second.finish()


def test_eight_session_cap_is_hard_and_releases_idempotently(monkeypatch):
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_SESSIONS', '8')
    admission = window.WindowAdmission()
    releases = [admission.acquire() for _ in range(8)]
    assert admission.active == 8
    with pytest.raises(st.ParakeetConnectionError, match='capacity_full') as overflow:
        admission.acquire()
    assert overflow.value.capacity_subtype == 'admission'
    releases[0]()
    releases[0]()
    assert admission.active == 7
    replacement = admission.acquire()
    assert admission.active == 8
    for release in releases[1:]:
        release()
    replacement()
    assert admission.active == 0


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
    assert sock.typed_death_reason == 'capacity_full'
    assert sock.capacity_subtype == 'buffer_cap'
    assert st._parakeet_circuit.state == 'open'
    assert window.admission.active == 0
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_fragmented_vad_speech_does_not_exhaust_span_capacity(monkeypatch):
    sock = window.connect_window(lambda _: None, 16000)
    # Forty-four seconds of 20 ms speech/20 ms hangover frames fits the PCM
    # buffer, but the old one-span-per-VAD-toggle limit killed the leg at 1025.
    frame = b'\x01\x00' * 320
    gap = bytes(len(frame))
    for _ in range(1100):
        sock.mark_speech()
        assert sock.send(frame)
        assert sock.send(gap)
    assert len(sock._buf) < sock._buffer_cap()
    assert len(sock._speech_spans) <= 1024
    assert not sock.is_connection_dead
    anchor = sock._to_bytes(22)
    sock._advance_anchor(anchor)
    assert sock._speech_spans[0][0] >= anchor
    assert len(sock._buf) == sock._received_bytes - anchor
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancellation_before_pump_start_and_during_drain_release(monkeypatch):
    sock = window.connect_window(lambda _: None, 16000)
    sock._pump_task.cancel()
    await asyncio.gather(sock._pump_task, return_exceptions=True)
    assert window.admission.active == 0
    assert sock.is_connection_dead
    assert sock.death_reason == 'cancelled'
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

    async def soniox(callback, *args, **kwargs):
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
    # Audio-timeline v2: the managed chain connect carries the receiver's
    # provider epoch translator (None on legacy sessions).
    connect.assert_awaited_once_with(16000, epoch=None)


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

    async def tail(callback, *args, **kwargs):
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
@pytest.mark.parametrize('reason', ['first_text_deadline', 'empty_streak'])
async def test_no_first_text_bounds_fail_over_once_and_replay_all_capture(monkeypatch, reason):
    monkeypatch.setenv(
        'PARAKEET_WINDOW_FIRST_TEXT_DEADLINE_SECONDS', '0.05' if reason == 'first_text_deadline' else '30'
    )
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_EMPTY_STREAK', '2')
    if reason == 'empty_streak':
        monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    client = Client(data={'text': ''})
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    base = receiver()
    host = base.host
    host.request.sample_rate = 16000
    host.request.websocket = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
    host.state.stt_terminal_failure = False
    host.client_device_context = SimpleNamespace(platform='ios')
    host.transcripts = SimpleNamespace(enqueue=base.emitted.extend)
    host.spawn = lambda coro, **kw: coro.close()
    actual = ListenReceiver(host, [], {})
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda callback, segments: callback(segments))
    replayed = []
    callbacks = []

    async def tail(callback, *args, **kwargs):
        callbacks.append(callback)
        return SimpleNamespace(
            is_connection_dead=False,
            send=lambda data: replayed.append(data) or True,
            finalize=lambda: None,
            finish=lambda: None,
        )

    monkeypatch.setattr(st, 'process_audio_soniox', tail)
    before_outcome = WINDOW_SESSION_OUTCOME.labels(outcome='no_text', reason=reason)._value.get()
    before_fallback = OMI_FALLBACK_TOTAL.labels(
        component='stt_live_session', from_mode='parakeet', to_mode='soniox', reason=reason, outcome='recovered'
    )._value.get()
    assert await actual.initialize_stt()
    previous = actual.stt_socket
    first = b'\x01\x00' * 16000 * (6 if reason == 'empty_streak' else 1)
    chunks = [first]
    actual.capture_timeline.accept(first, window.time.time(), window.time.monotonic())
    assert previous.send(first, start_sample=0)
    actual._window_ring().append(first, 0)
    if reason == 'empty_streak':
        await _wait_requests(client, 1)
        for _ in range(100):
            if previous.raw._empty_streak:
                break
            await _REAL_SLEEP(0)
        second = b'\x02\x00' * 16000 * 6
        chunks.append(second)
        actual.capture_timeline.accept(second, window.time.time(), window.time.monotonic())
        assert previous.send(second, start_sample=len(first) // 2)
        actual._window_ring().append(second, len(first) // 2)
    for _ in range(500):
        if previous.is_connection_dead:
            break
        await _REAL_SLEEP(0.001)
    assert previous.is_connection_dead
    assert previous.typed_death_reason == reason
    await asyncio.gather(previous.raw._pump_task, return_exceptions=True)
    assert base.emitted == []
    assert await actual._failover_stt_socket()
    assert await actual._failover_stt_socket()  # already serving; no second replacement
    assert actual._stt_failed_providers == {'parakeet'}
    assert host.stt_service == st.STTService.soniox
    assert len(callbacks) == 1
    assert b''.join(replayed) == b''.join(chunks)
    assert actual._pending_live_failover.reason == reason
    assert WINDOW_SESSION_OUTCOME.labels(outcome='no_text', reason=reason)._value.get() == before_outcome + 1
    callbacks[0]([{'speaker': 'speaker_0', 'text': 'replacement', 'start': 0, 'end': 1}])
    assert (
        OMI_FALLBACK_TOTAL.labels(
            component='stt_live_session', from_mode='parakeet', to_mode='soniox', reason=reason, outcome='recovered'
        )._value.get()
        == before_fallback + 1
    )
    assert [segment['text'] for segment in base.emitted] == ['replacement']
    await actual._drain_stt_sockets()


class RacingTextClient:
    def __init__(self, *, propagate_cancel: bool = False):
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.release = asyncio.Event()
        self.propagate_cancel = propagate_cancel
        self.requests = []

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            await self.release.wait()
            if self.propagate_cancel:
                raise
        return httpx.Response(
            200,
            json={'segments': [{'text': 'Done.', 'start': 0.0, 'end': 4.0}]},
            request=httpx.Request('POST', url),
        )


async def _receiver_with_racing_window(monkeypatch, client, *, speech_seconds=6, silence_seconds=0):
    monkeypatch.setenv('PARAKEET_WINDOW_FIRST_TEXT_DEADLINE_SECONDS', '30')
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    monkeypatch.setattr(window.WindowedParakeetSocket, '_assign_speaker', AsyncMock(return_value=0))
    base = receiver()
    host = base.host
    host.request.sample_rate = 16000
    host.request.websocket = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
    host.state.stt_terminal_failure = False
    host.state.fair_use_dg_budget_exhausted = False
    host.state.fair_use_track_dg_usage = False
    host.state.dg_usage_ms_pending = 0
    host.client_device_context = SimpleNamespace(platform='ios')
    host.transcripts = SimpleNamespace(enqueue=base.emitted.extend)
    host.spawn = lambda coro, **kw: coro.close()
    actual = ListenReceiver(host, [], {})
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda callback, segments: callback(segments))
    replayed = []
    callbacks = []

    async def tail(callback, *args, **kwargs):
        callbacks.append(callback)
        return SimpleNamespace(
            is_connection_dead=False,
            send=lambda data: replayed.append(data) or True,
            finalize=lambda: None,
            finish=lambda: None,
        )

    monkeypatch.setattr(st, 'process_audio_soniox', tail)
    assert await actual.initialize_stt()
    previous = actual.stt_socket
    speech = b'\x01\x00' * 16000 * speech_seconds
    silence = bytes(16000 * 2 * silence_seconds)
    pcm = speech + silence
    actual.capture_timeline.accept(pcm, window.time.time(), window.time.monotonic())
    if silence:
        previous.raw.mark_speech()
        assert previous.raw.send(speech)
        assert previous.raw.send(silence)
    else:
        assert previous.send(pcm, start_sample=0)
    actual._window_ring().append(pcm, 0)
    await asyncio.wait_for(client.started.wait(), timeout=2)
    assert previous.raw._first_text_timer is not None
    return actual, base, previous, pcm, replayed, callbacks


class ProgressThenHoldClient:
    def __init__(self, *, hold_after=None):
        self.hold_after = hold_after
        self.requests = []
        self.blocked = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.release = asyncio.Event()

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        if self.hold_after is not None and len(self.requests) >= self.hold_after:
            self.blocked.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.cancelled.set()
                await self.release.wait()
        duration = _wav_duration(kwargs)
        return httpx.Response(
            200,
            json={'segments': [{'text': f'Part {len(self.requests)}.', 'start': 0.0, 'end': duration - 1.5}]},
            request=httpx.Request('POST', url),
        )


class UnpunctuatedClient(ProgressThenHoldClient):
    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        duration = _wav_duration(kwargs)
        return httpx.Response(
            200,
            json={'segments': [{'text': 'ongoing speech', 'start': 0.0, 'end': duration - 0.5}]},
            request=httpx.Request('POST', url),
        )


class LongTailClient(ProgressThenHoldClient):
    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        duration = _wav_duration(kwargs)
        return httpx.Response(
            200,
            json={
                'segments': [
                    {'text': 'short prefix', 'start': 0.0, 'end': 0.5},
                    {'text': 'continuing speech', 'start': 0.5, 'end': duration - 0.1},
                ]
            },
            request=httpx.Request('POST', url),
        )


async def _receiver_for_anchor_replay(monkeypatch, client):
    monkeypatch.setenv('PARAKEET_WINDOW_FIRST_TEXT_DEADLINE_SECONDS', '60')
    monkeypatch.setenv('PARAKEET_WINDOW_POST_TIMEOUT_SECONDS', '60')
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    monkeypatch.setattr(window.WindowedParakeetSocket, '_assign_speaker', AsyncMock(return_value=0))
    base = receiver()
    host = base.host
    host.request.sample_rate = 16000
    host.request.websocket = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
    host.state.stt_terminal_failure = False
    host.state.fair_use_dg_budget_exhausted = False
    host.state.fair_use_track_dg_usage = False
    host.state.dg_usage_ms_pending = 0
    host.client_device_context = SimpleNamespace(platform='ios')
    host.transcripts = SimpleNamespace(enqueue=base.emitted.extend)
    host.spawn = lambda coro, **kw: coro.close()
    actual = ListenReceiver(host, [], {})
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda callback, segments: callback(segments))
    replayed = []
    callbacks = []

    async def tail(callback, *args, **kwargs):
        callbacks.append(callback)
        return SimpleNamespace(
            is_connection_dead=False,
            send=lambda data: replayed.append(data) or True,
            finalize=lambda: None,
            finish=lambda: None,
        )

    monkeypatch.setattr(st, 'process_audio_soniox', tail)
    assert await actual.initialize_stt()
    return actual, base, actual.stt_socket, replayed, callbacks


async def _flush_capture(actual, pcm, start_sample):
    actual.capture_timeline.accept(pcm, window.time.time(), window.time.monotonic())
    actual._stt_buffer_start_sample = start_sample
    await actual._flush_stt_buffer(bytearray(pcm), force=True)


async def _wait_replay_anchor(raw, previous):
    deadline = asyncio.get_running_loop().time() + 2
    while raw.replay_anchor_sample() is None or raw.replay_anchor_sample() <= previous:
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError('window emit anchor did not advance')
        await _REAL_SLEEP(0)


@pytest.mark.asyncio
async def test_five_minutes_of_continuous_window_speech_keeps_bounded_replay(monkeypatch):
    client = ProgressThenHoldClient()
    actual, base, previous, replayed, callbacks = await _receiver_for_anchor_replay(monkeypatch, client)
    ring = actual._window_ring()
    pcm = b'\x01\x00' * 16000 * 6
    before_trims = WINDOW_REPLAY_SAFE_TRIMS._value.get()
    anchor = -1

    for step in range(50):
        await _flush_capture(actual, pcm, step * len(pcm) // 2)
        await _wait_requests(client, step + 1)
        await _wait_replay_anchor(previous.raw, anchor)
        anchor = previous.raw.replay_anchor_sample()
        assert actual.stt_socket is previous
        assert not previous.is_connection_dead
        assert ring.buffered_bytes <= 90 * 16000 * 2

    assert len(client.requests) == 50
    assert len(base.emitted) == 50
    assert replayed == [] and callbacks == []
    assert WINDOW_REPLAY_SAFE_TRIMS._value.get() > before_trims
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_unpunctuated_continuous_speech_forces_context_cut_before_buffer_cap(monkeypatch):
    client = UnpunctuatedClient()
    actual, base, previous, replayed, callbacks = await _receiver_for_anchor_replay(monkeypatch, client)
    pcm = b'\x01\x00' * 16000 * 6
    for step in range(50):
        await _flush_capture(actual, pcm, step * len(pcm) // 2)
        await _wait_requests(client, step + 1)
        assert not previous.is_connection_dead
        assert len(previous.raw._buf) <= previous.raw._buffer_cap()
    assert len(base.emitted) > 0
    assert replayed == [] and callbacks == []
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_long_unfinished_tdt_tail_cuts_at_context_cap_instead_of_filling_pcm_buffer(monkeypatch):
    client = LongTailClient()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    monkeypatch.setattr(window.WindowedParakeetSocket, '_assign_speaker', AsyncMock(return_value=0))
    emitted = []
    sock = window.WindowedParakeetSocket(emitted.extend, 'http://tdt.invalid', 16000, lambda: None)
    pcm = b'\x01\x00' * 16000 * 6
    anchors = []
    for _ in range(50):
        sock.mark_speech()
        assert sock.send(pcm)
        job = sock._next_job()
        assert job is not None
        await sock._run_job(job)
        anchors.append(sock._anchor_bytes)
        assert len(sock._buf) <= sock._buffer_cap()
    assert len(client.requests) == 50
    assert anchors[3] < sock._pace_bytes  # early cuts keep the sentence anchor
    assert any(right - left > sock._pace_bytes for left, right in zip(anchors, anchors[1:]))
    assert emitted
    assert not sock.is_connection_dead
    sock.finish()


@pytest.mark.asyncio
async def test_partial_vad_admission_unfinished_tdt_tail_keeps_replay_anchor_within_ninety_seconds(monkeypatch):
    client = LongTailClient()
    pump_release = asyncio.Event()

    async def parked_pump(_self):
        await pump_release.wait()

    monkeypatch.setattr(window.WindowedParakeetSocket, '_pump', parked_pump)
    actual, base, previous, replayed, callbacks = await _receiver_for_anchor_replay(monkeypatch, client)
    ring = actual._window_ring()
    pcm = b'\x01\x00' * 16000 * 6
    assert previous.gate is not None and not previous.passthrough

    def admit_half(data, _wall_time, _score_pcm, start_sample):
        assert start_sample is not None
        return vad_gate.GateOutput(
            audio_to_send=data[: len(data) // 2],
            is_speech=True,
            send_spans=((start_sample, len(data) // 4),),
        )

    monkeypatch.setattr(previous.gate, 'process_audio', admit_half)
    before_cuts = WINDOW_FORCED_CUTS._value.get()

    for step in range(50):  # Five capture minutes, half admitted to the provider after VAD.
        await _flush_capture(actual, pcm, step * len(pcm) // 2)
        assert actual.stt_socket is previous, (step, previous.capacity_subtype, previous.raw.death_reason)
        assert previous.capacity_subtype is None
        assert ring.buffered_bytes <= 90 * 16000 * 2
        job = previous.raw._next_job()
        if job is not None:
            await previous.raw._run_job(job)

    assert base.emitted
    ends = [float(item['end']) for item in base.emitted]
    assert ends == sorted(set(ends))  # Re-posted context never duplicates emitted text.
    assert WINDOW_FORCED_CUTS._value.get() > before_cuts
    assert replayed == [] and callbacks == []
    trim_window_replay_to_anchor(ring, previous)
    replay_snapshot = ring.snapshot()
    assert replay_snapshot and replay_snapshot[0][0] == previous.window_replay_anchor_sample()
    previous.raw.fail('timeout')
    assert await actual._failover_stt_socket()
    assert b''.join(replayed) == b''.join(data for _, data in replay_snapshot)
    assert len(callbacks) == 1
    assert [float(item['end']) for item in base.emitted] == ends
    pump_release.set()
    await actual._drain_stt_sockets()


class LagScenarioClient(ProgressThenHoldClient):
    def __init__(self, *, tiny=False):
        super().__init__()
        self.tiny = tiny

    async def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        duration = _wav_duration(kwargs)
        if len(self.requests) == 1:
            segments = [{'text': 'Initial.', 'start': 0.0, 'end': duration - 1.5}]
        elif self.tiny:
            segments = [{'text': 'Brief.', 'start': 0.0, 'end': 0.1}]
        else:
            segments = []
        return httpx.Response(200, json={'segments': segments}, request=httpx.Request('POST', url))


@pytest.mark.asyncio
@pytest.mark.parametrize('scenario', ['answered_empty', 'very_short', 'sparse_empty', 'vad_noise_after_text'])
async def test_replay_lag_scenarios_preserve_answered_audio_and_explain_overflow(monkeypatch, caplog, scenario):
    # Run the real window jobs at deterministic capture steps; no synthetic
    # speech predicate, no real audio/content and no wall-clock waiting.
    async def parked_pump(_self):
        await asyncio.Future()

    monkeypatch.setattr(window.WindowedParakeetSocket, '_pump', parked_pump)
    client = LagScenarioClient(tiny=scenario == 'very_short')
    actual, base, previous, replayed, callbacks = await _receiver_for_anchor_replay(monkeypatch, client)
    raw = previous.raw
    ring = actual._window_ring()
    pcm = b'\x01\x00' * 16000 * 6
    await _flush_capture(actual, pcm, 0)
    await raw._run_job(raw._next_job())
    initial_anchor = previous.window_replay_anchor_sample()
    assert initial_anchor == int(4.5 * 16000)
    admitted_samples = 16000 if scenario == 'sparse_empty' else 3 * 16000

    def admit_partial(data, _wall, _score, start_sample):
        return vad_gate.GateOutput(
            audio_to_send=data[: admitted_samples * 2],
            is_speech=True,
            send_spans=((start_sample, admitted_samples),),
        )

    monkeypatch.setattr(previous.gate, 'process_audio', admit_partial)
    requested_before = window.WINDOW_REPLAY_CUT_REQUESTS._value.get()
    skipped_before = window.WINDOW_REPLAY_CUT_SKIPPED.labels(reason='no_text_yet')._value.get()
    snapshot = None
    for step in range(1, 30):
        snapshot = ring.snapshot()
        await _flush_capture(actual, pcm, step * 6 * 16000)
        if actual.stt_socket is not previous:
            break
        job = raw._next_job()
        if job is not None:
            await raw._run_job(job)
    else:
        pytest.fail('scenario did not reproduce replay-ring overflow')

    diagnostics = raw.replay_lag_diagnostics
    assert raw.capacity_subtype == 'replay_ring_cap'
    assert diagnostics.capture_seconds > 90
    assert 0 < diagnostics.admitted_seconds < diagnostics.capture_seconds / 2
    assert not diagnostics.post_in_flight and not diagnostics.pacing_wait
    assert diagnostics.cut_pending
    assert window.WINDOW_REPLAY_CUT_REQUESTS._value.get() > requested_before
    assert len(callbacks) == 1
    # No answered-empty samples are discarded. Replay covers exactly the
    # protected snapshot plus the unsent chunk, once, starting at the anchor.
    assert snapshot[0][0] == previous.window_replay_anchor_sample()
    assert b''.join(replayed) == b''.join(data for _, data in snapshot) + pcm
    if scenario == 'very_short':
        assert diagnostics.empty_posts_since_anchor == 0 and diagnostics.empty_streak == 0
    else:
        assert diagnostics.posts_since_anchor == diagnostics.empty_posts_since_anchor > 0
        assert diagnostics.empty_streak > 0
        assert window.WINDOW_REPLAY_CUT_SKIPPED.labels(reason='no_text_yet')._value.get() > skipped_before
    # Snapshot survives cancellation/rebuild and arrives on the existing
    # outcome line only when the replacement leg actually transcribes.
    assert actual._pending_live_failover.replay_lag_diagnostics is diagnostics
    callbacks[0]([{'speaker': 'speaker_0', 'text': 'Replacement.', 'start': 0, 'end': 1}])
    lines = [r.message for r in caplog.records if 'subtype=replay_ring_cap' in r.message]
    assert len(lines) == 1
    assert 'un_emitted_capture_seconds=' in lines[0] and 'vad_admitted_seconds=' in lines[0]
    assert 'posts_since_anchor=' in lines[0] and 'empty_posts_since_anchor=' in lines[0]
    assert 'Initial.' not in lines[0] and 'Replacement.' not in lines[0]
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_sparse_healthy_speech_idle_flushes_without_replay_pressure(monkeypatch):
    pump_release = asyncio.Event()

    async def parked_pump(_self):
        await pump_release.wait()

    monkeypatch.setattr(window.WindowedParakeetSocket, '_pump', parked_pump)
    client = UnpunctuatedClient()
    actual, base, previous, replayed, callbacks = await _receiver_for_anchor_replay(monkeypatch, client)
    clock = [window.time.monotonic()]
    monkeypatch.setattr(window.time, 'monotonic', lambda: clock[0])
    pcm = b'\x01\x00' * 16000 * 30

    def admit_sparse(data, _wall, _score, start_sample):
        return vad_gate.GateOutput(audio_to_send=data[: 16000 * 2], is_speech=True, send_spans=((start_sample, 16000),))

    monkeypatch.setattr(previous.gate, 'process_audio', admit_sparse)
    for step in range(10):
        await _flush_capture(actual, pcm, step * 30 * 16000)
        clock[0] += 2  # production idle flush budget, after the admitted second
        job = previous.raw._next_job()
        assert job is not None and job.force
        await previous.raw._run_job(job)
        clock[0] += 28
        assert actual.stt_socket is previous and not previous.is_connection_dead
        assert actual._window_ring().buffered_bytes <= 30 * 16000 * 2
    assert len(base.emitted) == 10 and len(client.requests) == 10
    assert not replayed and not callbacks
    pump_release.set()
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_cut_with_unusable_timestamps_counts_other_without_discarding_speech(monkeypatch):
    monkeypatch.setattr(
        window, 'get_stt_client', lambda: Client(data={'segments': [{'text': 'Drift', 'start': 6, 'end': 8}]})
    )
    sock = window.WindowedParakeetSocket(
        lambda _: pytest.fail('invalid text emitted'), 'http://tdt.invalid', 16000, lambda: None
    )
    sock.mark_speech()
    assert sock.send(b'\x01\x00' * 16000 * 6)
    sock.request_replay_cut()
    before = window.WINDOW_REPLAY_CUT_SKIPPED.labels(reason='other')._value.get()
    await sock._run_job(sock._next_job())
    assert window.WINDOW_REPLAY_CUT_SKIPPED.labels(reason='other')._value.get() == before + 1
    assert sock.replay_anchor_sample() is None and sock.has_untranscribed_speech()
    assert sock._replay_cut_requested
    sock.finish()


@pytest.mark.asyncio
async def test_no_first_text_cut_is_noop_but_startup_deadline_still_protects_noise(monkeypatch):
    client = Client(data={'text': ''})
    actual, base, previous, replayed, callbacks = await _receiver_for_anchor_replay(monkeypatch, client)
    raw = previous.raw
    before = window.WINDOW_REPLAY_CUT_SKIPPED.labels(reason='no_text_yet')._value.get()
    pcm = b'\x01\x00' * 16000 * 6  # synthetic noise classified as speech by the real gate seam
    raw.request_replay_cut()
    await _flush_capture(actual, pcm, 0)
    await _wait_requests(client, 1)
    for _ in range(100):
        if raw._empty_streak:
            break
        await _REAL_SLEEP(0)
    assert raw._empty_streak == 1 and raw.has_untranscribed_speech()
    assert raw.replay_anchor_sample() is None
    assert raw._replay_cut_requested and not base.emitted
    assert window.WINDOW_REPLAY_CUT_SKIPPED.labels(reason='no_text_yet')._value.get() == before + 1
    # Fire the production deadline callback rather than disabling the budget
    # to fabricate a >90s startup. A no-text session fails much earlier.
    raw._expire_first_text()
    assert await actual._failover_stt_socket()
    assert raw.death_reason == 'first_text_deadline'
    assert len(callbacks) == 1 and b''.join(replayed) == pcm
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_pacing_wait_with_capture_burst_reports_deferred_cut_and_exact_replay(monkeypatch):
    client = ProgressThenHoldClient()
    actual, base, previous, replayed, callbacks = await _receiver_for_anchor_replay(monkeypatch, client)
    raw = previous.raw
    pcm = b'\x01\x00' * 16000 * 6
    await _flush_capture(actual, pcm, 0)
    await _wait_replay_anchor(raw, -1)
    pacing_started, pacing_release = asyncio.Event(), asyncio.Event()

    async def hold_pacing(_delay):
        pacing_started.set()
        await pacing_release.wait()

    monkeypatch.setattr(window.asyncio, 'sleep', hold_pacing)

    # Only one admitted second per six capture seconds: the PCM buffer cannot
    # hit its own cap first. A catch-up burst can consume 30 capture seconds
    # of ring headroom before the next six-second wall pacing wait ends.
    def admit_sparse(data, _wall, _score, start_sample):
        return vad_gate.GateOutput(audio_to_send=data[: 16000 * 2], is_speech=True, send_spans=((start_sample, 16000),))

    monkeypatch.setattr(previous.gate, 'process_audio', admit_sparse)
    await _flush_capture(actual, pcm, 6 * 16000)
    await asyncio.wait_for(pacing_started.wait(), 2)
    skipped_before = window.WINDOW_REPLAY_CUT_SKIPPED.labels(reason='post_pacing')._value.get()
    for step in range(2, 17):
        snapshot = actual._window_ring().snapshot()
        await _flush_capture(actual, pcm, step * 6 * 16000)
        if actual.stt_socket is not previous:
            break
    diagnostics = raw.replay_lag_diagnostics
    assert raw.capacity_subtype == 'replay_ring_cap'
    assert diagnostics.pacing_wait and not diagnostics.post_in_flight
    assert diagnostics.cut_pending and diagnostics.posts_since_anchor == 0
    assert window.WINDOW_REPLAY_CUT_SKIPPED.labels(reason='post_pacing')._value.get() == skipped_before + 1
    assert len(callbacks) == 1 and b''.join(replayed) == b''.join(data for _, data in snapshot) + pcm
    assert len(base.emitted) == 1
    pacing_release.set()
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
@pytest.mark.parametrize('held_tail', [False, True])
async def test_cut_result_counters_distinguish_natural_progress_from_forced_tail(monkeypatch, held_tail):
    client = LongTailClient() if held_tail else ProgressThenHoldClient()
    actual, base, previous, _replayed, _callbacks = await _receiver_for_anchor_replay(monkeypatch, client)
    raw = previous.raw
    performed_before = window.WINDOW_REPLAY_CUT_PERFORMED._value.get()
    skipped_before = window.WINDOW_REPLAY_CUT_SKIPPED.labels(reason='no_held_tail')._value.get()
    requests_before = window.WINDOW_REPLAY_CUT_REQUESTS._value.get()
    raw.request_replay_cut()
    raw.request_replay_cut()  # incoming capture chunks coalesce into one request
    pcm = b'\x01\x00' * 16000 * 6
    await _flush_capture(actual, pcm, 0)
    await _wait_replay_anchor(raw, -1)
    assert window.WINDOW_REPLAY_CUT_REQUESTS._value.get() == requests_before + 1
    assert window.WINDOW_REPLAY_CUT_PERFORMED._value.get() == performed_before + int(held_tail)
    assert window.WINDOW_REPLAY_CUT_SKIPPED.labels(reason='no_held_tail')._value.get() == skipped_before + int(
        not held_tail
    )
    assert not raw._replay_cut_requested
    assert raw._posts_since_anchor == raw._empty_posts_since_anchor == 0
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_stalled_window_post_fails_once_and_replays_exactly_from_emit_anchor(monkeypatch):
    client = ProgressThenHoldClient(hold_after=2)
    actual, base, previous, replayed, callbacks = await _receiver_for_anchor_replay(monkeypatch, client)
    ring = actual._window_ring()
    ring.ring_seconds = 12
    pcm = b'\x01\x00' * 16000 * 6
    await _flush_capture(actual, pcm, 0)
    await _wait_replay_anchor(previous.raw, -1)
    anchor = previous.window_replay_anchor_sample()
    assert anchor is not None and anchor > 0
    assert ring.snapshot()[0][0] == anchor

    await _flush_capture(actual, pcm, 6 * 16000)
    await asyncio.wait_for(client.blocked.wait(), 2)
    assert previous.raw.has_untranscribed_speech()
    assert previous.raw._post_in_flight
    assert not previous.raw._pump_task.done()
    before_deferred = window.WINDOW_REPLAY_CUT_SKIPPED.labels(reason='post_in_flight')._value.get()
    await _flush_capture(actual, pcm, 12 * 16000)
    assert window.WINDOW_REPLAY_CUT_SKIPPED.labels(reason='post_in_flight')._value.get() == before_deferred + 1

    assert previous.raw.death_reason == 'capacity_full'
    assert previous.capacity_subtype == 'replay_ring_cap'
    assert previous.raw.replay_lag_diagnostics.post_in_flight
    assert previous.raw.replay_lag_diagnostics.posts_since_anchor == 1
    assert previous.raw.replay_lag_diagnostics.empty_posts_since_anchor == 0
    assert actual._pending_live_failover.reason == 'capacity_full'
    assert actual._pending_live_failover.capacity_subtype == 'replay_ring_cap'
    assert len(callbacks) == 1
    assert b''.join(replayed) == pcm[anchor * 2 :] + pcm + pcm
    client.release.set()
    await asyncio.gather(previous.raw._pump_task, return_exceptions=True)
    assert len(base.emitted) == 1
    assert await actual._failover_stt_socket()
    assert len(callbacks) == 1
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_stalled_window_pcm_cap_reports_buffer_subtype_and_replays(monkeypatch, caplog):
    client = ProgressThenHoldClient(hold_after=2)
    actual, base, previous, replayed, callbacks = await _receiver_for_anchor_replay(monkeypatch, client)
    pcm = b'\x01\x00' * 16000 * 6
    await _flush_capture(actual, pcm, 0)
    await _wait_replay_anchor(previous.raw, -1)
    anchor = previous.window_replay_anchor_sample()
    assert anchor is not None
    await _flush_capture(actual, pcm, 6 * 16000)
    await asyncio.wait_for(client.blocked.wait(), 2)
    for step in range(2, 11):
        await _flush_capture(actual, pcm, step * 6 * 16000)
    assert previous.raw.death_reason == 'capacity_full'
    assert previous.capacity_subtype == 'buffer_cap'
    assert actual._pending_live_failover.reason == 'capacity_full'
    assert actual._pending_live_failover.capacity_subtype == 'buffer_cap'
    actual._pending_live_failover.note_transcript([{'text': 'test'}])
    assert 'reason=capacity_full outcome=recovered subtype=buffer_cap' in caplog.text
    assert len(callbacks) == 1
    assert b''.join(replayed) == pcm[anchor * 2 :] + pcm * 10
    assert len(base.emitted) == 1
    client.release.set()
    await asyncio.gather(previous.raw._pump_task, return_exceptions=True)
    await actual._drain_stt_sockets()


def test_capacity_subtype_is_bounded_log_detail_not_a_metric_reason(caplog):
    label = OMI_FALLBACK_TOTAL.labels(
        component='stt_live_session',
        from_mode='parakeet',
        to_mode='soniox',
        reason='capacity_full',
        outcome='recovered',
    )
    before = label._value.get()
    record_fallback(
        component='stt_live_session',
        from_mode='parakeet',
        to_mode='soniox',
        reason='capacity_full',
        outcome='recovered',
        capacity_subtype='buffer_cap',
    )
    assert label._value.get() == before + 1
    assert 'reason=capacity_full outcome=recovered subtype=buffer_cap' in caplog.text
    record_fallback(
        component='stt_live_session',
        from_mode='parakeet',
        to_mode='soniox',
        reason='capacity_full',
        outcome='recovered',
        capacity_subtype='unbounded-user-content',
    )
    assert 'subtype=unknown' in caplog.text
    assert 'unbounded-user-content' not in caplog.text


@pytest.mark.asyncio
async def test_trim_during_inflight_window_post_retains_its_entire_unemitted_span(monkeypatch):
    client = ProgressThenHoldClient(hold_after=2)
    actual, base, previous, replayed, callbacks = await _receiver_for_anchor_replay(monkeypatch, client)
    ring = actual._window_ring()
    ring.ring_seconds = 12
    pcm = b'\x01\x00' * 16000 * 6
    # Delay the immediate progress callback so this test trims while the next
    # real pump POST is in flight, as can happen at a send/failover boundary.
    previous.raw.set_replay_progress_callback(lambda: None)
    await _flush_capture(actual, pcm, 0)
    await _wait_replay_anchor(previous.raw, -1)
    anchor = previous.window_replay_anchor_sample()
    assert anchor is not None and anchor > 0
    actual.capture_timeline.accept(pcm, window.time.time(), window.time.monotonic())
    assert previous.send(pcm, start_sample=6 * 16000)
    ring.append(pcm, 6 * 16000)  # preserve the pre-trim state at this race boundary
    await asyncio.wait_for(client.blocked.wait(), 2)
    assert ring.snapshot()[0][0] == 0
    before = WINDOW_REPLAY_SAFE_TRIMS._value.get()
    trim_window_replay_to_anchor(ring, previous)
    assert ring.snapshot()[0][0] == anchor
    assert WINDOW_REPLAY_SAFE_TRIMS._value.get() == before + 1
    previous.raw.fail('provider_5xx')
    assert await actual._failover_stt_socket()
    assert len(callbacks) == 1
    assert b''.join(replayed) == pcm[anchor * 2 :] + pcm
    client.release.set()
    await asyncio.gather(previous.raw._pump_task, return_exceptions=True)
    assert len(base.emitted) == 1
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_pending_window_post_overflow_replays_speech_before_next_chunk(monkeypatch):
    client = RacingTextClient()
    actual, base, previous, pcm, replayed, callbacks = await _receiver_with_racing_window(monkeypatch, client)
    ring = actual._window_ring()
    ring.ring_seconds = 6
    next_speech = b'\x02\x00' * 16000
    actual.capture_timeline.accept(next_speech, window.time.time(), window.time.monotonic())
    actual._stt_buffer_start_sample = len(pcm) // 2
    before_trims = WINDOW_REPLAY_SAFE_TRIMS._value.get()

    assert previous.raw.has_untranscribed_speech()
    assert not previous.raw._pump_task.done()  # the real pump is still awaiting the POST
    assert ring.snapshot() == ((0, pcm),)
    await actual._flush_stt_buffer(bytearray(next_speech), force=True)

    assert WINDOW_REPLAY_SAFE_TRIMS._value.get() == before_trims
    assert previous.raw.death_reason == 'capacity_full'
    assert actual._pending_live_failover.reason == 'capacity_full'
    assert len(callbacks) == 1  # exactly one replacement leg
    assert b''.join(replayed) == pcm + next_speech
    assert base.emitted == []
    client.release.set()
    await asyncio.gather(previous.raw._pump_task, return_exceptions=True)
    assert base.emitted == []  # a late POST cannot duplicate the replayed speech
    assert await actual._failover_stt_socket()
    assert len(callbacks) == 1
    assert len(client.requests) == 1
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_completed_window_post_allows_silent_ring_trim_without_failover(monkeypatch):
    client = RacingTextClient()
    actual, base, previous, pcm, replayed, callbacks = await _receiver_with_racing_window(
        monkeypatch, client, speech_seconds=4, silence_seconds=2
    )
    ring = actual._window_ring()
    ring.ring_seconds = 6
    before_trims = WINDOW_REPLAY_SAFE_TRIMS._value.get()
    assert previous.raw.has_untranscribed_speech()

    client.release.set()
    for _ in range(100):
        if base.emitted and previous.raw._anchor_bytes >= 4 * 16000 * 2:
            break
        await _REAL_SLEEP(0)
    assert [segment['text'] for segment in base.emitted] == ['Done.']
    assert previous.raw._anchor_bytes >= 4 * 16000 * 2
    assert not previous.raw.has_untranscribed_speech()
    assert len(client.requests) == 1

    next_silence = bytes(16000 * 2)
    actual.capture_timeline.accept(next_silence, window.time.time(), window.time.monotonic())
    actual._stt_buffer_start_sample = len(pcm) // 2
    await actual._flush_stt_buffer(bytearray(next_silence), force=True)

    assert WINDOW_REPLAY_SAFE_TRIMS._value.get() == before_trims + 1
    assert actual.stt_socket is previous
    assert not previous.is_connection_dead
    assert replayed == []
    assert callbacks == []
    assert ring.snapshot()[0][0] == 16000
    assert ring.buffered_bytes == len(pcm)
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
@pytest.mark.parametrize('propagate_cancel', [False, True])
async def test_deadline_during_post_replays_once_without_late_text(monkeypatch, propagate_cancel):
    client = RacingTextClient(propagate_cancel=propagate_cancel)
    actual, base, previous, pcm, replayed, callbacks = await _receiver_with_racing_window(monkeypatch, client)
    before_outcome = WINDOW_SESSION_OUTCOME.labels(outcome='no_text', reason='first_text_deadline')._value.get()
    fallback = OMI_FALLBACK_TOTAL.labels(
        component='stt_live_session',
        from_mode='parakeet',
        to_mode='soniox',
        reason='first_text_deadline',
        outcome='recovered',
    )
    before_fallback = fallback._value.get()
    previous.raw._expire_first_text()
    await asyncio.wait_for(client.cancelled.wait(), timeout=2)
    client.release.set()  # the POST completes with text after the deadline, or propagates cancellation
    await asyncio.gather(previous.raw._pump_task, return_exceptions=True)
    assert previous.death_reason == 'first_text_deadline'
    assert previous.typed_death_reason == 'first_text_deadline'
    assert base.emitted == []
    assert (
        WINDOW_SESSION_OUTCOME.labels(outcome='no_text', reason='first_text_deadline')._value.get()
        == before_outcome + 1
    )
    assert await actual._failover_stt_socket()
    assert await actual._failover_stt_socket()
    assert len(callbacks) == 1
    assert b''.join(replayed) == pcm
    assert actual._pending_live_failover.reason == 'first_text_deadline'
    callbacks[0]([{'speaker': 'speaker_0', 'text': 'Done.', 'start': 0, 'end': 4}])
    assert [segment['text'] for segment in base.emitted] == ['Done.']
    assert fallback._value.get() == before_fallback + 1
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_text_post_just_before_deadline_disarms_failover(monkeypatch):
    client = RacingTextClient()
    actual, base, previous, _pcm, replayed, callbacks = await _receiver_with_racing_window(monkeypatch, client)
    client.release.set()
    for _ in range(100):
        if base.emitted:
            break
        await _REAL_SLEEP(0)
    assert [segment['text'] for segment in base.emitted] == ['Done.']
    assert previous.raw._first_text_recorded
    assert previous.raw._first_text_timer is None
    previous.raw._expire_first_text()  # stale scheduled callback cannot fail a session with text
    assert not previous.is_connection_dead
    assert await actual._failover_stt_socket()
    assert actual.stt_socket is previous
    assert replayed == []
    assert callbacks == []
    assert len(client.requests) == 1
    await actual._drain_stt_sockets()


@pytest.mark.asyncio
async def test_first_text_disarms_deadline_and_empty_streak(monkeypatch):
    monkeypatch.setenv('PARAKEET_WINDOW_FIRST_TEXT_DEADLINE_SECONDS', '0.2')
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_EMPTY_STREAK', '1')
    posted = []
    client = SeqClient([{'segments': [{'text': 'Done.', 'start': 0.0, 'end': 4.0}]}, {'text': ''}])
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(posted.extend, 16000)
    sock.mark_speech()
    assert sock.send(b'\x01\x00' * 16000 * 6)
    await _wait_requests(client, 1)
    for _ in range(100):
        if posted:
            break
        await _REAL_SLEEP(0)
    assert [segment['text'] for segment in posted] == ['Done.']
    assert sock._first_text_timer is None
    await _REAL_SLEEP(0.22)
    assert not sock.is_connection_dead
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_empty_post_without_speech_does_not_advance_streak(monkeypatch):
    monkeypatch.setenv('PARAKEET_WINDOW_MAX_EMPTY_STREAK', '1')
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client(data={'text': ''}))
    sock = window.connect_window(lambda _: None, 16000)
    pcm = bytes(16000 * 2)
    await sock._run_job(window._WindowJob(pcm, 0.0, 1.0, 0, len(pcm), False, False))
    assert sock._empty_streak == 0
    assert not sock.is_connection_dead
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_long_vad_silence_does_not_replace_healthy_window_leg(monkeypatch):
    client = Client()
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    fallback = AsyncMock(side_effect=AssertionError('silent window must not select Soniox'))
    monkeypatch.setattr(st, 'process_audio_soniox', fallback)
    base = receiver()
    host = base.host
    host.request.sample_rate = 16000
    host.request.websocket = SimpleNamespace(send_json=AsyncMock(), close=AsyncMock())
    host.state.stt_terminal_failure = False
    host.state.fair_use_dg_budget_exhausted = False
    host.state.fair_use_track_dg_usage = False
    host.state.dg_usage_ms_pending = 0
    host.client_device_context = SimpleNamespace(platform='ios')
    host.transcripts = SimpleNamespace(enqueue=base.emitted.extend)
    host.spawn = lambda coro, **kw: coro.close()
    actual = ListenReceiver(host, [], {})
    assert await actual.initialize_stt()
    previous = actual.stt_socket
    ring = actual._window_ring()
    ring.ring_seconds = 3
    one_second = bytes(16000 * 2)
    for second in range(5):
        actual.capture_timeline.accept(one_second, window.time.time(), window.time.monotonic())
        actual._stt_buffer_start_sample = second * 16000
        await actual._flush_stt_buffer(bytearray(one_second), force=True)
    assert actual.stt_socket is previous
    assert not previous.is_connection_dead
    assert not previous.raw.has_untranscribed_speech()
    assert ring.buffered_bytes == 3 * len(one_second)
    assert ring.snapshot()[0][0] == 2 * 16000
    assert client.requests == []
    fallback.assert_not_awaited()
    await actual._drain_stt_sockets()
    assert previous.raw.death_reason is None  # normal teardown never becomes connection_lost


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
    # Audio-timeline v2: _stt_rebuild holds a callback factory plus the
    # sample rate; the factory returns fresh callbacks bound to a new
    # provider epoch's translator on each rebuild.
    actual._stt_rebuild = (lambda: (lambda _: None, lambda _: None, None), 16000)
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
    monkeypatch.setattr(window.batch_pressure, 'allows', lambda *_: True)
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
    replay_cut = decide_window([first, held], 6.0, 24.0, force=False, force_replay_cut=True)
    assert replay_cut.emit == (first, held)
    assert replay_cut.new_anchor == 5.0
    assert replay_cut.forced_cut is True
    assert decide_window([], 6.0, 24.0, force=False, force_replay_cut=True).emit == ()

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
    tiny = RawSegment('short prefix', 0.0, 0.5)
    long_tail = RawSegment('continuing speech', 0.5, 23.9)
    stalled_cap = decide_window([tiny, long_tail], 24.0, 24.0, force=False, min_cap_progress=6.0)
    assert stalled_cap.emit == (tiny, long_tail)
    assert stalled_cap.new_anchor == 23.9
    assert stalled_cap.forced_cut is True
    progressed = RawSegment('complete prefix.', 0.0, 18.0)
    healthy_cap = decide_window([progressed, long_tail], 24.0, 24.0, force=False, min_cap_progress=6.0)
    assert healthy_cap.emit == (progressed,)
    assert healthy_cap.new_anchor == 18.0
    assert healthy_cap.forced_cut is False
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
    from utils.stt.window_anchor import DEFAULT_PACE_SECONDS, read_max_context_seconds, read_pace_seconds

    monkeypatch.setenv('PARAKEET_WINDOW_PACE_SECONDS', '0')
    assert read_pace_seconds() == 1.0
    monkeypatch.setenv('PARAKEET_WINDOW_PACE_SECONDS', '99')
    assert read_pace_seconds() == 15.0
    monkeypatch.setenv('PARAKEET_WINDOW_PACE_SECONDS', 'nope')
    # Pace decides window size, and window size is what drives accuracy on this leg,
    # so pin the fallback to the declared default rather than a literal.
    assert read_pace_seconds() == DEFAULT_PACE_SECONDS == 15.0
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

    monkeypatch.setattr(window.batch_pressure, 'allows', lambda *_: True)
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
async def test_default_pace_waits_for_fifteen_seconds_of_speech(monkeypatch):
    # Window size drives accuracy on this leg, so continuous speech must not be posted
    # in small slices: at the default pace, 6 s does not post and 15 s does.
    from utils.stt.window_anchor import DEFAULT_PACE_SECONDS

    monkeypatch.delenv('PARAKEET_WINDOW_PACE_SECONDS')
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    client = Client(data={'segments': [{'text': 'Go on', 'start': 0.0, 'end': 5.0}]})
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(lambda _: None, 16000)
    assert sock._pace_seconds == DEFAULT_PACE_SECONDS == 15.0
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 6)
    for _ in range(50):
        await _REAL_SLEEP(0)
    assert client.requests == []
    sock.mark_speech()
    sock.send(b'\x01\x00' * 16000 * 9)
    await _wait_requests(client, 1)
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
@pytest.mark.parametrize('pace', ['6', '15'])
async def test_empty_at_cap_slides_six_seconds_and_later_post_recovers(monkeypatch, pace):
    # The slide is fixed, not the pace: at a 15 s pace, sliding by pace would
    # discard 15 s of speech the model returned nothing for.
    monkeypatch.setenv('PARAKEET_WINDOW_PACE_SECONDS', pace)
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

    monkeypatch.setattr(window.batch_pressure, 'allows', lambda *_: True)
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


def _head_socket(monkeypatch, payloads):
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    client = SeqClient(payloads)
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(lambda _: None, 16000)
    return sock, client


def _job(sock, seconds: float) -> window._WindowJob:
    pcm = b'\x01\x00' * int(16000 * seconds)
    return window._WindowJob(pcm, 0.0, seconds, 0, len(pcm), False, False)


@pytest.mark.asyncio
async def test_skipped_leading_speech_is_reposted_and_prepended(monkeypatch):
    later = window.RawSegment('Later sentence.', 15.1, 23.8)
    sock, client = _head_socket(monkeypatch, [{'segments': [{'text': 'Skipped head.', 'start': 1.5, 'end': 14.8}]}])
    job = _job(sock, 24.0)
    sock._speech_spans.append((0, len(job.pcm)))
    before = window.WINDOW_HEAD_RECOVERIES.labels(outcome='recovered')._value.get()
    out = await sock._recover_skipped_head(job, [later])
    assert [s.text for s in out] == ['Skipped head.', 'Later sentence.']
    body = _posted_pcm(client.requests[0][1])
    assert len(body) == sock._to_bytes(15.1)
    assert window.WINDOW_HEAD_RECOVERIES.labels(outcome='recovered')._value.get() == before + 1
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_normal_lead_in_is_not_reposted(monkeypatch):
    sock, client = _head_socket(monkeypatch, [{'text': 'unused'}])
    job = _job(sock, 24.0)
    sock._speech_spans.append((0, len(job.pcm)))
    first = window.RawSegment('Starts on time.', 1.2, 9.0)
    assert await sock._recover_skipped_head(job, [first]) == [first]
    assert client.requests == []
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_late_first_segment_after_nonspeech_is_not_reposted(monkeypatch):
    sock, client = _head_socket(monkeypatch, [{'text': 'unused'}])
    job = _job(sock, 24.0)
    # The VAD saw only 1 s of speech before the first segment: that gap is a pause.
    sock._speech_spans.append((sock._to_bytes(9.0), sock._to_bytes(10.0)))
    sock._speech_spans.append((sock._to_bytes(12.0), len(job.pcm)))
    first = window.RawSegment('After a pause.', 12.1, 20.0)
    assert await sock._recover_skipped_head(job, [first]) == [first]
    assert client.requests == []
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


def test_decoder_loops_collapse_and_ordinary_repetition_survives():
    from utils.stt.window_anchor import collapse_decoder_loops

    loop = 'roles have increased in a little bit of a little bit of a little bit of a little bit of a ability to retain'
    assert collapse_decoder_loops(loop) == ('roles have increased in a little bit of a ability to retain', 1)
    for speech in (
        'no no no I said',
        'the the market',
        'yeah yeah yeah yeah',
        "I think I think that's right",
        'we did forty million of incremental billings',
    ):
        assert collapse_decoder_loops(speech) == (speech, 0)


@pytest.mark.asyncio
async def test_window_segments_have_decoder_loops_collapsed(monkeypatch):
    monkeypatch.setattr(window.asyncio, 'sleep', lambda _delay: _REAL_SLEEP(0))
    looped = 'It went up a bit more a bit more a bit more a bit more than planned.'
    client = SeqClient([{'segments': [{'text': looped, 'start': 0.2, 'end': 5.0}]}])
    monkeypatch.setattr(window, 'get_stt_client', lambda: client)
    sock = window.connect_window(lambda _: None, 16000)
    before = window.WINDOW_DECODER_LOOPS._value.get()
    out = await sock._post_and_parse(b'\x01\x00' * 16000 * 6, 6.0)
    assert [s.text for s in out] == ['It went up a bit more than planned.']
    assert window.WINDOW_DECODER_LOOPS._value.get() == before + 1
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)
