"""Sync local-files pipeline: decode → VAD → fair-use → STT → conversation merge.

Extracted from routers/sync.py so the router stays thin and utils never imports routers.
"""

# pyright: reportPrivateUsage=false, reportUnusedFunction=false, reportUnusedVariable=false, reportUnnecessaryComparison=false, reportAssignmentType=false, reportIndexIssue=false, reportArgumentType=false

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import logging
import os
import shutil
import threading
import time
import wave
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx
import numpy as np
from fastapi import HTTPException, UploadFile
from pydub import AudioSegment

from database import conversations as conversations_db
from database import users as users_db
from database.conversations import get_closest_conversation_to_timestamps, update_conversation_segments
from database.sync_jobs import (
    RUN_LOCK_HEARTBEAT_SECONDS,
    RUN_LOCK_RENEWAL_SAFETY_SECONDS,
    RUN_LOCK_TTL_SECONDS,
    FencedSyncJobMutation,
    add_processed_segment,
    add_processed_segment_if_run_owner,
    delete_sync_job_run_lock_epoch,
    fenced_finalize_sync_job,
    fenced_mark_job_failed,
    fenced_mark_job_processing,
    fenced_update_sync_job,
    finalize_sync_job,
    get_sync_job_run_lock_epoch,
    get_sync_job,
    get_processed_segments,
    mark_job_failed,
    mark_job_processing,
    release_job_run_lock,
    renew_job_run_lock,
    try_mark_once,
    update_sync_job,
)
from database.sync_ledger import (
    add_processed_sync_segment_id,
    bind_sync_content_run_token,
    checkpoint_sync_content_partial_result,
    get_processed_sync_segment_ids,
    get_sync_content_partial_result,
    is_valid_completed_sync_content_result,
    mark_sync_content_completed,
    release_sync_content_claim_after_job_retired,
    release_sync_content_claim,
)
from models.conversation import CreateConversation
from models.conversation_enums import ConversationSource
from models.transcript_segment import TranscriptSegment
from utils.analytics import record_usage
from utils.byok import get_byok_keys, set_byok_keys, set_byok_uid
from utils.conversations.factory import deserialize_conversation
from utils.conversations.process_conversation import process_conversation
from utils.executors import db_executor, run_blocking, start_background_task, storage_executor, sync_executor
from utils.fair_use import (
    FAIR_USE_ENABLED,
    FAIR_USE_RESTRICT_DAILY_DG_MS,
    check_soft_caps,
    get_enforcement_stage,
    get_rolling_speech_ms,
    is_dg_budget_exhausted,
    record_dg_usage_ms,
    record_speech_ms,
    trigger_classifier_if_needed,
)
from utils.http_client import _get_semaphore
from utils.cloud_tasks import is_audio_merge_dispatch_enabled
from utils.other.storage import (
    compute_audio_files_fingerprint,
    delete_syncing_temporal_file,
    download_syncing_temporal_file,
    enqueue_conversation_artifact_build,
    get_syncing_file_temporal_signed_url,
    precache_conversation_audio,
    schedule_syncing_temporal_file_deletion,
    upload_audio_chunk,
    upload_syncing_temporal_file,
)
from utils.observability.transcription import record_sync_transcription_outcome
from utils.speaker_assignment import process_speaker_assigned_segments
from utils.speaker_identification import detect_speaker_from_text
from utils.stt.pre_recorded import get_prerecorded_service, postprocess_words, prerecorded
from utils.stt.outcomes import (
    TranscriptionFailure,
    TranscriptionOutcome,
    bounded_provider,
    empty_unexpected_failure,
    failure_from_exception,
)
from utils.stt.speaker_embedding import (
    SPEAKER_MATCH_THRESHOLD,
    compare_embeddings,
    extract_embedding_from_bytes,
)
from utils.stt.vad import vad_is_empty
from utils.sync.files import decode_files_to_wav, get_timestamp_from_path, get_wav_duration
from utils.sync.backfill import release_backfill_slot, reserve_backfill_speech
from utils.sync.content_id import compute_sync_segment_id
from utils.sync.lanes import SyncLane
from utils.metrics import OMI_SYNC_BACKFILL_DAILY_USED_MS, OMI_SYNC_LANE_SPEECH_MS_TOTAL

logger = logging.getLogger(__name__)

MAX_VAD_SEGMENT_SECONDS = int(os.getenv('SYNC_MAX_VAD_SEGMENT_SECONDS', '300'))
_SYNC_STT_MODELS = {'nova-3', 'velma-2', 'parakeet'}
_SYNC_FAILURE_REASON_CODES = {
    'backfill_capacity',
    'backfill_paced',
    'stt_empty_unexpected',
    'stt_invalid_input',
    'stt_provider_configuration_error',
    'stt_timeout',
    'stt_upstream_error',
    'sync_backfill_dispatch_unavailable',
    'sync_backfill_paced',
    'sync_dispatch_staging_failed',
    'sync_decode_failed',
    'sync_invalid_audio',
    'sync_staged_audio_expired',
    'sync_transcription_budget_exhausted',
    'sync_vad_failed',
    'sync_worker_stale',
}


def _bounded_sync_model(model: str | None) -> str:
    normalized = (model or '').strip().lower()
    return normalized if normalized in _SYNC_STT_MODELS else 'unknown'


def _bounded_sync_lane(lane: str | None) -> str:
    return lane if lane in {SyncLane.FRESH.value, SyncLane.BACKFILL.value} else 'unknown'


def _bounded_exception_type(error: BaseException) -> str:
    name = error.__class__.__name__
    return name if name.replace('_', '').isalnum() and len(name) <= 64 else 'Exception'


def _bounded_sync_failure_reason(reason: str | None) -> str:
    return reason if reason in _SYNC_FAILURE_REASON_CODES else 'other'


def _record_sync_segment_outcome(
    outcome: TranscriptionOutcome,
    *,
    provider: str,
    model: str,
    lane: str,
    retryable: bool,
    job_id: str | None = None,
    segment_key: str | None = None,
) -> None:
    """Emit one fixed-shape event without audio, transcript, or user identity."""
    if isinstance(job_id, str) and isinstance(segment_key, str):
        metric_tag = f'segment_outcome:{hashlib.sha256(segment_key.encode()).hexdigest()[:24]}'
        try:
            if not try_mark_once(job_id, metric_tag):
                return
        except Exception:
            # Observability cannot prevent a durable segment checkpoint from
            # completing. A later retry may duplicate this metric, but not the
            # customer-visible transcription result.
            logger.warning('event=sync_transcription_metric outcome=dedupe_failed kind=segment')
    log = logger.info if outcome == TranscriptionOutcome.SUCCESS else logger.error
    log(
        'event=sync_transcription_segment outcome=%s provider=%s model=%s lane=%s retryable=%s',
        outcome.value,
        bounded_provider(provider),
        _bounded_sync_model(model),
        _bounded_sync_lane(lane),
        str(retryable).lower(),
    )
    try:
        record_sync_transcription_outcome(
            kind='segment',
            provider=provider,
            model=model,
            lane=lane,
            outcome=outcome,
        )
    except Exception:
        logger.warning('event=sync_transcription_metric outcome=emit_failed kind=segment')


def _record_sync_segment_failure(
    failure: TranscriptionFailure,
    *,
    model: str,
    lane: str,
    lock: threading.Lock,
    errors: list,
    record_metric: bool = True,
    job_id: str | None = None,
    segment_key: str | None = None,
) -> None:
    if record_metric:
        _record_sync_segment_outcome(
            failure.outcome,
            provider=failure.provider,
            model=model,
            lane=lane,
            retryable=failure.retryable,
            job_id=job_id,
            segment_key=segment_key,
        )
    with lock:
        errors.append(failure.error_code)


def _set_deferred_segment_outcome(
    deferred_outcome: dict | None,
    *,
    outcome: TranscriptionOutcome,
    provider: str,
    model: str,
    retryable: bool,
) -> None:
    """Keep v2 outcome data local until its durable checkpoint commits."""
    if deferred_outcome is not None:
        deferred_outcome.update(
            outcome=outcome,
            provider=provider,
            model=model,
            retryable=retryable,
        )


def _deferred_segment_labels(
    deferred_outcome: dict,
    *,
    fallback_outcome: TranscriptionOutcome,
    fallback_provider: str,
    fallback_model: str,
    fallback_retryable: bool,
) -> tuple[TranscriptionOutcome, str, str, bool]:
    """Read locally deferred values without widening telemetry labels."""
    outcome = deferred_outcome.get('outcome')
    provider = deferred_outcome.get('provider')
    model = deferred_outcome.get('model')
    retryable = deferred_outcome.get('retryable')
    return (
        outcome if isinstance(outcome, TranscriptionOutcome) else fallback_outcome,
        provider if isinstance(provider, str) else fallback_provider,
        model if isinstance(model, str) else fallback_model,
        retryable if isinstance(retryable, bool) else fallback_retryable,
    )


_SYNC_ERROR_CODE_OUTCOMES = {
    'stt_provider_configuration_error': TranscriptionOutcome.CONFIG_ERROR,
    'stt_timeout': TranscriptionOutcome.TIMEOUT,
    'stt_upstream_error': TranscriptionOutcome.UPSTREAM_ERROR,
    'stt_empty_unexpected': TranscriptionOutcome.EMPTY_UNEXPECTED,
    'stt_invalid_input': TranscriptionOutcome.INVALID_INPUT,
}


def _job_transcription_outcome(segment_errors: list[str]) -> TranscriptionOutcome:
    if not segment_errors:
        return TranscriptionOutcome.SUCCESS
    present = set(segment_errors)
    for error_code, outcome in _SYNC_ERROR_CODE_OUTCOMES.items():
        if error_code in present:
            return outcome
    return TranscriptionOutcome.UPSTREAM_ERROR


def _record_sync_job_outcome(
    outcome: TranscriptionOutcome,
    *,
    provider: str,
    model: str,
    lane: str,
    job_id: str | None = None,
) -> None:
    if isinstance(job_id, str):
        try:
            if not try_mark_once(job_id, 'terminal_outcome_metric'):
                return
        except Exception:
            logger.warning('event=sync_transcription_metric outcome=dedupe_failed kind=job')
    try:
        record_sync_transcription_outcome(
            kind='job',
            provider=provider,
            model=model,
            lane=lane,
            outcome=outcome,
        )
    except Exception:
        logger.warning('event=sync_transcription_metric outcome=emit_failed kind=job')


async def _record_sync_job_outcome_async(
    outcome: TranscriptionOutcome,
    *,
    provider: str,
    model: str,
    lane: str,
    job_id: str | None = None,
) -> None:
    """Keep Redis-backed job metric dedupe off the pipeline coordinator loop."""
    try:
        await run_blocking(
            db_executor,
            _record_sync_job_outcome,
            outcome,
            provider=provider,
            model=model,
            lane=lane,
            job_id=job_id,
        )
    except Exception:
        # Telemetry must not turn a durably finalized transcription into a
        # failed/retryable job when the DB executor is unavailable.
        logger.warning('event=sync_transcription_metric outcome=offload_failed kind=job')


async def _record_sync_segment_failure_async(
    failure: TranscriptionFailure,
    *,
    model: str,
    lane: str,
    lock: threading.Lock,
    errors: list,
    job_id: str | None = None,
    segment_key: str | None = None,
) -> None:
    """Record a coordinator-observed segment failure without blocking the loop."""
    try:
        await run_blocking(
            db_executor,
            _record_sync_segment_outcome,
            failure.outcome,
            provider=failure.provider,
            model=model,
            lane=lane,
            retryable=failure.retryable,
            job_id=job_id,
            segment_key=segment_key,
        )
    except Exception:
        # Preserve the retryable failure even when best-effort metric delivery
        # cannot obtain a DB executor slot.
        logger.warning('event=sync_transcription_metric outcome=offload_failed kind=segment')
    with lock:
        errors.append(failure.error_code)


class SyncJobRunLeaseLost(RuntimeError):
    """A worker tried to write after its run token stopped owning the job."""


def _require_run_owner(mutation: FencedSyncJobMutation, *, job_id: str) -> Dict | None:
    """Turn a non-applied Redis CAS result into the worker's stop signal."""
    if getattr(mutation, 'applied', False):
        return getattr(mutation, 'job', None)
    outcome = getattr(getattr(mutation, 'outcome', None), 'value', 'unknown')
    raise SyncJobRunLeaseLost(f'sync job run lease lost: job={job_id} outcome={outcome}')


def _update_sync_job_for_run(job_id: str, run_lock_token: str | None, updates: Dict) -> Dict | None:
    if run_lock_token is None:
        # During the mixed-revision compatibility phase, the raw-CAS helper
        # returns None when another worker already reached a terminal state.
        # Treat that exactly like a lost fenced lease: a late worker must stop
        # before it can release retry material or publish more side effects.
        updated = update_sync_job(job_id, updates)
        if updated is None:
            raise SyncJobRunLeaseLost(f'sync job legacy state is no longer mutable: job={job_id}')
        return updated
    return _require_run_owner(
        fenced_update_sync_job(
            job_id,
            run_lock_token,
            updates,
            allowed_current_statuses={'processing'},
        ),
        job_id=job_id,
    )


def _mark_job_processing_for_run(job_id: str, run_lock_token: str | None) -> Dict | None:
    if run_lock_token is None:
        updated = mark_job_processing(job_id)
        if updated is None:
            raise SyncJobRunLeaseLost(f'sync job legacy state is no longer mutable: job={job_id}')
        return updated
    return _require_run_owner(fenced_mark_job_processing(job_id, run_lock_token), job_id=job_id)


def _finalize_sync_job_for_run(job_id: str, run_lock_token: str | None, result: Dict) -> Dict | None:
    if run_lock_token is None:
        finalized = finalize_sync_job(job_id, result)
        if finalized is None:
            raise SyncJobRunLeaseLost(f'sync job legacy state is no longer mutable: job={job_id}')
        return finalized
    return _require_run_owner(fenced_finalize_sync_job(job_id, run_lock_token, result), job_id=job_id)


def _mark_job_failed_for_run(
    job_id: str,
    run_lock_token: str | None,
    error: str,
    *,
    reason_code: str | None = None,
    retry_after: int | None = None,
) -> Dict | None:
    if run_lock_token is None:
        failed = mark_job_failed(job_id, error, reason_code=reason_code, retry_after=retry_after)
        if failed is None:
            raise SyncJobRunLeaseLost(f'sync job legacy state is no longer mutable: job={job_id}')
        return failed
    return _require_run_owner(
        fenced_mark_job_failed(
            job_id,
            run_lock_token,
            error,
            reason_code=reason_code,
            retry_after=retry_after,
        ),
        job_id=job_id,
    )


def _add_processed_segment_for_run(job_id: str, run_lock_token: str | None, segment_path: str) -> None:
    if run_lock_token is None:
        add_processed_segment(job_id, segment_path)
        return
    _require_run_owner(add_processed_segment_if_run_owner(job_id, run_lock_token, segment_path), job_id=job_id)


def bind_or_converge_sync_ledger_completion(
    *,
    job_id: str,
    uid: str,
    content_id: str | None,
    run_lock_token: str | None,
) -> Dict | None:
    """Bind a live lease to the durable ledger or converge a proven completion.

    This synchronous DB-boundary helper is shared by Cloud Tasks, inline work,
    and stale polling. A higher epoch displaces an old owner before any decode,
    provider, ledger mutation, or stale failure can occur. A valid completion
    that landed just before lease replacement becomes the current Redis result
    through the caller's *current* fenced token rather than being overwritten
    as a failure.
    """
    if not content_id or run_lock_token is None:
        return None

    binding = bind_sync_content_run_token(
        uid,
        content_id,
        job_id,
        run_lock_token,
        get_sync_job_run_lock_epoch(run_lock_token),
    )
    if binding.bound:
        return None
    if not binding.completed or not is_valid_completed_sync_content_result(binding.result):
        raise SyncJobRunLeaseLost(f'sync content ledger owner lost: job={job_id}')

    finalized = _finalize_sync_job_for_run(job_id, run_lock_token, binding.result)
    delete_sync_job_run_lock_epoch(job_id)
    return finalized


async def _finalize_sync_job_failure(
    *,
    job_id: str,
    uid: str,
    content_id: str | None,
    error_code: str,
    outcome: TranscriptionOutcome,
    provider: str,
    model: str,
    lane: str,
    reason_code: str | None = None,
    retry_after: int | None = None,
    run_lock_token: str | None = None,
) -> None:
    """Offload the atomic failure publication boundary to the DB executor."""
    finalized = await run_blocking(
        db_executor,
        finalize_sync_job_failure_now,
        job_id=job_id,
        uid=uid,
        content_id=content_id,
        error_code=error_code,
        outcome=outcome,
        provider=provider,
        model=model,
        lane=lane,
        reason_code=reason_code,
        retry_after=retry_after,
        run_lock_token=run_lock_token,
    )
    if finalized is None:
        # The epoch-fenced path lost its lease; the compatibility path saw an
        # already-terminal raw-CAS state. Both mean this worker no longer owns
        # the authority to release retry material or publish a second result.
        raise SyncJobRunLeaseLost(f'sync job state is no longer mutable: job={job_id} outcome=terminal_failure')


def finalize_sync_job_failure_now(
    *,
    job_id: str,
    uid: str,
    content_id: str | None,
    error_code: str,
    outcome: TranscriptionOutcome,
    provider: str,
    model: str,
    lane: str,
    reason_code: str | None = None,
    retry_after: int | None = None,
    run_lock_token: str | None = None,
) -> Optional[Dict]:
    """Publish one truthful failure and then make its retry claim available.

    This synchronous boundary is shared by async workers and the polling stale
    reaper. A run-token owner fences the Redis terminal transition first; only
    that winning owner may release the durable retry claim afterward.
    """
    if run_lock_token is None:
        finalized = mark_job_failed(
            job_id,
            error_code,
            reason_code=reason_code or error_code,
            retry_after=retry_after,
        )
    else:
        try:
            finalized = _mark_job_failed_for_run(
                job_id,
                run_lock_token,
                error_code,
                reason_code=reason_code or error_code,
                retry_after=retry_after,
            )
        except SyncJobRunLeaseLost:
            return None
    if finalized is None:
        return None
    if content_id:
        if run_lock_token is None:
            # The pre-cutover protocol has no epoch binding. Keep all ledger
            # operations tokenless while legacy revisions may still exist.
            release_sync_content_claim(uid, content_id, job_id)
        else:
            # The fenced Redis terminal transition already succeeded. A lease
            # can expire between that CAS and Firestore release, so use the
            # deliberately retired-job transaction rather than treating this
            # as a live write.
            release_sync_content_claim_after_job_retired(uid, content_id, job_id)
    if run_lock_token is not None:
        delete_sync_job_run_lock_epoch(job_id)
    logger.error(
        'event=sync_transcription_job outcome=%s status=failed provider=%s model=%s lane=%s reason_code=%s',
        outcome.value,
        bounded_provider(provider),
        _bounded_sync_model(model),
        _bounded_sync_lane(lane),
        _bounded_sync_failure_reason(reason_code or error_code),
    )
    _record_sync_job_outcome(outcome, provider=provider, model=model, lane=lane, job_id=job_id)
    return finalized


def _merge_and_cap_vad_segments(voice_segments: list) -> list:
    merged = []
    for segment in voice_segments:
        if (
            merged
            and (segment['start'] - merged[-1]['end']) < 120
            and (segment['end'] - merged[-1]['start']) <= MAX_VAD_SEGMENT_SECONDS
        ):
            merged[-1]['end'] = segment['end']
        else:
            merged.append(dict(segment))

    segments = []
    for segment in merged:
        if segment['end'] - segment['start'] <= MAX_VAD_SEGMENT_SECONDS:
            segments.append(segment)
        else:
            chunk_start = segment['start']
            while chunk_start < segment['end']:
                chunk_end = min(chunk_start + MAX_VAD_SEGMENT_SECONDS, segment['end'])
                segments.append({'start': chunk_start, 'end': chunk_end})
                chunk_start = chunk_end
    return segments


def retrieve_vad_segments(path: str, segmented_paths: set, errors: list = None):
    try:
        start_timestamp = get_timestamp_from_path(path)
        voice_segments = vad_is_empty(path, return_segments=True, cache=True)
    except Exception as e:
        error_code = 'sync_vad_failed'
        logger.error(
            'event=sync_vad outcome=upstream_error exception_type=%s',
            _bounded_exception_type(e),
        )
        if errors is not None:
            errors.append(error_code)
        raise  # Re-raise to ensure thread failure is visible

    segments = _merge_and_cap_vad_segments(voice_segments)
    logger.info('event=sync_vad outcome=success segment_count=%d', len(segments))

    aseg = AudioSegment.from_wav(path)
    path_dir = '/'.join(path.split('/')[:-1])

    try:
        for i, segment in enumerate(segments):
            if (segment['end'] - segment['start']) < 1:
                continue
            segment_timestamp = start_timestamp + segment['start']
            segment_path = f'{path_dir}/{segment_timestamp}.wav'
            segment_aseg = aseg[segment['start'] * 1000 : segment['end'] * 1000]
            segment_aseg.export(segment_path, format='wav')
            segmented_paths.add(segment_path)
            # Explicitly delete segment to free memory immediately
            del segment_aseg
    finally:
        # Explicitly delete main audio to free memory
        del aseg


def _reprocess_conversation_after_update(uid: str, conversation_id: str, language: str):
    """
    Reprocess a conversation after new segments have been added.
    This checks if the conversation should still be discarded and regenerates
    the summary/structured data if it now has sufficient content.
    """
    # Fetch the updated conversation with all segments
    conversation_data = conversations_db.get_conversation(uid, conversation_id)
    if not conversation_data:
        logger.warning(f'Conversation {conversation_id} not found for reprocessing')
        return

    # Convert to Conversation object
    conversation = deserialize_conversation(conversation_data)

    process_conversation(
        uid=uid,
        language_code=language or 'en',
        conversation=conversation,
        force_process=True,
        is_reprocess=True,
    )

    logger.info(f'Successfully reprocessed conversation {conversation_id}')


USER_SELF_PERSON_ID = 'user'
SPEAKER_ID_MIN_AUDIO = 1.0  # Minimum seconds of audio per speaker for embedding extraction


def build_person_embeddings_cache(uid: str) -> Dict[str, dict]:
    """Build a cache of person embeddings for speaker identification.

    Loads the user's own speaker embedding and all people with stored embeddings.
    Returns dict mapping person_id -> {embedding: np.ndarray, name: str}.
    """
    cache: Dict[str, dict] = {}

    # Load user's own speaker embedding
    embedding_list = users_db.get_user_speaker_embedding(uid)
    if embedding_list:
        user_embedding = np.array(embedding_list, dtype=np.float32).reshape(1, -1)
        cache[USER_SELF_PERSON_ID] = {'embedding': user_embedding, 'name': 'User'}

    # Load all people with speaker embeddings
    people = users_db.get_people(uid)
    for person in people or []:
        emb = person.get('speaker_embedding')
        # Only load embedding if person has speech samples — contacts without
        # samples may have stale embeddings from a pre-v3 model (#6238)
        if emb and person.get('speech_samples'):
            cache[person['id']] = {
                'embedding': np.array(emb, dtype=np.float32).reshape(1, -1),
                'name': person['name'],
            }

    return cache


def _download_audio_bytes(url: str) -> Optional[bytes]:
    """Download audio from a signed URL. Returns WAV bytes or None on failure."""
    try:
        resp = httpx.get(url, timeout=60.0)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        logger.warning(f'Speaker ID: failed to download audio: {e}')
        return None


def _extract_speaker_clip_wav(audio_bytes: bytes, start_sec: float, end_sec: float) -> Optional[bytes]:
    """Extract a clip from WAV audio bytes between start_sec and end_sec.

    Returns WAV bytes for the clip, or None if extraction fails or clip is too short.
    """
    try:
        with wave.open(io.BytesIO(audio_bytes), 'rb') as wf:
            framerate = wf.getframerate()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            total_duration = n_frames / framerate

            # Clamp to audio bounds
            start_sec = max(0.0, start_sec)
            end_sec = min(total_duration, end_sec)
            if end_sec - start_sec < SPEAKER_ID_MIN_AUDIO:
                return None

            # Cap extraction at 10 seconds
            if end_sec - start_sec > 10.0:
                center = (start_sec + end_sec) / 2
                start_sec = center - 5.0
                end_sec = center + 5.0
                start_sec = max(0.0, start_sec)
                end_sec = min(total_duration, end_sec)

            start_frame = int(start_sec * framerate)
            end_frame = int(end_sec * framerate)

            wf.setpos(start_frame)
            frames = wf.readframes(end_frame - start_frame)

        # Write clip as WAV
        clip_buf = io.BytesIO()
        with wave.open(clip_buf, 'wb') as out_wf:
            out_wf.setnchannels(n_channels)
            out_wf.setsampwidth(sampwidth)
            out_wf.setframerate(framerate)
            out_wf.writeframes(frames)
        return clip_buf.getvalue()
    except Exception as e:
        logger.warning(f'Speaker ID: failed to extract clip: {e}')
        return None


def identify_speakers_for_segments(
    transcript_segments: List['TranscriptSegment'],
    audio_bytes: Optional[bytes],
    person_embeddings_cache: Dict[str, dict],
    uid: str,
) -> None:
    """Identify speakers in transcript segments using voice embeddings and text detection.

    Modifies segments in-place by assigning person_id and is_user fields.

    Steps:
    1. Voice embedding matching (requires audio_bytes and non-empty cache):
       For each unique speaker_id, find the longest segment (>=1s), extract audio clip,
       get embedding, match against person_embeddings_cache.
    2. Text-based detection ("I am X") runs independently for all unmatched speakers.
    3. Apply assignments via process_speaker_assigned_segments.
    """
    speaker_to_person_map: Dict[int, Tuple[str, str]] = {}
    segment_person_assignment_map: Dict[str, str] = {}

    # Group segments by speaker_id, find best (longest) segment per speaker for embedding
    speaker_segments: Dict[int, List[TranscriptSegment]] = {}
    for seg in transcript_segments:
        sid = seg.speaker_id if seg.speaker_id is not None else 0
        speaker_segments.setdefault(sid, []).append(seg)

    # Voice embedding matching (only when audio and cached embeddings are available)
    # Track matched person_ids so each person is only assigned to one speaker
    # (diarization tells us speakers are distinct — no person can be two speakers).
    matched_person_ids: set = set()

    if audio_bytes and person_embeddings_cache:
        # Sort speakers by best single segment duration (longest first) — this is the clip
        # actually used for embedding, so it determines match quality.
        # Note: matched_person_ids assumes diarization is correct (one person = one speaker).
        # If diarization fragments one person across speaker IDs, only the best match wins.
        sorted_speakers = sorted(
            speaker_segments.items(),
            key=lambda kv: max(s.end - s.start for s in kv[1]),
            reverse=True,
        )

        for speaker_id, segments in sorted_speakers:
            best_seg = max(segments, key=lambda s: s.end - s.start)
            seg_duration = best_seg.end - best_seg.start

            if seg_duration < SPEAKER_ID_MIN_AUDIO:
                continue

            clip_wav = _extract_speaker_clip_wav(audio_bytes, best_seg.start, best_seg.end)
            if not clip_wav:
                continue

            try:
                query_embedding = extract_embedding_from_bytes(clip_wav, "sync_speaker.wav")
            except (ValueError, Exception) as e:
                logger.info(f'Speaker ID: embedding extraction failed for speaker {speaker_id}: {e} uid={uid}')
                continue

            # Compare only against unmatched candidates (each person can be one speaker)
            best_match = None
            best_distance = float('inf')
            for person_id, data in person_embeddings_cache.items():
                if person_id in matched_person_ids:
                    continue
                distance = compare_embeddings(query_embedding, data['embedding'])
                if distance < best_distance:
                    best_distance = distance
                    best_match = (person_id, data['name'])

            if best_match and best_distance < SPEAKER_MATCH_THRESHOLD:
                person_id, person_name = best_match
                speaker_to_person_map[speaker_id] = (person_id, person_name)
                segment_person_assignment_map[best_seg.id] = person_id
                matched_person_ids.add(person_id)
                logger.info(
                    f'Speaker ID (sync): speaker {speaker_id} -> {person_id} '
                    f'(distance={best_distance:.3f}) uid={uid}'
                )

    # Text-based detection runs independently for all unmatched speakers.
    # For speaker_id > 0 (diarized): update both speaker_to_person_map and per-segment map.
    # For speaker_id <= 0 (undiarized): only assign per-segment (avoid mapping all speaker_id=0
    # segments to one person when diarization is inactive).
    for speaker_id, segments in speaker_segments.items():
        if speaker_id in speaker_to_person_map:
            continue
        for seg in segments:
            detected_name = detect_speaker_from_text(seg.text)
            if detected_name:
                person = users_db.get_person_by_name(uid, detected_name)
                if person:
                    # Per-segment assignment always applies
                    segment_person_assignment_map[seg.id] = person['id']
                    # Update speaker map only when diarization is active
                    if speaker_id > 0:
                        speaker_to_person_map[speaker_id] = (person['id'], person['name'])
                    logger.info(
                        f'Speaker ID (sync): text detection speaker {speaker_id} -> '
                        f'{person["id"]} via "{detected_name}" uid={uid}'
                    )
                    if speaker_id > 0:
                        break  # One match per diarized speaker is enough

    # Apply all assignments to segments
    if speaker_to_person_map or segment_person_assignment_map:
        process_speaker_assigned_segments(
            transcript_segments,
            segment_person_assignment_map,
            speaker_to_person_map,
        )


ORDERED_ASSIGNMENT_WAIT_SECONDS = 600


class _OrderedTurnstile:
    """Serializes conversation assignment across parallel segment threads in timestamp order.

    Segments are transcribed concurrently, but each must wait its (chronological) turn
    before looking up / creating a conversation. Without this, timestamp-adjacent chunks
    race get_closest_conversation_to_timestamps() before any of them has persisted a
    conversation, so every chunk becomes its own conversation (#6551, #5747).
    """

    def __init__(self, ordered_keys: List[str]):
        self._pending = deque(ordered_keys)
        self._done = set()
        self._cond = threading.Condition()

    def _advance(self):
        while self._pending and self._pending[0] in self._done:
            self._pending.popleft()

    def wait_turn(self, key: str, timeout: float = ORDERED_ASSIGNMENT_WAIT_SECONDS) -> bool:
        """Block until every earlier key has completed. Returns False on timeout (fail-open)."""
        with self._cond:
            return self._cond.wait_for(
                lambda: self._advance() or not self._pending or self._pending[0] == key, timeout=timeout
            )

    def complete(self, key: str):
        with self._cond:
            self._done.add(key)
            self._advance()
            self._cond.notify_all()


def process_segment(
    path: str,
    uid: str,
    response: dict,
    lock: threading.Lock,
    errors: list,
    source: ConversationSource = ConversationSource.omi,
    is_locked: bool = False,
    transcription_prefs: dict = None,
    person_embeddings_cache: dict = None,
    target_conversation_id: str = None,
    turnstile: Optional[_OrderedTurnstile] = None,
    private_cloud_sync_enabled: bool = False,
    data_protection_level: str = None,
    client_device_id: Optional[str] = None,
    client_platform: Optional[str] = None,
    sync_lane: str = SyncLane.FRESH.value,
    deferred_outcome: dict | None = None,
):
    provider = 'unknown'
    model = 'unknown'
    try:
        url = get_syncing_file_temporal_signed_url(path)
        schedule_syncing_temporal_file_deletion(path)

        # Apply user transcription preferences (vocabulary, language, model)
        prefs = transcription_prefs or {}
        user_vocab = [w for w in dict.fromkeys(prefs.get('vocabulary', [])) if w != "Omi"]
        vocabulary = ["Omi"] + user_vocab[:99]
        user_language = prefs.get('language', '') or ''
        single_language_mode = prefs.get('single_language_mode', False)

        req_language = user_language if (single_language_mode and user_language) else 'multi'
        provider, _, model = get_prerecorded_service(req_language)

        # When single-language mode is active, trust the user's language choice
        # rather than Deepgram's detection (avoids overriding explicit selection).
        use_return_language = not (single_language_mode and user_language)
        words, detected_language = prerecorded(
            url,
            speakers_count=3,
            attempts=0,
            return_language=True,
            language=req_language,
            keywords=vocabulary if vocabulary else None,
        )
        language = user_language if (single_language_mode and user_language) else detected_language
        if not words:
            # Every process_segment input has already passed VAD and is therefore
            # speech-eligible. A provider returning no words here is not the same
            # as the valid zero-segment result produced by the VAD phase.
            failure = empty_unexpected_failure(provider)
            _set_deferred_segment_outcome(
                deferred_outcome,
                outcome=failure.outcome,
                provider=failure.provider,
                model=model,
                retryable=failure.retryable,
            )
            _record_sync_segment_failure(
                failure,
                model=model,
                lane=sync_lane,
                lock=lock,
                errors=errors,
                record_metric=deferred_outcome is None,
            )
            return False
        transcript_segments: List[TranscriptSegment] = postprocess_words(words, 0)
        if not transcript_segments:
            failure = empty_unexpected_failure(provider)
            _set_deferred_segment_outcome(
                deferred_outcome,
                outcome=failure.outcome,
                provider=failure.provider,
                model=model,
                retryable=failure.retryable,
            )
            _record_sync_segment_failure(
                failure,
                model=model,
                lane=sync_lane,
                lock=lock,
                errors=errors,
                record_metric=deferred_outcome is None,
            )
            return False

        # Download the segment audio once — used for speaker ID and/or to persist the
        # conversation's audio as a private-cloud chunk (realtime parity, below).
        audio_bytes = _download_audio_bytes(url) if (person_embeddings_cache or private_cloud_sync_enabled) else None
        try:
            identify_speakers_for_segments(
                transcript_segments,
                audio_bytes if person_embeddings_cache else None,
                person_embeddings_cache or {},
                uid,
            )
        except Exception as e:
            logger.warning(
                'event=sync_speaker_id outcome=failed exception_type=%s',
                _bounded_exception_type(e),
            )
        finally:
            # Keep audio_bytes for chunk storage when private cloud sync is on; free it now otherwise.
            if audio_bytes is not None and not private_cloud_sync_enabled:
                audio_bytes = None

        # Conversation assignment must happen chronologically across the batch: wait until
        # every earlier-timestamped segment has created/merged its conversation, otherwise
        # the closest-conversation lookup races and adjacent chunks split into separate
        # conversations.
        if turnstile and not turnstile.wait_turn(path):
            logger.warning(f'sync: ordered assignment wait timed out for {path}, proceeding out of order')

        timestamp = get_timestamp_from_path(path)
        segment_end_timestamp = timestamp + transcript_segments[-1].end

        # When a target conversation is specified (auto-sync from live capture),
        # attach segments to it directly instead of searching by timestamp.
        if target_conversation_id:
            closest_memory = conversations_db.get_conversation(uid, target_conversation_id)
            if not closest_memory:
                logger.warning(
                    f'Target conversation {target_conversation_id} not found, falling back to timestamp lookup'
                )
                closest_memory = get_closest_conversation_to_timestamps(uid, timestamp, segment_end_timestamp)
        else:
            closest_memory = get_closest_conversation_to_timestamps(uid, timestamp, segment_end_timestamp)

        if not closest_memory:
            started_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            finished_at = datetime.fromtimestamp(segment_end_timestamp, tz=timezone.utc)
            create_memory = CreateConversation(
                started_at=started_at,
                finished_at=finished_at,
                transcript_segments=transcript_segments,
                source=source,
                is_locked=is_locked,
                private_cloud_sync_enabled=private_cloud_sync_enabled,
                client_device_id=client_device_id,
                client_platform=client_platform,
            )
            created = process_conversation(uid, language, create_memory)
            with lock:
                response['new_memories'].add(created.id)
            if private_cloud_sync_enabled:
                _store_sync_audio_chunk(uid, created.id, timestamp, audio_bytes, data_protection_level)
        else:

            transcript_segments = [s.model_dump() for s in transcript_segments]

            # assign timestamps to each segment
            for segment in transcript_segments:
                segment['timestamp'] = timestamp + segment['start']
            for segment in closest_memory['transcript_segments']:
                segment['timestamp'] = closest_memory['started_at'].timestamp() + segment['start']

            # Deduplicate: skip new segments whose timestamp range already exists in the conversation
            # (protects against retry after partial failure returning 207)
            existing_timestamps = {
                (round(s['timestamp'], 2), round(s['timestamp'] + (s['end'] - s['start']), 2))
                for s in closest_memory['transcript_segments']
            }
            deduped_segments = []
            for seg in transcript_segments:
                seg_key = (round(seg['timestamp'], 2), round(seg['timestamp'] + (seg['end'] - seg['start']), 2))
                if seg_key not in existing_timestamps:
                    deduped_segments.append(seg)
            if not deduped_segments:
                logger.info(f'All segments already exist in conversation {closest_memory["id"]}, skipping merge')
                with lock:
                    response['updated_memories'].add(closest_memory['id'])
                # No chunk upload here: this segment is a duplicate (retry or overlap with an
                # existing/realtime conversation), so its audio is already represented — uploading
                # again would double the audio in the merge.
                _set_deferred_segment_outcome(
                    deferred_outcome,
                    outcome=TranscriptionOutcome.SUCCESS,
                    provider=provider,
                    model=model,
                    retryable=False,
                )
                if deferred_outcome is None:
                    _record_sync_segment_outcome(
                        TranscriptionOutcome.SUCCESS,
                        provider=provider,
                        model=model,
                        lane=sync_lane,
                        retryable=False,
                    )
                return True

            # merge and sort segments by start timestamp
            segments = closest_memory['transcript_segments'] + deduped_segments
            segments.sort(key=lambda x: x['timestamp'])

            # fix segment.start .end to be relative to the memory
            for i, segment in enumerate(segments):
                duration = segment['end'] - segment['start']
                segment['start'] = segment['timestamp'] - closest_memory['started_at'].timestamp()
                segment['end'] = segment['start'] + duration

            # Calculate new finished_at based on the latest segment
            last_segment_end = segments[-1]['end'] if segments else 0
            new_finished_at = datetime.fromtimestamp(
                closest_memory['started_at'].timestamp() + last_segment_end, tz=timezone.utc
            )

            # Ensure finished_at doesn't go backwards
            if new_finished_at < closest_memory['finished_at']:
                new_finished_at = closest_memory['finished_at']

            # remove timestamp field
            for segment in segments:
                segment.pop('timestamp')

            # save with updated finished_at
            with lock:
                response['updated_memories'].add(closest_memory['id'])
            # Store the chunk before saving segments so "segment present ⇒ chunk present"
            # holds — a retry that dedup-skips this segment won't leave its audio missing.
            # Deterministic chunk path makes the upload overwrite-safe.
            if private_cloud_sync_enabled:
                _store_sync_audio_chunk(uid, closest_memory['id'], timestamp, audio_bytes, data_protection_level)
            update_conversation_segments(uid, closest_memory['id'], segments, finished_at=new_finished_at)

            # Lock existing conversation if credits exhausted
            if is_locked:
                conversations_db.update_conversation(uid, closest_memory['id'], {'is_locked': True})

            # Reprocess if conversation was discarded or if auto-synced WALs added new segments
            if closest_memory.get('discarded', False) or target_conversation_id:
                reason = 'discarded' if closest_memory.get('discarded', False) else 'auto-sync'
                logger.info(f'Conversation {closest_memory["id"]} reprocessing ({reason}) after segment merge')
                _reprocess_conversation_after_update(uid, closest_memory['id'], language)
            else:
                # Summary/structured data is now stale (it predates the merged segments).
                # Record it so the caller reprocesses once per conversation at batch end,
                # instead of once per merged segment.
                with lock:
                    response.setdefault('_merged', {})[closest_memory['id']] = language
        _set_deferred_segment_outcome(
            deferred_outcome,
            outcome=TranscriptionOutcome.SUCCESS,
            provider=provider,
            model=model,
            retryable=False,
        )
        if deferred_outcome is None:
            _record_sync_segment_outcome(
                TranscriptionOutcome.SUCCESS,
                provider=provider,
                model=model,
                lane=sync_lane,
                retryable=False,
            )
        return True
    except Exception as e:
        failure = failure_from_exception(e, provider=provider)
        _set_deferred_segment_outcome(
            deferred_outcome,
            outcome=failure.outcome,
            provider=failure.provider,
            model=model,
            retryable=failure.retryable,
        )
        _record_sync_segment_failure(
            failure,
            model=model,
            lane=sync_lane,
            lock=lock,
            errors=errors,
            record_metric=deferred_outcome is None,
        )
        return False
    finally:
        if turnstile:
            turnstile.complete(path)


def _reprocess_merged_conversations(uid: str, response: dict):
    """Regenerate summary/structured data for conversations that gained segments this batch.

    The merge path in process_segment only appends transcript segments; without this the
    conversation keeps the summary generated from its first chunk only.
    """
    merged = response.pop('_merged', {})
    for conversation_id, language in merged.items():
        try:
            _reprocess_conversation_after_update(uid, conversation_id, language)
        except Exception as e:
            logger.error(f'sync: failed to reprocess merged conversation {conversation_id}: {e}')


def _wav_bytes_to_pcm16_16k(audio_bytes: Optional[bytes]) -> Optional[bytes]:
    """Decode WAV bytes to raw PCM16, 16 kHz mono — the format upload_audio_chunk
    expects (it opus-encodes internally) and the audio merge is hardcoded to."""
    if not audio_bytes:
        return None
    seg = AudioSegment.from_wav(io.BytesIO(audio_bytes))
    seg = seg.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    return seg.raw_data


def _store_sync_audio_chunk(
    uid: str,
    conversation_id: str,
    timestamp: float,
    audio_bytes: Optional[bytes],
    data_protection_level: Optional[str],
):
    """Persist a sync segment's audio as a private-cloud chunk, identical in format and
    naming to the realtime path (chunks/{uid}/{conversation_id}/{ts}.opus[.enc]), so the
    conversation plays through the existing audio player. Best-effort — audio storage must
    never fail transcription."""
    try:
        pcm = _wav_bytes_to_pcm16_16k(audio_bytes)
        if not pcm:
            return
        upload_audio_chunk(pcm, uid, conversation_id, float(timestamp), data_protection_level)
        del pcm
    except Exception as e:
        logger.warning(f'sync: failed to store audio chunk for {conversation_id}@{timestamp}: {e}')


def _finalize_sync_audio_files(uid: str, response: dict):
    """After all segments are assigned, build audio_files from the uploaded chunks and
    persist them on each conversation — exactly as the realtime flush does — then warm the
    playback artifact. Rebuild+replace is idempotent across retries (create_audio_files_from_chunks
    always rebuilds from the full chunk listing)."""
    conversation_ids = set(response.get('new_memories', set())) | set(response.get('updated_memories', set()))
    for conversation_id in conversation_ids:
        try:
            audio_files = conversations_db.create_audio_files_from_chunks(uid, conversation_id)
            if not audio_files:
                continue
            files_payload = [af.model_dump() for af in audio_files]
            conversations_db.update_conversation(uid, conversation_id, {'audio_files': files_payload})
            precache_conversation_audio(uid, conversation_id, files_payload)
            if is_audio_merge_dispatch_enabled():
                enqueue_conversation_artifact_build(
                    uid, conversation_id, compute_audio_files_fingerprint(files_payload), caller='sync_finalize'
                )
        except Exception as e:
            logger.error(
                'event=sync_audio_finalize outcome=failed exception_type=%s',
                type(e).__name__,
            )


def _cleanup_files(file_paths: List[str]):
    """Helper to clean up temporary files."""
    for path in file_paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.error('event=sync_cleanup outcome=failed exception_type=%s', type(e).__name__)


def _retrieve_file_paths_v2(files: List[UploadFile], uid: str, job_id: str):
    """Like retrieve_file_paths but uses a job-specific directory to avoid concurrency conflicts."""
    directory = f'syncing/{uid}/{job_id}/'
    os.makedirs(directory, exist_ok=True)
    paths = []
    for file in files:
        filename = file.filename
        if not filename:
            raise HTTPException(status_code=400, detail='Uploaded file is missing a filename')
        if not filename.endswith('.bin'):
            raise HTTPException(status_code=400, detail='Invalid sync file format')
        if '_' not in filename:
            raise HTTPException(status_code=400, detail='Invalid sync file format')
        try:
            timestamp = get_timestamp_from_path(filename)
        except ValueError:
            raise HTTPException(status_code=400, detail='Invalid sync file format: invalid timestamp')

        time_val = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if time_val > datetime.now(timezone.utc) or time_val < datetime(2024, 1, 1, tzinfo=timezone.utc):
            raise HTTPException(status_code=400, detail='Invalid sync file format: invalid timestamp')

        path = f"{directory}{filename}"
        try:
            with open(path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            paths.append(path)
        except Exception as error:
            if os.path.exists(path):
                os.remove(path)
            raise HTTPException(status_code=500, detail='Unable to stage sync file') from error
    return paths


def _get_sync_pipeline_semaphore(sync_lane: str = SyncLane.FRESH.value) -> asyncio.Semaphore:
    """Return a loop-scoped semaphore capping concurrent sync pipelines."""
    if sync_lane == SyncLane.BACKFILL.value:
        return _get_semaphore('sync_pipeline_backfill', int(os.getenv('SYNC_INLINE_BACKFILL_CONCURRENCY', '2')))
    return _get_semaphore('sync_pipeline_fresh', 16)


async def _maintain_inline_run_lease(
    job_id: str,
    token: str,
    stop_event: asyncio.Event,
    lease_lost_event: asyncio.Event,
    owner_task: asyncio.Task[object] | None,
) -> None:
    """Renew an inline run lease without using job-state writes as a heartbeat."""
    lease_deadline = time.monotonic() + RUN_LOCK_TTL_SECONDS

    def lose_lease(outcome: str) -> None:
        """Stop before a stale/unowned coordinator can publish a terminal result."""
        logger.error('event=sync_inline_lease outcome=%s', outcome)
        lease_lost_event.set()
        if owner_task is not None:
            owner_task.cancel()

    while True:
        remaining_safe_lease = lease_deadline - time.monotonic() - RUN_LOCK_RENEWAL_SAFETY_SECONDS
        if remaining_safe_lease <= 0:
            # Do not keep retrying a broken Redis connection until a token has
            # actually expired. A late executor leaf is safer to preserve than
            # an unowned coordinator that could race another delivery.
            lose_lease('renew_deadline_exceeded')
            return
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=min(RUN_LOCK_HEARTBEAT_SECONDS, remaining_safe_lease))
            return
        except asyncio.TimeoutError:
            pass

        renew_timeout = lease_deadline - time.monotonic() - RUN_LOCK_RENEWAL_SAFETY_SECONDS
        if renew_timeout <= 0:
            lose_lease('renew_deadline_exceeded')
            return
        try:
            renewed = await asyncio.wait_for(
                run_blocking(db_executor, renew_job_run_lock, job_id, token), timeout=renew_timeout
            )
        except asyncio.TimeoutError:
            logger.warning('event=sync_inline_lease outcome=renew_timeout')
            continue
        except Exception as error:
            # Retries are bounded by ``lease_deadline`` above. Continuing past
            # that point would let an unowned inline coordinator race a later
            # delivery after Redis recovers.
            logger.warning(
                'event=sync_inline_lease outcome=renew_error exception_type=%s',
                _bounded_exception_type(error),
            )
            continue

        if renewed:
            lease_deadline = time.monotonic() + RUN_LOCK_TTL_SECONDS
            continue

        # The token no longer owns this lease. Stop at the next safe await;
        # cancellation preserves retry material because executor leaves may
        # still be completing after the coordinator unwinds.
        lose_lease('lost')
        return


async def _load_sync_segment_context(uid: str) -> tuple[bool, str | None, dict]:
    """Read the user settings needed by the ordered segment worker phase."""
    private_cloud_sync_enabled = bool(
        await run_blocking(db_executor, users_db.get_user_private_cloud_sync_enabled, uid)
    )
    data_protection_level = (
        await run_blocking(db_executor, users_db.get_data_protection_level, uid) if private_cloud_sync_enabled else None
    )
    try:
        person_embeddings_cache = await run_blocking(db_executor, build_person_embeddings_cache, uid)
        if person_embeddings_cache:
            logger.info(
                'event=sync_speaker_cache outcome=loaded embedding_count=%d',
                len(person_embeddings_cache),
            )
    except Exception as error:
        logger.warning(
            'event=sync_speaker_cache outcome=load_failed exception_type=%s',
            _bounded_exception_type(error),
        )
        person_embeddings_cache = {}
    return private_cloud_sync_enabled, data_protection_level, person_embeddings_cache


async def _record_restricted_sync_dg_usage(
    *,
    enabled: bool,
    uid: str,
    job_id: str,
    content_id: str | None,
    total_speech_seconds: float,
) -> None:
    """Meter post-STT Deepgram usage without complicating the coordinator flow."""
    if not enabled:
        return
    try:
        dg_ms = int(total_speech_seconds * 1000)
        should_record_dg = bool(content_id) or await run_blocking(db_executor, try_mark_once, job_id, 'dg_ms')
        if dg_ms > 0 and should_record_dg:
            await run_blocking(
                db_executor,
                record_dg_usage_ms,
                uid,
                dg_ms,
                idempotency_key=content_id,
                raise_on_error=bool(content_id),
            )
    except Exception as error:
        logger.error(
            'event=sync_usage outcome=dg_record_failed exception_type=%s',
            _bounded_exception_type(error),
        )
        if content_id:
            raise


async def _run_sync_vad_phase(wav_paths: list, segmented_paths: set) -> tuple[list[str], int]:
    """Finish all mutating VAD work before the coordinator advances or cleans up."""
    phase_started = time.monotonic()
    vad_errors: list[str] = []

    def _run_vad_bg(path: str):
        local_errors: list[str] = []
        try:
            retrieve_vad_segments(path, segmented_paths, local_errors)
        except Exception as error:
            if not local_errors:
                local_errors.append(_bounded_exception_type(error))
        finally:
            vad_errors.extend(local_errors)

    # Executor futures cannot stop their underlying threads when cancelled.
    # Abandoning a timed-out VAD worker would let it keep appending paths while
    # this coordinator cleans up and finalizes the job, so await every mutating
    # worker to completion. Provider/network calls inside the worker own their
    # actual request timeouts.
    vad_tasks = [run_blocking(sync_executor, _run_vad_bg, path) for path in wav_paths]
    vad_results = await asyncio.gather(*vad_tasks, return_exceptions=True)
    for result in vad_results:
        if isinstance(result, Exception):
            vad_errors.append(_bounded_exception_type(result))

    vad_ms = int((time.monotonic() - phase_started) * 1000)
    await run_blocking(storage_executor, _cleanup_files, wav_paths)
    return vad_errors, vad_ms


async def _run_full_pipeline_background_async(
    job_id: str,
    uid: str,
    raw_paths: list,
    source: ConversationSource,
    should_lock: bool,
    job_dir: str,
    target_conversation_id: str = None,
    task_mode: bool = False,
    client_device_id: Optional[str] = None,
    client_platform: Optional[str] = None,
    sync_lane: str = SyncLane.FRESH.value,
    content_id: Optional[str] = None,
    run_lock_token: Optional[str] = None,
    inline_run_lock_token: Optional[str] = None,
    content_run_bound: bool = False,
    ledger_fence_active: bool = True,
):
    """Async coordinator for the full sync pipeline (decode → VAD → fair-use → STT → LLM).

    Inline dispatch (task_mode=False): runs as a fire-and-forget asyncio task,
    bounded by the per-instance pipeline semaphore; unexpected errors mark the
    job failed (no retry exists).

    Cloud Tasks dispatch (task_mode=True): runs inside the /v2/sync-jobs/run
    request — Cloud Run's containerConcurrency is the concurrency bound, so no
    semaphore; unexpected errors re-raise so the handler can reset the job for
    a queue retry; segments that completed in a prior attempt are skipped via
    the processed-segment ledger.

    All blocking work is offloaded to thread pools via run_blocking(). The
    coordinator itself holds zero thread pool slots — only leaf operations use
    threads, and only for their actual duration.
    """
    sync_provider = 'unknown'
    sync_model = 'unknown'
    job_outcome_recorded = False
    preserve_retry_material = False
    # Both dispatch modes own a Redis token for every worker-driven job write.
    # Inline additionally renews it because it can wait behind the local
    # semaphore; Cloud Tasks stays below the request-timeout < lease invariant.
    # The separate inline argument owns heartbeat lifecycle only. It is also a
    # compatibility bridge for direct coordinator tests; production callers
    # pass the same token in both positions for inline work.
    # ``legacy`` is deliberately all-or-nothing during the mixed-revision
    # rollout: generic locks may still serialize work, but no epoch-aware
    # Redis or ledger mutation is attempted until the hard cutover enables
    # ``active`` for newly admitted jobs.
    active_run_lock_token = (run_lock_token or inline_run_lock_token) if ledger_fence_active else None
    active_run_lock_epoch: int | None = None
    concurrency_gate = contextlib.nullcontext() if task_mode else _get_sync_pipeline_semaphore(sync_lane)
    inline_lease_stop_event = asyncio.Event()
    inline_lease_lost_event = asyncio.Event()
    inline_lease_task = None
    propagate_finally_cancellation = False
    if inline_run_lock_token:
        owner_task = asyncio.current_task()
        inline_lease_task = start_background_task(
            _maintain_inline_run_lease(
                job_id,
                inline_run_lock_token,
                inline_lease_stop_event,
                inline_lease_lost_event,
                owner_task,
            ),
            name=f'sync:inline-lease:{job_id}',
        )
        if owner_task is not None:
            # If cancellation arrives while waiting for the concurrency gate,
            # this coordinator never reaches its inner cleanup/finally block.
            # Wake the heartbeat immediately instead of leaving it to renew a
            # lease for an abandoned task until its next five-minute tick.
            owner_task.add_done_callback(lambda _task: inline_lease_stop_event.set())
    async with concurrency_gate:
        set_byok_uid(uid if get_byok_keys() else None)
        segmented_paths = set()
        wav_paths = []
        stage_timings = {}
        pipeline_start = time.monotonic()
        try:
            if active_run_lock_token is not None:
                active_run_lock_epoch = await run_blocking(
                    db_executor, get_sync_job_run_lock_epoch, active_run_lock_token
                )
            if not content_run_bound:
                durable_completion = await run_blocking(
                    db_executor,
                    bind_or_converge_sync_ledger_completion,
                    job_id=job_id,
                    uid=uid,
                    content_id=content_id,
                    run_lock_token=active_run_lock_token,
                )
                if durable_completion is not None:
                    completed_outcome = (
                        TranscriptionOutcome(durable_completion['outcome'])
                        if durable_completion.get('outcome') in {item.value for item in TranscriptionOutcome}
                        else TranscriptionOutcome.SUCCESS
                    )
                    await _record_sync_job_outcome_async(
                        completed_outcome,
                        provider=durable_completion.get('provider', 'unknown'),
                        model=durable_completion.get('model', 'unknown'),
                        lane=sync_lane,
                        job_id=job_id,
                    )
                    job_outcome_recorded = True
                    return
            await run_blocking(db_executor, _mark_job_processing_for_run, job_id, active_run_lock_token)

            # --- Phase 1: Decode ---
            await run_blocking(
                db_executor, _update_sync_job_for_run, job_id, active_run_lock_token, {'stage': 'decoding'}
            )
            t0 = time.monotonic()
            try:
                wav_paths = await run_blocking(sync_executor, decode_files_to_wav, raw_paths)
            except asyncio.CancelledError:
                # Cancellation detaches only the asyncio Future; the decoder
                # leaf may still be reading these inputs in its executor. Keep
                # them, plus all retry ownership, until the original lease
                # expires rather than racing a destructive cleanup against it.
                preserve_retry_material = True
                raise
            except HTTPException:
                await _finalize_sync_job_failure(
                    job_id=job_id,
                    uid=uid,
                    content_id=content_id,
                    error_code='sync_invalid_audio',
                    outcome=TranscriptionOutcome.INVALID_INPUT,
                    provider=sync_provider,
                    model=sync_model,
                    lane=sync_lane,
                    run_lock_token=active_run_lock_token,
                )
                return
            except Exception as e:
                logger.error(
                    'event=sync_transcription_job outcome=upstream_error stage=decode exception_type=%s',
                    _bounded_exception_type(e),
                )
                await _finalize_sync_job_failure(
                    job_id=job_id,
                    uid=uid,
                    content_id=content_id,
                    error_code='sync_decode_failed',
                    outcome=TranscriptionOutcome.UPSTREAM_ERROR,
                    provider=sync_provider,
                    model=sync_model,
                    lane=sync_lane,
                    run_lock_token=active_run_lock_token,
                )
                return
            finally:
                current_task = asyncio.current_task()
                if (
                    not preserve_retry_material
                    and not inline_lease_lost_event.is_set()
                    and not (current_task and current_task.cancelling())
                ):
                    await run_blocking(storage_executor, _cleanup_files, raw_paths)
            stage_timings['decode_ms'] = int((time.monotonic() - t0) * 1000)

            if not wav_paths:
                # Decoding an admitted non-empty batch must yield at least one
                # WAV. Silence is authoritative only after decoded audio passes
                # VAD; an empty decoder result is invalid/retryable input.
                await _finalize_sync_job_failure(
                    job_id=job_id,
                    uid=uid,
                    content_id=content_id,
                    error_code='sync_invalid_audio',
                    outcome=TranscriptionOutcome.INVALID_INPUT,
                    provider='unknown',
                    model='unknown',
                    lane=sync_lane,
                    run_lock_token=active_run_lock_token,
                )
                return

            # --- Phase 2: VAD ---
            await run_blocking(db_executor, _update_sync_job_for_run, job_id, active_run_lock_token, {'stage': 'vad'})
            vad_errors, vad_ms = await _run_sync_vad_phase(wav_paths, segmented_paths)
            stage_timings['vad_ms'] = vad_ms
            wav_paths = []

            if vad_errors:
                await run_blocking(storage_executor, _cleanup_files, list(segmented_paths))
                segmented_paths = set()
                logger.error(
                    'event=sync_transcription_job outcome=upstream_error stage=vad failure_count=%d',
                    len(vad_errors),
                )
                await _finalize_sync_job_failure(
                    job_id=job_id,
                    uid=uid,
                    content_id=content_id,
                    error_code='sync_vad_failed',
                    outcome=TranscriptionOutcome.UPSTREAM_ERROR,
                    provider=sync_provider,
                    model=sync_model,
                    lane=sync_lane,
                    run_lock_token=active_run_lock_token,
                )
                return

            # --- Phase 3: Speech metrics & fair-use ---
            total_speech_seconds = await run_blocking(
                sync_executor, lambda: sum(get_wav_duration(p) for p in segmented_paths)
            )
            total_speech_ms = int(total_speech_seconds * 1000)
            total_segments = len(segmented_paths)

            await run_blocking(
                db_executor,
                _update_sync_job_for_run,
                job_id,
                active_run_lock_token,
                {'total_segments': total_segments, 'stage': 'processing'},
            )

            if total_segments == 0:
                empty_result = {
                    'new_memories': [],
                    'updated_memories': [],
                    'failed_segments': 0,
                    'total_segments': 0,
                    'errors': [],
                    'outcome': TranscriptionOutcome.EXPECTED_SILENCE.value,
                    'provider': 'unknown',
                    'model': 'unknown',
                    'lane': sync_lane,
                }
                if content_id:
                    completed_ledger = await run_blocking(
                        db_executor,
                        mark_sync_content_completed,
                        uid,
                        content_id,
                        job_id,
                        empty_result,
                        run_token=active_run_lock_token,
                        run_epoch=active_run_lock_epoch,
                    )
                    if not completed_ledger:
                        raise SyncJobRunLeaseLost(f'sync content ledger owner lost: job={job_id}')
                await run_blocking(
                    db_executor,
                    _finalize_sync_job_for_run,
                    job_id,
                    active_run_lock_token,
                    empty_result,
                )
                if ledger_fence_active:
                    await run_blocking(db_executor, delete_sync_job_run_lock_epoch, job_id)
                await _record_sync_job_outcome_async(
                    TranscriptionOutcome.EXPECTED_SILENCE,
                    provider='unknown',
                    model='unknown',
                    lane=sync_lane,
                    job_id=job_id,
                )
                return

            if sync_lane == SyncLane.BACKFILL.value:
                reservation = await run_blocking(
                    db_executor,
                    reserve_backfill_speech,
                    uid,
                    content_id or job_id,
                    total_speech_ms,
                )
                try:
                    OMI_SYNC_BACKFILL_DAILY_USED_MS.set(reservation.global_used_ms)
                except Exception:
                    pass
                if not reservation.allowed:
                    await run_blocking(storage_executor, _cleanup_files, list(segmented_paths))
                    segmented_paths = set()
                    await _finalize_sync_job_failure(
                        job_id=job_id,
                        uid=uid,
                        content_id=content_id,
                        error_code='sync_backfill_paced',
                        outcome=TranscriptionOutcome.UPSTREAM_ERROR,
                        provider=sync_provider,
                        model=sync_model,
                        lane=sync_lane,
                        reason_code=reservation.reason,
                        retry_after=reservation.retry_after,
                        run_lock_token=active_run_lock_token,
                    )
                    return

            try:
                OMI_SYNC_LANE_SPEECH_MS_TOTAL.labels(lane=sync_lane).inc(total_speech_ms)
            except Exception:
                pass

            if FAIR_USE_ENABLED and total_speech_ms > 0:
                # Redis performs the content-key check and increment in one
                # Lua transaction. Legacy jobs retain their job-scoped guard.
                should_meter = bool(content_id) or await run_blocking(db_executor, try_mark_once, job_id, 'speech_ms')
                if should_meter:
                    # Use a distinct local for the metering source. Reassigning `source`
                    # here clobbered the ConversationSource parameter, so later
                    # conversation creation received the metering string
                    # ('sync_fresh'/'sync_backfill'), which coerces to
                    # ConversationSource.unknown — every v2-synced new conversation was
                    # stored with source=unknown. Mirrors the v1 endpoint's meter_source
                    # local.
                    meter_source = 'sync_backfill' if sync_lane == SyncLane.BACKFILL.value else 'sync_fresh'
                    await run_blocking(
                        db_executor,
                        record_speech_ms,
                        uid,
                        total_speech_ms,
                        source=meter_source,
                        idempotency_key=content_id,
                        raise_on_error=bool(content_id),
                    )
                if sync_lane == SyncLane.FRESH.value:
                    speech_totals = await run_blocking(db_executor, get_rolling_speech_ms, uid)
                    triggered_caps = await run_blocking(db_executor, check_soft_caps, uid, speech_totals=speech_totals)
                    if triggered_caps:
                        logger.info(
                            'event=sync_fair_use outcome=soft_cap_triggered cap_count=%d',
                            len(triggered_caps),
                        )
                        try:
                            asyncio.create_task(trigger_classifier_if_needed(uid, triggered_caps))
                        except Exception as e:
                            logger.error(
                                'event=sync_classifier outcome=schedule_failed exception_type=%s',
                                _bounded_exception_type(e),
                            )

            # DG budget gate
            fair_use_restrict_dg = False
            if FAIR_USE_ENABLED and sync_lane == SyncLane.FRESH.value:
                try:
                    fair_use_stage = await run_blocking(db_executor, get_enforcement_stage, uid)
                    if fair_use_stage == 'restrict' and FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
                        fair_use_restrict_dg = True
                        if await run_blocking(db_executor, is_dg_budget_exhausted, uid):
                            await run_blocking(storage_executor, _cleanup_files, list(segmented_paths))
                            segmented_paths = set()
                            await _finalize_sync_job_failure(
                                job_id=job_id,
                                uid=uid,
                                content_id=content_id,
                                error_code='sync_transcription_budget_exhausted',
                                outcome=TranscriptionOutcome.UPSTREAM_ERROR,
                                provider=sync_provider,
                                model=sync_model,
                                lane=sync_lane,
                                run_lock_token=active_run_lock_token,
                            )
                            return
                except Exception as e:
                    logger.error(
                        'event=sync_fair_use outcome=check_failed exception_type=%s',
                        _bounded_exception_type(e),
                    )

            is_locked = should_lock

            # --- Phase 4: Fetch prefs & embeddings ---
            transcription_prefs = await run_blocking(db_executor, users_db.get_user_transcription_preferences, uid)
            user_language = transcription_prefs.get('language', '') or ''
            req_language = (
                user_language if transcription_prefs.get('single_language_mode', False) and user_language else 'multi'
            )
            sync_provider, _, sync_model = get_prerecorded_service(req_language)
            await run_blocking(
                db_executor,
                _update_sync_job_for_run,
                job_id,
                active_run_lock_token,
                {
                    'stt_provider': bounded_provider(sync_provider),
                    'stt_model': _bounded_sync_model(sync_model),
                },
            )
            # Mirror realtime: store conversation audio only when private cloud sync is on.
            private_cloud_sync_enabled, data_protection_level, person_embeddings_cache = (
                await _load_sync_segment_context(uid)
            )

            # --- Phase 5: Process segments (STT + LLM) ---
            await run_blocking(
                db_executor, _update_sync_job_for_run, job_id, active_run_lock_token, {'stage': 'stt_llm'}
            )
            t0 = time.monotonic()
            current_job = await run_blocking(db_executor, get_sync_job, job_id)
            partial_result = (current_job or {}).get('partial_result') or {}
            if content_id:
                durable_partial = await run_blocking(db_executor, get_sync_content_partial_result, uid, content_id)
                partial_result = {
                    'new_memories': sorted(
                        set(partial_result.get('new_memories') or []) | set(durable_partial.get('new_memories') or [])
                    ),
                    'updated_memories': sorted(
                        set(partial_result.get('updated_memories') or [])
                        | set(durable_partial.get('updated_memories') or [])
                    ),
                }
            response = {
                'updated_memories': set(partial_result.get('updated_memories') or []),
                'new_memories': set(partial_result.get('new_memories') or []),
            }
            segment_errors = []
            segment_lock = threading.Lock()

            # Segments that fully landed in a prior Cloud Tasks attempt are skipped
            already_processed = set()
            if task_mode:
                already_processed = await run_blocking(db_executor, get_processed_segments, job_id)
                if already_processed:
                    logger.info(
                        'event=sync_transcription_retry outcome=deduplicated segment_count=%d',
                        len(already_processed),
                    )

            durable_processed_segment_ids: set[str] = set()
            segment_ids_by_path: dict[str, str] = {}
            if content_id:
                durable_processed_segment_ids = await run_blocking(
                    db_executor, get_processed_sync_segment_ids, uid, content_id
                )
                segment_ids_by_path = {
                    path: await run_blocking(sync_executor, compute_sync_segment_id, uid, path)
                    for path in segmented_paths
                }

            # Chronological order + turnstile: STT runs in parallel (per chunk), but
            # conversation assignment is serialized oldest-first so adjacent chunks merge
            # instead of racing into separate conversations (#6551, #5747).
            segment_list = sorted(segmented_paths, key=get_timestamp_from_path)
            assignment_turnstile = _OrderedTurnstile(segment_list)

            def _process_one_segment(path: str):
                segment_id = segment_ids_by_path.get(path)
                if path in already_processed or (segment_id and segment_id in durable_processed_segment_ids):
                    # Release the assignment slot — later segments wait on it
                    assignment_turnstile.complete(path)
                    return
                deferred_outcome: dict = {}
                ok = process_segment(
                    path,
                    uid,
                    response,
                    segment_lock,
                    segment_errors,
                    source,
                    is_locked,
                    transcription_prefs,
                    person_embeddings_cache,
                    target_conversation_id,
                    assignment_turnstile,
                    private_cloud_sync_enabled=private_cloud_sync_enabled,
                    data_protection_level=data_protection_level,
                    client_device_id=client_device_id,
                    client_platform=client_platform,
                    sync_lane=sync_lane,
                    deferred_outcome=deferred_outcome,
                )
                if ok:
                    # Persist result contributions before the processed marker.
                    # Therefore any skipped segment on a retry has its visible
                    # conversation IDs available for response hydration.
                    with segment_lock:
                        partial = {
                            'new_memories': sorted(response['new_memories']),
                            'updated_memories': sorted(response['updated_memories']),
                        }
                        _update_sync_job_for_run(job_id, active_run_lock_token, {'partial_result': partial})
                        if content_id:
                            checkpointed = checkpoint_sync_content_partial_result(
                                uid,
                                content_id,
                                job_id,
                                partial,
                                run_token=active_run_lock_token,
                                run_epoch=active_run_lock_epoch,
                            )
                            if not checkpointed:
                                raise SyncJobRunLeaseLost(f'sync content ledger owner lost: job={job_id}')
                if ok and task_mode:
                    _add_processed_segment_for_run(job_id, active_run_lock_token, path)
                if ok and content_id and segment_id:
                    marked_segment = add_processed_sync_segment_id(
                        uid,
                        content_id,
                        job_id,
                        segment_id,
                        run_token=active_run_lock_token,
                        run_epoch=active_run_lock_epoch,
                    )
                    if not marked_segment:
                        raise SyncJobRunLeaseLost(f'sync content ledger owner lost: job={job_id}')
                metric_key = segment_id or path
                if ok:
                    outcome, outcome_provider, outcome_model, retryable = _deferred_segment_labels(
                        deferred_outcome,
                        fallback_outcome=TranscriptionOutcome.SUCCESS,
                        fallback_provider=sync_provider,
                        fallback_model=sync_model,
                        fallback_retryable=False,
                    )
                    _record_sync_segment_outcome(
                        outcome,
                        provider=outcome_provider,
                        model=outcome_model,
                        lane=sync_lane,
                        retryable=retryable,
                        job_id=job_id,
                        segment_key=metric_key,
                    )
                elif ok is False:
                    outcome, outcome_provider, outcome_model, retryable = _deferred_segment_labels(
                        deferred_outcome,
                        fallback_outcome=TranscriptionOutcome.UPSTREAM_ERROR,
                        fallback_provider=sync_provider,
                        fallback_model=sync_model,
                        fallback_retryable=True,
                    )
                    _record_sync_segment_outcome(
                        outcome,
                        provider=outcome_provider,
                        model=outcome_model,
                        lane=sync_lane,
                        retryable=retryable,
                        job_id=job_id,
                        segment_key=metric_key,
                    )

            chunk_size = 5
            for i in range(0, len(segment_list), chunk_size):
                chunk = segment_list[i : i + chunk_size]
                # Do not wrap executor work in asyncio.wait_for: cancellation only
                # detaches the Future while the thread keeps mutating response, job,
                # conversation, and audio state. Await the whole chunk before any
                # reprocessing/finalization step can observe it.
                seg_tasks = [run_blocking(sync_executor, _process_one_segment, path) for path in chunk]
                seg_results = await asyncio.gather(*seg_tasks, return_exceptions=True)
                for path, r in zip(chunk, seg_results):
                    if isinstance(r, SyncJobRunLeaseLost):
                        raise r
                    if isinstance(r, Exception):
                        failure = failure_from_exception(r, provider=sync_provider)
                        await _record_sync_segment_failure_async(
                            failure,
                            model=sync_model,
                            lane=sync_lane,
                            lock=segment_lock,
                            errors=segment_errors,
                            job_id=job_id,
                            segment_key=segment_ids_by_path.get(path) or path,
                        )
                try:
                    await run_blocking(
                        db_executor,
                        _update_sync_job_for_run,
                        job_id,
                        active_run_lock_token,
                        {'processed_segments': min(i + chunk_size, len(segment_list))},
                    )
                except SyncJobRunLeaseLost:
                    raise
                except Exception:
                    pass

            await run_blocking(sync_executor, _reprocess_merged_conversations, uid, response)

            # Persist conversation audio (private-cloud chunks → audio_files) so synced
            # conversations play exactly like realtime ones. Gated on the user's setting.
            if private_cloud_sync_enabled:
                await run_blocking(sync_executor, _finalize_sync_audio_files, uid, response)

            stage_timings['stt_llm_ms'] = int((time.monotonic() - t0) * 1000)

            # Record DG usage after processing.
            await _record_restricted_sync_dg_usage(
                enabled=fair_use_restrict_dg,
                uid=uid,
                job_id=job_id,
                content_id=content_id,
                total_speech_seconds=total_speech_seconds,
            )

            # Build result
            failed_segments = len(segment_errors)
            successful_segments = total_segments - failed_segments
            job_outcome = _job_transcription_outcome(segment_errors)
            result = {
                'new_memories': sorted(response['new_memories']),
                'updated_memories': sorted(response['updated_memories']),
            }
            if failed_segments > 0:
                result['failed_segments'] = failed_segments
                result['total_segments'] = total_segments
                result['errors'] = segment_errors[:10]

            if successful_segments > 0:
                try:
                    usage_seconds = int(total_speech_seconds)
                    should_record_usage = bool(content_id) or await run_blocking(
                        db_executor, try_mark_once, job_id, 'usage'
                    )
                    if usage_seconds > 0 and should_record_usage:
                        await run_blocking(
                            db_executor,
                            record_usage,
                            uid,
                            transcription_seconds=usage_seconds,
                            speech_seconds=usage_seconds,
                            idempotency_key=content_id,
                        )
                except Exception as e:
                    logger.error(
                        'event=sync_usage outcome=record_failed exception_type=%s',
                        _bounded_exception_type(e),
                    )
                    if content_id:
                        raise

            stage_timings['total_ms'] = int((time.monotonic() - pipeline_start) * 1000)
            final_result = {
                'new_memories': result['new_memories'],
                'updated_memories': result['updated_memories'],
                'failed_segments': failed_segments,
                'total_segments': total_segments,
                'errors': segment_errors[:10] if segment_errors else [],
                'stage_timings': stage_timings,
                'outcome': job_outcome.value,
                'provider': bounded_provider(sync_provider),
                'model': _bounded_sync_model(sync_model),
                'lane': sync_lane,
            }
            if content_id and failed_segments == 0:
                # The durable content ledger proves every successful segment
                # before the WAL-visible completed status is published.
                completed_ledger = await run_blocking(
                    db_executor,
                    mark_sync_content_completed,
                    uid,
                    content_id,
                    job_id,
                    final_result,
                    run_token=active_run_lock_token,
                    run_epoch=active_run_lock_epoch,
                )
                if not completed_ledger:
                    raise SyncJobRunLeaseLost(f'sync content ledger owner lost: job={job_id}')
            # The fenced terminal write is the only state transition that can
            # authorize a retry-claim release. A stale owner cannot free the
            # current owner's material after its lease is replaced.
            await run_blocking(
                db_executor,
                _finalize_sync_job_for_run,
                job_id,
                active_run_lock_token,
                final_result,
            )
            if content_id and failed_segments > 0:
                if ledger_fence_active:
                    await run_blocking(
                        db_executor,
                        release_sync_content_claim_after_job_retired,
                        uid,
                        content_id,
                        job_id,
                    )
                else:
                    await run_blocking(db_executor, release_sync_content_claim, uid, content_id, job_id)
            if ledger_fence_active:
                await run_blocking(db_executor, delete_sync_job_run_lock_epoch, job_id)
            await _record_sync_job_outcome_async(
                job_outcome,
                provider=sync_provider,
                model=sync_model,
                lane=sync_lane,
                job_id=job_id,
            )
            job_outcome_recorded = True

            logger.info(
                'event=sync_transcription_job outcome=%s status=finalized provider=%s model=%s '
                'lane=%s successful_segments=%d total_segments=%d total_ms=%d',
                job_outcome.value,
                bounded_provider(sync_provider),
                _bounded_sync_model(sync_model),
                _bounded_sync_lane(sync_lane),
                successful_segments,
                total_segments,
                stage_timings['total_ms'],
            )
        except asyncio.CancelledError:
            # Never release the lock, claim, or local files under an executor
            # leaf that can outlive this coordinator. Cloud Tasks/inline retry
            # only after the token lease naturally expires.
            preserve_retry_material = True
            logger.warning('event=sync_transcription_job outcome=cancelled retry_material=preserved')
            raise
        except SyncJobRunLeaseLost:
            # A replacement owner may already be working. Do not publish a
            # fallback failure, release its claim, clean local inputs, or drop
            # the run token; the caller/client recovers after the lease bound.
            preserve_retry_material = True
            logger.warning('event=sync_transcription_job outcome=lease_lost retry_material=preserved')
            raise
        except Exception as e:
            failure = failure_from_exception(e, provider=sync_provider)
            logger.error(
                'event=sync_transcription_job outcome=%s status=%s provider=%s model=%s ' 'lane=%s exception_type=%s',
                failure.outcome.value,
                'retrying' if task_mode else 'failed',
                failure.provider,
                _bounded_sync_model(sync_model),
                _bounded_sync_lane(sync_lane),
                _bounded_exception_type(e),
            )
            # Cloud Tasks owns retry/final-attempt state outside this function.
            # Counting a retry here as a terminal job would corrupt the
            # accepted-to-completed SLI, so only inline terminal failures emit
            # the terminal counter at this boundary.
            if not job_outcome_recorded and not task_mode:
                await _record_sync_job_outcome_async(
                    failure.outcome,
                    provider=failure.provider,
                    model=sync_model,
                    lane=sync_lane,
                    job_id=job_id,
                )
            if task_mode:
                # Let the handler decide: queued-reset + Cloud Tasks retry, or
                # final-attempt consume. Marking failed here would be terminal.
                raise
            try:
                await _finalize_sync_job_failure(
                    job_id=job_id,
                    uid=uid,
                    content_id=content_id,
                    error_code=failure.error_code,
                    outcome=failure.outcome,
                    provider=failure.provider,
                    model=sync_model,
                    lane=sync_lane,
                    run_lock_token=active_run_lock_token,
                )
            except SyncJobRunLeaseLost:
                preserve_retry_material = True
                raise
            except Exception as terminal_error:
                preserve_retry_material = True
                logger.error(
                    'event=sync_transcription_job outcome=persist_failed exception_type=%s',
                    _bounded_exception_type(terminal_error),
                )
        finally:
            if inline_lease_task is not None:
                inline_lease_stop_event.set()
                try:
                    await inline_lease_task
                except asyncio.CancelledError:
                    # This can be the coordinator cancellation requested by a
                    # lost lease while teardown awaits the heartbeat. Never
                    # swallow it into normal cleanup/release behavior.
                    preserve_retry_material = True
                    propagate_finally_cancellation = True
            if inline_lease_lost_event.is_set():
                # The lease task may have completed just before cancellation
                # is delivered to this coordinator. The event makes that
                # terminal ownership loss durable across teardown scheduling.
                preserve_retry_material = True
            set_byok_keys({})
            set_byok_uid(None)
            if not preserve_retry_material:
                await run_blocking(storage_executor, _cleanup_files, list(segmented_paths))
                await run_blocking(storage_executor, _cleanup_files, wav_paths)
                try:
                    if job_dir and os.path.isdir(job_dir):
                        await run_blocking(storage_executor, shutil.rmtree, job_dir, True)
                except Exception as e:
                    logger.error(
                        'event=sync_cleanup outcome=failed exception_type=%s',
                        _bounded_exception_type(e),
                    )
            if not task_mode and not preserve_retry_material:
                if sync_lane == SyncLane.BACKFILL.value:
                    try:
                        await run_blocking(db_executor, release_backfill_slot, uid, job_id)
                    except Exception as e:
                        logger.warning(
                            'event=sync_backfill_slot outcome=release_failed exception_type=%s',
                            _bounded_exception_type(e),
                        )
            if inline_run_lock_token and not preserve_retry_material:
                await run_blocking(db_executor, release_job_run_lock, job_id, inline_run_lock_token)
            if propagate_finally_cancellation:
                raise asyncio.CancelledError


def _stage_files_to_gcs(paths: list):
    """Upload raw .bin files to the syncing bucket (blob name = local path)."""
    for p in paths:
        upload_syncing_temporal_file(p)


def _delete_staged_blobs(blob_paths: list):
    for p in blob_paths:
        try:
            delete_syncing_temporal_file(p)
        except Exception as e:
            logger.warning('event=sync_unstage outcome=failed exception_type=%s', type(e).__name__)


async def _delete_staged_blobs_async(blob_paths: list):
    await run_blocking(storage_executor, _delete_staged_blobs, blob_paths)


def _download_staged_files(blob_paths: list) -> bool:
    """Download staged blobs back to their local paths. False if any is gone."""
    for p in blob_paths:
        if not download_syncing_temporal_file(p):
            return False
    return True
