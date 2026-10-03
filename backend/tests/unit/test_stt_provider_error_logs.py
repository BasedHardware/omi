"""Provider error logs must not echo raw provider or user payload text.

Provider error bodies, close frames, and exception strings can carry account
details, signed URLs, file paths, or transcript text. ``sanitize_provider_error``
emits only a bounded numeric code and a canonical diagnostic phrase, so log
severity and typed death classification stay intact while the payload never
reaches a log line. These tests cover Omi-owned logging only; the Deepgram
SDK's own private loggers are out of scope.
"""

import asyncio
import io
import json
import logging
import wave
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from utils.stt import parakeet_window, pre_recorded, provider_resilience, soniox, speaker_embedding, streaming, vad
from utils.stt.safe_socket import SafeDeepgramSocket
from utils.stt.streaming import MODULATE_DEATH_SERVE_ERROR, ParakeetConnectionError, SafeModulateSocket
from utils.stt.stream_close import PROVIDER_BUDGET_EXHAUSTED

SENTINEL = 'quixotictranscriptzebra'
SENTINEL_EMAIL = 'victim@sentinel-domain.example'
SENTINEL_URL = 'https://signed.example.invalid/audio.wav?sig=abcdef123456'


def _caplog_text(caplog) -> str:
    return '\n'.join(record.getMessage() for record in caplog.records)


class FakeWebSocket:
    def __init__(self, inbound):
        self._inbound = list(inbound)
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    async def close(self):
        pass

    def __aiter__(self):
        async def gen():
            for msg in self._inbound:
                yield json.dumps(msg)

        return gen()


async def _drive(sock_cls, frames):
    ws = FakeWebSocket(frames)
    sock = sock_cls(ws, lambda _segs: None, asyncio.get_running_loop())
    await asyncio.wait_for(sock._done_event.wait(), timeout=1)
    await sock.drain_and_close()
    return sock


def _wav_bytes(seconds: float, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b'\x00\x00' * int(sample_rate * seconds))
    return buf.getvalue()


@pytest.mark.asyncio
async def test_soniox_budget_error_logs_severity_and_code_without_payload(caplog):
    frame = {'error_code': 402, 'error_type': 'organization_balance_exhausted', 'error_message': SENTINEL}
    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        sock = await _drive(soniox.SafeSonioxSocket, [frame])
    assert sock.is_connection_dead
    assert sock.typed_death_reason == PROVIDER_BUDGET_EXHAUSTED
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and 'Soniox streaming error:' in r.getMessage()]
    assert errors
    assert 'code=402' in errors[0].getMessage()
    assert 'organization_balance_exhausted' in errors[0].getMessage()
    assert SENTINEL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_soniox_warning_path_redacts_payload(caplog):
    frame = {'error_code': 400, 'error_type': 'invalid_request', 'error_message': f'No audio received {SENTINEL}'}
    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        await _drive(soniox.SafeSonioxSocket, [frame])
    warnings = [r for r in caplog.records if 'Soniox stream closed:' in r.getMessage()]
    assert warnings
    assert 'code=400' in warnings[0].getMessage()
    assert 'no audio received' in warnings[0].getMessage()
    assert SENTINEL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_soniox_arbitrary_error_type_stays_typed_and_bounded(caplog):
    frame = {
        'error_code': 500,
        'error_type': f'unexpected_vendor_shape {SENTINEL}',
        'error_message': f'{SENTINEL_EMAIL} {SENTINEL_URL}',
    }
    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        sock = await _drive(soniox.SafeSonioxSocket, [frame])
    assert sock.typed_death_reason == 'connection_lost'
    warnings = [r for r in caplog.records if 'Soniox stream closed:' in r.getMessage()]
    assert warnings
    assert 'code=500' in warnings[0].getMessage()
    assert '[redacted]' in warnings[0].getMessage()
    assert SENTINEL not in _caplog_text(caplog)
    assert SENTINEL_EMAIL not in _caplog_text(caplog)
    assert SENTINEL_URL not in _caplog_text(caplog)


def test_soniox_persistent_rate_limit_log_redacts_payload(monkeypatch, caplog):
    monkeypatch.setattr(soniox, '_last_rate_limit_error_log', 0.0)
    monkeypatch.setattr(soniox, '_rate_limit_events', [])
    with caplog.at_level(logging.WARNING, logger='utils.stt.soniox'):
        soniox._rate_limit_persistent_error(f'429 limit_exceeded {SENTINEL} {SENTINEL_URL}', force=True)
    errors = [r for r in caplog.records if 'rate limiting persists' in r.getMessage()]
    assert errors
    assert 'code=429' in errors[0].getMessage()
    assert 'limit_exceeded' in errors[0].getMessage()
    assert SENTINEL not in _caplog_text(caplog)
    assert SENTINEL_URL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_modulate_serve_error_logs_severity_and_code_without_payload(caplog):
    frame = {'type': 'error', 'error': f'Internal server error {SENTINEL} {SENTINEL_EMAIL}'}
    with caplog.at_level(logging.WARNING, logger='utils.stt.streaming'):
        sock = await _drive(SafeModulateSocket, [frame])
    assert sock.is_connection_dead
    assert sock.typed_death_reason == MODULATE_DEATH_SERVE_ERROR
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and 'Modulate streaming error:' in r.getMessage()]
    assert errors
    assert 'internal server error' in errors[0].getMessage()
    assert SENTINEL not in _caplog_text(caplog)
    assert SENTINEL_EMAIL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_modulate_session_frame_logs_warning_without_payload(caplog):
    frame = {'type': 'error', 'error': f'Invalid input audio {SENTINEL}'}
    with caplog.at_level(logging.WARNING, logger='utils.stt.streaming'):
        await _drive(SafeModulateSocket, [frame])
    warnings = [r for r in caplog.records if 'Modulate stream closed:' in r.getMessage()]
    assert warnings
    assert 'invalid input audio' in warnings[0].getMessage()
    assert SENTINEL not in _caplog_text(caplog)


def test_safe_deepgram_send_exception_redacts_payload(caplog):
    conn = MagicMock()
    conn.send.side_effect = RuntimeError(f'send failed {SENTINEL} {SENTINEL_URL}')
    sock = SafeDeepgramSocket(conn)
    try:
        with caplog.at_level(logging.WARNING, logger='utils.stt.safe_socket'):
            assert sock.send(b'\x00' * 960) is False
        warnings = [r for r in caplog.records if 'DG send exception' in r.getMessage()]
        assert warnings
        assert SENTINEL not in _caplog_text(caplog)
        assert SENTINEL_URL not in _caplog_text(caplog)
    finally:
        sock.finish()


def test_safe_deepgram_finalize_exception_redacts_payload(caplog):
    conn = MagicMock()
    conn.finalize.side_effect = RuntimeError(f'finalize failed {SENTINEL}')
    sock = SafeDeepgramSocket(conn)
    try:
        with caplog.at_level(logging.WARNING, logger='utils.stt.safe_socket'):
            with pytest.raises(RuntimeError):
                sock.finalize()
        warnings = [r for r in caplog.records if 'DG finalize exception' in r.getMessage()]
        assert warnings
        assert SENTINEL not in _caplog_text(caplog)
    finally:
        sock.finish()


@pytest.mark.asyncio
async def test_deepgram_owned_callbacks_log_safely_and_latch_close(caplog):
    mock_dg_conn = MagicMock()
    captured_on_error = {}

    async def fake_connect(on_message, on_error, *args, **kwargs):
        captured_on_error['handler'] = on_error
        return mock_dg_conn

    with (
        patch.object(streaming, 'connect_to_deepgram_with_backoff', new=AsyncMock(side_effect=fake_connect)),
        caplog.at_level(logging.INFO, logger='utils.stt.streaming'),
    ):
        safe = await streaming.process_audio_dg(
            stream_transcript=MagicMock(), language='en', sample_rate=16000, channels=1
        )
        try:
            captured_on_error['handler'](None, f'ErrorResponse {SENTINEL}')
            registered = {call[0][0]: call[0][1] for call in mock_dg_conn.on.call_args_list}
            close_handler = registered[streaming.LiveTranscriptionEvents.Close]
            error_handler = registered[streaming.LiveTranscriptionEvents.Error]
            close_handler(None, f'CloseResponse {SENTINEL} {SENTINEL_URL}')
            assert safe.is_connection_dead
            error_handler(None, f'ErrorResponse {SENTINEL_EMAIL}')
        finally:
            safe.finish()
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and r.getMessage().startswith('Deepgram error:')]
    assert errors
    warnings = [r for r in caplog.records if 'close-reason capture' in r.getMessage()]
    assert warnings
    infos = [r for r in caplog.records if 'Deepgram connection closed:' in r.getMessage()]
    assert infos
    text = _caplog_text(caplog)
    assert SENTINEL not in text
    assert SENTINEL_EMAIL not in text
    assert SENTINEL_URL not in text


@pytest.mark.asyncio
async def test_parakeet_transcribe_failure_redacts_payload(monkeypatch, caplog):
    class FailingClient:
        async def post(self, url, **kwargs):
            raise RuntimeError(f'provider replied {SENTINEL} {SENTINEL_EMAIL}\nstack {SENTINEL_URL}')

    @asynccontextmanager
    async def semaphore():
        yield

    monkeypatch.setattr(streaming, 'get_stt_client', lambda: FailingClient())
    monkeypatch.setattr(streaming, 'get_stt_semaphore', semaphore)
    sock = streaming.ParakeetStreamingSocket(lambda _segs: None, 'http://fake', 16000)
    with caplog.at_level(logging.WARNING, logger='utils.stt.streaming'):
        assert await sock._transcribe_chunk(b'\x00\x00' * 1600, 0.0, 0.1) == []
    errors = [r for r in caplog.records if 'Parakeet transcribe failed' in r.getMessage()]
    assert errors
    assert SENTINEL not in _caplog_text(caplog)
    assert SENTINEL_EMAIL not in _caplog_text(caplog)
    assert SENTINEL_URL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_parakeet_ws_start_failure_redacts_dead_reason(monkeypatch, caplog):
    sock = streaming.ParakeetWebSocketSocket(lambda _segs: None, 'ws://fake.invalid', 16000)
    sock._mark_dead(f'parakeet ws failed: {SENTINEL}')

    async def stub_run():
        sock._startup_event.set()

    monkeypatch.setattr(sock, '_run', stub_run)
    with caplog.at_level(logging.WARNING, logger='utils.stt.streaming'):
        with pytest.raises(ParakeetConnectionError):
            await sock.start()
    errors = [r for r in caplog.records if 'Parakeet WS failed before connection' in r.getMessage()]
    assert errors
    assert SENTINEL not in _caplog_text(caplog)
    await asyncio.gather(sock._sender_task, return_exceptions=True)


def test_parakeet_batch_diarization_failure_redacts_payload(monkeypatch, caplog):
    def boom(_wav):
        raise RuntimeError(f'embedding service: {SENTINEL}')

    monkeypatch.setattr(pre_recorded, 'extract_embedding_from_bytes', boom)
    with caplog.at_level(logging.WARNING, logger='utils.stt.pre_recorded'):
        assert pre_recorded._parakeet_assign_speaker_sync(_wav_bytes(1.0), 16000, 0.0, 1.0, [], []) == 'SPEAKER_00'
    warnings = [r for r in caplog.records if 'batch diarization failed' in r.getMessage()]
    assert warnings
    assert SENTINEL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_embedding_failure_redacts_payload(monkeypatch, caplog):
    class FailingClient:
        async def post(self, url, **kwargs):
            raise RuntimeError(f'embedding endpoint: {SENTINEL} {SENTINEL_URL}')

    monkeypatch.setenv('HOSTED_SPEAKER_EMBEDDING_API_URL', 'http://embedding.invalid')
    monkeypatch.setattr(speaker_embedding, 'get_stt_client', lambda: FailingClient())
    with caplog.at_level(logging.WARNING, logger='utils.stt.speaker_embedding'):
        with pytest.raises(RuntimeError):
            await speaker_embedding.async_extract_embedding_from_bytes(_wav_bytes(0.7))
    errors = [r for r in caplog.records if 'async_extract_embedding_from_bytes failed' in r.getMessage()]
    assert errors
    assert SENTINEL not in _caplog_text(caplog)
    assert SENTINEL_URL not in _caplog_text(caplog)


def test_vad_decode_failure_drops_path_and_payload(monkeypatch, caplog, tmp_path):
    secret_path = tmp_path / f'{SENTINEL}.wav'
    secret_path.write_bytes(b'not-audio')

    def boom(_path):
        raise RuntimeError(f'decode failed {SENTINEL}')

    monkeypatch.setattr(vad.AudioSegment, 'from_file', boom)
    with caplog.at_level(logging.WARNING, logger='utils.stt.vad'):
        assert vad._run_file_vad(str(secret_path)) == []
    errors = [r for r in caplog.records if 'Failed to read audio file' in r.getMessage()]
    assert errors
    assert SENTINEL not in _caplog_text(caplog)


@pytest.mark.asyncio
async def test_parakeet_window_post_failure_stays_bounded_without_body(monkeypatch, caplog):
    monkeypatch.setattr(
        streaming,
        '_parakeet_circuit',
        provider_resilience.ProviderCircuitBreaker(failure_threshold=1, cooldown_seconds=30),
    )

    class BodyClient:
        async def post(self, url, **kwargs):
            return httpx.Response(500, text=f'upstream exploded {SENTINEL}', request=httpx.Request('POST', url))

    @asynccontextmanager
    async def semaphore():
        yield

    monkeypatch.setattr(parakeet_window, 'get_stt_client', lambda: BodyClient())
    monkeypatch.setattr(parakeet_window, 'get_stt_semaphore', semaphore)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://fake')
    sock = parakeet_window.WindowedParakeetSocket(lambda _segs: None, 'http://fake', 16000, lambda: None)
    sock.start()
    with caplog.at_level(logging.WARNING, logger='utils.stt.parakeet_window'):
        with pytest.raises(Exception):
            await sock._post_and_parse(b'\x01\x00' * 16000, 1.0)
    assert sock._dead_reason == 'provider_5xx'
    assert SENTINEL not in _caplog_text(caplog)
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)


@pytest.mark.asyncio
async def test_parakeet_window_invalid_body_logs_no_payload(monkeypatch, caplog):
    class BadJsonClient:
        async def post(self, url, **kwargs):
            return httpx.Response(200, text=SENTINEL, request=httpx.Request('POST', url))

    @asynccontextmanager
    async def semaphore():
        yield

    monkeypatch.setattr(parakeet_window, 'get_stt_client', lambda: BadJsonClient())
    monkeypatch.setattr(parakeet_window, 'get_stt_semaphore', semaphore)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://fake')
    sock = parakeet_window.WindowedParakeetSocket(lambda _segs: None, 'http://fake', 16000, lambda: None)
    sock.start()
    with caplog.at_level(logging.WARNING, logger='utils.stt.parakeet_window'):
        with pytest.raises(Exception):
            await sock._post_and_parse(b'\x01\x00' * 16000, 1.0)
    assert sock._dead_reason == 'provider_5xx'
    assert SENTINEL not in _caplog_text(caplog)
    sock.finish()
    await asyncio.gather(sock._pump_task, return_exceptions=True)
