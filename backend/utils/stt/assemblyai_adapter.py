import os
import time
from typing import Callable, Optional, Sequence, Tuple, Union

import httpx

from models.transcript_segment import ProviderTranscriptResult, ProviderTranscriptUtterance, ProviderTranscriptWord
from utils.stt.providers import STTProviderName


class AssemblyAIError(RuntimeError):
    pass


class AssemblyAIProviderError(AssemblyAIError):
    pass


class AssemblyAIRetryableError(AssemblyAIError):
    pass


class AssemblyAITimeoutError(AssemblyAIError):
    pass


def assemblyai_speaker_fields(speaker_id) -> dict:
    if speaker_id is None:
        return {'provider_cluster_id': None, 'provider_speaker_label': None}

    provider_cluster_id = str(speaker_id)
    return {
        'provider_cluster_id': provider_cluster_id,
        'provider_speaker_label': f'ASSEMBLYAI_SPEAKER_{provider_cluster_id}',
    }


def normalize_assemblyai_transcript_result(
    result: dict, model: str, language: Optional[str] = None
) -> ProviderTranscriptResult:
    status = result.get('status')
    if status and status != 'completed':
        raise AssemblyAIProviderError(f'AssemblyAI transcript status is {status}')

    utterances = [_normalize_assemblyai_utterance(utterance) for utterance in result.get('utterances') or []]
    words = [_normalize_assemblyai_word(word) for word in result.get('words') or []]
    if not words and utterances:
        words = [word for utterance in utterances for word in (utterance.words or [])]

    requested_language = None if language == 'multi' else language
    return ProviderTranscriptResult(
        provider=STTProviderName.assemblyai.value,
        model=result.get('speech_model_used') or result.get('speech_model') or model,
        language=_normalize_language(result.get('language_code') or requested_language),
        duration=_seconds_float(result.get('audio_duration')),
        words=words,
        utterances=utterances,
        raw_provider_result_id=result.get('id'),
    )


def _normalize_assemblyai_word(word: dict) -> ProviderTranscriptWord:
    speaker_fields = assemblyai_speaker_fields(word.get('speaker'))
    return ProviderTranscriptWord(
        text=word.get('text', ''),
        start=_milliseconds_to_seconds(word.get('start')),
        end=_milliseconds_to_seconds(word.get('end')),
        provider_cluster_id=speaker_fields['provider_cluster_id'],
        speaker_label=speaker_fields['provider_speaker_label'],
        confidence=word.get('confidence'),
    )


def _normalize_assemblyai_utterance(utterance: dict) -> ProviderTranscriptUtterance:
    speaker_fields = assemblyai_speaker_fields(utterance.get('speaker'))
    utterance_words = utterance.get('words') or []
    return ProviderTranscriptUtterance(
        text=utterance.get('text', ''),
        start=_milliseconds_to_seconds(utterance.get('start')),
        end=_milliseconds_to_seconds(utterance.get('end')),
        provider_cluster_id=speaker_fields['provider_cluster_id'],
        speaker_label=speaker_fields['provider_speaker_label'],
        confidence=utterance.get('confidence'),
        words=[_normalize_assemblyai_word(word) for word in utterance_words] if utterance_words else None,
    )


def _milliseconds_to_seconds(value) -> float:
    if value is None:
        return 0.0
    return float(value) / 1000.0


def _seconds_float(value) -> float:
    if value is None:
        return 0.0
    return float(value)


def _normalize_language(language: Optional[str]) -> Optional[str]:
    if language and '_' in language:
        return language.split('_', 1)[0]
    if language and '-' in language:
        return language.split('-', 1)[0]
    return language


class AssemblyAIAsyncTranscriptionProvider:
    provider_name = STTProviderName.assemblyai

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[httpx.Timeout] = None,
        poll_interval_seconds: Optional[float] = None,
        max_poll_seconds: Optional[float] = None,
        client_factory: Callable[[], httpx.Client] = httpx.Client,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._api_key = api_key or os.getenv('ASSEMBLYAI_API_KEY')
        self._base_url = (base_url or os.getenv('ASSEMBLYAI_BASE_URL') or 'https://api.assemblyai.com').rstrip('/')
        self._timeout = timeout or httpx.Timeout(30.0, read=30.0)
        self._poll_interval_seconds = float(
            poll_interval_seconds
            if poll_interval_seconds is not None
            else os.getenv('ASSEMBLYAI_POLL_INTERVAL_SECONDS', '3')
        )
        self._max_poll_seconds = float(
            max_poll_seconds if max_poll_seconds is not None else os.getenv('ASSEMBLYAI_MAX_POLL_SECONDS', '900')
        )
        self._client_factory = client_factory
        self._sleeper = sleeper
        self._clock = clock

    def transcribe_url(
        self,
        audio_url: str,
        speakers_count: int = None,
        return_language: bool = False,
        diarize: bool = True,
        language: Optional[str] = None,
        model: str = 'universal-2',
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[ProviderTranscriptResult, Tuple[ProviderTranscriptResult, str]]:
        payload = self._transcript_payload(
            audio_url=audio_url,
            speakers_count=speakers_count,
            return_language=return_language,
            diarize=diarize,
            language=language,
            model=model,
            keywords=keywords,
        )
        result = self._submit_and_poll(payload)
        transcript_result = normalize_assemblyai_transcript_result(result, model=model, language=language)
        if return_language:
            return transcript_result, transcript_result.language or 'en'
        return transcript_result

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        diarize: bool = True,
        encoding: Optional[str] = None,
        channels: int = 1,
        language: Optional[str] = None,
        model: str = 'universal-2',
        return_language: bool = False,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[ProviderTranscriptResult, Tuple[ProviderTranscriptResult, str]]:
        del sample_rate, encoding, channels
        upload_url = self._upload_audio(audio_bytes)
        return self.transcribe_url(
            upload_url,
            return_language=return_language,
            diarize=diarize,
            language=language,
            model=model,
            keywords=keywords,
        )

    def _headers(self, content_type: Optional[str] = 'application/json') -> dict:
        if not self._api_key:
            raise AssemblyAIProviderError('ASSEMBLYAI_API_KEY is not configured')
        headers = {'Authorization': self._api_key}
        if content_type:
            headers['Content-Type'] = content_type
        return headers

    def _transcript_payload(
        self,
        audio_url: str,
        speakers_count: int = None,
        return_language: bool = False,
        diarize: bool = True,
        language: Optional[str] = None,
        model: str = 'universal-2',
        keywords: Optional[Sequence[str]] = None,
    ) -> dict:
        payload = {
            'audio_url': audio_url,
            'speaker_labels': diarize,
            'punctuate': True,
            'format_text': True,
        }
        if model:
            payload['speech_models'] = [model] if isinstance(model, str) else list(model)
        if speakers_count:
            payload['speakers_expected'] = speakers_count
        if language and language != 'multi':
            payload['language_code'] = language
        elif return_language or language == 'multi':
            payload['language_detection'] = True
        if keywords:
            payload['keyterms_prompt'] = list(keywords)
        return payload

    def _upload_audio(self, audio_bytes: bytes) -> str:
        with self._client_factory() as client:
            response = self._request(
                client,
                'POST',
                f'{self._base_url}/v2/upload',
                headers=self._headers('application/octet-stream'),
                content=audio_bytes,
            )
        upload_url = response.get('upload_url')
        if not upload_url:
            raise AssemblyAIProviderError('AssemblyAI upload response did not include upload_url')
        return upload_url

    def _submit_and_poll(self, payload: dict) -> dict:
        with self._client_factory() as client:
            submitted = self._request(
                client,
                'POST',
                f'{self._base_url}/v2/transcript',
                headers=self._headers(),
                json=payload,
            )
            transcript_id = submitted.get('id')
            if not transcript_id:
                raise AssemblyAIProviderError('AssemblyAI transcript response did not include id')
            return self._poll_transcript(client, transcript_id)

    def _poll_transcript(self, client: httpx.Client, transcript_id: str) -> dict:
        deadline = self._clock() + self._max_poll_seconds
        while True:
            result = self._request(
                client,
                'GET',
                f'{self._base_url}/v2/transcript/{transcript_id}',
                headers=self._headers(None),
            )
            status = result.get('status')
            if status == 'completed':
                return result
            if status == 'error':
                raise AssemblyAIProviderError(result.get('error') or 'AssemblyAI transcript failed')
            if status not in ('queued', 'processing'):
                raise AssemblyAIProviderError(f'AssemblyAI returned unexpected transcript status: {status}')
            if self._clock() >= deadline:
                raise AssemblyAITimeoutError(f'AssemblyAI transcript {transcript_id} timed out')
            self._sleeper(self._poll_interval_seconds)

    def _request(self, client: httpx.Client, method: str, url: str, **kwargs) -> dict:
        last_error = None
        for attempt in range(2):
            try:
                response = client.request(method, url, timeout=self._timeout, **kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                last_error = e
                if e.response.status_code in (408, 429, 500, 502, 503, 504) and attempt == 0:
                    self._sleeper(min(self._poll_interval_seconds, 1.0))
                    continue
                if e.response.status_code in (408, 429, 500, 502, 503, 504):
                    raise AssemblyAIRetryableError(f'AssemblyAI HTTP {e.response.status_code}: {e}') from e
                raise AssemblyAIProviderError(f'AssemblyAI HTTP {e.response.status_code}: {e}') from e
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last_error = e
                if attempt == 0:
                    self._sleeper(min(self._poll_interval_seconds, 1.0))
                    continue
                raise AssemblyAIRetryableError(f'AssemblyAI request failed: {e}') from e
        raise AssemblyAIRetryableError(f'AssemblyAI request failed: {last_error}')
