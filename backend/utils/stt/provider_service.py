import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

from models.transcript_segment import ProviderTranscriptResult, TranscriptSegment
from utils.stt.conversation_reconstructor import reconstruct_conversation
from utils.stt.deepgram_adapter import provider_result_to_legacy_words
from utils.stt.providers import STTProviderName, STTWorkload, get_prerecorded_provider_name

logger = logging.getLogger(__name__)


def create_provider_run(**kwargs) -> str:
    from database.transcription_provider_usage import create_provider_run as _create_provider_run

    return _create_provider_run(**kwargs)


def finalize_provider_run(**kwargs) -> None:
    from database.transcription_provider_usage import finalize_provider_run as _finalize_provider_run

    _finalize_provider_run(**kwargs)


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
    from utils.stt.pre_recorded import _deepgram_prerecorded_provider as _provider

    return _provider()


def get_deepgram_model_for_language(language: str) -> Tuple[str, str]:
    from utils.stt.pre_recorded import get_deepgram_model_for_language as _get_deepgram_model_for_language

    return _get_deepgram_model_for_language(language)


@dataclass
class PrerecordedTranscriptionResponse:
    result: ProviderTranscriptResult
    detected_language: Optional[str]
    segments: List[TranscriptSegment]
    words: List[dict]
    run_id: Optional[str]


def resolve_prerecorded_language_model(language: Optional[str]) -> Tuple[str, str]:
    return get_deepgram_model_for_language(language or 'multi')


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
    provider_name = get_prerecorded_provider_name(workload)
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
        _finalize_failed_run(run_id, provider_name.value, model, workload.value, started_at, e, raw_audio_seconds)
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
    provider_name = get_prerecorded_provider_name(workload)
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
        _finalize_failed_run(run_id, provider_name.value, model, workload.value, started_at, e, raw_audio_seconds)
        raise RuntimeError(f'{provider_name.value} transcription failed after 2 attempts: {e}')


def _get_prerecorded_provider(provider_name: STTProviderName):
    if provider_name == STTProviderName.deepgram:
        return _deepgram_prerecorded_provider()
    raise ValueError(f'Unsupported prerecorded STT provider: {provider_name}')


def _transcribe_url_with_retry(
    provider, audio_url: str, **kwargs
) -> Tuple[ProviderTranscriptResult, Optional[str], int]:
    last_error = None
    for attempt in range(2):
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
    raise last_error


def _transcribe_bytes_with_retry(
    provider, audio_bytes: bytes, **kwargs
) -> Tuple[ProviderTranscriptResult, Optional[str], int]:
    last_error = None
    for attempt in range(2):
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
    raise last_error


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
) -> None:
    if not run_id:
        return
    clusters = {
        item.provider_cluster_id for item in list(result.words) + list(result.utterances) if item.provider_cluster_id
    }
    confidences = [segment.speaker_identity_confidence for segment in segments]
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
            billable_seconds=raw_audio_seconds,
            retry_count=retry_count,
            transcript_segment_count=len(segments),
            transcript_word_count=len(result.words),
            speaker_cluster_count=len(clusters),
            identified_speaker_cluster_count=len(
                {segment.provider_cluster_id for segment in segments if segment.person_id}
            ),
            identity_confidence_summary=summarize_identity_confidences(confidences),
        )
    except Exception as e:
        logger.warning('failed to finalize transcription provider run ledger run_id=%s: %s', run_id, e)


def _finalize_failed_run(
    run_id: Optional[str],
    provider: str,
    model: str,
    workload: str,
    started_at: datetime,
    error: Exception,
    raw_audio_seconds: float,
) -> None:
    if not run_id:
        return
    try:
        finalize_provider_run(
            run_id=run_id,
            provider=provider,
            model=model,
            workload=workload,
            status='failed',
            started_at=started_at,
            raw_audio_seconds=raw_audio_seconds,
            error_class=error.__class__.__name__,
        )
    except Exception as finalize_error:
        logger.warning(
            'failed to finalize failed transcription provider run ledger run_id=%s: %s', run_id, finalize_error
        )
