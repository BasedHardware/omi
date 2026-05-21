from dataclasses import dataclass
from io import BytesIO
from typing import Callable, List, Optional, Sequence, Tuple, Union

import httpx
from deepgram import DeepgramClient

from models.transcript_segment import ProviderTranscriptResult, ProviderTranscriptUtterance, ProviderTranscriptWord
from utils.stt.providers import STTProviderName


@dataclass(frozen=True)
class DeepgramPrerecordedOptions:
    model: str = 'nova-3'
    diarize: bool = True
    language: Optional[str] = None
    return_language: bool = False
    keywords: Optional[Sequence[str]] = None
    sample_rate: int = 16000
    encoding: Optional[str] = None
    channels: int = 1
    nova3_keyword_prefix_match: bool = False


def deepgram_speaker_fields(speaker_id) -> dict:
    if speaker_id is None:
        return {'speaker': None, 'provider_cluster_id': None, 'provider_speaker_label': None}

    provider_cluster_id = str(speaker_id)
    try:
        speaker_label = f'SPEAKER_{int(speaker_id):02d}'
    except (TypeError, ValueError):
        speaker_label = None

    return {
        'speaker': speaker_label,
        'provider_cluster_id': provider_cluster_id,
        'provider_speaker_label': speaker_label,
    }


def normalize_deepgram_prerecorded_result(
    result: dict, model: str, language: Optional[str] = None
) -> ProviderTranscriptResult:
    channels = result.get('results', {}).get('channels', [])
    if not channels:
        raise Exception('No channels found in response')

    alternatives = channels[0].get('alternatives', [])
    if not alternatives:
        raise Exception('No alternatives found in response')

    alternative = alternatives[0]
    detected_language = _normalize_language(channels[0].get('detected_language') or language)
    words = [_normalize_deepgram_word(word) for word in alternative.get('words', [])]
    utterances = [
        _normalize_deepgram_utterance(utterance) for utterance in result.get('results', {}).get('utterances', [])
    ]
    duration = result.get('metadata', {}).get('duration')

    return ProviderTranscriptResult(
        provider=STTProviderName.deepgram.value,
        model=model,
        language=detected_language,
        duration=duration,
        words=words,
        utterances=utterances,
        raw_provider_result_id=result.get('metadata', {}).get('request_id'),
    )


def provider_result_to_legacy_words(result: ProviderTranscriptResult) -> List[dict]:
    words = []
    for word in result.words:
        words.append(
            {
                'timestamp': [word.start, word.end],
                'speaker': word.speaker_label,
                'provider_cluster_id': word.provider_cluster_id,
                'provider_speaker_label': word.speaker_label,
                'stt_provider': result.provider,
                'stt_model': result.model,
                'text': word.text,
            }
        )
    return words


def _normalize_language(language: Optional[str]) -> Optional[str]:
    if language and '-' in language:
        return language.split('-', 1)[0]
    return language


def _normalize_deepgram_word(word: dict) -> ProviderTranscriptWord:
    speaker_fields = deepgram_speaker_fields(word.get('speaker'))
    return ProviderTranscriptWord(
        text=word.get('punctuated_word', word.get('word', '')),
        start=word['start'],
        end=word['end'],
        provider_cluster_id=speaker_fields['provider_cluster_id'],
        speaker_label=speaker_fields['speaker'],
        confidence=word.get('confidence'),
    )


def _normalize_deepgram_utterance(utterance: dict) -> ProviderTranscriptUtterance:
    speaker_fields = deepgram_speaker_fields(utterance.get('speaker'))
    utterance_words = utterance.get('words')
    return ProviderTranscriptUtterance(
        text=utterance.get('transcript', ''),
        start=utterance['start'],
        end=utterance['end'],
        provider_cluster_id=speaker_fields['provider_cluster_id'],
        speaker_label=speaker_fields['speaker'],
        confidence=utterance.get('confidence'),
        words=[_normalize_deepgram_word(word) for word in utterance_words] if utterance_words else None,
    )


class DeepgramPrerecordedTranscriptionProvider:
    provider_name = STTProviderName.deepgram

    def __init__(
        self,
        client_factory: Callable[[], DeepgramClient],
        timeout: httpx.Timeout,
    ):
        self._client_factory = client_factory
        self._timeout = timeout

    def transcribe_url(
        self,
        audio_url: str,
        speakers_count: int = None,
        return_language: bool = False,
        diarize: bool = True,
        language: Optional[str] = None,
        model: str = 'nova-3',
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[ProviderTranscriptResult, Tuple[ProviderTranscriptResult, str]]:
        options = DeepgramPrerecordedOptions(
            model=model,
            diarize=diarize,
            language=language,
            return_language=return_language,
            keywords=keywords,
        )
        request_options = self._request_options(options)
        response = (
            self._client_factory()
            .listen.rest.v('1')
            .transcribe_url({'url': audio_url}, request_options, timeout=self._timeout)
        )
        result = normalize_deepgram_prerecorded_result(response.to_dict(), model=model, language=language)
        if return_language:
            return result, result.language or 'en'
        return result

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        diarize: bool = True,
        encoding: Optional[str] = None,
        channels: int = 1,
        language: Optional[str] = None,
        model: str = 'nova-3',
        return_language: bool = False,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[ProviderTranscriptResult, Tuple[ProviderTranscriptResult, str]]:
        options = DeepgramPrerecordedOptions(
            model=model,
            diarize=diarize,
            language=language,
            return_language=return_language,
            keywords=keywords,
            sample_rate=sample_rate,
            encoding=encoding,
            channels=channels,
            nova3_keyword_prefix_match=True,
        )
        request_options = self._request_options(options)
        audio_buffer = BytesIO(audio_bytes)
        mimetype = 'audio/raw' if encoding else 'audio/wav'
        source = {'buffer': audio_buffer, 'mimetype': mimetype}
        response = (
            self._client_factory().listen.rest.v('1').transcribe_file(source, request_options, timeout=self._timeout)
        )
        result = normalize_deepgram_prerecorded_result(response.to_dict(), model=model, language=language)
        if return_language:
            return result, result.language or 'en'
        return result

    def _request_options(self, options: DeepgramPrerecordedOptions) -> dict:
        is_multi = options.language == 'multi'
        request_options = {
            'model': options.model,
            'smart_format': True,
            'punctuate': True,
            'diarize': options.diarize,
            'utterances': True,
            'detect_language': options.return_language or is_multi,
        }
        if options.language and not is_multi:
            request_options['language'] = options.language

        if options.keywords:
            is_nova3_keyword_model = options.model in ('nova-3',) or (
                options.nova3_keyword_prefix_match and str(options.model).startswith('nova-3')
            )
            if is_nova3_keyword_model:
                request_options['keyterm'] = list(options.keywords)
            else:
                request_options['keywords'] = list(options.keywords)

        if options.encoding:
            request_options['encoding'] = options.encoding
            request_options['sample_rate'] = options.sample_rate
            request_options['channels'] = options.channels

        return request_options
