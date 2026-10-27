"""Unit tests for the authed STT proxy (POST /v1/stt/transcribe).

The route fronts parakeet's `/v2/transcribe` with the standard Omi auth guard
plus per-UID rate limiting (issue #8854 step 1). These tests mount the real
router with the auth dependency overridden and the dedicated STT-proxy httpx
client replaced by a fake, and exercise: the auth requirement, the upstream
config guard, payload validation (including chunked bodies that carry no
Content-Length), filename sanitization, upstream slot exhaustion, response
passthrough, and upstream error mapping.
"""

import os

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import asyncio
import io
import wave
from unittest.mock import Mock, call

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import routers.stt as stt_router
from utils.stt import duration_probe
from utils.other import endpoints as auth
from utils.rate_limit_config import RATE_POLICIES
from utils.subscription import TranscriptionAllowance, TRANSCRIPTION_MODE_MANAGED, TRANSCRIPTION_MODE_ON_DEVICE

_PARAKEET_URL = 'http://parakeet.internal:8000'
_UID = 'test-uid'
_REAL_PROBE_AUDIO_SECONDS = stt_router._probe_audio_seconds


@pytest.fixture(autouse=True)
def metering(monkeypatch):
    # Every request exercises real route control flow without touching account
    # data or the production usage ledger. Media probing has its own WAV test.
    allowance = Mock(return_value=TranscriptionAllowance(TRANSCRIPTION_MODE_MANAGED, 100, 'plan_within_allowance'))
    record = Mock()

    async def probe(data):
        return 10

    monkeypatch.setattr(stt_router, '_probe_audio_seconds', probe)
    monkeypatch.setattr(stt_router, 'resolve_transcription_allowance', allowance)
    monkeypatch.setattr(stt_router, 'record_usage', record)
    return allowance, record


@pytest.mark.parametrize('remaining', [0, 9])
def test_exhausted_or_insufficient_allowance_never_calls_provider(monkeypatch, metering, remaining):
    allowance, record = metering
    allowance.return_value = TranscriptionAllowance(TRANSCRIPTION_MODE_MANAGED, remaining, 'plan_within_allowance')
    fake = _FakeSttClient()
    response = _upload(_make_client(monkeypatch, fake))
    assert response.status_code == 402
    assert fake.calls == []
    record.assert_not_called()


@pytest.mark.parametrize('reason', ['allowance_unavailable', 'usage_invalid'])
def test_unavailable_allowance_never_calls_provider(monkeypatch, metering, reason):
    allowance, record = metering
    allowance.return_value = TranscriptionAllowance(TRANSCRIPTION_MODE_ON_DEVICE, 0, reason)
    fake = _FakeSttClient()
    response = _upload(_make_client(monkeypatch, fake))
    assert response.status_code == 503
    assert fake.calls == []
    record.assert_not_called()


@pytest.mark.parametrize('remaining', [10, None])
def test_success_charges_media_duration_even_without_transcript(monkeypatch, metering, remaining):
    allowance, record = metering
    allowance.return_value = TranscriptionAllowance(TRANSCRIPTION_MODE_MANAGED, remaining, 'plan_within_allowance')
    fake = _FakeSttClient(response=_FakeResponse(json_data={'text': '', 'segments': []}))
    response = _upload(_make_client(monkeypatch, fake))
    assert response.status_code == 200
    record.assert_called_once_with(
        _UID,
        transcription_seconds=10,
        usage_metadata={'funding': 'omi', 'provider': 'parakeet', 'source': 'parakeet_proxy'},
    )
    assert allowance.call_args_list == [call(_UID, source=None, byok_active=False)] * 2


def test_provider_failure_does_not_record_success_usage(monkeypatch, metering):
    _, record = metering
    fake = _FakeSttClient(response=_FakeResponse(status_code=503))
    assert _upload(_make_client(monkeypatch, fake)).status_code == 503
    record.assert_not_called()


def test_duration_probe_uses_media_frames_and_rounds_up(monkeypatch):
    # Restore the production probe masked by the autouse route fixture.
    monkeypatch.undo()
    monkeypatch.setenv('PATH', '')  # CI has no ffprobe; the decoder must be self-contained.
    data = io.BytesIO()
    with wave.open(data, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b'\x00\x00' * 10000)
    assert duration_probe.audio_seconds(io.BytesIO(data.getvalue())) == 2


def test_duration_probe_rejects_unreadable_media(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setenv('PATH', '')
    with pytest.raises(HTTPException) as exc:
        duration_probe.audio_seconds(io.BytesIO(b'not audio'))
    assert exc.value.status_code == 400


@pytest.mark.parametrize('record_fails', [False, True])
def test_proxy_slot_is_held_through_usage_accounting_and_released(monkeypatch, record_fails, caplog):
    semaphore = asyncio.Semaphore(1)
    monkeypatch.setattr(stt_router, 'get_stt_proxy_semaphore', lambda: semaphore)

    def record(*args, **kwargs):
        assert semaphore.locked(), 'another admission must not reuse this slot before accounting finishes'
        if record_fails:
            raise RuntimeError('synthetic accounting failure')

    monkeypatch.setattr(stt_router, 'record_usage', record)
    fake = _FakeSttClient(response=_FakeResponse(json_data={'text': '', 'segments': []}))
    client = _make_client(monkeypatch, fake)
    assert _upload(client).status_code == 200
    if record_fails:
        assert 'usage write failed exception_type=RuntimeError' in caplog.text
        assert 'synthetic accounting failure' not in caplog.text
    assert not semaphore.locked()


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=''):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    def json(self):
        if self._json is None:
            raise ValueError('not json')
        return self._json


class _FakeSttClient:
    """Stands in for the shared httpx.AsyncClient from utils.http_client."""

    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.calls = []

    async def post(self, url, files=None, data=None):
        self.calls.append({'url': url, 'files': files, 'data': data})
        if self.exc is not None:
            raise self.exc
        return self.response


def _make_client(monkeypatch, fake_stt_client, authed=True) -> TestClient:
    app = FastAPI()
    app.include_router(stt_router.router)
    if authed:
        app.dependency_overrides[auth.get_current_user_uid] = lambda: _UID
    monkeypatch.setattr(stt_router, 'get_stt_proxy_client', lambda: fake_stt_client)
    # Rate limiting is fail-open on Redis errors, but skip it entirely so unit
    # tests never touch a Redis connection attempt.
    monkeypatch.setattr(auth, '_enforce_rate_limit', lambda *args, **kwargs: None)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', _PARAKEET_URL)
    return TestClient(app)


def _upload(client: TestClient, content=b'RIFF-fake-wav', filename='audio.wav', data=None):
    return client.post(
        '/v1/stt/transcribe',
        files={'file': (filename, content, 'audio/wav')},
        data=data or {},
    )


def _chunked_upload(client: TestClient, content: bytes):
    """Upload via a generator body — Transfer-Encoding: chunked, no
    Content-Length header, so only the bounded read can enforce the cap.
    """
    boundary = 'sttproxyboundary'
    body = (
        (
            f'--{boundary}\r\n'
            'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
            'Content-Type: audio/wav\r\n\r\n'
        ).encode()
        + content
        + f'\r\n--{boundary}--\r\n'.encode()
    )

    def gen():
        yield body

    return client.post(
        '/v1/stt/transcribe',
        content=gen(),
        headers={'content-type': f'multipart/form-data; boundary={boundary}'},
    )


# ---------------------------------------------------------------------------
# Auth and configuration guards
# ---------------------------------------------------------------------------
def test_policy_registered():
    # with_rate_limit raises at import time if the policy is missing; assert
    # explicitly so a policy rename fails with a readable message.
    assert 'stt:transcribe' in RATE_POLICIES


def test_requires_auth(monkeypatch):
    client = _make_client(monkeypatch, _FakeSttClient(), authed=False)
    response = _upload(client)
    assert response.status_code == 401


def test_503_when_parakeet_not_configured(monkeypatch):
    fake = _FakeSttClient()
    client = _make_client(monkeypatch, fake)
    monkeypatch.delenv('HOSTED_PARAKEET_API_URL')
    response = _upload(client)
    assert response.status_code == 503
    assert fake.calls == []


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------
def test_rejects_empty_file(monkeypatch):
    fake = _FakeSttClient()
    client = _make_client(monkeypatch, fake)
    response = _upload(client, content=b'')
    assert response.status_code == 400
    assert fake.calls == []


def test_rejects_oversized_body_via_content_length(monkeypatch):
    fake = _FakeSttClient()
    client = _make_client(monkeypatch, fake)
    monkeypatch.setattr(stt_router, '_MAX_UPLOAD_BYTES', 10)
    response = _upload(client, content=b'x' * 32)
    assert response.status_code == 413
    assert fake.calls == []


def test_rejects_oversized_chunked_body(monkeypatch):
    # No Content-Length header — starlette still populates file.size for
    # every multipart part, so the size pre-check rejects before any read.
    fake = _FakeSttClient()
    client = _make_client(monkeypatch, fake)
    monkeypatch.setattr(stt_router, '_MAX_UPLOAD_BYTES', 10)
    response = _chunked_upload(client, content=b'x' * 32)
    assert response.status_code == 413
    assert fake.calls == []


class _NoSizeUpload:
    """UploadFile stand-in whose size is unavailable — pins the bounded read
    as the defense-in-depth enforcement should a starlette upgrade ever stop
    populating multipart part sizes.
    """

    filename = 'audio.wav'
    content_type = 'audio/wav'
    size = None

    def __init__(self, payload: bytes):
        self._payload = payload
        self.read_sizes = []

    async def read(self, size=-1):
        self.read_sizes.append(size)
        if size is None or size < 0:
            return self._payload
        return self._payload[:size]


class _BareRequest:
    headers = {}


async def test_bounded_read_enforces_cap_when_size_unavailable(monkeypatch):
    fake = _FakeSttClient()
    monkeypatch.setattr(stt_router, 'get_stt_proxy_client', lambda: fake)
    monkeypatch.setattr(stt_router, '_MAX_UPLOAD_BYTES', 10)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', _PARAKEET_URL)

    upload = _NoSizeUpload(b'x' * 32)
    with pytest.raises(HTTPException) as exc_info:
        await stt_router.stt_transcribe(request=_BareRequest(), file=upload, diarize=True, uid=_UID)
    assert exc_info.value.status_code == 413
    assert upload.read_sizes == [11]  # cap + 1 — resident RAM never exceeds this
    assert fake.calls == []


def test_chunked_body_within_cap_succeeds(monkeypatch):
    fake = _FakeSttClient(response=_FakeResponse(json_data={'text': 'ok', 'segments': []}))
    client = _make_client(monkeypatch, fake)
    response = _chunked_upload(client, content=b'x' * 32)
    assert response.status_code == 200
    assert len(fake.calls[0]['files']['file'][1]) == 32


@pytest.mark.parametrize(
    'raw,expected',
    [
        ('../../etc/passwd', 'passwd'),
        ('..', 'audio.wav'),
        ('', 'audio.wav'),
        (None, 'audio.wav'),
        ('my clip (1).wav', 'my_clip__1_.wav'),
        ('recording.m4a', 'recording.m4a'),
        # Truncation preserves a short extension...
        ('a' * 100 + '.wav', 'a' * 60 + '.wav'),
        # ...but not an overlong one, and no-extension names truncate flat.
        ('b' * 70 + '.' + 'e' * 20, ('b' * 70 + '.' + 'e' * 20)[:64]),
        ('a' * 100, 'a' * 64),
    ],
)
def test_safe_upstream_filename(raw, expected):
    assert stt_router._safe_upstream_filename(raw) == expected


def test_filename_sanitized_before_forwarding(monkeypatch):
    fake = _FakeSttClient(response=_FakeResponse(json_data={'text': '', 'segments': []}))
    client = _make_client(monkeypatch, fake)
    response = _upload(client, filename='clip.wav')
    assert response.status_code == 200
    forwarded_name = fake.calls[0]['files']['file'][0]
    assert '/' not in forwarded_name
    assert not forwarded_name.startswith('.')
    assert len(forwarded_name) <= stt_router._MAX_FILENAME_LEN


# ---------------------------------------------------------------------------
# Proxy behavior
# ---------------------------------------------------------------------------
def test_success_passthrough(monkeypatch):
    body = {
        'text': 'hola mundo',
        'segments': [{'start': 0.0, 'end': 1.2, 'text': 'hola mundo', 'speaker': 'SPEAKER_00'}],
        'detected_language': 'es',
    }
    fake = _FakeSttClient(response=_FakeResponse(json_data=body))
    client = _make_client(monkeypatch, fake)
    response = _upload(client)
    assert response.status_code == 200
    assert response.json() == body
    call = fake.calls[0]
    assert call['url'] == f'{_PARAKEET_URL}/v2/transcribe'
    assert call['data'] == {'diarize': 'true'}


def test_upstream_request_time_is_attributed_to_app_proxy(monkeypatch):
    from prometheus_client import REGISTRY

    labels = {'caller': 'app_proxy', 'route': 'v2'}
    before = REGISTRY.get_sample_value('omi_parakeet_request_seconds_count', labels) or 0.0
    fake = _FakeSttClient(response=_FakeResponse(json_data={'text': '', 'segments': []}))
    response = _upload(_make_client(monkeypatch, fake))
    assert response.status_code == 200
    assert REGISTRY.get_sample_value('omi_parakeet_request_seconds_count', labels) == before + 1


def test_diarize_false_forwarded(monkeypatch):
    fake = _FakeSttClient(response=_FakeResponse(json_data={'text': '', 'segments': []}))
    client = _make_client(monkeypatch, fake)
    response = _upload(client, data={'diarize': 'false'})
    assert response.status_code == 200
    assert fake.calls[0]['data'] == {'diarize': 'false'}


def test_busy_when_no_upstream_slot(monkeypatch):
    fake = _FakeSttClient(response=_FakeResponse(json_data={'text': '', 'segments': []}))
    client = _make_client(monkeypatch, fake)
    monkeypatch.setattr(stt_router, 'get_stt_proxy_semaphore', lambda: asyncio.Semaphore(0))
    monkeypatch.setattr(stt_router, '_UPSTREAM_WAIT_SECS', 0.05)
    response = _upload(client)
    assert response.status_code == 503
    assert fake.calls == []


@pytest.mark.parametrize('upstream_status', [413, 503])
def test_actionable_upstream_errors_forwarded(monkeypatch, upstream_status):
    fake = _FakeSttClient(response=_FakeResponse(status_code=upstream_status, json_data={'detail': 'nope'}))
    client = _make_client(monkeypatch, fake)
    response = _upload(client)
    assert response.status_code == upstream_status
    assert response.json()['detail'] == 'nope'


def test_actionable_upstream_error_with_non_json_body(monkeypatch):
    # An LB in front of parakeet can 503 with an HTML body — fall back to the
    # generic detail instead of 500ing.
    fake = _FakeSttClient(response=_FakeResponse(status_code=503, json_data=None, text='<html>busy</html>'))
    client = _make_client(monkeypatch, fake)
    response = _upload(client)
    assert response.status_code == 503
    assert 'html' not in response.json()['detail']


def test_actionable_upstream_error_with_non_dict_json_body(monkeypatch):
    fake = _FakeSttClient(response=_FakeResponse(status_code=503, json_data=['unexpected', 'shape']))
    client = _make_client(monkeypatch, fake)
    response = _upload(client)
    assert response.status_code == 503
    assert response.json()['detail'] == 'Transcription failed upstream'


def test_other_upstream_errors_become_502(monkeypatch):
    fake = _FakeSttClient(response=_FakeResponse(status_code=500, text='internal trace'))
    client = _make_client(monkeypatch, fake)
    response = _upload(client)
    assert response.status_code == 502
    assert 'internal trace' not in response.text


def test_network_error_becomes_502(monkeypatch):
    fake = _FakeSttClient(exc=httpx.ConnectError('boom'))
    client = _make_client(monkeypatch, fake)
    response = _upload(client)
    assert response.status_code == 502


def test_non_json_success_body_becomes_502(monkeypatch):
    fake = _FakeSttClient(response=_FakeResponse(status_code=200, json_data=None, text='<html>'))
    client = _make_client(monkeypatch, fake)
    response = _upload(client)
    assert response.status_code == 502


def test_platform_forwarding_and_admission_before_slot(monkeypatch, metering):
    allowance, _ = metering
    semaphore = asyncio.Semaphore(1)
    monkeypatch.setattr(stt_router, 'get_stt_proxy_semaphore', lambda: semaphore)
    states = []

    def resolve(*args, **kwargs):
        states.append(semaphore.locked())
        return TranscriptionAllowance(TRANSCRIPTION_MODE_MANAGED, 100, 'plan_within_allowance')

    allowance.side_effect = resolve
    fake = _FakeSttClient(response=_FakeResponse(json_data={'text': 'ok'}))
    response = _make_client(monkeypatch, fake).post(
        '/v1/stt/transcribe',
        files={'file': ('audio.wav', b'audio', 'audio/wav')},
        headers={'X-App-Platform': 'ios'},
    )
    assert response.status_code == 200
    assert states == [False, True]
    assert allowance.call_args_list == [call(_UID, source='ios', byok_active=False)] * 2


def test_credit_rechecked_after_queueing(monkeypatch, metering):
    allowance, record = metering
    allowance.side_effect = [
        TranscriptionAllowance(TRANSCRIPTION_MODE_MANAGED, 100, 'plan_within_allowance'),
        TranscriptionAllowance(TRANSCRIPTION_MODE_ON_DEVICE, 0, 'plan_exhausted'),
    ]
    fake = _FakeSttClient()
    assert _upload(_make_client(monkeypatch, fake)).status_code == 402
    assert fake.calls == []
    record.assert_not_called()


async def test_probe_deadline_is_503_before_provider_slot(monkeypatch, metering):
    fake = _FakeSttClient()
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', _PARAKEET_URL)
    monkeypatch.setattr(stt_router, 'get_stt_proxy_client', lambda: fake)
    monkeypatch.setattr(stt_router, '_PROBE_TIMEOUT_SECS', 0.01)

    async def blocked(*args, **kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(stt_router, '_probe_audio_seconds', blocked)
    from starlette.datastructures import UploadFile

    upload = UploadFile(io.BytesIO(b'audio'), size=5, filename='audio.wav')
    with pytest.raises(HTTPException) as exc:
        await stt_router.stt_transcribe(request=_BareRequest(), file=upload, uid=_UID)
    assert exc.value.status_code == 503
    assert 'probe timed out' in exc.value.detail
    assert fake.calls == []
    metering[0].assert_not_called()


@pytest.mark.parametrize('duration,expected', [(1_250_000, 2), (None, 2), (0, 400), (float('nan'), 400)])
def test_probe_metadata_rounding_and_validation_at_seam(monkeypatch, duration, expected):
    from contextlib import nullcontext
    from types import SimpleNamespace

    monkeypatch.undo()
    stream = SimpleNamespace(duration=10, time_base=0.125)
    audio = SimpleNamespace(duration=duration, streams=SimpleNamespace(audio=[stream]))
    monkeypatch.setattr(duration_probe.av, 'open', lambda *args, **kwargs: nullcontext(audio))
    if expected == 400:
        with pytest.raises(HTTPException) as exc:
            duration_probe.audio_seconds(io.BytesIO(b'fake'))
        assert exc.value.status_code == 400
    else:
        assert duration_probe.audio_seconds(io.BytesIO(b'fake')) == expected


def test_probe_native_timeout_is_503(monkeypatch):
    monkeypatch.undo()

    def timeout(*args, **kwargs):
        raise duration_probe.FFmpegError(duration_probe.errno.ETIMEDOUT, 'sensitive decoder details')

    monkeypatch.setattr(duration_probe.av, 'open', timeout)
    with pytest.raises(HTTPException) as exc:
        duration_probe.audio_seconds(io.BytesIO(b'fake'))
    assert exc.value.status_code == 503
    assert 'sensitive' not in exc.value.detail


def test_real_probe_rewinds_upload_for_provider(monkeypatch, metering):
    monkeypatch.setattr(stt_router, '_probe_audio_seconds', _REAL_PROBE_AUDIO_SECONDS)
    monkeypatch.setenv('PATH', '')
    data = io.BytesIO()
    with wave.open(data, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b'\x00\x00' * 10000)
    body = data.getvalue()
    fake = _FakeSttClient(response=_FakeResponse(json_data={'text': 'ok'}))
    assert _upload(_make_client(monkeypatch, fake), content=body).status_code == 200
    assert fake.calls[0]['files']['file'][1] == body
    metering[1].assert_called_once_with(
        _UID,
        transcription_seconds=2,
        usage_metadata={'funding': 'omi', 'provider': 'parakeet', 'source': 'parakeet_proxy'},
    )


async def test_child_probe_suppresses_native_playlist_logs_without_changing_parent():
    import sys
    import tempfile
    import av.logging as av_logging

    payload = b"ffconcat version 1.0\nfile '/private/tmp/probe-private-canary.wav'\n"
    level = av_logging.get_level()
    with tempfile.TemporaryFile() as spool:
        spool.write(payload)
        spool.seek(0)
        # Control proves this media exercises libav's native stderr callback.
        control = await asyncio.create_subprocess_exec(
            sys.executable,
            '-c',
            "import av,sys; av.logging.restore_default_callback();\n"
            "try: av.open(sys.stdin.buffer, mode='r')\n"
            "except av.error.FFmpegError: pass",
            stdin=spool,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, control_error = await control.communicate()
        assert b'probe-private-canary' in control_error
        spool.seek(0)
        probe = await asyncio.create_subprocess_exec(
            sys.executable,
            '-m',
            duration_probe.__name__,
            stdin=spool,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        output, error = await probe.communicate()
    assert probe.returncode == 2, error.decode()
    assert output == error == b''
    assert av_logging.get_level() == level


async def test_timed_out_native_probe_is_killed_and_reaped_before_response(monkeypatch, metering):
    import sys
    import tempfile
    from starlette.datastructures import UploadFile

    real_spawn = asyncio.create_subprocess_exec
    processes = []

    async def spawn(*args, **kwargs):
        process = await real_spawn(sys.executable, '-c', 'import time; time.sleep(60)', **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(stt_router.asyncio, 'create_subprocess_exec', spawn)
    monkeypatch.setattr(stt_router, '_probe_audio_seconds', _REAL_PROBE_AUDIO_SECONDS)
    monkeypatch.setattr(stt_router, '_PROBE_TIMEOUT_SECS', 0.05)
    semaphore = asyncio.Semaphore(1)
    monkeypatch.setattr(stt_router, 'get_stt_probe_semaphore', lambda: semaphore)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', _PARAKEET_URL)
    with tempfile.TemporaryFile() as spool:
        spool.write(b'audio')
        spool.seek(0)
        upload = UploadFile(spool, size=5, filename='audio.wav')
        with pytest.raises(HTTPException) as exc:
            await stt_router.stt_transcribe(request=_BareRequest(), file=upload, uid=_UID)
        assert exc.value.status_code == 503
        assert processes and processes[0].returncode is not None
        assert not spool.closed  # caller can now safely close its upload
        assert not semaphore.locked()
    metering[0].assert_not_called()


async def test_repeated_request_cancellation_waits_for_probe_reaping(monkeypatch):
    from types import SimpleNamespace

    started = asyncio.Event()
    reaping = asyncio.Event()
    finish = asyncio.Event()

    class Process:
        returncode = None

        async def communicate(self):
            started.set()
            await asyncio.Event().wait()

        def kill(self):
            self.returncode = -9

        async def wait(self):
            reaping.set()
            await finish.wait()
            return self.returncode

    process = Process()

    async def spawn(*args, **kwargs):
        return process

    monkeypatch.setattr(stt_router.asyncio, 'create_subprocess_exec', spawn)
    semaphore = asyncio.Semaphore(1)
    monkeypatch.setattr(stt_router, 'get_stt_probe_semaphore', lambda: semaphore)
    task = asyncio.create_task(_REAL_PROBE_AUDIO_SECONDS(SimpleNamespace(fileno=lambda: 0)))
    await started.wait()
    task.cancel()
    await reaping.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    assert semaphore.locked()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.returncode == -9
    assert not semaphore.locked()


async def test_cancellation_during_spawn_keeps_child_owned_until_reaped(monkeypatch):
    from types import SimpleNamespace

    spawning = asyncio.Event()
    finish_spawn = asyncio.Event()

    class Process:
        returncode = None

        def kill(self):
            self.returncode = -9

        async def wait(self):
            return self.returncode

    process = Process()

    async def spawn(*args, **kwargs):
        spawning.set()
        await finish_spawn.wait()
        return process

    monkeypatch.setattr(stt_router.asyncio, 'create_subprocess_exec', spawn)
    semaphore = asyncio.Semaphore(1)
    monkeypatch.setattr(stt_router, 'get_stt_probe_semaphore', lambda: semaphore)
    task = asyncio.create_task(_REAL_PROBE_AUDIO_SECONDS(SimpleNamespace(fileno=lambda: 0)))
    await spawning.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    assert semaphore.locked()
    finish_spawn.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert process.returncode == -9
    assert not semaphore.locked()


async def test_first_cancellation_during_success_cleanup_is_not_swallowed(monkeypatch):
    from types import SimpleNamespace

    reaping = asyncio.Event()
    finish = asyncio.Event()

    class Process:
        returncode = 0

        async def communicate(self):
            return b'2\n', b''

        async def wait(self):
            reaping.set()
            await finish.wait()
            return 0

    async def spawn(*args, **kwargs):
        return Process()

    monkeypatch.setattr(stt_router.asyncio, 'create_subprocess_exec', spawn)
    task = asyncio.create_task(_REAL_PROBE_AUDIO_SECONDS(SimpleNamespace(fileno=lambda: 0)))
    await reaping.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
