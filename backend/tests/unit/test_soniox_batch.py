"""HTTP-contract tests for independent recovery; synthetic bytes, no network."""

import json
from unittest.mock import Mock

import httpx
import pytest

from utils.stt import soniox_batch as module
from config.prerecorded_stt import PrerecordedSTTConfigurationError

FILE = '11111111-1111-4111-8111-111111111111'
TRANSCRIPTION = '22222222-2222-4222-8222-222222222222'
TRANSCRIPT = {
    'text': 'Synthetic fixture.',
    'tokens': [
        {'text': 'Syn', 'start_ms': 100, 'end_ms': 200, 'speaker': '1', 'language': 'vi'},
        {'text': 'thetic', 'start_ms': 200, 'end_ms': 300, 'speaker': '1', 'language': 'vi'},
        {'text': ' fixture', 'start_ms': 400, 'end_ms': 500, 'speaker': '1', 'language': 'vi'},
        {'text': '.', 'start_ms': 500, 'end_ms': 510, 'speaker': '1', 'language': 'vi'},
    ],
}


def client(handler):
    return lambda **kwargs: httpx.Client(transport=httpx.MockTransport(handler), **kwargs)


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-only-key')
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'true')


@pytest.mark.parametrize('hint,expected', [('vi-VN', ['vi']), ('xx-unsupported', None), (None, None)])
def test_single_submission_hints_timestamps_and_cleanup(key, hint, expected):
    calls, bodies = [], []

    def handler(request):
        calls.append((request.method, request.url.path))
        assert request.headers['authorization'] == 'Bearer synthetic-only-key'
        if request.method == 'DELETE':
            return httpx.Response(204)
        if request.url.path == '/v1/files':
            assert b'synthetic-pcm-fixture' in request.content
            return httpx.Response(201, json={'id': FILE})
        if request.method == 'POST':
            body = json.loads(request.content)
            bodies.append(body)
            assert body.get('language_hints') == expected
            assert body['model'] == module.MODEL and body['file_id'] == FILE
            assert 'audio_url' not in body and 'client_reference_id' not in body
            assert not body.get('language_hints_strict')
            return httpx.Response(201, json={'id': TRANSCRIPTION, 'status': 'queued'})
        if request.url.path.endswith('/transcript'):
            return httpx.Response(200, json=TRANSCRIPT)
        return httpx.Response(200, json={'status': 'completed'})

    words, language = module.transcribe(
        b'synthetic-pcm-fixture',
        5,
        language=hint,
        client_factory=client(handler),
        sleep=lambda _: None,
    )
    assert [w['text'] for w in words] == ['Synthetic', 'fixture.']
    assert [w['timestamp'] for w in words] == [[0.1, 0.3], [0.4, 0.51]]
    assert language == 'vi'
    assert [method for method, _ in calls].count('POST') == 2
    assert calls[-2:] == [('DELETE', f'/v1/transcriptions/{TRANSCRIPTION}'), ('DELETE', f'/v1/files/{FILE}')]


def test_valid_empty_reply_retains_unknown_language_without_fabrication(key):
    assert module.transcript_words({'text': '', 'tokens': []}, 5) == ([], 'multi')


@pytest.mark.parametrize('parts', [('Hello ', 'world'), ('Hello', ' ', 'world'), ('Hello', '<end>', 'world')])
def test_whitespace_and_finalization_boundaries_do_not_join_distinct_words(parts):
    tokens = [
        {'text': text, 'start_ms': i * 100, 'end_ms': (i + 1) * 100, 'speaker': '1'} for i, text in enumerate(parts)
    ]
    words, _ = module.transcript_words({'text': 'Hello world', 'tokens': tokens}, 5)
    assert [w['text'] for w in words] == ['Hello', 'world']
    assert all(w['speaker'] == 'SPEAKER_00' for w in words)


@pytest.mark.parametrize(
    'payload',
    [
        {'text': 'words', 'tokens': []},
        {'tokens': []},
        {'text': '', 'tokens': None},
        {'text': 'x', 'tokens': [{'text': 'x', 'start_ms': -1, 'end_ms': 100}]},
        {'text': 'x', 'tokens': [{'text': 'x', 'start_ms': 1, 'end_ms': 6000}]},
        {'text': 'x', 'tokens': [{'text': 'x', 'start_ms': True, 'end_ms': 10}]},
        {'text': 'x', 'tokens': [{'text': 'x', 'start_ms': float('nan'), 'end_ms': 10}]},
    ],
)
def test_malformed_reply_never_counts_as_empty(payload):
    with pytest.raises(module.SonioxBatchError):
        module.transcript_words(payload, 5)


@pytest.mark.parametrize('failure', ['upload', 'create', 'poll', 'transcript'])
def test_failure_is_single_submit_content_free_and_cleans_known_resources(key, failure, caplog):
    calls = []

    def handler(request):
        calls.append((request.method, request.url.path))
        if request.method == 'DELETE':
            return httpx.Response(204)
        stage = (
            'upload'
            if request.url.path == '/v1/files'
            else (
                'create'
                if request.method == 'POST'
                else 'transcript' if request.url.path.endswith('/transcript') else 'poll'
            )
        )
        if stage == failure:
            return httpx.Response(429, json={'error_message': 'PRIVATE_SENTINEL'})
        if stage == 'upload':
            return httpx.Response(201, json={'id': FILE})
        if stage == 'create':
            return httpx.Response(201, json={'id': TRANSCRIPTION, 'status': 'queued'})
        return httpx.Response(200, json={'status': 'completed'})

    with pytest.raises(module.SonioxBatchError, match='^soniox_batch_failed$'):
        module.transcribe(b'synthetic', 5, client_factory=client(handler), sleep=lambda _: None)
    assert sum(m == 'POST' and p == '/v1/transcriptions' for m, p in calls) <= 1
    assert sum(m == 'POST' and p == '/v1/files' for m, p in calls) == 1
    if failure != 'upload':
        assert ('DELETE', f'/v1/files/{FILE}') in calls
    assert 'PRIVATE_SENTINEL' not in caplog.text


def test_deadline_bounds_polling_without_resubmission(key):
    now, calls = [0], []

    def handler(request):
        calls.append(request.method)
        if request.method == 'DELETE':
            return httpx.Response(204)
        if request.url.path == '/v1/files':
            return httpx.Response(201, json={'id': FILE})
        return httpx.Response(
            201 if request.method == 'POST' else 200, json={'id': TRANSCRIPTION, 'status': 'processing'}
        )

    with pytest.raises(module.SonioxBatchError):
        module.transcribe(
            b'synthetic',
            5,
            client_factory=client(handler),
            clock=lambda: now[0],
            sleep=lambda seconds: now.__setitem__(0, now[0] + seconds),
        )
    assert now[0] == module.DEADLINE_SECONDS
    assert calls.count('POST') == 2 and calls.count('GET') < 60


def test_missing_key_refuses_before_http(monkeypatch):
    monkeypatch.delenv('SONIOX_API_KEY', raising=False)
    monkeypatch.setenv('BATCH_PIPELINE_INDEPENDENT_LANGUAGE_RECOVERY_ENABLED', 'true')
    factory = Mock()
    with pytest.raises(PrerecordedSTTConfigurationError):
        module.transcribe(b'synthetic', 5, client_factory=factory)
    factory.assert_not_called()


def test_provider_ids_cannot_escape_authenticated_path(key):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(201, json={'id': 'https://untrusted.example/secrets'})

    with pytest.raises(module.SonioxBatchError):
        module.transcribe(b'synthetic', 5, client_factory=client(handler))
    assert len(calls) == 1
