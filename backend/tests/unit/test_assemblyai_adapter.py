import httpx
import os
import pytest

from utils.stt.assemblyai_adapter import (
    AssemblyAIAsyncTranscriptionProvider,
    AssemblyAIProviderError,
    AssemblyAITimeoutError,
    normalize_assemblyai_transcript_result,
)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request('GET', 'https://api.assemblyai.com/test')

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError('failed', request=self.request, response=self)


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _completed_transcript():
    return {
        'id': 'aai-transcript-1',
        'status': 'completed',
        'language_code': 'en_us',
        'speech_model_used': 'universal-2',
        'audio_duration': 2.5,
        'utterances': [
            {
                'speaker': 'A',
                'text': 'Hello world.',
                'start': 0,
                'end': 1100,
                'confidence': 0.93,
                'words': [
                    {'speaker': 'A', 'text': 'Hello', 'start': 0, 'end': 400, 'confidence': 0.94},
                    {'speaker': 'A', 'text': 'world.', 'start': 500, 'end': 1100, 'confidence': 0.91},
                ],
            }
        ],
    }


def test_assemblyai_result_normalizes_utterances_words_and_speaker_clusters():
    result = normalize_assemblyai_transcript_result(_completed_transcript(), model='universal-2')

    assert result.provider == 'assemblyai'
    assert result.model == 'universal-2'
    assert result.language == 'en'
    assert result.duration == 2.5
    assert result.raw_provider_result_id == 'aai-transcript-1'
    assert result.utterances[0].provider_cluster_id == 'A'
    assert result.utterances[0].speaker_label == 'ASSEMBLYAI_SPEAKER_A'
    assert result.words[1].text == 'world.'
    assert result.words[1].start == 0.5
    assert result.words[1].provider_cluster_id == 'A'


def test_assemblyai_result_does_not_report_multi_when_detection_returns_no_language():
    transcript = _completed_transcript()
    transcript.pop('language_code')

    result = normalize_assemblyai_transcript_result(transcript, model='universal-2', language='multi')

    assert result.language is None


def test_assemblyai_transcribe_url_submits_diarization_and_polls_to_completion():
    fake_client = FakeClient(
        [
            FakeResponse({'id': 'aai-transcript-1', 'status': 'queued'}),
            FakeResponse({'id': 'aai-transcript-1', 'status': 'processing'}),
            FakeResponse(_completed_transcript()),
        ]
    )
    provider = AssemblyAIAsyncTranscriptionProvider(
        api_key='test-key',
        client_factory=lambda: fake_client,
        poll_interval_seconds=0,
        max_poll_seconds=5,
        sleeper=lambda seconds: None,
    )

    result, detected_language = provider.transcribe_url(
        'https://example.test/audio.wav',
        speakers_count=2,
        return_language=True,
        language='multi',
        model='universal-2',
        keywords=['Omi'],
    )

    assert result.provider == 'assemblyai'
    assert detected_language == 'en'
    submit_payload = fake_client.requests[0][2]['json']
    assert submit_payload['audio_url'] == 'https://example.test/audio.wav'
    assert submit_payload['speaker_labels'] is True
    assert submit_payload['speech_models'] == ['universal-2']
    assert submit_payload['speakers_expected'] == 2
    assert submit_payload['language_detection'] is True
    assert submit_payload['keyterms_prompt'] == ['Omi']
    assert fake_client.requests[1][0] == 'GET'


def test_assemblyai_transcribe_bytes_uploads_then_transcribes_upload_url():
    fake_client = FakeClient(
        [
            FakeResponse({'upload_url': 'https://cdn.assemblyai.test/uploaded.wav'}),
            FakeResponse({'id': 'aai-transcript-1'}),
            FakeResponse(_completed_transcript()),
        ]
    )
    provider = AssemblyAIAsyncTranscriptionProvider(
        api_key='test-key',
        client_factory=lambda: fake_client,
        poll_interval_seconds=0,
        max_poll_seconds=5,
        sleeper=lambda seconds: None,
    )

    result = provider.transcribe_bytes(b'audio-bytes', diarize=True)

    assert result.provider == 'assemblyai'
    assert fake_client.requests[0][0] == 'POST'
    assert fake_client.requests[0][1].endswith('/v2/upload')
    assert fake_client.requests[1][2]['json']['audio_url'] == 'https://cdn.assemblyai.test/uploaded.wav'


def test_assemblyai_failure_status_normalizes_to_provider_error():
    fake_client = FakeClient(
        [
            FakeResponse({'id': 'aai-transcript-1'}),
            FakeResponse({'id': 'aai-transcript-1', 'status': 'error', 'error': 'unsupported media'}),
        ]
    )
    provider = AssemblyAIAsyncTranscriptionProvider(
        api_key='test-key',
        client_factory=lambda: fake_client,
        poll_interval_seconds=0,
        max_poll_seconds=5,
        sleeper=lambda seconds: None,
    )

    with pytest.raises(AssemblyAIProviderError, match='unsupported media'):
        provider.transcribe_url('https://example.test/audio.wav')


def test_assemblyai_poll_timeout_raises_timeout_error():
    current_time = {'value': 0.0}

    def clock():
        current_time['value'] += 2.0
        return current_time['value']

    fake_client = FakeClient(
        [
            FakeResponse({'id': 'aai-transcript-1'}),
            FakeResponse({'id': 'aai-transcript-1', 'status': 'processing'}),
            FakeResponse({'id': 'aai-transcript-1', 'status': 'processing'}),
        ]
    )
    provider = AssemblyAIAsyncTranscriptionProvider(
        api_key='test-key',
        client_factory=lambda: fake_client,
        poll_interval_seconds=0,
        max_poll_seconds=1,
        sleeper=lambda seconds: None,
        clock=clock,
    )

    with pytest.raises(AssemblyAITimeoutError):
        provider.transcribe_url('https://example.test/audio.wav')


def test_assemblyai_retries_retryable_http_once():
    fake_client = FakeClient(
        [
            FakeResponse({'temporarily': 'busy'}, status_code=503),
            FakeResponse({'id': 'aai-transcript-1'}),
            FakeResponse(_completed_transcript()),
        ]
    )
    provider = AssemblyAIAsyncTranscriptionProvider(
        api_key='test-key',
        client_factory=lambda: fake_client,
        poll_interval_seconds=0,
        max_poll_seconds=5,
        sleeper=lambda seconds: None,
    )

    result = provider.transcribe_url('https://example.test/audio.wav')

    assert result.provider == 'assemblyai'
    assert len(fake_client.requests) == 3


def test_assemblyai_live_smoke_with_gated_credentials():
    api_key = os.getenv('ASSEMBLYAI_API_KEY')
    audio_url = os.getenv('ASSEMBLYAI_SMOKE_AUDIO_URL')
    if not api_key or not audio_url:
        pytest.skip('ASSEMBLYAI_API_KEY and ASSEMBLYAI_SMOKE_AUDIO_URL are required for live smoke')

    provider = AssemblyAIAsyncTranscriptionProvider(api_key=api_key, poll_interval_seconds=3, max_poll_seconds=180)

    result = provider.transcribe_url(audio_url, diarize=True, language='en', model='universal-2')

    assert result.provider == 'assemblyai'
    assert result.raw_provider_result_id
    assert result.words or result.utterances
