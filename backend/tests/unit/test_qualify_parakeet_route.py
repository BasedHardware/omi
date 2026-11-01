"""Route gate exercises served clients with mocked HTTP/WebSocket transports."""

import asyncio
from contextlib import asynccontextmanager
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import wave

import httpx
import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.frames import Close

from scripts import qualify_parakeet_route as probe
from utils.stt import pre_recorded, streaming
from utils.stt import parakeet_window as window


@pytest.fixture
def fast_clock(monkeypatch):
    real_sleep = asyncio.sleep

    async def sleep(_seconds):
        await real_sleep(0)

    monkeypatch.setattr(asyncio, 'sleep', sleep)


class WebSocketTransport:
    def __init__(self, ready='ready', order=True, close_code=1000, refusal=None):
        self.open = True
        self.response_headers = {'Upgrade': 'websocket'}
        self.close_code = close_code
        self.close_reason = ''
        self.ready = ready
        self.order = order
        self.refusal = refusal
        self.messages = asyncio.Queue()
        self.sent = []
        self.pcm_count = 0
        self.url = ''

    async def recv(self):
        if self.refusal:
            raise ConnectionClosedError(Close(1013, self.refusal), None)
        return json.dumps({'type': self.ready})

    async def send(self, data):
        self.sent.append(data)
        if data == "finalize":
            await self.close()
        if isinstance(data, bytes):
            self.pcm_count += 1
            if self.pcm_count in (4, 12):
                start = 0.0 if self.pcm_count == 4 else (0.4 if self.order else -0.1)
                end = 0.3 if self.pcm_count == 4 else 0.8
                await self.messages.put(json.dumps({'text': 'blue bird', 'start': start, 'end': end}))

    def __aiter__(self):
        return self

    async def __anext__(self):
        item = await self.messages.get()
        if item is None:
            raise StopAsyncIteration
        return item

    async def close(self):
        self.open = False
        await self.messages.put(None)

    @asynccontextmanager
    async def connect(self, url, **_kwargs):
        self.url = url
        try:
            yield self
        finally:
            await self.close()


@pytest.mark.asyncio
async def test_stream_uses_real_ready_pcm_finalize_protocol(monkeypatch, fast_clock):
    transport = WebSocketTransport()
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    _, pcm = probe.load_corpus()
    result = await probe.stream_check(streaming, 'http://gateway/parakeet', pcm, idle_seconds=35)
    assert transport.url == 'ws://gateway/parakeet/v3/stream?sample_rate=16000'
    assert b''.join(item for item in transport.sent if isinstance(item, bytes)) == pcm
    assert transport.sent[-1] == 'finalize'
    assert all(isinstance(item, bytes) for item in transport.sent[:-1])
    assert result['text'] == 'blue bird blue bird'
    assert result['http_status'] == 101 and result['close_code'] == 1000
    assert result['idle_seconds'] == 35 and result['segments'] == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('kwargs', [{'ready': 'wrong'}, {'order': False}, {'close_code': 1011}])
async def test_stream_rejects_invalid_protocol_order_or_close(monkeypatch, fast_clock, kwargs):
    transport = WebSocketTransport(**kwargs)
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    _, pcm = probe.load_corpus()
    with pytest.raises((ValueError, streaming.ParakeetConnectionError)):
        await probe.stream_check(streaming, 'http://legacy', pcm)
    assert not transport.open


@pytest.mark.asyncio
async def test_admission_refusal_is_json_outcome_not_crash(monkeypatch, fast_clock, capsys):
    transport = WebSocketTransport(refusal='capacity_full')
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    ok = await probe.receipt('v3', lambda: probe.stream_check(streaming, 'http://legacy', b'\0\0'), 1, {})
    receipt = json.loads(capsys.readouterr().out)
    assert not ok
    assert receipt['outcome'] == 'refused' and receipt['reason'] == 'capacity_full'
    assert receipt['first_words'] == '' and receipt['latency_ms'] >= 0
    assert transport.sent == []


@pytest.mark.asyncio
async def test_deadline_is_failure_receipt_and_cancels_work(capsys):
    cancelled = asyncio.Event()

    async def hung():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    assert not await probe.receipt('timeout', hung, 0.001, {})
    assert cancelled.is_set()
    receipt = json.loads(capsys.readouterr().out)
    assert receipt['outcome'] == 'fail' and receipt['reason'] == 'TimeoutError'


@pytest.mark.asyncio
async def test_window_uses_existing_live_window_transport(monkeypatch):
    def answer(request):
        assert request.url == 'http://gateway/parakeet/v1/transcribe'
        assert request.headers['X-Omi-STT-Surface'] == 'live-window'
        assert 0 < float(request.headers['X-Omi-STT-Timeout-Seconds']) <= 8
        assert b'filename="audio.wav"' in request.content and b'RIFF' in request.content
        return httpx.Response(200, json={'text': 'blue bird', 'segments': []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        monkeypatch.setattr(window, 'get_stt_client', lambda: client)
        monkeypatch.setattr(window, 'get_stt_semaphore', lambda: asyncio.Semaphore(1))
        _, pcm = probe.load_corpus()
        result = await probe.window_check(window.WindowedParakeetSocket, 'http://gateway/parakeet', pcm)
    assert result == {'http_status': 200, 'text': 'blue bird'}


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [200, 201, 404, 503])
async def test_prerecorded_uses_v2_and_never_hides_refusal_or_fallback(monkeypatch, status):
    calls = []
    original_client = httpx.Client

    def answer(request):
        calls.append(request)
        assert request.url == 'http://gateway/parakeet/v2/transcribe'
        assert b'name="diarize"' in request.content and b'filename="audio.wav"' in request.content
        return httpx.Response(
            status, headers={'X-Omi-STT-Error': 'capacity_full'}, json={'text': 'blue bird', 'segments': []}
        )

    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://gateway/parakeet')
    monkeypatch.setenv('PARAKEET_USE_V2', '1')
    monkeypatch.setattr(
        pre_recorded.httpx, 'Client', lambda **kwargs: original_client(transport=httpx.MockTransport(answer), **kwargs)
    )
    wav, _ = probe.load_corpus()
    if status == 200:
        assert (await probe.prerecorded_check(pre_recorded, wav, 1))['text'] == 'blue bird'
    else:
        with pytest.raises(RuntimeError) as error:
            await probe.prerecorded_check(pre_recorded, wav, 1)
        assert probe.refusal_reason(error.value) == ('capacity_full' if status == 503 else None)
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("refused", [False, True])
async def test_qualification_runs_parallel_streams_then_idle_and_reconnect(monkeypatch, capsys, refused):
    # The CLI owns env in its dedicated process. Tests must restore that state
    # and avoid closing another test's shared HTTP client singletons.
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://before-qualification')
    monkeypatch.setenv('PARAKEET_USE_V2', '0')
    closed = AsyncMock()
    monkeypatch.setattr('utils.http_client.close_all_clients', closed)
    active = peak = 0
    starts = []
    client = object()
    monkeypatch.setattr(probe, 'load_clients', lambda: (client, client, client))

    async def post(*_args):
        return {'http_status': 200, 'text': 'blue bird'}

    async def stream(_client, _base, _pcm, idle_seconds=0):
        nonlocal active, peak
        starts.append(idle_seconds)
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        active -= 1
        if refused:
            raise streaming.ParakeetConnectionError('capacity_full')
        return {'http_status': 101, 'text': 'blue bird'}

    monkeypatch.setattr(probe, 'window_check', post)
    monkeypatch.setattr(probe, 'prerecorded_check', post)
    monkeypatch.setattr(probe, 'stream_check', stream)
    args = SimpleNamespace(base='http://gateway/parakeet', concurrency=4, timeout=1, idle_seconds=35)
    assert await probe.qualify(args) == (1 if refused else 0)
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(rows) == 8
    assert all(row['outcome'] == ('refused' if refused else 'pass') for row in rows[2:])
    assert peak == 4 and starts == [0, 0, 0, 0, 35, 0]
    closed.assert_awaited_once()


def test_corpus_and_cli_are_bounded_and_image_module_layout_is_supported():
    wav, pcm = probe.load_corpus()
    assert 0 < len(wav) <= 200_000
    with wave.open(io.BytesIO(wav)) as audio:
        assert audio.getnframes() > 16000 * 3
    assert any(pcm)
    args = probe.arguments(['--base', 'http://gateway/parakeet'])
    assert args.concurrency == 4 and args.timeout == 120 and args.idle_seconds == 35
    for argv in (
        ['--base', 'http://api.omi.me'],
        ['--base', 'http://gateway', '--concurrency', '9'],
        ['--base', 'http://gateway', '--timeout', 'nan'],
    ):
        with pytest.raises(SystemExit):
            probe.arguments(argv)


@pytest.mark.asyncio
@pytest.mark.parametrize('status,text,reason', [(200, '', None), (503, '', 'queue_timeout')])
async def test_window_empty_speech_and_admission_fail_the_gate(monkeypatch, status, text, reason):
    def answer(_request):
        return httpx.Response(status, headers={'X-Omi-STT-Error': reason or ''}, json={'text': text, 'segments': []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(answer)) as client:
        monkeypatch.setattr(window, 'get_stt_client', lambda: client)
        monkeypatch.setattr(window, 'get_stt_semaphore', lambda: asyncio.Semaphore(1))
        _, pcm = probe.load_corpus()
        with pytest.raises((probe.QualificationFailure, httpx.HTTPStatusError)) as error:
            await probe.window_check(window.WindowedParakeetSocket, 'http://gateway/parakeet', pcm)
        assert probe.refusal_reason(error.value) == reason


@pytest.mark.asyncio
async def test_realistic_rnnt_suffix_spans_and_zero_start_offset(monkeypatch, fast_clock):
    class RNNTTransport(WebSocketTransport):
        async def send(self, data):
            self.sent.append(data)
            if data == 'finalize':
                # flush emits the remaining hypothesis with the utterance span.
                await self.messages.put(json.dumps({'text': 'route.', 'start': 3.0, 'end': 6.0}))
                await self.close()
            elif isinstance(data, bytes):
                self.pcm_count += 1
                if self.pcm_count == 30:
                    # _speech_start_s == 0.0 falls through to _stream_offset_s;
                    # _build_segments then adds pending_audio duration again.
                    await self.messages.put(json.dumps({'text': 'The blue bird', 'start': 3.0, 'end': 6.0}))
                if self.pcm_count == 40:
                    # Suffix of a cumulative RNNT hypothesis, same span.
                    await self.messages.put(json.dumps({'text': 'sings. We test the audio', 'start': 3.0, 'end': 6.0}))

    transport = RNNTTransport()
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    _, pcm = probe.load_corpus()
    result = await probe.stream_check(streaming, 'http://legacy', pcm)
    assert result['segments'] == 3 and result['close_code'] == 1000
    assert result['text'] == 'The blue bird sings. We test the audio route.'
    assert result['first_text_ms'] >= 0
    assert result['overlap_against_previous_end'] == 2
    assert result['end_past_bytes_sent'] == 3
    assert result['is_connection_dead'] is False
    # The production consumer accepts/merges these overlapping utterance spans.
    from models.transcript_segment import TranscriptSegment

    merged = TranscriptSegment.combine_segments(
        [],
        [
            TranscriptSegment(text=text, start=3.0, end=6.0, is_user=False)
            for text in ('The blue bird', 'sings. We test the audio', 'route.')
        ],
    )
    assert len(merged.segments) == 1
    assert merged.segments[0].text == result['text']


@pytest.mark.asyncio
async def test_stream_failure_receipt_has_bounded_spans_and_no_text(monkeypatch, fast_clock, capsys):
    transport = WebSocketTransport(order=False)
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    _, pcm = probe.load_corpus()
    assert not await probe.receipt('v3', lambda: probe.stream_check(streaming, 'http://legacy', pcm), 5, {})
    result = json.loads(capsys.readouterr().out)
    assert result['reason'].startswith('bad start/end')
    assert result['segment_spans'] == [{'start': 0.0, 'end': 0.3}, {'start': -0.1, 'end': 0.8}]
    assert result['is_connection_dead'] is False
    assert result['first_words'] == '' and 'blue bird' not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'start,end,text,reason',
    [
        (float('nan'), 1, 'speech', 'bad start/end'),
        (2, 1, 'speech', 'bad start/end'),
        (0, 1, '   ', 'empty text'),
    ],
)
async def test_bad_segments_report_specific_private_diagnostics(
    monkeypatch, fast_clock, capsys, start, end, text, reason
):
    class BadTransport(WebSocketTransport):
        async def send(self, data):
            self.sent.append(data)
            if data == 'finalize':
                await self.close()
            elif isinstance(data, bytes) and len(self.sent) == 1:
                for _ in range(7):
                    await self.messages.put(json.dumps({'start': start, 'end': end, 'text': text}))
                # Signal speech too, so invalid whitespace is diagnosed promptly.
                await self.messages.put(json.dumps({'start': 0, 'end': 1, 'text': 'speech'}))

    transport = BadTransport()
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    _, pcm = probe.load_corpus()
    assert not await probe.receipt('v3', lambda: probe.stream_check(streaming, 'http://legacy', pcm), 5, {})
    result = json.loads(capsys.readouterr().out)
    assert result['reason'].startswith(reason)
    assert len(result['segment_spans']) == 5
    assert all(set(span) == {'start', 'end'} for span in result['segment_spans'])
    assert result['first_words'] == '' and 'speech' not in json.dumps(result)


@pytest.mark.asyncio
async def test_stream_dead_connection_names_condition(monkeypatch, fast_clock, capsys):
    class DeadTransport(WebSocketTransport):
        async def send(self, data):
            if isinstance(data, bytes):
                await self.close()

    transport = DeadTransport()
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    _, pcm = probe.load_corpus()
    assert not await probe.receipt('v3', lambda: probe.stream_check(streaming, 'http://legacy', pcm), 5, {})
    result = json.loads(capsys.readouterr().out)
    assert 'connection dead' in result['reason']
    assert result['is_connection_dead'] is True
    assert result['first_words'] == ''


@pytest.mark.asyncio
async def test_stream_timeout_retains_diagnostics(monkeypatch, capsys):
    transport = WebSocketTransport()
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    _, pcm = probe.load_corpus()
    assert not await probe.receipt('v3', lambda: probe.stream_check(streaming, 'http://legacy', pcm), 0.01, {})
    result = json.loads(capsys.readouterr().out)
    assert result['reason'] == 'stream timeout before qualification completed'
    assert result['segment_spans'] == [] and result['is_connection_dead'] is False
    assert not transport.open


@pytest.mark.asyncio
@pytest.mark.parametrize('close_code', [1000, 1001, 1005, 1006])
async def test_clean_or_finalized_legacy_finish_codes(monkeypatch, fast_clock, close_code):
    transport = WebSocketTransport(close_code=close_code)
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    _, pcm = probe.load_corpus()
    result = await probe.stream_check(streaming, 'http://legacy', pcm)
    assert result['close_code'] == close_code and result['close_reason'] == ''
    assert result['finalize_sent'] is True
    assert result['close_kind'] == ('server_dropped_after_finalize' if close_code == 1006 else 'normal')
    assert result['sender_task'] == result['receiver_task'] == {'state': 'completed'}


@pytest.mark.asyncio
@pytest.mark.parametrize('close_code', [1011])
async def test_abnormal_close_receipt_even_when_drain_suppresses_receive_error(
    monkeypatch, fast_clock, capsys, close_code
):
    transport = WebSocketTransport(close_code=close_code)
    transport.close_reason = 'server failure'
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    _, pcm = probe.load_corpus()
    assert not await probe.receipt('v3', lambda: probe.stream_check(streaming, 'http://legacy', pcm), 5, {})
    result = json.loads(capsys.readouterr().out)
    assert result['close_code'] == close_code and result['close_reason'] == 'server failure'
    assert 'abnormal' in result['reason'] and result['first_words'] == ''
    assert result['sender_task']['state'] == result['receiver_task']['state'] == 'completed'


@pytest.mark.asyncio
async def test_actual_main_handler_flushes_before_transport_finish(monkeypatch, fast_clock):
    # Execute the actual handler alone with fake inference/admission. Avoid GPU
    # imports; preserve its control flow rather than invent a finalize ACK.
    import ast
    import logging
    from pathlib import Path
    from typing import Any, cast
    from starlette.websockets import WebSocketDisconnect
    from unittest.mock import MagicMock

    source = Path(__file__).parents[2] / 'parakeet' / 'main.py'
    handler = next(
        n
        for n in ast.parse(source.read_text()).body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == 'stream_transcribe'
    )
    handler.decorator_list = []
    namespace = {
        'asyncio': asyncio,
        'time': probe.time,
        'Query': lambda value: value,
        'cast': cast,
        'Any': Any,
        'List': list,
        'WebSocketDisconnect': WebSocketDisconnect,
        'gpu_worker': None,
        'logger': logging.getLogger('fake_parakeet_server'),
        '_WS_RECEIVE_TIMEOUT': 30,
    }
    for metric in ('REQUESTS_TOTAL', 'ACTIVE_STREAMS', 'STREAM_DURATION'):
        namespace[metric] = MagicMock()
    lease = SimpleNamespace(release=MagicMock())
    namespace['stream_admission'] = SimpleNamespace(try_acquire=lambda: SimpleNamespace(lease=lease))
    session = SimpleNamespace(
        feed=AsyncMock(return_value=[{'text': 'blue bird', 'start': 0, 'end': 0.1}]),
        flush=AsyncMock(return_value=[{'text': 'sings', 'start': 0, 'end': 0.1}]),
        cleanup=MagicMock(),
    )
    namespace['StreamSession'] = lambda **kwargs: session
    exec(
        compile(
            ast.fix_missing_locations(
                ast.Module(
                    body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), handler],
                    type_ignores=[],
                )
            ),
            str(source),
            'exec',
        ),
        namespace,
    )

    class MainTransport(WebSocketTransport):
        def __init__(self):
            super().__init__()
            self.inbound = asyncio.Queue()
            self.app_close = AsyncMock(side_effect=self.server_close)

        async def send(self, data):
            self.sent.append(data)
            await self.inbound.put({'bytes': data} if isinstance(data, bytes) else {'text': data})

        @asynccontextmanager
        async def connect(self, url, **kwargs):
            websocket = SimpleNamespace(
                accept=AsyncMock(), receive=self.inbound.get, send_json=self.emit, close=self.app_close
            )

            async def server():
                await namespace['stream_transcribe'](websocket, 16000, None, None)
                # Served ASGI transport drops TCP after handler return, without
                # a close frame: production receipts report synthetic 1006.
                if self.open:
                    self.close_code = 1006
                    await self.close()

            server_task = asyncio.create_task(server())
            try:
                yield self
            finally:
                await self.close()
                await server_task

        async def server_close(self, code):
            self.close_code = code
            await self.close()

        async def recv(self):
            return await self.messages.get()

        async def emit(self, message):
            await self.messages.put(json.dumps(message))

    transport = MainTransport()
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    result = await probe.stream_check(streaming, 'http://legacy', b'\0\0' * 1600)
    assert result['finalize_sent'] is True
    if transport.app_close.await_count:
        transport.app_close.assert_awaited_once_with(code=1000)
        assert result['close_code'] == 1000 and result['close_kind'] == 'normal'
    else:
        assert result['close_code'] == 1006 and result['close_kind'] == 'server_dropped_after_finalize'
    assert result['text'] == 'blue bird sings'
    assert transport.sent[-1] == 'finalize'
    session.flush.assert_awaited_once()
    session.cleanup.assert_called_once()
    lease.release.assert_called_once()


@pytest.mark.asyncio
async def test_bounded_production_cleanup_cancellation_is_reported(monkeypatch, fast_clock):
    original_wait = asyncio.wait_for

    async def short_wait(awaitable, timeout):
        return await original_wait(awaitable, 0.01 if timeout == 10 else timeout)

    monkeypatch.setattr(asyncio, 'wait_for', short_wait)

    class ClientClosesTransport(WebSocketTransport):
        async def send(self, data):
            if data == 'finalize':
                self.sent.append(data)  # main.py flushes/returns, no app close.
            else:
                await super().send(data)

    transport = ClientClosesTransport()
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    _, pcm = probe.load_corpus()
    result = await probe.stream_check(streaming, 'http://legacy', pcm)
    assert result['close_code'] == 1000
    assert result['receiver_task']['state'] == 'cancelled'
    assert result['sender_task']['state'] in {'completed', 'cancelled'}
    assert not transport.open


@pytest.mark.asyncio
async def test_task_state_reports_error_type_without_payload():
    async def fail():
        raise RuntimeError('private exception payload')

    task = asyncio.create_task(fail())
    await asyncio.gather(task, return_exceptions=True)
    assert probe.task_state(task) == {'state': 'error', 'exception_type': 'RuntimeError'}


@pytest.mark.asyncio
async def test_1006_before_finalize_fails_even_after_speech(monkeypatch, fast_clock, capsys):
    class EarlyDrop(WebSocketTransport):
        async def send(self, data):
            await super().send(data)
            if self.pcm_count == 4:
                await self.close()

    transport = EarlyDrop(close_code=1006)
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    _, pcm = probe.load_corpus()
    assert not await probe.receipt('v3', lambda: probe.stream_check(streaming, 'http://legacy', pcm), 5, {})
    result = json.loads(capsys.readouterr().out)
    assert result['close_code'] == 1006 and result['finalize_sent'] is False
    assert result['outcome'] == 'fail' and result['first_words'] == ''
    assert 'finalize' not in transport.sent


@pytest.mark.asyncio
async def test_no_speech_fails_without_sending_finalize(monkeypatch, fast_clock, capsys):
    original_wait = asyncio.wait_for

    async def short_wait(awaitable, timeout):
        return await original_wait(awaitable, 0.01 if timeout == 15 else timeout)

    monkeypatch.setattr(asyncio, 'wait_for', short_wait)

    class SilentTransport(WebSocketTransport):
        async def send(self, data):
            self.sent.append(data)

    transport = SilentTransport(close_code=1006)
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    _, pcm = probe.load_corpus()
    assert not await probe.receipt('v3', lambda: probe.stream_check(streaming, 'http://legacy', pcm), 5, {})
    result = json.loads(capsys.readouterr().out)
    assert result['reason'] == 'empty text before finalize'
    assert result['finalize_sent'] is False and 'finalize' not in transport.sent


@pytest.mark.asyncio
async def test_1006_with_task_error_fails(monkeypatch, fast_clock, capsys):
    original_drain = streaming.ParakeetWebSocketSocket.drain_and_close

    async def broken_drain(socket):
        await original_drain(socket)

        async def fail():
            raise RuntimeError('private error payload')

        socket._receiver_task = asyncio.create_task(fail())
        await asyncio.gather(socket._receiver_task, return_exceptions=True)

    monkeypatch.setattr(streaming.ParakeetWebSocketSocket, 'drain_and_close', broken_drain)
    transport = WebSocketTransport(close_code=1006)
    monkeypatch.setattr(streaming.websockets, 'connect', transport.connect)
    _, pcm = probe.load_corpus()
    assert not await probe.receipt('v3', lambda: probe.stream_check(streaming, 'http://legacy', pcm), 5, {})
    result = json.loads(capsys.readouterr().out)
    assert result['reason'] == 'stream finalization left receiver task error'
    assert result['finalize_sent'] is True
    assert result['first_words'] == '' and 'private error payload' not in json.dumps(result)
