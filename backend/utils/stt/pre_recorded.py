import os
import wave as _wave
from abc import ABC, abstractmethod
from collections import defaultdict
from io import BytesIO
from typing import List, Optional, Sequence, Tuple, Union

import fal_client
import httpx
import numpy as np
from deepgram import DeepgramClient, DeepgramClientOptions

from models.transcript_segment import TranscriptSegment
from utils.byok import get_byok_key
from utils.other.endpoints import timeit
from utils.stt.speaker_embedding import SPEAKER_MATCH_THRESHOLD, compare_embeddings, extract_embedding_from_bytes
import logging

_DG_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
_MODULATE_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

logger = logging.getLogger(__name__)

stt_prerecorded_models = os.getenv('STT_PRERECORDED_MODEL', 'dg-nova-3').split(',')

_parakeet_languages = {
    'multi',
    'bg',
    'hr',
    'cs',
    'da',
    'nl',
    'en',
    'et',
    'fi',
    'fr',
    'de',
    'el',
    'hu',
    'it',
    'lt',
    'lv',
    'mt',
    'pl',
    'pt',
    'ro',
    'ru',
    'sk',
    'sl',
    'es',
    'sv',
    'uk',
}


# ---------------------------------------------------------------------------
# Provider-agnostic ABC — mirrors STTSocket for streaming
# ---------------------------------------------------------------------------


class PrerecordedSTTProvider(ABC):

    @abstractmethod
    def transcribe_url(
        self,
        audio_url: str,
        speakers_count: int = None,
        attempts: int = 0,
        return_language: bool = False,
        diarize: bool = True,
        language: Optional[str] = None,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[List[dict], Tuple[List[dict], str]]: ...

    @abstractmethod
    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        diarize: bool = True,
        attempts: int = 0,
        encoding: Optional[str] = None,
        channels: int = 1,
        language: Optional[str] = None,
        return_language: bool = False,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[List[dict], Tuple[List[dict], str]]: ...


class PrerecordedSTTService:
    DEEPGRAM = 'deepgram'
    MODULATE = 'modulate'
    PARAKEET = 'parakeet'


def get_prerecorded_service(language: str = 'en') -> Tuple[str, str, str]:
    """Route pre-recorded STT based on STT_PRERECORDED_MODEL env var.

    Iterates comma-separated models (same pattern as STT_SERVICE_MODELS for streaming).
    First model that supports the language wins; falls back to Deepgram nova-3.
    """
    base_lang = language.split('-')[0].split('_')[0].lower() if language else 'en'
    for m in stt_prerecorded_models:
        m = m.strip()
        if m.startswith('dg-'):
            dg_model = m.replace('dg-', '', 1)
            lang = language if (language is None or language in _deepgram_nova3_languages) else 'multi'
            return PrerecordedSTTService.DEEPGRAM, lang, dg_model
        if m == 'modulate-velma-2':
            if base_lang in {'en', 'es', 'fr', 'de', 'it', 'pt', 'nl', 'ja', 'ko', 'zh'}:
                return PrerecordedSTTService.MODULATE, base_lang, 'velma-2'
            continue
        if m == 'parakeet':
            if base_lang in _parakeet_languages:
                return PrerecordedSTTService.PARAKEET, base_lang, 'parakeet'
            continue
    return PrerecordedSTTService.DEEPGRAM, language, 'nova-3'


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


# Languages supported by nova-3
_deepgram_nova3_languages = {
    "ar",
    "ar-AE",
    "ar-SA",
    "ar-QA",
    "ar-KW",
    "ar-SY",
    "ar-LB",
    "ar-PS",
    "ar-JO",
    "ar-EG",
    "ar-SD",
    "ar-TD",
    "ar-MA",
    "ar-DZ",
    "ar-TN",
    "ar-IQ",
    "ar-IR",
    "be",
    "bg",
    "bn",
    "bs",
    "ca",
    "cs",
    "da",
    "da-DK",
    "de",
    "de-CH",
    "el",
    "en",
    "en-US",
    "en-AU",
    "en-GB",
    "en-IN",
    "en-NZ",
    "es",
    "es-419",
    "et",
    "fa",
    "fi",
    "fr",
    "fr-CA",
    "he",
    "hi",
    "hr",
    "hu",
    "id",
    "it",
    "ja",
    "kn",
    "ko",
    "ko-KR",
    "lt",
    "lv",
    "mk",
    "mr",
    "ms",
    "nl",
    "nl-BE",
    "no",
    "pl",
    "pt",
    "pt-BR",
    "pt-PT",
    "ro",
    "ru",
    "sk",
    "sl",
    "sr",
    "sv",
    "sv-SE",
    "ta",
    "te",
    "th",
    "th-TH",
    "tl",
    "tr",
    "uk",
    "ur",
    "vi",
    "zh",
    "zh-CN",
    "zh-Hans",
    "zh-HK",
    "zh-Hant",
    "zh-TW",
}


def get_deepgram_model_for_language(language: str) -> Tuple[str, str]:
    """
    Determine the appropriate Deepgram model and language for pre-recorded transcription.

    Args:
        language: The requested language code or 'multi' for auto-detection

    Returns:
        Tuple of (language_to_use, model_name)
    """
    # For multi-language mode
    if language == 'multi':
        return 'multi', 'nova-3'

    # Languages supported by nova-3
    if language in _deepgram_nova3_languages:
        return language, 'nova-3'

    # Unsupported language - fall back to multi for auto-detection
    return 'multi', 'nova-3'


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
        # 'multi' language means auto-detection
        is_multi = language == 'multi'
        should_detect_language = return_language or is_multi
        options = {
            "model": model,
            "smart_format": True,
            "punctuate": True,
            "diarize": diarize,
            "detect_language": should_detect_language,
            "utterances": True,
        }
        if language and not is_multi:
            options["language"] = language

        if keywords:
            if model in ('nova-3',):
                options["keyterm"] = list(keywords)
            else:
                options["keywords"] = list(keywords)

        response = (
            _deepgram_client_for_request()
            .listen.rest.v("1")
            .transcribe_url({"url": audio_url}, options, timeout=_DG_TIMEOUT)
        )

        # Extract words from response
        result = response.to_dict()
        channels = result.get('results', {}).get('channels', [])
        if not channels:
            raise Exception('No channels found in response')

        alternatives = channels[0].get('alternatives', [])
        if not alternatives:
            raise Exception('No alternatives found in response')

        dg_words = alternatives[0].get('words', [])
        if not dg_words:
            if return_language:
                detected_lang = channels[0].get('detected_language', 'en')
                if detected_lang and '-' in detected_lang:
                    detected_lang = detected_lang.split('-')[0]
                return [], detected_lang or 'en'
            return []

        # Convert Deepgram format to fal_whisperx compatible format
        # Deepgram: {word, start, end, confidence, punctuated_word, speaker (int)}
        # Expected: {timestamp: [start, end], speaker: 'SPEAKER_XX', text: 'word'}
        words = []
        for w in dg_words:
            speaker_id = w.get('speaker', 0)
            words.append(
                {
                    'timestamp': [w['start'], w['end']],
                    'speaker': f"SPEAKER_{speaker_id:02d}" if speaker_id is not None else None,
                    'text': w.get('punctuated_word', w['word']),
                }
            )

        if return_language:
            # Deepgram returns detected_language in the channel
            detected_lang = channels[0].get('detected_language', 'en')
            # Normalize language code (Deepgram might return 'en-US', we want 'en')
            if detected_lang and '-' in detected_lang:
                detected_lang = detected_lang.split('-')[0]
            return words, detected_lang or 'en'

        return words

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
        f'deepgram_prerecorded_from_bytes bytes_len={len(audio_bytes)} {sample_rate} {diarize} {attempts} encoding={encoding} language={language} model={model}'
    )

    try:
        is_multi = language == 'multi'
        should_detect_language = return_language or is_multi
        options = {
            "model": model,
            "smart_format": True,
            "punctuate": True,
            "diarize": diarize,
            "utterances": True,
            "detect_language": should_detect_language,
        }
        if language and not is_multi:
            options["language"] = language

        if keywords:
            if str(model).startswith("nova-3"):
                options["keyterm"] = list(keywords)
            else:
                options["keywords"] = list(keywords)

        # For raw PCM, Deepgram needs encoding + sample_rate to interpret the bytes
        if encoding:
            options["encoding"] = encoding
            options["sample_rate"] = sample_rate
            options["channels"] = channels

        # Wrap bytes in BytesIO for Deepgram client
        audio_buffer = BytesIO(audio_bytes)
        mimetype = "audio/raw" if encoding else "audio/wav"
        source = {"buffer": audio_buffer, "mimetype": mimetype}

        response = (
            _deepgram_client_for_request().listen.rest.v("1").transcribe_file(source, options, timeout=_DG_TIMEOUT)
        )

        # Extract words from response
        result = response.to_dict()
        result_channels = result.get('results', {}).get('channels', [])
        if not result_channels:
            raise Exception('No channels found in response')

        alternatives = result_channels[0].get('alternatives', [])
        if not alternatives:
            raise Exception('No alternatives found in response')

        dg_words = alternatives[0].get('words', [])
        if not dg_words:
            if return_language:
                detected_lang = result_channels[0].get('detected_language', 'en')
                if detected_lang and '-' in detected_lang:
                    detected_lang = detected_lang.split('-')[0]
                return [], detected_lang or 'en'
            return []

        # Convert Deepgram format to standard format
        # Deepgram: {word, start, end, confidence, punctuated_word, speaker (int)}
        # Expected: {timestamp: [start, end], speaker: 'SPEAKER_XX', text: 'word'}
        words = []
        for w in dg_words:
            speaker_id = w.get('speaker', 0)
            words.append(
                {
                    'timestamp': [w['start'], w['end']],
                    'speaker': f"SPEAKER_{speaker_id:02d}" if speaker_id is not None else None,
                    'text': w.get('punctuated_word', w['word']),
                }
            )

        if return_language:
            detected_lang = result_channels[0].get('detected_language', 'en')
            if detected_lang and '-' in detected_lang:
                detected_lang = detected_lang.split('-')[0]
            return words, detected_lang or 'en'

        return words

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


@timeit
def modulate_prerecorded_from_bytes(
    audio_bytes: bytes,
    sample_rate: int = 16000,
    diarize: bool = True,
    attempts: int = 0,
    return_language: bool = False,
) -> Union[List[dict], Tuple[List[dict], str]]:
    logger.info(f'modulate_prerecorded_from_bytes bytes_len={len(audio_bytes)} {sample_rate} {diarize} {attempts}')

    api_key = os.getenv('MODULATE_API_KEY')
    if not api_key:
        raise ValueError('MODULATE_API_KEY environment variable is not set')

    try:
        url = 'https://modulate-developer-apis.com/api/velma-2-stt-batch'
        headers = {'X-API-Key': api_key}
        files = {'upload_file': ('audio.wav', BytesIO(audio_bytes), 'audio/wav')}
        data = {'speaker_diarization': str(diarize).lower()}

        with httpx.Client(timeout=300) as client:
            response = client.post(url, headers=headers, files=files, data=data)
        response.raise_for_status()
        result = response.json()

        utterances = result.get('utterances', [])
        if not utterances:
            if return_language:
                return [], 'en'
            return []

        words = []
        detected_language = 'en'
        for utt in utterances:
            text = utt.get('text', '').strip()
            if not text:
                continue

            start_ms = utt.get('start_ms', 0)
            duration_ms = utt.get('duration_ms', 0)
            start = start_ms / 1000.0
            end = (start_ms + duration_ms) / 1000.0

            raw_speaker = utt.get('speaker')
            if isinstance(raw_speaker, int) and raw_speaker >= 1:
                speaker_idx = raw_speaker - 1
            else:
                speaker_idx = 0
            speaker = f'SPEAKER_{speaker_idx:02d}'

            words.append({'timestamp': [start, end], 'speaker': speaker, 'text': text})

            lang = utt.get('language')
            if lang:
                detected_language = lang

        if return_language:
            return words, detected_language

        return words

    except Exception as e:
        logger.error(f'Modulate prerecorded error: {e}')
        if attempts < 2:
            return modulate_prerecorded_from_bytes(audio_bytes, sample_rate, diarize, attempts + 1, return_language)
        raise RuntimeError(f'Modulate transcription failed after {attempts + 1} attempts: {e}')


@timeit
def modulate_prerecorded(
    audio_url: str,
    speakers_count: int = None,
    attempts: int = 0,
    return_language: bool = False,
    diarize: bool = True,
    language: Optional[str] = None,
) -> Union[List[dict], Tuple[List[dict], str]]:
    logger.info(f'modulate_prerecorded {audio_url} {speakers_count} {attempts}')
    try:
        with httpx.Client(timeout=_MODULATE_TIMEOUT) as client:
            resp = client.get(audio_url)
            resp.raise_for_status()
            audio_bytes = resp.content
        return modulate_prerecorded_from_bytes(
            audio_bytes, diarize=diarize, attempts=attempts, return_language=return_language
        )
    except Exception as e:
        logger.error(f'Modulate prerecorded (url) error: {e}')
        if attempts < 1:
            return modulate_prerecorded(audio_url, speakers_count, attempts + 1, return_language, diarize, language)
        raise RuntimeError(f'Modulate transcription (url) failed after {attempts + 1} attempts: {e}')


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


class DeepgramPrerecordedProvider(PrerecordedSTTProvider):

    def __init__(self, model: str = 'nova-3'):
        self._model = model

    def transcribe_url(
        self,
        audio_url,
        speakers_count=None,
        attempts=0,
        return_language=False,
        diarize=True,
        language=None,
        keywords=None,
    ):
        lang = language if (language is None or language in _deepgram_nova3_languages) else 'multi'
        return deepgram_prerecorded(
            audio_url,
            speakers_count=speakers_count,
            attempts=attempts,
            return_language=return_language,
            diarize=diarize,
            language=lang,
            model=self._model,
            keywords=keywords,
        )

    def transcribe_bytes(
        self,
        audio_bytes,
        sample_rate=16000,
        diarize=True,
        attempts=0,
        encoding=None,
        channels=1,
        language=None,
        return_language=False,
        keywords=None,
    ):
        lang = language if (language is None or language in _deepgram_nova3_languages) else 'multi'
        return deepgram_prerecorded_from_bytes(
            audio_bytes,
            sample_rate=sample_rate,
            diarize=diarize,
            attempts=attempts,
            encoding=encoding,
            channels=channels,
            language=lang,
            model=self._model,
            return_language=return_language,
            keywords=keywords,
        )


class ModulatePrerecordedProvider(PrerecordedSTTProvider):

    def _normalize_lang(self, language: Optional[str]) -> str:
        if not language:
            return 'en'
        return language.split('-')[0].split('_')[0].lower()

    def transcribe_url(
        self,
        audio_url,
        speakers_count=None,
        attempts=0,
        return_language=False,
        diarize=True,
        language=None,
        keywords=None,
    ):
        return modulate_prerecorded(
            audio_url,
            speakers_count=speakers_count,
            attempts=attempts,
            return_language=return_language,
            diarize=diarize,
            language=self._normalize_lang(language),
        )

    def transcribe_bytes(
        self,
        audio_bytes,
        sample_rate=16000,
        diarize=True,
        attempts=0,
        encoding=None,
        channels=1,
        language=None,
        return_language=False,
        keywords=None,
    ):
        if encoding:
            audio_bytes = _wrap_pcm_as_wav(audio_bytes, sample_rate, channels)
        return modulate_prerecorded_from_bytes(
            audio_bytes,
            sample_rate=sample_rate,
            diarize=diarize,
            attempts=attempts,
            return_language=return_language,
        )


_PARAKEET_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
_PARAKEET_URL_DOWNLOAD_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
_PARAKEET_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


@timeit
def parakeet_prerecorded_from_bytes(
    audio_bytes: bytes,
    sample_rate: int = 16000,
    diarize: bool = True,
    attempts: int = 0,
    encoding: Optional[str] = None,
    channels: int = 1,
    language: Optional[str] = None,
    return_language: bool = False,
) -> Union[List[dict], Tuple[List[dict], str]]:
    logger.info(
        f'parakeet_prerecorded_from_bytes bytes_len={len(audio_bytes)} {sample_rate} {diarize} {attempts} encoding={encoding}'
    )

    api_url = os.getenv('HOSTED_PARAKEET_API_URL')
    if not api_url:
        raise ValueError('HOSTED_PARAKEET_API_URL environment variable is not set')

    try:
        if encoding:
            audio_bytes = _wrap_pcm_as_wav(audio_bytes, sample_rate, channels)

        files = {'file': ('audio.wav', BytesIO(audio_bytes), 'audio/wav')}

        use_v2 = diarize and os.getenv('PARAKEET_USE_V2', '1') == '1'
        if use_v2:
            url = api_url.rstrip('/') + '/v2/transcribe'
            data = {'diarize': 'true'}
        else:
            url = api_url.rstrip('/') + '/v1/transcribe'
            data = {}

        with httpx.Client(timeout=_PARAKEET_TIMEOUT) as client:
            response = client.post(url, files=files, data=data if data else None)
            if response.status_code == 404 and use_v2:
                url = api_url.rstrip('/') + '/v1/transcribe'
                response = client.post(url, files={'file': ('audio.wav', BytesIO(audio_bytes), 'audio/wav')})
                use_v2 = False
        response.raise_for_status()
        result = response.json()

        segments = result.get('segments', []) or []
        full_text = (result.get('text') or '').strip()

        if not segments and not full_text:
            if return_language:
                return [], language or 'en'
            return []

        spk_centroids: List[np.ndarray] = []
        spk_counts: List[int] = []

        words = []
        for seg in segments:
            text = (seg.get('text') or '').strip()
            if not text:
                continue
            start = float(seg.get('start', 0.0))
            end = float(seg.get('end', start))

            speaker_label = seg.get('speaker', '') if use_v2 else ''
            if not speaker_label:
                speaker_label = 'SPEAKER_00'
                if diarize:
                    speaker_label = _parakeet_assign_speaker_sync(
                        audio_bytes, sample_rate, start, end, spk_centroids, spk_counts
                    )

            if not speaker_label.startswith('SPEAKER_'):
                speaker_label = f'SPEAKER_{speaker_label}'

            words.append({'timestamp': [start, end], 'speaker': speaker_label, 'text': text})

        if not words and full_text:
            words.append({'timestamp': [0.0, 0.0], 'speaker': 'SPEAKER_00', 'text': full_text})

        if return_language:
            detected = result.get('detected_language') or language or 'en'
            return words, detected

        return words

    except Exception as e:
        logger.error(f'Parakeet prerecorded error: {e}')
        if attempts < 1:
            return parakeet_prerecorded_from_bytes(
                audio_bytes, sample_rate, diarize, attempts + 1, None, channels, language, return_language
            )
        raise RuntimeError(f'Parakeet transcription failed after {attempts + 1} attempts: {e}')


@timeit
def parakeet_prerecorded(
    audio_url: str,
    speakers_count: int = None,
    attempts: int = 0,
    return_language: bool = False,
    diarize: bool = True,
    language: Optional[str] = None,
) -> Union[List[dict], Tuple[List[dict], str]]:
    logger.info(f'parakeet_prerecorded url_len={len(audio_url)} {speakers_count} {attempts}')
    try:
        with httpx.Client(timeout=_PARAKEET_URL_DOWNLOAD_TIMEOUT) as client:
            with client.stream('GET', audio_url) as resp:
                resp.raise_for_status()
                content_length = resp.headers.get('content-length')
                if content_length and int(content_length) > _PARAKEET_MAX_DOWNLOAD_BYTES:
                    raise ValueError(
                        f'Audio file too large: {content_length} bytes (max {_PARAKEET_MAX_DOWNLOAD_BYTES})'
                    )
                chunks = []
                total = 0
                for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                    total += len(chunk)
                    if total > _PARAKEET_MAX_DOWNLOAD_BYTES:
                        raise ValueError(f'Audio download exceeded {_PARAKEET_MAX_DOWNLOAD_BYTES} bytes')
                    chunks.append(chunk)
                audio_bytes = b''.join(chunks)
                del chunks
        return parakeet_prerecorded_from_bytes(
            audio_bytes, diarize=diarize, attempts=attempts, return_language=return_language, language=language
        )
    except Exception as e:
        logger.error(f'Parakeet prerecorded (url) error: {e}')
        if attempts < 1:
            return parakeet_prerecorded(audio_url, speakers_count, attempts + 1, return_language, diarize, language)
        raise RuntimeError(f'Parakeet transcription (url) failed after {attempts + 1} attempts: {e}')


def _parakeet_assign_speaker_sync(
    wav_bytes: bytes,
    sample_rate: int,
    seg_start: float,
    seg_end: float,
    centroids: List[np.ndarray],
    counts: List[int],
) -> str:
    if seg_end - seg_start < 0.6:
        return 'SPEAKER_00'

    try:
        seg_pcm = _extract_pcm_segment_from_wav(wav_bytes, seg_start, seg_end)

        if len(seg_pcm) < int(sample_rate * 2 * 0.6):
            return 'SPEAKER_00'

        seg_wav = _wrap_pcm_as_wav(seg_pcm, sample_rate, 1)
        emb = extract_embedding_from_bytes(seg_wav)

        best_i, best_dist = -1, 1e9
        for i, centroid in enumerate(centroids):
            d = compare_embeddings(emb, centroid)
            if d < best_dist:
                best_i, best_dist = i, d

        if best_i >= 0 and best_dist < SPEAKER_MATCH_THRESHOLD:
            n = counts[best_i]
            centroids[best_i] = (centroids[best_i] * n + emb) / (n + 1)
            counts[best_i] = n + 1
            return f'SPEAKER_{best_i:02d}'

        centroids.append(emb)
        counts.append(1)
        return f'SPEAKER_{len(centroids) - 1:02d}'
    except Exception as e:
        logger.warning(f'Parakeet batch diarization failed, defaulting to SPEAKER_00: {e}')
        return 'SPEAKER_00'


def _extract_pcm_segment_from_wav(wav_bytes: bytes, start: float, end: float) -> bytes:
    buf = BytesIO(wav_bytes)
    with _wave.open(buf, 'rb') as wf:
        sr = wf.getframerate()
        start_frame = int(start * sr)
        end_frame = int(end * sr)
        wf.setpos(start_frame)
        return wf.readframes(end_frame - start_frame)


def _wrap_pcm_as_wav(pcm_bytes: bytes, sample_rate: int, channels: int, bits_per_sample: int = 16) -> bytes:
    buf = BytesIO()
    with _wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(bits_per_sample // 8)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


class ParakeetPrerecordedProvider(PrerecordedSTTProvider):

    def transcribe_url(
        self,
        audio_url,
        speakers_count=None,
        attempts=0,
        return_language=False,
        diarize=True,
        language=None,
        keywords=None,
    ):
        return parakeet_prerecorded(
            audio_url,
            speakers_count=speakers_count,
            attempts=attempts,
            return_language=return_language,
            diarize=diarize,
            language=language,
        )

    def transcribe_bytes(
        self,
        audio_bytes,
        sample_rate=16000,
        diarize=True,
        attempts=0,
        encoding=None,
        channels=1,
        language=None,
        return_language=False,
        keywords=None,
    ):
        return parakeet_prerecorded_from_bytes(
            audio_bytes,
            sample_rate=sample_rate,
            diarize=diarize,
            attempts=attempts,
            encoding=encoding,
            channels=channels,
            language=language,
            return_language=return_language,
        )


def get_prerecorded_provider(language: str = 'en') -> PrerecordedSTTProvider:
    """Factory: return the active provider based on STT_PRERECORDED_MODEL with language fallback."""
    base_lang = language.split('-')[0].split('_')[0].lower() if language else 'en'
    for m in stt_prerecorded_models:
        m = m.strip()
        if m == 'modulate-velma-2':
            return ModulatePrerecordedProvider()
        if m == 'parakeet':
            if base_lang in _parakeet_languages:
                return ParakeetPrerecordedProvider()
            continue
        if m.startswith('dg-'):
            return DeepgramPrerecordedProvider(model=m.replace('dg-', '', 1))
    return DeepgramPrerecordedProvider(model='nova-3')


# ---------------------------------------------------------------------------
# Convenience wrappers — delegate to the active provider
# ---------------------------------------------------------------------------


def prerecorded(
    audio_url: str,
    speakers_count: int = None,
    attempts: int = 0,
    return_language: bool = False,
    diarize: bool = True,
    language: Optional[str] = None,
    model: str = "nova-3",
    keywords: Optional[Sequence[str]] = None,
) -> Union[List[dict], Tuple[List[dict], str]]:
    """Route pre-recorded URL transcription through STT_PRERECORDED_MODEL."""
    provider = get_prerecorded_provider()
    return provider.transcribe_url(
        audio_url,
        speakers_count=speakers_count,
        attempts=attempts,
        return_language=return_language,
        diarize=diarize,
        language=language,
        keywords=keywords,
    )


def prerecorded_from_bytes(
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
    """Route pre-recorded bytes transcription through STT_PRERECORDED_MODEL."""
    provider = get_prerecorded_provider()
    return provider.transcribe_bytes(
        audio_bytes,
        sample_rate=sample_rate,
        diarize=diarize,
        attempts=attempts,
        encoding=encoding,
        channels=channels,
        language=language,
        return_language=return_language,
        keywords=keywords,
    )


def _words_cleaning(words: List[dict]):
    words_cleaned: List[dict] = []
    for i, w in enumerate(words):
        # if w['timestamp'][0] == w['timestamp'][1]:
        #     continue
        words_cleaned.append(
            {
                'start': round(w['timestamp'][0], 2),
                'end': round(w['timestamp'][1] or w['timestamp'][0] + 1, 2),
                'speaker': w['speaker'],
                'text': str(w['text']).strip(),
                'is_user': False,
                'person_id': None,
            }
        )

    for i, word in enumerate(words_cleaned):
        speaker = word['speaker']
        if not speaker:
            prev_chunk = words_cleaned[i - 1] if i > 0 else None
            next_chunk = words_cleaned[i + 1] if i < len(words_cleaned) - 1 else None
            prev_speaker = prev_chunk['speaker'] if prev_chunk else None
            next_speaker = next_chunk['speaker'] if next_chunk else None

            if prev_speaker and next_speaker:
                if prev_speaker == next_speaker:
                    speaker = prev_chunk['speaker']
                else:
                    secs_from_prev = word['start'] - prev_chunk['end'] if prev_chunk else 0
                    secs_to_next = next_chunk['start'] - word['end'] if next_chunk else 0
                    speaker = prev_speaker if secs_from_prev < secs_to_next else next_speaker
            elif prev_speaker:
                speaker = prev_speaker
            elif next_speaker:
                speaker = next_speaker
            else:
                speaker = 'SPEAKER_00'

            words_cleaned[i]['speaker'] = speaker

    # for chunk in words_cleaned:
    #     print(chunk)
    return words_cleaned


def _retrieve_user_speaker_id(words: list, skip_n_seconds: int):
    if not skip_n_seconds:
        return None

    user_speaker_id = defaultdict(int)
    for word in words:
        if word['start'] >= skip_n_seconds:
            break
        if not word['speaker']:
            continue
        user_speaker_id[word['speaker']] += 1

    user_speaker_id = max(user_speaker_id, key=user_speaker_id.get) if user_speaker_id else None
    return user_speaker_id


def _merge_segments(words: List[dict], skip_n_seconds: int, user_speaker_id: str):
    segments = []
    for word in words:
        if word['start'] < skip_n_seconds:
            continue
        word['is_user'] = word['speaker'] == user_speaker_id if word['speaker'] else False

        same_prev_speaker = word['speaker'] == segments[-1]['speaker'] if segments else False
        seconds_from_prev = word['start'] - segments[-1]['end'] if segments else 0

        # TODO: consider having a max segment size too
        if segments and same_prev_speaker and seconds_from_prev < 30:
            segments[-1]['end'] = word['end']
            segments[-1]['text'] += ' ' + word['text']
        else:
            segments.append(word)
    return segments


def _segments_as_objects(segments: List[dict]) -> List[TranscriptSegment]:
    if not segments:
        return []
    starts_at = segments[0]['start']
    return [
        TranscriptSegment(
            text=str(segment['text']).strip().capitalize(),
            speaker=segment['speaker'],
            is_user=segment['is_user'],
            person_id=None,
            start=round(segment['start'] - starts_at, 2),
            end=round(segment['end'] - starts_at, 2),
        )
        for segment in segments
    ]


def postprocess_words(
    words: List[dict], duration: int, skip_n_seconds: int = 0  # , merge_segments: bool = True
) -> List[TranscriptSegment]:
    words: List[dict] = _words_cleaning(words)
    user_speaker_id = _retrieve_user_speaker_id(words, skip_n_seconds)
    segments = _merge_segments(words, skip_n_seconds, user_speaker_id)
    segments = _segments_as_objects(segments)
    return segments
