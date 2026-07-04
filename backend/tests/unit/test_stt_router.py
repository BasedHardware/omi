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

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import routers.stt as stt_router
from utils.other import endpoints as auth
from utils.rate_limit_config import RATE_POLICIES

_PARAKEET_URL = 'http://parakeet.internal:8000'
_UID = 'test-uid'


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
