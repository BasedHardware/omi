from utils.observability.sync_phases import observe_sync_call, sync_phase_timer
import logging
import os
import random
import time
import wave as _wave
from abc import ABC, abstractmethod
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from io import BytesIO
from math import ceil
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union, cast

import httpx
import numpy as np
from deepgram import DeepgramClient
from pydub import AudioSegment  # pydub is untyped

from config.prerecorded_stt import (
    PrerecordedSTTConfigurationError as _PrerecordedSTTConfigurationError,
    PrerecordedSTTService,
    TranscriptionOutcome,
    get_prerecorded_models,
    require_provider_environment,
)
from config.prerecorded_language import language_class, language_guard_enabled
from config.prerecorded_vendor import vendor_fail_fast_enabled
from config.stt_provider_policy import (
    MODULATE_PROVIDER,
    PARAKEET_PROVIDER,
    STTServingSurface,
    default_models_for_surface,
    normalized_stt_language,
    parakeet_supports_language,
    provider_is_enabled,
)
from models.transcript_segment import TranscriptSegment
from utils.log_sanitizer import sanitize_provider_error
from utils.observability.fallback import record_fallback
from utils.stt.stream_close import MODULATE_BUDGET_MARKERS
from utils.other.endpoints import timeit
from utils.stt.outcomes import TranscriptionFailure
from utils.stt.parakeet_request_metrics import observe_parakeet_request
from utils.stt.brand_terms import normalize_brand_terms
from utils.stt.speaker_clustering import select_speaker_cluster
from utils.stt.speaker_embedding import compare_embeddings, extract_embedding_from_bytes
from utils.stt.vendor_guard import (
    ENDPOINT_STT,
    ModulateQuotaError,
    breaker_allows,
    breaker_budget_exhausted,
    is_quota_error,
    record_breaker_other_failure,
    record_breaker_quota_error,
    record_breaker_success,
    record_vendor_burn,
)

_DG_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
_MODULATE_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)
_verification_deadline: ContextVar[Optional[float]] = ContextVar('verification_stt_deadline', default=None)

_held_single_attempt: ContextVar[bool] = ContextVar('held_stt_single_attempt', default=False)


@contextmanager
def held_single_attempt():
    """The durable held-piece coordinator alone owns paid dispatch retries."""
    token = _held_single_attempt.set(True)
    try:
        yield
    finally:
        _held_single_attempt.reset(token)


@contextmanager
def verification_stt_deadline(deadline: float):
    """Limit the prompt verifier's one provider attempt to its caller's budget."""
    token = _verification_deadline.set(deadline)
    try:
        yield
    finally:
        _verification_deadline.reset(token)


def _verification_timeout(default: httpx.Timeout | float) -> httpx.Timeout | float:
    deadline = _verification_deadline.get()
    if deadline is None:
        return default
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError('speaker tag verification deadline expired')
    return httpx.Timeout(remaining)


_MAX_PRE_RECORDED_SEGMENT_DURATION_SECONDS = 30.0

# Fail-fast retry backoff bounds (sync functions on executor threads).
MODULATE_FAIL_FAST_RETRY_SLEEP_MIN_SECONDS = 0.25
MODULATE_FAIL_FAST_RETRY_SLEEP_MAX_SECONDS = 0.75


def _wav_duration_seconds(audio_bytes: bytes) -> float:
    """Cheap WAV-header duration for burn accounting; unparseable audio is 0 seconds."""
    try:
        with _wave.open(BytesIO(audio_bytes)) as source:
            rate = source.getframerate()
            return source.getnframes() / rate if rate > 0 else 0.0
    except Exception:
        return 0.0


def _fail_fast_retry_sleep() -> None:
    time.sleep(random.uniform(MODULATE_FAIL_FAST_RETRY_SLEEP_MIN_SECONDS, MODULATE_FAIL_FAST_RETRY_SLEEP_MAX_SECONDS))


logger = logging.getLogger(__name__)

# Public compatibility export used by chat/router boundaries.
PrerecordedSTTConfigurationError = _PrerecordedSTTConfigurationError

# ---------------------------------------------------------------------------
# Provider-agnostic ABC — mirrors STTSocket for streaming
# ---------------------------------------------------------------------------


class PrerecordedSTTProvider(ABC):
    @abstractmethod
    def transcribe_url(
        self,
        audio_url: str,
        speakers_count: Optional[int] = None,
        attempts: int = 0,
        return_language: bool = False,
        diarize: bool = True,
        language: Optional[str] = None,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]: ...

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
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]: ...


def get_prerecorded_service(language: Optional[str] = 'en') -> Tuple[str, Optional[str], str]:
    """Route pre-recorded STT based on STT_PRERECORDED_MODEL env var.

    Iterates comma-separated models (same pattern as STT_SERVICE_MODELS for streaming).
    First model allowed by the central serving policy that supports the language
    wins. Disabled-provider tokens are ignored, then policy-owned defaults provide
    the serving fallback. A language no capability map claims falls through to Velma
    rather than failing selection.
    """
    from config.prerecorded_language import requires_multilingual

    base_lang = normalized_stt_language(language.strip() if isinstance(language, str) else None)
    if requires_multilingual(language) and base_lang in {'', 'und', 'multi', 'unknown'}:
        if provider_is_enabled(MODULATE_PROVIDER, STTServingSurface.PRERECORDED):
            return PrerecordedSTTService.MODULATE, 'multi', 'velma-2'
        raise TranscriptionFailure(TranscriptionOutcome.CONFIG_ERROR, retryable=False)
    base_lang = base_lang or 'en'

    def select(models: Sequence[str]) -> Optional[Tuple[str, Optional[str], str]]:
        for m in models:
            m = m.strip()
            if m == 'modulate-velma-2' and provider_is_enabled(MODULATE_PROVIDER, STTServingSurface.PRERECORDED):
                if base_lang in {'en', 'es', 'fr', 'de', 'it', 'pt', 'nl', 'ja', 'ko', 'zh'}:
                    return PrerecordedSTTService.MODULATE, base_lang, 'velma-2'
                continue
            if m == 'parakeet' and provider_is_enabled(PARAKEET_PROVIDER, STTServingSurface.PRERECORDED):
                if parakeet_supports_language(STTServingSurface.PRERECORDED, base_lang):
                    return PrerecordedSTTService.PARAKEET, base_lang, 'parakeet'
        return None

    selected = select(get_prerecorded_models())
    if selected is not None:
        return selected

    # A disabled/unknown preference must not become a provider call. Use the
    # deployment-validated, policy-owned defaults instead.
    selected = select(default_models_for_surface(STTServingSurface.PRERECORDED))
    if selected is not None:
        return selected

    # Velma's batch API detects the language itself — we never send a code — so it can
    # serve languages the capability maps omit, and values that are not codes at all.
    if provider_is_enabled(MODULATE_PROVIDER, STTServingSurface.PRERECORDED):
        return PrerecordedSTTService.MODULATE, 'multi', 'velma-2'

    # Only reachable with every pre-recorded provider disabled, which no retry resolves.
    raise TranscriptionFailure(TranscriptionOutcome.CONFIG_ERROR, retryable=False)


def _deepgram_client_for_request() -> DeepgramClient:
    """Fail closed: Deepgram retired 2026-08-27 (no contract); do not route or add keys."""
    logger.error('Deepgram pre-recorded STT is retired (2026-08-27, no contract); refusing the call')
    raise PrerecordedSTTConfigurationError(PrerecordedSTTService.DEEPGRAM, 'DEEPGRAM_RETIRED')


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
    speakers_count: Optional[int] = None,
    attempts: int = 0,
    return_language: bool = False,
    diarize: bool = True,
    language: Optional[str] = None,
    model: str = "nova-3",
    keywords: Optional[Sequence[str]] = None,
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
    """
    Transcribe audio using Deepgram's pre-recorded API.
    Returns words in same format as prerecorded for compatibility with existing postprocessing.

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
    logger.info(
        'deepgram_prerecorded url_len=%s speakers_count=%s attempt=%s',
        len(audio_url),
        speakers_count,
        attempts,
    )

    try:
        # 'multi' language means auto-detection
        is_multi = language == 'multi'
        should_detect_language = return_language or is_multi
        options: Dict[str, Any] = {
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

        rest_client: Any = _deepgram_client_for_request().listen.rest.v("1")
        response = rest_client.transcribe_url({"url": audio_url}, options, timeout=_DG_TIMEOUT)

        # Extract words from response
        result: Dict[str, Any] = response.to_dict()
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

        # Convert Deepgram format to prerecorded compatible format
        # Deepgram: {word, start, end, confidence, punctuated_word, speaker (int)}
        # Expected: {timestamp: [start, end], speaker: 'SPEAKER_XX', text: 'word'}
        words: List[Dict[str, Any]] = []
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
        logger.error('Deepgram prerecorded error exception_type=%s attempt=%s', type(e).__name__, attempts + 1)
        if attempts < 1 and not _held_single_attempt.get():
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
        raise RuntimeError(f'Deepgram transcription failed after {attempts + 1} attempts') from e


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
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
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
        options: Dict[str, Any] = {
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
        source: Dict[str, Any] = {"buffer": audio_buffer, "mimetype": mimetype}

        rest_client: Any = _deepgram_client_for_request().listen.rest.v("1")
        response = rest_client.transcribe_file(source, options, timeout=_verification_timeout(_DG_TIMEOUT))

        # Extract words from response
        result: Dict[str, Any] = response.to_dict()
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
        words: List[Dict[str, Any]] = []
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
        logger.error(
            'Deepgram prerecorded from bytes error exception_type=%s attempt=%s',
            type(e).__name__,
            attempts + 1,
        )
        if attempts < 1 and _verification_deadline.get() is None and not _held_single_attempt.get():
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
        raise RuntimeError(f'Deepgram transcription failed after {attempts + 1} attempts') from e


def _modulate_budget_refusal(status_code: int, body: str) -> bool:
    """True when Velma's batch answer is account-budget, not a transient error.

    402 is credits regardless of wording; 429 is budget only when the body
    carries a budget marker such as "insufficient credits" — the answer
    Velma-2 gives when the account is out of credits (2026-10-22 outage: sync
    jobs recorded it as a retryable upstream_error under provider=unknown).
    The body is matched, never logged or labeled.
    """

    if status_code == 402:
        return True
    return status_code == 429 and any(marker in body.lower() for marker in MODULATE_BUDGET_MARKERS)


@timeit
def modulate_prerecorded_from_bytes(
    audio_bytes: bytes,
    sample_rate: int = 16000,
    diarize: bool = True,
    attempts: int = 0,
    return_language: bool = False,
    language: Optional[str] = None,
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
    logger.info(f'modulate_prerecorded_from_bytes bytes_len={len(audio_bytes)} {sample_rate} {diarize} {attempts}')

    require_provider_environment(PrerecordedSTTService.MODULATE)
    api_key = os.environ['MODULATE_API_KEY']
    fail_fast = vendor_fail_fast_enabled()
    if fail_fast and not breaker_allows(ENDPOINT_STT):
        if breaker_budget_exhausted(ENDPOINT_STT):
            # Same typed terminal outcome as the refusal that opened it.
            raise TranscriptionFailure(
                TranscriptionOutcome.PROVIDER_BUDGET_EXHAUSTED,
                provider=PrerecordedSTTService.MODULATE,
                retryable=False,
            )
        raise ModulateQuotaError('Modulate transcription failed: vendor circuit breaker open')

    posted = False
    post_2xx = False
    burn_seconds = 0.0

    try:
        url = 'https://modulate-developer-apis.com/api/velma-2-stt-batch'
        headers = {'X-API-Key': api_key}
        files = {'upload_file': ('audio.wav', BytesIO(audio_bytes), 'audio/wav')}
        data = {'speaker_diarization': str(diarize).lower()}

        with httpx.Client(timeout=_verification_timeout(300)) as client:
            burn_seconds = _wav_duration_seconds(audio_bytes)
            posted = True
            response = client.post(url, headers=headers, files=files, data=data)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            if _modulate_budget_refusal(response.status_code, response.text):
                record_vendor_burn(ENDPOINT_STT, 'error', burn_seconds)
                if fail_fast:
                    record_breaker_quota_error(ENDPOINT_STT, budget=True)
                # Out-of-credits is deterministic until the account is funded:
                # terminal and typed, so the sync job counts
                # outcome=provider_budget_exhausted provider=modulate instead
                # of retrying a dead account into upstream_error.
                raise TranscriptionFailure(
                    TranscriptionOutcome.PROVIDER_BUDGET_EXHAUSTED,
                    provider=PrerecordedSTTService.MODULATE,
                    retryable=False,
                ) from error
            raise
        post_2xx = True
        if fail_fast:
            record_breaker_success(ENDPOINT_STT)
        # The POST itself reached the vendor and was accepted; a later shape
        # validation failure is not a second burned POST.
        record_vendor_burn(ENDPOINT_STT, 'ok', burn_seconds)
        result = response.json()

        # Velma's batch success shape carries utterances (a list, empty for silence)
        # beside text ("" for silence) and duration_ms. A 2xx body without the list
        # (a JSON error envelope, a null, a bare string) is not a no-speech verdict,
        # and neither is {"utterances": []} alone, which any unrelated 2xx envelope
        # could carry. Silence therefore also needs text as a str or duration_ms as a
        # number — one of them, not both, so the older host this client targets is
        # held to no more than the docs promise. A non-empty list is parsed as
        # before. Raise so callers keep the audio as retry material and held-piece
        # recovery never checkpoints the reply as a completed empty result. See #23081.
        if not isinstance(result, dict) or not isinstance(result.get('utterances'), list):
            raise RuntimeError('Modulate response must carry an utterances list')

        utterances = result['utterances']
        if not utterances:
            has_text = isinstance(result.get('text'), str)
            duration_ms = result.get('duration_ms')
            has_duration = isinstance(duration_ms, (int, float)) and not isinstance(duration_ms, bool)
            if not (has_text or has_duration):
                raise RuntimeError('Modulate response with empty utterances must carry text or duration_ms')
            if has_text and result['text'].strip():
                # Transcript text without utterances contradicts itself; never settle it as silence.
                raise RuntimeError('Modulate response with empty utterances must not carry transcript text')
            if return_language:
                return [], language or 'multi'
            return []

        words: List[Dict[str, Any]] = []
        language_votes: List[Tuple[str, int, float]] = []
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
                lang = lang.split('-')[0].split('_')[0].lower()
                language_votes.append((lang, len(text.split()), max(0, duration_ms)))

        top_text = result.get('text')
        if not words and isinstance(top_text, str) and top_text.strip():
            # Transcript text with only blank utterances is contradictory; never return it as silence.
            raise RuntimeError('Modulate response with blank utterances must not carry transcript text')

        if return_language:
            # Tiny acknowledgments are noisy detection evidence. Only use them
            # when the provider supplied no longer transcribed utterance.
            has_long_utterance = any(len(utt.get('text', '').split()) >= 3 for utt in utterances)
            totals: Dict[str, Tuple[int, float]] = {}
            for lang, word_count, duration in language_votes:
                if has_long_utterance and word_count < 3:
                    continue
                count, seconds = totals.get(lang, (0, 0))
                totals[lang] = (count + word_count, seconds + duration)
            detected_language = max(totals, key=lambda lang: totals[lang]) if totals else language or 'multi'
            return words, detected_language

        return words

    except TranscriptionFailure:
        # Typed terminal failures never retry and never re-wrap into the
        # generic RuntimeError (which erases the outcome the sync job counts).
        raise
    except Exception as e:
        if posted and not post_2xx:
            record_vendor_burn(ENDPOINT_STT, 'error', burn_seconds)
        logger.error('Modulate prerecorded error exception_type=%s attempt=%s', type(e).__name__, attempts + 1)
        if fail_fast:
            if is_quota_error(e):
                record_breaker_quota_error(ENDPOINT_STT)
                # Quota/auth rejections are terminal: the account is out of credits,
                # retrying only burns more vendor quota. The prefix keeps callers and
                # tests matching 'Modulate transcription failed' working.
                raise ModulateQuotaError('Modulate transcription failed: vendor quota error') from e
            if posted and not post_2xx:
                record_breaker_other_failure(ENDPOINT_STT)
            # Transient failures (5xx, timeouts, transport, malformed bodies) get at
            # most one retry — 2 paid POSTs total — behind a short jittered backoff.
            if attempts < 1 and _verification_deadline.get() is None and not _held_single_attempt.get():
                _fail_fast_retry_sleep()
                return modulate_prerecorded_from_bytes(
                    audio_bytes, sample_rate, diarize, attempts + 1, return_language, language
                )
            raise RuntimeError(f'Modulate transcription failed after {attempts + 1} attempts') from e
        if attempts < 2 and _verification_deadline.get() is None and not _held_single_attempt.get():
            return modulate_prerecorded_from_bytes(
                audio_bytes, sample_rate, diarize, attempts + 1, return_language, language
            )
        raise RuntimeError(f'Modulate transcription failed after {attempts + 1} attempts') from e


@timeit
def modulate_prerecorded(
    audio_url: str,
    speakers_count: Optional[int] = None,
    attempts: int = 0,
    return_language: bool = False,
    diarize: bool = True,
    language: Optional[str] = None,
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
    logger.info(
        'modulate_prerecorded url_len=%s speakers_count=%s attempt=%s', len(audio_url), speakers_count, attempts
    )
    if vendor_fail_fast_enabled():
        # Only the download is retried; the paid bytes path runs once per URL call
        # (its own single transient retry is bounded to 2 Modulate POSTs).
        audio_bytes = b''
        for download_attempt in (0, 1):
            try:
                with httpx.Client(timeout=_MODULATE_TIMEOUT) as client:
                    resp = client.get(audio_url)
                    resp.raise_for_status()
                    audio_bytes = resp.content
                break
            except Exception as e:
                logger.error(
                    'Modulate prerecorded (url) download error exception_type=%s attempt=%s',
                    type(e).__name__,
                    download_attempt + 1,
                )
                if download_attempt == 0 and attempts < 1 and not _held_single_attempt.get():
                    continue
                raise RuntimeError(f'Modulate transcription (url) failed after {attempts + 1} attempts') from e
        return modulate_prerecorded_from_bytes(
            audio_bytes, diarize=diarize, attempts=attempts, return_language=return_language, language=language
        )
    try:
        with httpx.Client(timeout=_MODULATE_TIMEOUT) as client:
            resp = client.get(audio_url)
            resp.raise_for_status()
            audio_bytes = resp.content
        return modulate_prerecorded_from_bytes(
            audio_bytes, diarize=diarize, attempts=attempts, return_language=return_language, language=language
        )
    except TranscriptionFailure:
        raise
    except Exception as e:
        logger.error(
            'Modulate prerecorded (url) error exception_type=%s attempt=%s',
            type(e).__name__,
            attempts + 1,
        )
        if attempts < 1 and not _held_single_attempt.get():
            return modulate_prerecorded(audio_url, speakers_count, attempts + 1, return_language, diarize, language)
        raise RuntimeError(f'Modulate transcription (url) failed after {attempts + 1} attempts') from e


# ---------------------------------------------------------------------------
# Provider implementations
# ---------------------------------------------------------------------------


class DeepgramPrerecordedProvider(PrerecordedSTTProvider):
    def __init__(self, model: str = 'nova-3'):
        self._model = model

    def transcribe_url(
        self,
        audio_url: str,
        speakers_count: Optional[int] = None,
        attempts: int = 0,
        return_language: bool = False,
        diarize: bool = True,
        language: Optional[str] = None,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
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
        audio_bytes: bytes,
        sample_rate: int = 16000,
        diarize: bool = True,
        attempts: int = 0,
        encoding: Optional[str] = None,
        channels: int = 1,
        language: Optional[str] = None,
        return_language: bool = False,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
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
            return 'multi'
        return language.split('-')[0].split('_')[0].lower()

    def transcribe_url(
        self,
        audio_url: str,
        speakers_count: Optional[int] = None,
        attempts: int = 0,
        return_language: bool = False,
        diarize: bool = True,
        language: Optional[str] = None,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
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
        audio_bytes: bytes,
        sample_rate: int = 16000,
        diarize: bool = True,
        attempts: int = 0,
        encoding: Optional[str] = None,
        channels: int = 1,
        language: Optional[str] = None,
        return_language: bool = False,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
        if encoding:
            audio_bytes = _wrap_pcm_as_wav(audio_bytes, sample_rate, channels)
        return modulate_prerecorded_from_bytes(
            audio_bytes,
            sample_rate=sample_rate,
            diarize=diarize,
            attempts=attempts,
            return_language=return_language,
            language=self._normalize_lang(language),
        )


_PARAKEET_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
_PARAKEET_URL_DOWNLOAD_TIMEOUT = httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0)
_PARAKEET_MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024  # 100 MB
_PARAKEET_CONTAINER_MIME_FORMATS = {
    'audio/webm': 'webm',
    'video/webm': 'webm',
    'audio/mp4': 'mp4',
    'video/mp4': 'mp4',
}


class ParakeetAudioDecodeError(ValueError):
    """A downloaded browser container cannot be made safe for Parakeet."""


def _normalize_parakeet_download(audio_bytes: bytes, content_type: str | None) -> bytes:
    """Convert browser containers to WAV before Parakeet's WAV-only batch path."""

    media_type = (content_type or '').split(';', 1)[0].strip().lower()
    container_format = _PARAKEET_CONTAINER_MIME_FORMATS.get(media_type)
    if container_format is None:
        return audio_bytes

    try:
        decoded_audio = AudioSegment.from_file(BytesIO(audio_bytes), format=container_format)
        wav_buffer = BytesIO()
        decoded_audio.export(wav_buffer, format='wav')
        wav_bytes = wav_buffer.getvalue()
        del decoded_audio
        del wav_buffer
        return wav_bytes
    except Exception as error:
        raise ParakeetAudioDecodeError('Browser audio container could not be decoded') from error


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
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
    logger.info(
        f'parakeet_prerecorded_from_bytes bytes_len={len(audio_bytes)} {sample_rate} {diarize} {attempts} encoding={encoding}'
    )

    require_provider_environment(PrerecordedSTTService.PARAKEET)
    api_url = os.environ['HOSTED_PARAKEET_API_URL']

    original_audio_bytes = audio_bytes
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

        with httpx.Client(timeout=_verification_timeout(_PARAKEET_TIMEOUT)) as client:
            with observe_parakeet_request('v2' if use_v2 else 'v1'):
                response = observe_sync_call('parakeet', client.post, url, files=files, data=data if data else None)
            if response.status_code == 404 and use_v2:
                url = api_url.rstrip('/') + '/v1/transcribe'
                client.timeout = _verification_timeout(_PARAKEET_TIMEOUT)
                with observe_parakeet_request('v1'):
                    response = observe_sync_call(
                        'parakeet', client.post, url, files={'file': ('audio.wav', BytesIO(audio_bytes), 'audio/wav')}
                    )
                use_v2 = False
        response.raise_for_status()
        payload: Any = response.json()

        # A Parakeet result always carries both keys, even for silence ({"text": "",
        # "segments": []}). A 200 body missing either key, or carrying them with the
        # wrong type, is a degraded or foreign responder (misrouted ILB, proxy error
        # shell, partial envelope), not a no-speech verdict. Raise so the sync job
        # stays truthful, clients keep the audio as retry material instead of
        # marking the WAL synced and discarding it, and held-piece recovery never
        # checkpoints the reply as a completed empty result. See #9586, #23081.
        if not isinstance(payload, dict) or 'segments' not in payload or 'text' not in payload:
            raise RuntimeError('Parakeet response must carry both segments and text')

        result: Dict[str, Any] = cast(Dict[str, Any], payload)
        raw_segments = result['segments']
        if not isinstance(raw_segments, list):
            raise RuntimeError('Parakeet response segments must be a list')
        raw_text = result['text']
        if raw_text is not None and not isinstance(raw_text, str):
            raise RuntimeError('Parakeet response text must be a string')
        segments: List[Dict[str, Any]] = list(raw_segments)  # type: ignore[reportUnknownArgumentType]  # untyped external JSON
        full_text = (raw_text or '').strip()

        if not segments and not full_text:
            if return_language:
                return [], language or 'en'
            return []

        spk_centroids: List[np.ndarray[Any, Any]] = []
        spk_counts: List[int] = []

        words: List[Dict[str, Any]] = []
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
        logger.error('Parakeet prerecorded error exception_type=%s attempt=%s', type(e).__name__, attempts + 1)
        if attempts < 1 and _verification_deadline.get() is None and not _held_single_attempt.get():
            return parakeet_prerecorded_from_bytes(
                original_audio_bytes, sample_rate, diarize, attempts + 1, encoding, channels, language, return_language
            )
        raise RuntimeError(f'Parakeet transcription failed after {attempts + 1} attempts') from e


@timeit
def parakeet_prerecorded(
    audio_url: str,
    speakers_count: Optional[int] = None,
    attempts: int = 0,
    return_language: bool = False,
    diarize: bool = True,
    language: Optional[str] = None,
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
    logger.info(f'parakeet_prerecorded url_len={len(audio_url)} {speakers_count} {attempts}')
    try:
        with sync_phase_timer('gcs'), httpx.Client(timeout=_PARAKEET_URL_DOWNLOAD_TIMEOUT) as client:
            with client.stream('GET', audio_url) as resp:
                resp.raise_for_status()
                content_length = resp.headers.get('content-length')
                if content_length and int(content_length) > _PARAKEET_MAX_DOWNLOAD_BYTES:
                    raise ValueError(
                        f'Audio file too large: {content_length} bytes (max {_PARAKEET_MAX_DOWNLOAD_BYTES})'
                    )
                chunks: List[bytes] = []
                total = 0
                for chunk in resp.iter_bytes(chunk_size=1024 * 1024):
                    total += len(chunk)
                    if total > _PARAKEET_MAX_DOWNLOAD_BYTES:
                        raise ValueError(f'Audio download exceeded {_PARAKEET_MAX_DOWNLOAD_BYTES} bytes')
                    chunks.append(chunk)
                audio_bytes = b''.join(chunks)
                del chunks
                audio_bytes = _normalize_parakeet_download(audio_bytes, resp.headers.get('content-type'))
        return parakeet_prerecorded_from_bytes(
            audio_bytes, diarize=diarize, attempts=attempts, return_language=return_language, language=language
        )
    except ParakeetAudioDecodeError:
        raise
    except Exception as e:
        logger.error(
            'Parakeet prerecorded (url) error exception_type=%s attempt=%s',
            type(e).__name__,
            attempts + 1,
        )
        if attempts < 1 and not _held_single_attempt.get():
            return parakeet_prerecorded(audio_url, speakers_count, attempts + 1, return_language, diarize, language)
        raise RuntimeError(f'Parakeet transcription (url) failed after {attempts + 1} attempts') from e


def _parakeet_assign_speaker_sync(
    wav_bytes: bytes,
    sample_rate: int,
    seg_start: float,
    seg_end: float,
    centroids: List[np.ndarray[Any, Any]],
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

        best_i, create_new, _, capped = select_speaker_cluster(emb, centroids, compare_embeddings)
        if not create_new:
            if capped:
                # Forced by the cap: the embedding missed every centroid, so keep
                # it out of the running mean and report the degraded merge.
                record_fallback(
                    component='other',
                    from_mode='new_speaker_centroid',
                    to_mode='nearest_centroid',
                    reason='capacity_full',
                    outcome='degraded',
                    log=logger,
                )
                return f'SPEAKER_{best_i:02d}'
            n = counts[best_i]
            centroids[best_i] = (centroids[best_i] * n + emb) / (n + 1)
            counts[best_i] = n + 1
            return f'SPEAKER_{best_i:02d}'

        centroids.append(emb)
        counts.append(1)
        return f'SPEAKER_{best_i:02d}'
    except Exception as e:
        logger.warning('Parakeet batch diarization failed, defaulting to SPEAKER_00: %s', sanitize_provider_error(e))
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
        audio_url: str,
        speakers_count: Optional[int] = None,
        attempts: int = 0,
        return_language: bool = False,
        diarize: bool = True,
        language: Optional[str] = None,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
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
        audio_bytes: bytes,
        sample_rate: int = 16000,
        diarize: bool = True,
        attempts: int = 0,
        encoding: Optional[str] = None,
        channels: int = 1,
        language: Optional[str] = None,
        return_language: bool = False,
        keywords: Optional[Sequence[str]] = None,
    ) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
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


def get_prerecorded_provider(
    language: Optional[str] = 'en', *, selected_service: Optional[Tuple[str, Optional[str], str]] = None
) -> PrerecordedSTTProvider:
    """Construct exactly the language-aware provider selected for telemetry."""
    # Offline harness sessions swap the provider for a deterministic stub
    # (selection/telemetry still resolve normally above them). Imported lazily:
    # the stub module imports this one for the provider ABC.
    from utils.stt.prerecorded_stub import PrerecordedStubProvider, prerecorded_stub_enabled

    if prerecorded_stub_enabled():
        return PrerecordedStubProvider()
    service, _provider_language, model = selected_service or get_prerecorded_service(language)
    if service == PrerecordedSTTService.MODULATE:
        return ModulatePrerecordedProvider()
    if service == PrerecordedSTTService.PARAKEET:
        return ParakeetPrerecordedProvider()
    raise RuntimeError(f'Unsupported serving pre-recorded STT provider {service!r} ({model!r})')


# ---------------------------------------------------------------------------
# Convenience wrappers — delegate to the active provider
# ---------------------------------------------------------------------------


def prerecorded(
    audio_url: str,
    speakers_count: Optional[int] = None,
    attempts: int = 0,
    return_language: bool = False,
    diarize: bool = True,
    language: Optional[str] = None,
    model: str = "nova-3",
    keywords: Optional[Sequence[str]] = None,
    *,
    selected_service: Optional[Tuple[str, Optional[str], str]] = None,
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
    """Route pre-recorded URL transcription through STT_PRERECORDED_MODEL."""
    if selected_service is None and language_guard_enabled() and language_class(language) == 'unknown':
        from utils.stt.batch_language import resolve_url

        selected_service = resolve_url(language, audio_url, selector=get_prerecorded_service)
    provider = (
        get_prerecorded_provider(language, selected_service=selected_service)
        if selected_service is not None
        else get_prerecorded_provider(language)
    )
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
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], str]]:
    """Route pre-recorded bytes transcription through STT_PRERECORDED_MODEL."""
    from utils.stt.batch_language import resolve_language, select_decision

    decision = resolve_language(language, audio_bytes, sample_rate=sample_rate, channels=channels, encoding=encoding)
    resolved = decision.language if decision.parakeet_safe else language
    if not language_guard_enabled() or language_class(language) != 'unknown':
        resolved = language
    selected = select_decision(language, decision, get_prerecorded_service)
    provider = get_prerecorded_provider(resolved, selected_service=selected)
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


def _words_cleaning(words: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    words_cleaned: List[Dict[str, Any]] = []
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
                    speaker = prev_speaker
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


def _retrieve_user_speaker_id(words: List[Dict[str, Any]], skip_n_seconds: int) -> Optional[str]:
    if not skip_n_seconds:
        return None

    user_speaker_id: defaultdict[str, int] = defaultdict(int)
    for word in words:
        if word['start'] >= skip_n_seconds:
            break
        if not word['speaker']:
            continue
        user_speaker_id[word['speaker']] += 1

    if not user_speaker_id:
        return None
    return max(user_speaker_id, key=user_speaker_id.get)  # type: ignore[reportUnknownVariableType,reportUnknownArgumentType]  # pyright can't infer defaultdict key type


def _merge_segments(
    words: List[Dict[str, Any]], skip_n_seconds: int, user_speaker_id: Optional[str]
) -> List[Dict[str, Any]]:
    def split_long_entry(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
        start = float(entry['start'])
        end = float(entry['end'])
        duration = end - start
        if duration <= _MAX_PRE_RECORDED_SEGMENT_DURATION_SECONDS:
            return [entry]

        text_words = str(entry['text']).split()
        if not text_words:
            return [entry]

        chunk_count = min(ceil(duration / _MAX_PRE_RECORDED_SEGMENT_DURATION_SECONDS), len(text_words))
        chunk_duration = duration / chunk_count
        words_per_chunk, remainder = divmod(len(text_words), chunk_count)
        chunks: List[Dict[str, Any]] = []
        text_offset = 0
        for index in range(chunk_count):
            chunk_word_count = words_per_chunk + (1 if index < remainder else 0)
            next_text_offset = text_offset + chunk_word_count
            chunk = dict(entry)
            chunk['start'] = start + index * chunk_duration
            chunk['end'] = end if index == chunk_count - 1 else start + (index + 1) * chunk_duration
            chunk['text'] = ' '.join(text_words[text_offset:next_text_offset])
            chunks.append(chunk)
            text_offset = next_text_offset
        return chunks

    segments: List[Dict[str, Any]] = []
    for word in words:
        if word['start'] < skip_n_seconds:
            continue
        for entry in split_long_entry(word):
            entry['is_user'] = entry['speaker'] == user_speaker_id if entry['speaker'] else False

            same_prev_speaker = entry['speaker'] == segments[-1]['speaker'] if segments else False
            seconds_from_prev = entry['start'] - segments[-1]['end'] if segments else 0

            within_max_duration = (
                entry['end'] - segments[-1]['start'] < _MAX_PRE_RECORDED_SEGMENT_DURATION_SECONDS if segments else False
            )
            if (
                segments
                and same_prev_speaker
                and seconds_from_prev < _MAX_PRE_RECORDED_SEGMENT_DURATION_SECONDS
                and within_max_duration
            ):
                segments[-1]['end'] = entry['end']
                segments[-1]['text'] += ' ' + entry['text']
            else:
                segments.append(entry)
    return segments


def _capitalize_first(text: str) -> str:
    """Capitalize only the first character; providers already return cased names, acronyms and "I"."""
    return text[:1].capitalize() + text[1:]


def _segments_as_objects(segments: List[Dict[str, Any]]) -> List[TranscriptSegment]:
    if not segments:
        return []
    starts_at = segments[0]['start']
    return [
        TranscriptSegment(
            text=normalize_brand_terms(_capitalize_first(str(segment['text']).strip())),
            speaker=segment['speaker'],
            is_user=segment['is_user'],
            person_id=None,
            start=round(segment['start'] - starts_at, 2),
            end=round(segment['end'] - starts_at, 2),
        )
        for segment in segments
    ]


def postprocess_words(
    words: List[Dict[str, Any]], duration: int, skip_n_seconds: int = 0  # , merge_segments: bool = True
) -> List[TranscriptSegment]:
    cleaned_words = _words_cleaning(words)
    user_speaker_id = _retrieve_user_speaker_id(cleaned_words, skip_n_seconds)
    segments = _merge_segments(cleaned_words, skip_n_seconds, user_speaker_id)
    segments_objs = _segments_as_objects(segments)
    return segments_objs
