import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

import httpx
from deepgram import DeepgramClient, DeepgramClientOptions

from models.transcript_segment import ProviderTranscriptResult, TranscriptSegment
from utils.stt.assemblyai_adapter import AssemblyAIAsyncTranscriptionProvider, AssemblyAITimeoutError
from utils.stt.conversation_reconstructor import reconstruct_conversation
from utils.stt.deepgram_adapter import DeepgramPrerecordedTranscriptionProvider
from utils.stt.deepgram_adapter import provider_result_to_legacy_words
from utils.stt.provider_costs import estimate_prerecorded_provider_cost_usd
from utils.stt.providers import (
    BackgroundProviderMode,
    STTProviderName,
    STTWorkload,
    assemblyai_prerecorded_fallback_enabled,
    get_background_provider_mode,
    get_fallback_prerecorded_provider_name,
    get_prerecorded_provider_name,
)
from utils.stt.deepgram_config import get_deepgram_model_for_language

try:
    from utils.byok import get_byok_key
except ImportError:
    get_byok_key = None

try:
    from database.transcription_provider_usage import (
        create_provider_run as _db_create_provider_run,
        finalize_provider_run as _db_finalize_provider_run,
        update_provider_run_identity_metrics as _db_update_provider_run_identity_metrics,
    )

    _PROVIDER_USAGE_IMPORT_ERROR = None
except ImportError as e:
    _db_create_provider_run = None
    _db_finalize_provider_run = None
    _db_update_provider_run_identity_metrics = None
    _PROVIDER_USAGE_IMPORT_ERROR = e

logger = logging.getLogger(__name__)

_DG_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)
_DEEPGRAM_OPTIONS = DeepgramClientOptions(options={"keepalive": "true"})
_DEEPGRAM_CLIENT = DeepgramClient(os.getenv('DEEPGRAM_API_KEY'), _DEEPGRAM_OPTIONS)
_LOCAL_CLUSTER_SPLIT_MARKER = '::local_part:'
_UNKNOWN_SPEAKER_STATES = {'unknown', 'unassigned', 'legacy_ambiguous'}


def create_provider_run(**kwargs) -> str:
    if _db_create_provider_run is None:
        raise _PROVIDER_USAGE_IMPORT_ERROR
    return _db_create_provider_run(**kwargs)


def finalize_provider_run(**kwargs) -> None:
    if _db_finalize_provider_run is None:
        raise _PROVIDER_USAGE_IMPORT_ERROR
    _db_finalize_provider_run(**kwargs)


def summarize_identity_confidences(confidences):
    summary = {}
    for confidence in confidences:
        bucket = _identity_confidence_bucket(confidence)
        summary[bucket] = summary.get(bucket, 0) + 1
    return summary


def _identity_confidence_bucket(confidence: Optional[float]) -> str:
    if confidence is None:
        return 'unknown'
    if confidence >= 0.90:
        return 'very_high'
    if confidence >= 0.75:
        return 'high'
    if confidence >= 0.50:
        return 'medium'
    return 'low'


def _deepgram_prerecorded_provider():
    return DeepgramPrerecordedTranscriptionProvider(_deepgram_client_for_request, _DG_TIMEOUT)


def _assemblyai_prerecorded_provider():
    byok = get_byok_key('assemblyai') if get_byok_key else None
    return AssemblyAIAsyncTranscriptionProvider(api_key=byok)


def resolve_prerecorded_provider_for_request(workload: STTWorkload) -> STTProviderName:
    """Pick prerecorded STT provider for this request, respecting BYOK headers.

    When env flags select AssemblyAI but the BYOK user did not supply an Assembly
    key, use Deepgram BYOK instead of Omi's server Assembly key. When server
    AssemblyAI credentials are absent, skip directly to Deepgram if fallback is
    enabled and a usable Deepgram key is available.
    """
    selected = get_prerecorded_provider_name(workload)
    if selected != STTProviderName.assemblyai:
        return selected
    assemblyai_byok = get_byok_key('assemblyai') if get_byok_key else None
    deepgram_byok = get_byok_key('deepgram') if get_byok_key else None
    if assemblyai_byok:
        return STTProviderName.assemblyai
    if deepgram_byok and assemblyai_prerecorded_fallback_enabled():
        return STTProviderName.deepgram
    if os.getenv('ASSEMBLYAI_API_KEY'):
        return STTProviderName.assemblyai
    if assemblyai_prerecorded_fallback_enabled() and _has_deepgram_key_for_request():
        return STTProviderName.deepgram
    return STTProviderName.assemblyai


def _has_deepgram_key_for_request() -> bool:
    return bool((get_byok_key('deepgram') if get_byok_key else None) or os.getenv('DEEPGRAM_API_KEY'))


def _has_assemblyai_key_for_request() -> bool:
    return bool((get_byok_key('assemblyai') if get_byok_key else None) or os.getenv('ASSEMBLYAI_API_KEY'))


def _deepgram_client_for_request() -> DeepgramClient:
    byok = get_byok_key('deepgram') if get_byok_key else None
    if byok:
        return DeepgramClient(byok, _DEEPGRAM_OPTIONS)
    return _DEEPGRAM_CLIENT


@dataclass
class PrerecordedTranscriptionResponse:
    result: ProviderTranscriptResult
    detected_language: Optional[str]
    segments: List[TranscriptSegment]
    words: List[dict]
    run_id: Optional[str]


@dataclass(frozen=True)
class BackgroundProviderPolicy:
    mode: BackgroundProviderMode
    primary_provider: STTProviderName
    effective_provider: Optional[STTProviderName]
    fallback_provider: Optional[STTProviderName]
    fallback_enabled: bool
    fallback_available: bool
    enabled: bool
    reason: Optional[str]


class ProviderTranscriptionRetriesExhausted(RuntimeError):
    def __init__(self, provider_error: Exception, retry_count: int):
        super().__init__(str(provider_error))
        self.provider_error = provider_error
        self.retry_count = retry_count


def resolve_prerecorded_language_model(language: Optional[str]) -> Tuple[str, str]:
    return get_deepgram_model_for_language(language or 'multi')


def resolve_background_provider_policy() -> BackgroundProviderPolicy:
    mode = get_background_provider_mode()
    primary_provider = get_prerecorded_provider_name(STTWorkload.background)
    effective_provider = resolve_prerecorded_provider_for_request(STTWorkload.background)
    fallback_provider = get_fallback_prerecorded_provider_name(primary_provider, STTWorkload.background)

    assemblyai_key_available = _has_assemblyai_key_for_request()
    deepgram_key_available = _has_deepgram_key_for_request()
    fallback_available = fallback_provider == STTProviderName.deepgram and deepgram_key_available

    usable_provider = None
    reason = None
    if effective_provider == STTProviderName.assemblyai:
        if assemblyai_key_available:
            usable_provider = STTProviderName.assemblyai
        elif fallback_available:
            usable_provider = STTProviderName.deepgram
            reason = 'fallback_deepgram_available'
        else:
            reason = 'missing_assemblyai_api_key'
    elif effective_provider == STTProviderName.deepgram:
        if deepgram_key_available:
            usable_provider = STTProviderName.deepgram
            if mode == BackgroundProviderMode.shadow_only:
                reason = 'shadow_only'
        else:
            reason = 'missing_deepgram_api_key'
    else:
        reason = 'no_usable_batch_provider'

    return BackgroundProviderPolicy(
        mode=mode,
        primary_provider=primary_provider,
        effective_provider=usable_provider,
        fallback_provider=fallback_provider,
        fallback_enabled=fallback_provider is not None,
        fallback_available=fallback_available,
        enabled=usable_provider is not None,
        reason=reason,
    )


def transcribe_url(
    audio_url: str,
    workload: STTWorkload,
    uid: Optional[str] = None,
    conversation_id: Optional[str] = None,
    speakers_count: int = None,
    return_language: bool = False,
    diarize: bool = True,
    language: Optional[str] = None,
    model: str = 'nova-3',
    keywords: Optional[Sequence[str]] = None,
    skip_n_seconds: int = 0,
    raw_audio_seconds: float = 0.0,
) -> PrerecordedTranscriptionResponse:
    workload = STTWorkload(workload)
    provider_name = resolve_prerecorded_provider_for_request(workload)
    model = _model_for_provider(provider_name, model)
    provider = _get_prerecorded_provider(provider_name)
    started_at = datetime.now(timezone.utc)
    run_id = _create_run(uid, provider_name.value, model, workload.value, conversation_id, started_at)

    try:
        provider_result, detected_language, retry_count = _transcribe_url_with_retry(
            provider,
            audio_url,
            speakers_count=speakers_count,
            return_language=return_language,
            diarize=diarize,
            language=language,
            model=model,
            keywords=keywords,
        )
        segments = reconstruct_conversation(provider_result, skip_n_seconds=skip_n_seconds)
        words = provider_result_to_legacy_words(provider_result)
        _finalize_run(
            run_id,
            provider_result,
            workload,
            started_at,
            'succeeded',
            retry_count=retry_count,
            raw_audio_seconds=raw_audio_seconds or provider_result.duration or 0.0,
            segments=segments,
        )
        return PrerecordedTranscriptionResponse(
            result=provider_result,
            detected_language=detected_language,
            segments=segments,
            words=words,
            run_id=run_id,
        )
    except Exception as e:
        _finalize_failed_run(
            run_id,
            provider_name.value,
            model,
            workload.value,
            started_at,
            _provider_error_from_exception(e),
            raw_audio_seconds,
            retry_count=_retry_count_from_exception(e),
        )
        fallback_provider_name = _resolve_usable_fallback_prerecorded_provider(provider_name, workload)
        if fallback_provider_name:
            fallback_reason = _fallback_reason_from_exception(e)
            logger.warning(
                'provider prerecorded url transcription falling back workload=%s from_provider=%s to_provider=%s reason=%s: %s',
                workload.value,
                provider_name.value,
                fallback_provider_name.value,
                fallback_reason,
                e,
            )
            return _transcribe_url_with_provider(
                fallback_provider_name,
                audio_url,
                workload,
                uid=uid,
                conversation_id=conversation_id,
                speakers_count=speakers_count,
                return_language=return_language,
                diarize=diarize,
                language=language,
                model=_model_for_provider(fallback_provider_name, model),
                keywords=keywords,
                skip_n_seconds=skip_n_seconds,
                raw_audio_seconds=raw_audio_seconds,
                fallback_from_provider=provider_name.value,
                fallback_reason=fallback_reason,
            )
        raise RuntimeError(f'{provider_name.value} transcription failed after 2 attempts: {e}')


def transcribe_bytes(
    audio_bytes: bytes,
    workload: STTWorkload,
    uid: Optional[str] = None,
    conversation_id: Optional[str] = None,
    sample_rate: int = 16000,
    diarize: bool = True,
    encoding: Optional[str] = None,
    channels: int = 1,
    language: Optional[str] = None,
    model: str = 'nova-3',
    return_language: bool = False,
    keywords: Optional[Sequence[str]] = None,
    skip_n_seconds: int = 0,
    raw_audio_seconds: float = 0.0,
) -> PrerecordedTranscriptionResponse:
    workload = STTWorkload(workload)
    provider_name = resolve_prerecorded_provider_for_request(workload)
    model = _model_for_provider(provider_name, model)
    provider = _get_prerecorded_provider(provider_name)
    started_at = datetime.now(timezone.utc)
    run_id = _create_run(uid, provider_name.value, model, workload.value, conversation_id, started_at)

    try:
        provider_result, detected_language, retry_count = _transcribe_bytes_with_retry(
            provider,
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
        segments = reconstruct_conversation(provider_result, skip_n_seconds=skip_n_seconds)
        words = provider_result_to_legacy_words(provider_result)
        _finalize_run(
            run_id,
            provider_result,
            workload,
            started_at,
            'succeeded',
            retry_count=retry_count,
            raw_audio_seconds=raw_audio_seconds or provider_result.duration or 0.0,
            segments=segments,
        )
        return PrerecordedTranscriptionResponse(
            result=provider_result,
            detected_language=detected_language,
            segments=segments,
            words=words,
            run_id=run_id,
        )
    except Exception as e:
        _finalize_failed_run(
            run_id,
            provider_name.value,
            model,
            workload.value,
            started_at,
            _provider_error_from_exception(e),
            raw_audio_seconds,
            retry_count=_retry_count_from_exception(e),
        )
        fallback_provider_name = _resolve_usable_fallback_prerecorded_provider(provider_name, workload)
        if fallback_provider_name:
            fallback_reason = _fallback_reason_from_exception(e)
            logger.warning(
                'provider prerecorded bytes transcription falling back workload=%s from_provider=%s to_provider=%s reason=%s: %s',
                workload.value,
                provider_name.value,
                fallback_provider_name.value,
                fallback_reason,
                e,
            )
            return _transcribe_bytes_with_provider(
                fallback_provider_name,
                audio_bytes,
                workload,
                uid=uid,
                conversation_id=conversation_id,
                sample_rate=sample_rate,
                diarize=diarize,
                encoding=encoding,
                channels=channels,
                language=language,
                model=_model_for_provider(fallback_provider_name, model),
                return_language=return_language,
                keywords=keywords,
                skip_n_seconds=skip_n_seconds,
                raw_audio_seconds=raw_audio_seconds,
                fallback_from_provider=provider_name.value,
                fallback_reason=fallback_reason,
            )
        raise RuntimeError(f'{provider_name.value} transcription failed after 2 attempts: {e}')


def _get_prerecorded_provider(provider_name: STTProviderName):
    if provider_name == STTProviderName.assemblyai:
        return _assemblyai_prerecorded_provider()
    if provider_name == STTProviderName.deepgram:
        return _deepgram_prerecorded_provider()
    raise ValueError(f'Unsupported prerecorded STT provider: {provider_name}')


def _resolve_usable_fallback_prerecorded_provider(
    provider_name: STTProviderName, workload: STTWorkload
) -> Optional[STTProviderName]:
    fallback_provider_name = get_fallback_prerecorded_provider_name(provider_name, workload)
    if fallback_provider_name == STTProviderName.deepgram and not _has_deepgram_key_for_request():
        return None
    return fallback_provider_name


def _model_for_provider(provider_name: STTProviderName, requested_model: str) -> str:
    if provider_name == STTProviderName.assemblyai and str(requested_model or '').startswith('nova-'):
        return os.getenv('ASSEMBLYAI_STT_MODEL', 'universal-2')
    if provider_name == STTProviderName.deepgram and str(requested_model or '').startswith('universal-'):
        return 'nova-3'
    return requested_model


def _transcribe_url_with_provider(
    provider_name: STTProviderName,
    audio_url: str,
    workload: STTWorkload,
    uid: Optional[str] = None,
    conversation_id: Optional[str] = None,
    speakers_count: int = None,
    return_language: bool = False,
    diarize: bool = True,
    language: Optional[str] = None,
    model: str = 'nova-3',
    keywords: Optional[Sequence[str]] = None,
    skip_n_seconds: int = 0,
    raw_audio_seconds: float = 0.0,
    fallback_from_provider: Optional[str] = None,
    fallback_reason: str = 'provider_failure',
) -> PrerecordedTranscriptionResponse:
    provider = _get_prerecorded_provider(provider_name)
    started_at = datetime.now(timezone.utc)
    run_id = _create_run(uid, provider_name.value, model, workload.value, conversation_id, started_at)
    try:
        provider_result, detected_language, retry_count = _transcribe_url_with_retry(
            provider,
            audio_url,
            speakers_count=speakers_count,
            return_language=return_language,
            diarize=diarize,
            language=language,
            model=model,
            keywords=keywords,
        )
        return _build_success_response(
            run_id,
            provider_result,
            workload,
            started_at,
            retry_count,
            raw_audio_seconds,
            skip_n_seconds,
            fallback_from_provider=fallback_from_provider,
            fallback_reason=fallback_reason,
            detected_language=detected_language,
        )
    except Exception as e:
        _finalize_failed_run(
            run_id,
            provider_name.value,
            model,
            workload.value,
            started_at,
            _provider_error_from_exception(e),
            raw_audio_seconds,
            retry_count=_retry_count_from_exception(e),
        )
        raise RuntimeError(f'{provider_name.value} transcription failed after 2 attempts: {e}')


def _transcribe_bytes_with_provider(
    provider_name: STTProviderName,
    audio_bytes: bytes,
    workload: STTWorkload,
    uid: Optional[str] = None,
    conversation_id: Optional[str] = None,
    sample_rate: int = 16000,
    diarize: bool = True,
    encoding: Optional[str] = None,
    channels: int = 1,
    language: Optional[str] = None,
    model: str = 'nova-3',
    return_language: bool = False,
    keywords: Optional[Sequence[str]] = None,
    skip_n_seconds: int = 0,
    raw_audio_seconds: float = 0.0,
    fallback_from_provider: Optional[str] = None,
    fallback_reason: str = 'provider_failure',
) -> PrerecordedTranscriptionResponse:
    provider = _get_prerecorded_provider(provider_name)
    started_at = datetime.now(timezone.utc)
    run_id = _create_run(uid, provider_name.value, model, workload.value, conversation_id, started_at)
    try:
        provider_result, detected_language, retry_count = _transcribe_bytes_with_retry(
            provider,
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
        return _build_success_response(
            run_id,
            provider_result,
            workload,
            started_at,
            retry_count,
            raw_audio_seconds,
            skip_n_seconds,
            fallback_from_provider=fallback_from_provider,
            fallback_reason=fallback_reason,
            detected_language=detected_language,
        )
    except Exception as e:
        _finalize_failed_run(
            run_id,
            provider_name.value,
            model,
            workload.value,
            started_at,
            _provider_error_from_exception(e),
            raw_audio_seconds,
            retry_count=_retry_count_from_exception(e),
        )
        raise RuntimeError(f'{provider_name.value} transcription failed after 2 attempts: {e}')


def _build_success_response(
    run_id: Optional[str],
    provider_result: ProviderTranscriptResult,
    workload: STTWorkload,
    started_at: datetime,
    retry_count: int,
    raw_audio_seconds: float,
    skip_n_seconds: int,
    fallback_from_provider: Optional[str] = None,
    fallback_reason: str = 'provider_failure',
    detected_language: Optional[str] = None,
) -> PrerecordedTranscriptionResponse:
    segments = reconstruct_conversation(provider_result, skip_n_seconds=skip_n_seconds)
    words = provider_result_to_legacy_words(provider_result)
    _finalize_run(
        run_id,
        provider_result,
        workload,
        started_at,
        'succeeded',
        retry_count=retry_count,
        raw_audio_seconds=raw_audio_seconds or provider_result.duration or 0.0,
        segments=segments,
        fallback_count=1 if fallback_from_provider else 0,
        fallback_provider=fallback_from_provider,
        fallback_reason=fallback_reason,
    )
    return PrerecordedTranscriptionResponse(
        result=provider_result,
        detected_language=detected_language,
        segments=segments,
        words=words,
        run_id=run_id,
    )


def _transcribe_url_with_retry(
    provider, audio_url: str, **kwargs
) -> Tuple[ProviderTranscriptResult, Optional[str], int]:
    last_error = None
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            result = provider.transcribe_url(audio_url, **kwargs)
            transcript_result, detected_language = _unpack_provider_result(result, kwargs.get('return_language'))
            return transcript_result, detected_language, attempt
        except Exception as e:
            last_error = e
            logger.error(
                'provider prerecorded url transcription error attempt=%s provider=%s: %s',
                attempt,
                provider.provider_name,
                e,
            )
    raise ProviderTranscriptionRetriesExhausted(last_error, max_attempts - 1)


def _transcribe_bytes_with_retry(
    provider, audio_bytes: bytes, **kwargs
) -> Tuple[ProviderTranscriptResult, Optional[str], int]:
    last_error = None
    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            result = provider.transcribe_bytes(audio_bytes, **kwargs)
            transcript_result, detected_language = _unpack_provider_result(result, kwargs.get('return_language'))
            return transcript_result, detected_language, attempt
        except Exception as e:
            last_error = e
            logger.error(
                'provider prerecorded bytes transcription error attempt=%s provider=%s: %s',
                attempt,
                provider.provider_name,
                e,
            )
    raise ProviderTranscriptionRetriesExhausted(last_error, max_attempts - 1)


def _retry_count_from_exception(error: Exception) -> int:
    if isinstance(error, ProviderTranscriptionRetriesExhausted):
        return error.retry_count
    return 0


def _provider_error_from_exception(error: Exception) -> Exception:
    if isinstance(error, ProviderTranscriptionRetriesExhausted):
        return error.provider_error
    return error


def _fallback_reason_from_exception(error: Exception) -> str:
    provider_error = _provider_error_from_exception(error)
    if isinstance(provider_error, (AssemblyAITimeoutError, httpx.TimeoutException, TimeoutError)):
        return 'provider_timeout'
    return 'provider_failure'


def _unpack_provider_result(result, return_language: bool) -> Tuple[ProviderTranscriptResult, Optional[str]]:
    if return_language:
        transcript_result, detected_language = result
        return transcript_result, detected_language
    transcript_result = result
    return transcript_result, transcript_result.language


def _create_run(
    uid: Optional[str],
    provider: str,
    model: str,
    workload: str,
    conversation_id: Optional[str],
    started_at: datetime,
) -> Optional[str]:
    if not uid:
        return None
    try:
        return create_provider_run(
            uid=uid,
            provider=provider,
            model=model,
            workload=workload,
            conversation_id=conversation_id,
            started_at=started_at,
        )
    except Exception as e:
        logger.warning('failed to create transcription provider run ledger uid=%s workload=%s: %s', uid, workload, e)
        return None


def _finalize_run(
    run_id: Optional[str],
    result: ProviderTranscriptResult,
    workload: STTWorkload,
    started_at: datetime,
    status: str,
    retry_count: int,
    raw_audio_seconds: float,
    segments: List[TranscriptSegment],
    fallback_count: int = 0,
    fallback_provider: Optional[str] = None,
    fallback_reason: str = 'provider_failure',
) -> None:
    if not run_id:
        return
    billable_seconds = raw_audio_seconds
    clusters = {_segment_cluster_key(segment) for segment in segments if _segment_cluster_key(segment)}
    confidences = [segment.speaker_identity_confidence for segment in segments]
    identity_metrics = speaker_identity_metrics(segments)
    unknown_speaker_duration_seconds = _unknown_speaker_duration_seconds(segments)
    try:
        finalize_provider_run(
            run_id=run_id,
            provider=result.provider,
            model=result.model or 'unknown',
            workload=workload.value,
            status=status,
            started_at=started_at,
            raw_audio_seconds=raw_audio_seconds,
            speech_active_seconds=raw_audio_seconds,
            billable_seconds=billable_seconds,
            chunk_duration_seconds=raw_audio_seconds,
            estimated_cost_usd=estimate_prerecorded_provider_cost_usd(
                provider=result.provider,
                model=result.model,
                workload=workload.value,
                billable_seconds=billable_seconds,
            ),
            retry_count=retry_count,
            fallback_count=fallback_count,
            transcript_segment_count=len(segments),
            transcript_word_count=len(result.words),
            speaker_cluster_count=len(clusters),
            identified_speaker_cluster_count=_identified_cluster_count(segments),
            identity_match_count=identity_metrics['mapped_speaker_count'],
            identity_confidence_summary=summarize_identity_confidences(confidences),
            provider_speaker_count=identity_metrics['provider_speaker_count'],
            mapped_speaker_count=identity_metrics['mapped_speaker_count'],
            mapped_person_count=identity_metrics['mapped_person_count'],
            unmapped_speaker_count=identity_metrics['unmapped_speaker_count'],
            unknown_speaker_count=identity_metrics['unmapped_speaker_count'],
            unknown_speaker_duration_seconds=unknown_speaker_duration_seconds,
            split_count=_split_count(clusters),
            embedding_extraction_failure_count=identity_metrics['embedding_extraction_failure_count'],
            artifact_refs=_provider_artifact_refs(result),
            fallback_provider=fallback_provider,
            fallback_reason=fallback_reason,
        )
    except Exception as e:
        logger.warning('failed to finalize transcription provider run ledger run_id=%s: %s', run_id, e)


def _provider_artifact_refs(result: ProviderTranscriptResult) -> dict[str, str]:
    if not result.raw_provider_result_id:
        return {}
    return {'provider_result_id': result.raw_provider_result_id}


def _finalize_failed_run(
    run_id: Optional[str],
    provider: str,
    model: str,
    workload: str,
    started_at: datetime,
    error: Exception,
    raw_audio_seconds: float,
    retry_count: int = 0,
) -> None:
    if not run_id:
        return
    billable_seconds = raw_audio_seconds
    try:
        finalize_provider_run(
            run_id=run_id,
            provider=provider,
            model=model,
            workload=workload,
            status='failed',
            started_at=started_at,
            raw_audio_seconds=raw_audio_seconds,
            speech_active_seconds=raw_audio_seconds,
            billable_seconds=billable_seconds,
            chunk_duration_seconds=raw_audio_seconds,
            estimated_cost_usd=estimate_prerecorded_provider_cost_usd(
                provider=provider,
                model=model,
                workload=workload,
                billable_seconds=billable_seconds,
            ),
            retry_count=retry_count,
            fallback_count=0,
            error_class=error.__class__.__name__,
        )
    except Exception as finalize_error:
        logger.warning(
            'failed to finalize failed transcription provider run ledger run_id=%s: %s', run_id, finalize_error
        )


def update_provider_run_identity_metrics(
    run_id: Optional[str],
    provider: str,
    model: str,
    workload: STTWorkload,
    segments: List[TranscriptSegment],
    identity_metric_update_status: str = 'succeeded',
    identity_metric_update_skipped_reason: Optional[str] = None,
) -> None:
    if not run_id:
        return
    if _db_update_provider_run_identity_metrics is None:
        logger.warning(
            'failed to update transcription provider identity metrics run_id=%s: %s',
            run_id,
            _PROVIDER_USAGE_IMPORT_ERROR,
        )
        return
    try:
        identity_metrics = speaker_identity_metrics(segments)
        _db_update_provider_run_identity_metrics(
            run_id=run_id,
            provider=provider,
            model=model or 'unknown',
            workload=STTWorkload(workload).value,
            identified_speaker_cluster_count=_identified_cluster_count(segments),
            identity_confidence_summary=summarize_identity_confidences(
                [segment.speaker_identity_confidence for segment in segments]
            ),
            provider_speaker_count=identity_metrics['provider_speaker_count'],
            mapped_speaker_count=identity_metrics['mapped_speaker_count'],
            mapped_person_count=identity_metrics['mapped_person_count'],
            unmapped_speaker_count=identity_metrics['unmapped_speaker_count'],
            embedding_extraction_failure_count=identity_metrics['embedding_extraction_failure_count'],
            identity_metric_update_status=identity_metric_update_status,
            identity_metric_update_skipped_reason=identity_metric_update_skipped_reason,
        )
    except Exception as e:
        logger.warning('failed to update transcription provider identity metrics run_id=%s: %s', run_id, e)


def speaker_identity_metrics(segments: List[TranscriptSegment]) -> dict:
    provider_speakers = {_segment_cluster_key(segment) for segment in segments if _segment_cluster_key(segment)}
    mapped_speakers = {
        _segment_cluster_key(segment)
        for segment in segments
        if _segment_cluster_key(segment)
        and (segment.person_id or segment.is_user or segment.speaker_identity_state in ('identified', 'user'))
    }
    mapped_people = {
        segment.person_id or 'user'
        for segment in segments
        if segment.person_id or segment.is_user or segment.speaker_identity_state == 'user'
    }
    embedding_failures = {
        _segment_cluster_key(segment)
        for segment in segments
        if _segment_cluster_key(segment)
        and (segment.speaker_identity_provenance or {}).get('reason') == 'embedding_extraction_failed'
    }
    return {
        'provider_speaker_count': len(provider_speakers),
        'mapped_speaker_count': len(mapped_speakers),
        'mapped_person_count': len(mapped_people),
        'unmapped_speaker_count': max(len(provider_speakers) - len(mapped_speakers), 0),
        'embedding_extraction_failure_count': len(embedding_failures),
    }


def _unknown_speaker_duration_seconds(segments: List[TranscriptSegment]) -> float:
    duration = 0.0
    for segment in segments:
        if segment.speaker_identity_state in _UNKNOWN_SPEAKER_STATES:
            duration += max(0.0, segment.end - segment.start)
    return round(duration, 3)


def _split_count(clusters: set[str]) -> int:
    return sum(1 for cluster in clusters if _LOCAL_CLUSTER_SPLIT_MARKER in str(cluster))


def _identified_cluster_count(segments: List[TranscriptSegment]) -> int:
    return len(
        {
            _segment_cluster_key(segment)
            for segment in segments
            if _segment_cluster_key(segment)
            and (segment.person_id or segment.is_user or segment.speaker_identity_state in ('identified', 'user'))
        }
    )


def _segment_cluster_key(segment: TranscriptSegment) -> Optional[str]:
    return segment.provider_cluster_id or segment.provider_speaker_label
