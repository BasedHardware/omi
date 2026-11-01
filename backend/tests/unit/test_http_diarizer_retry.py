"""HttpDiarizer preemption retry: one bounded retry, then fail like today."""

import time

import httpx
import pytest

from utils.stt import diarization

RESULT = {
    'turns': [{'start': 0.0, 'end': 1.0, 'speaker': 'SPEAKER_00'}],
    'overlaps': [],
    'centroids': {},
    'embedding_space': 'pyannote/wespeaker-voxceleb-resnet34-LM:v2',
    'version': 'batch-test',
    'provenance': {'backend': 'pyannote'},
}


def _ok_response():
    return httpx.Response(200, json=RESULT, request=httpx.Request('POST', 'http://x/v2/diarization'))


def _status_response(code):
    return httpx.Response(code, json={}, request=httpx.Request('POST', 'http://x/v2/diarization'))


@pytest.fixture
def pyannote(monkeypatch):
    monkeypatch.setenv('HOSTED_DIARIZATION_API_URL', 'http://diarizer')
    return diarization.HttpDiarizer('pyannote')


def posts_recorder(monkeypatch, outcomes):
    """outcomes: callables/responses raised or returned in order; returns call log."""
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs.get('content'))
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(diarization.httpx, 'post', fake_post)
    return calls


def test_transport_error_retries_once_and_succeeds(pyannote, monkeypatch):
    calls = posts_recorder(monkeypatch, [httpx.ReadError('pod gone'), _ok_response()])
    result = pyannote.diarize(b'pcm', deadline=time.monotonic() + 60)
    assert result.provenance['backend'] == 'pyannote'
    assert len(calls) == 2


def test_server_error_retries_once_and_succeeds(pyannote, monkeypatch):
    calls = posts_recorder(monkeypatch, [_status_response(503), _ok_response()])
    pyannote.diarize(b'pcm', deadline=time.monotonic() + 60)
    assert len(calls) == 2


def test_client_error_is_not_retried(pyannote, monkeypatch):
    calls = posts_recorder(monkeypatch, [_status_response(404)])
    with pytest.raises(httpx.HTTPStatusError):
        pyannote.diarize(b'pcm', deadline=time.monotonic() + 60)
    assert len(calls) == 1


def test_second_failure_raises_after_single_retry(pyannote, monkeypatch):
    calls = posts_recorder(monkeypatch, [httpx.ConnectError('down'), httpx.ConnectError('still down')])
    with pytest.raises(httpx.ConnectError):
        pyannote.diarize(b'pcm', deadline=time.monotonic() + 60)
    assert len(calls) == 2


def test_retry_stops_at_deadline(pyannote, monkeypatch):
    calls = posts_recorder(monkeypatch, [httpx.ReadError('pod gone')])
    with pytest.raises(TimeoutError):
        # Deadline already spent when the retry would start.
        pyannote.diarize(b'pcm', deadline=time.monotonic() - 1)
    assert calls == []


def test_response_arriving_past_deadline_is_rejected(pyannote, monkeypatch):
    def slow_post(*args, **kwargs):
        time.sleep(0.05)
        return _ok_response()

    monkeypatch.setattr(diarization.httpx, 'post', slow_post)
    with pytest.raises(TimeoutError):
        pyannote.diarize(b'pcm', deadline=time.monotonic() + 0.01)
