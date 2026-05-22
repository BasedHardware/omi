import os
from typing import List, Optional, Sequence, Tuple, Union

import fal_client
import httpx
from deepgram import DeepgramClient, DeepgramClientOptions

from models.transcript_segment import ProviderTranscriptResult, ProviderTranscriptWord, TranscriptSegment
from utils.byok import get_byok_key
from utils.other.endpoints import timeit
from utils.stt.conversation_reconstructor import reconstruct_conversation
from utils.stt.deepgram_adapter import (
    DeepgramPrerecordedTranscriptionProvider,
    deepgram_speaker_fields,
    provider_result_to_legacy_words,
)
from utils.stt.deepgram_config import get_deepgram_model_for_language
import logging

_DG_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)

logger = logging.getLogger(__name__)

# Initialize Deepgram client for pre-recorded transcription
# WARN: the pre-recorded transcription is available on deepgram cloud
_deepgram_options = DeepgramClientOptions(options={"keepalive": "true"})
_deepgram_client = DeepgramClient(os.getenv('DEEPGRAM_API_KEY'), _deepgram_options)


def _deepgram_client_for_request() -> DeepgramClient:
    """Route to BYOK Deepgram key when set; otherwise use the process-wide client."""
    byok = get_byok_key('deepgram')
    if byok:
        return DeepgramClient(byok, _deepgram_options)
    return _deepgram_client


def _deepgram_speaker_fields(speaker_id) -> dict:
    return deepgram_speaker_fields(speaker_id)


def _deepgram_prerecorded_provider() -> DeepgramPrerecordedTranscriptionProvider:
    return DeepgramPrerecordedTranscriptionProvider(_deepgram_client_for_request, _DG_TIMEOUT)


@timeit
def deepgram_prerecorded(
    audio_url: str,
    speakers_count: int = None,
    attempts: int = 0,
    return_language: bool = False,
    diarize: bool = True,
    language: Optional[str] = None,
    model: str = "nova-3",
    keywords: Optional[Sequence[str]] = None,
) -> Union[List[dict], Tuple[List[dict], str]]:
    """
    Transcribe audio using Deepgram's pre-recorded API.
    Returns words in same format as fal_whisperx for compatibility with existing postprocessing.

    Args:
        audio_url: URL to the audio file
        speakers_count: Hint for number of speakers (not used by Deepgram, kept for API compatibility)
        attempts: Current retry attempt number
        return_language: If True, returns (words, language) tuple
        language: Language code to force, or 'multi' for multilingual auto-detection
        diarize: If True, enable speaker diarization
        keywords: Custom vocabulary words to boost transcription accuracy

    Returns:
        List of word dicts with format: {'timestamp': [start, end], 'speaker': 'SPEAKER_XX', 'text': 'word'}
        Or tuple of (words, language) if return_language=True
    """
    logger.info(f'deepgram_prerecorded {audio_url} {speakers_count} {attempts}')

    try:
        result = _deepgram_prerecorded_provider().transcribe_url(
            audio_url,
            speakers_count=speakers_count,
            return_language=return_language,
            diarize=diarize,
            language=language,
            model=model,
            keywords=keywords,
        )
        if return_language:
            transcript_result, detected_language = result
            return provider_result_to_legacy_words(transcript_result), detected_language

        return provider_result_to_legacy_words(result)

    except Exception as e:
        logger.error(f'Deepgram prerecorded error: {e}')
        if attempts < 1:
            return deepgram_prerecorded(
                audio_url,
                speakers_count,
                attempts + 1,
                return_language,
                diarize,
                language,
                model,
                keywords,
            )
        raise RuntimeError(f'Deepgram transcription failed after {attempts + 1} attempts: {e}')


@timeit
def deepgram_prerecorded_from_bytes(
    audio_bytes: bytes,
    sample_rate: int = 16000,
    diarize: bool = True,
    attempts: int = 0,
    encoding: Optional[str] = None,
    channels: int = 1,
    language: Optional[str] = None,
    model: str = "nova-3",
    return_language: bool = False,
    keywords: Optional[Sequence[str]] = None,
) -> Union[List[dict], Tuple[List[dict], str]]:
    """
    Transcribe audio bytes using Deepgram's pre-recorded API.
    Returns words with speaker labels when diarize=True.

    Supports both WAV format (default) and raw PCM audio.
    For raw PCM, pass encoding='linear16' with appropriate sample_rate and channels.

    Args:
        audio_bytes: Audio bytes (WAV format or raw PCM)
        sample_rate: Audio sample rate in Hz (required for raw PCM, ignored for WAV)
        diarize: If True, enable speaker diarization
        attempts: Current retry attempt number
        encoding: Audio encoding format (e.g. 'linear16' for raw PCM). None for WAV.
        channels: Number of audio channels (default 1 for mono)
        language: Language code for transcription, or None for auto-detect
        model: Deepgram model name (default 'nova-3')
        return_language: If True, returns (words, language) tuple
        keywords: Custom vocabulary words to boost transcription accuracy

    Returns:
        List of word dicts with format: {'timestamp': [start, end], 'speaker': 'SPEAKER_XX', 'text': 'word'}
        Or tuple of (words, language) if return_language=True
    """
    logger.info(
        'deepgram_prerecorded_from_bytes bytes_len=%s %s %s %s encoding=%s language=%s model=%s',
        len(audio_bytes),
        sample_rate,
        diarize,
        attempts,
        encoding,
        language,
        model,
    )

    try:
        result = _deepgram_prerecorded_provider().transcribe_bytes(
            audio_bytes,
            sample_rate=sample_rate,
            diarize=diarize,
            encoding=encoding,
            channels=channels,
            language=language,
            model=model,
            return_language=return_language,
            keywords=keywords,
        )
        if return_language:
            transcript_result, detected_language = result
            return provider_result_to_legacy_words(transcript_result), detected_language

        return provider_result_to_legacy_words(result)

    except Exception as e:
        logger.error(f'Deepgram prerecorded from bytes error: {e}')
        if attempts < 1:
            return deepgram_prerecorded_from_bytes(
                audio_bytes,
                sample_rate,
                diarize,
                attempts + 1,
                encoding,
                channels,
                language,
                model,
                return_language,
                keywords,
            )
        raise RuntimeError(f'Deepgram transcription failed after {attempts + 1} attempts: {e}')


@timeit
def fal_whisperx(
    audio_url: str,
    speakers_count: int = None,
    attempts: int = 0,
    return_language: bool = False,
    diarize: bool = True,
    chunk_level: str = 'word',
) -> List[dict]:
    logger.info(f'fal_whisperx {audio_url} {speakers_count} {attempts}')

    try:
        handler = fal_client.submit(
            "fal-ai/whisper",
            arguments={
                "audio_url": audio_url,
                'task': 'transcribe',
                'diarize': diarize,
                'chunk_level': chunk_level,
                'version': '3',
                'batch_size': 64,
                'num_speakers': speakers_count,
            },
        )
        result = handler.get()
        # print(result)
        words = result.get('chunks', [])
        if not words:
            raise Exception('No chunks found')
        if return_language:
            languages = result.get('inferred_languages', ['en'])
            language = languages[0] if languages else 'en'
            return words, language
        return words
    except Exception as e:
        logger.error(e)
        if attempts < 2:
            return fal_whisperx(audio_url, speakers_count, attempts + 1, return_language)
        if return_language:
            return [], 'en'
        return []


def legacy_words_to_provider_result(words: List[dict]) -> ProviderTranscriptResult:
    provider_words = []
    provider = None
    model = None
    for word in words:
        raw_speaker = word.get('speaker')
        speaker = raw_speaker if isinstance(raw_speaker, str) and raw_speaker.startswith('SPEAKER_') else None
        timestamp = word['timestamp']
        provider = provider or word.get('stt_provider')
        model = model or word.get('stt_model')
        provider_words.append(
            ProviderTranscriptWord(
                text=str(word['text']).strip(),
                start=round(timestamp[0], 2),
                end=round(timestamp[1] or timestamp[0] + 1, 2),
                provider_cluster_id=word.get('provider_cluster_id') or raw_speaker,
                speaker_label=word.get('provider_speaker_label') or speaker,
                confidence=word.get('confidence'),
            )
        )

    return ProviderTranscriptResult(provider=provider or 'unknown', model=model, words=provider_words)


def postprocess_words(words: List[dict], skip_n_seconds: int = 0) -> List[TranscriptSegment]:
    return reconstruct_conversation(legacy_words_to_provider_result(words), skip_n_seconds=skip_n_seconds)
