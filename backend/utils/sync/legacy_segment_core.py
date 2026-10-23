# LIFECYCLE: temporary (delete with lane 8 batch cap-hold rehome; owner lead/lane8, by 2026-11-01)
"""Recovery/staging core retained after legacy coordinator retirement.

Current source closure, with minimal-redrive-only behavior removed.
No legacy upload admission, sequencer or job coordinator remains here.
"""

# pyright: reportPrivateUsage=false, reportUnusedFunction=false, reportUnusedVariable=false, reportUnusedImport=false, reportUnnecessaryComparison=false, reportAssignmentType=false, reportIndexIssue=false, reportArgumentType=false

from __future__ import annotations

from utils.conversations.silent_redrive import is_silent_redrive
from utils.observability.sync_phases import sync_phase
from utils.sync.vad_segments import MAX_VAD_SEGMENT_SECONDS
import asyncio
import contextlib
import hashlib
import io
import logging
import os
import shutil
import threading
import time
from collections import deque
from functools import partial
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional
import httpx
from google.api_core import exceptions as google_exceptions
from database._client import (
    get_firestore_client,
    FIRESTORE_DOCUMENT_KINDS,
    firestore_document_kind,
    is_document_size_limit_error,
    is_expired_transaction_error,
)
from fastapi import HTTPException, UploadFile
from pydub import AudioSegment
from utils.sync import cap_recovery_provider
from utils.sync import conversation_turn as conversation_turn_lease
from database import conversations as conversations_db
from database.summary_processing import claim_from_snapshot
from utils.conversations.summary_delivery import (
    repair_fenced,
    refusal as summary_repair_refusal,
    REPAIR_CONTEXT,
    PROCESS_CONTEXT,
    SummaryRepairSuperseded,
)
from database import users as users_db
from database.auth import get_user_name
from database.conversations import get_closest_conversation_to_timestamps
from database.sync_jobs import delete_sync_job_run_lock_epoch, fenced_mark_job_failed, mark_job_failed, try_mark_once
from database.sync_ledger import release_sync_content_claim_after_job_retired, release_sync_content_claim
from utils.stt.transcript_admission import admit_segments
from models.conversation import Conversation, CreateConversation
from models.conversation_enums import ConversationSource
from models.geolocation import Geolocation
from models.transcript_segment import TranscriptSegment
from utils.dream_vocabulary import keyterms
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.factory import deserialize_conversation
from utils.conversations.fragment_visibility import is_user_curated
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.process_conversation import process_conversation
from utils.conversations.relevance import sync_intake_decision
from utils.executors import postprocess_executor, submit_with_context
from utils.cloud_tasks import is_audio_merge_dispatch_enabled
from utils.other.storage import (
    compute_audio_files_fingerprint,
    enqueue_conversation_artifact_build,
    get_syncing_file_temporal_signed_url,
    precache_conversation_audio,
    schedule_syncing_temporal_file_deletion,
    upload_audio_chunk,
)
from utils.observability.fallback import record_fallback
from utils.observability.transcription import record_sync_transcription_outcome
from config.transcription_final_pass import sync_enabled_for
from utils.speaker_assignment import process_speaker_assigned_segments
from utils.speaker_identification import detect_speaker_from_text
from utils.stt.voiceprints import usable_person_voiceprint
from config.stt_cap_dispatch import execution_admission_enabled as cap_enabled, recovery_admission_enabled, LANES
from utils.stt_cap_dispatch import sync_allowed, funded_allowance
from utils.observability.stt_cap_dispatch import record_audio as record_cap_audio
from utils.stt.pre_recorded import (
    get_prerecorded_service,
    modulate_prerecorded_from_bytes,
    postprocess_words,
    prerecorded,
)
from utils.sync import empty_recovery, empty_success_guard
from utils.sync.empty_recovery_intent import dispatch_once as dispatch_empty_recovery_once
from utils.stt.outcomes import (
    TranscriptionFailure,
    TranscriptionOutcome,
    bounded_provider,
    failure_from_exception,
    is_destructive_operation_in_progress,
)
from utils.stt.speaker_embedding import compare_embeddings, extract_embedding_from_bytes, speaker_embedding_configured
from utils.stt.speaker_match import mean_embedding, select_speaker_match
from utils.stt.sync_speaker_evidence import collect_speaker_audio
from utils.observability.speaker_identification import SYNC_SPEAKER_DECISIONS
from utils.stt.vad import vad_is_empty
from utils.sync.clock_run import SYNC_CLOCK_RUN_FIELD, clock_run_from_path, segment_name_prefix
from utils.sync.files import get_timestamp_from_path, get_wav_duration
from utils.sync.input_limits import raise_sync_storage_pressure
from utils.sync.capture import chunk_identity
from utils.capture.sync_coverage import record_sync, annotate_identity, covering_target
from utils.sync.word_timing import first_word_offset, shift_to_vad_file_clock
from config.sync_safety_wal import sync_safety_wal_enabled
from utils.sync.safety_wal_metrics import AUDIO_BYTES_NOT_STORED, SEGMENTS_DEDUPED, suppressed_pcm_bytes
from utils.sync.ledger_completion import SyncJobRunLeaseLost, _require_run_owner
from utils.sync.recording_lineage import ambiguous_binding_pending
from utils.sync.bridge import finish_sync_segment
from utils.sync.assignment_errors import (
    SyncAssignmentConflict,
    SyncAssignmentConflictReason as Conflict,
    SyncAssignmentSuperseded,
    bounded_sync_assignment_subtype,
)
from utils.sync.failure_reason import SYNC_INTERNAL_ERROR_CODES, outcome_label
from utils.sync.failure_reason import sync_failure_error_code
from config.sync_telemetry import SyncFailureReason
from utils.sync.failure_reason import persistence_failure_fingerprint as _persistence_failure_fingerprint
from utils.sync.failure_reason import sync_failure_reason as _sync_failure_reason
from utils.sync.content_id import compute_sync_segment_id
from utils.sync.intake_completion import (
    acknowledge_processed_segment,
    apply_capture_evidence_dark_write,
    complete_sync_intake,
    record_capture_evidence_metric,
)
from utils.sync.lanes import SyncLane
from utils.sync.telemetry import bounded_correlation_ref as _bounded_correlation_ref
from utils.sync.telemetry import bounded_exception_class, finalize_exception_site
from utils.sync.telemetry import bounded_exception_type as _bounded_exception_type
from utils.sync.telemetry import bounded_sync_lane as _bounded_sync_lane
from utils.sync.telemetry import bounded_sync_language as _bounded_retry_language
from utils.sync.telemetry import bounded_sync_model as _bounded_sync_model
from utils.sync.telemetry import bounded_sync_phase as _bounded_sync_phase
from utils.sync.merge_audio import store_partial_merge_survivor_audio, store_intake_audio, store_sync_audio_chunk
from utils.sync.assignment import fragment_rule
from utils.sync.speaker_identity import PersonEmbeddingsCache, SpeakerIdentityDependencies
from utils.sync.speaker_identity import build_person_embeddings_cache as _build_person_embeddings_cache
from utils.sync.speaker_identity import identify_speakers_for_segments as _identify_speakers_for_segments
from utils.manual_speaker_assignments import manual_owner_reserved
from utils.conversations.deterministic_minimum import build_deterministic_minimum_structured
from utils.journey_metrics_contract import resolve_client_kind
from utils.metrics import record_conversation_relevance
from utils.observability.journeys import record_client_journey_accepted, record_client_journey_terminal

logger = logging.getLogger(__name__)


_NON_ERROR_SEGMENT_OUTCOMES = frozenset({TranscriptionOutcome.SUCCESS, TranscriptionOutcome.EXPECTED_SILENCE})


_RESPONSE_FENCED_CONVERSATION_IDS = '_fenced_conversation_ids'


_LINEAGE_RETRY_LANGUAGE = '__stored_conversation_language__'


_SYNC_FAILURE_REASON_CODES = {
    'backfill_capacity',
    'backfill_paced',
    'destructive_operation_in_progress',
    'stt_empty_unexpected',
    'stt_invalid_input',
    'stt_provider_configuration_error',
    'stt_provider_budget_exhausted',
    'stt_timeout',
    'stt_upstream_error',
    'sync_backfill_dispatch_unavailable',
    'sync_backfill_paced',
    'sync_conversation_persistence_fenced',
    'sync_dispatch_staging_failed',
    'sync_decode_failed',
    'sync_invalid_audio',
    'sync_persistence_failed',
    'sync_staged_audio_expired',
    'sync_transcription_budget_exhausted',
    'sync_vad_failed',
    'sync_worker_stale',
} | SYNC_INTERNAL_ERROR_CODES


def _firestore_error_class(error: BaseException) -> str:
    if is_document_size_limit_error(error):
        return 'document_size_limit'
    if is_expired_transaction_error(error):
        return 'expired_transaction'
    if isinstance(error, google_exceptions.InvalidArgument):
        return 'invalid_argument_other'
    return bounded_exception_class(error) if isinstance(error, google_exceptions.GoogleAPICallError) else 'none'


def _firestore_doc_kind(error: BaseException) -> str:
    """Which document a Firestore rejection named, as one bounded token; never the path or ids.

    The sync assignment boundary may refine ``conversation`` to ``donor``.
    """
    stamped = getattr(error, 'sync_firestore_doc_kind', None)
    if isinstance(stamped, str) and stamped in FIRESTORE_DOCUMENT_KINDS:
        return stamped
    return firestore_document_kind(error)


def _bounded_sync_failure_reason(reason: str | None) -> str:
    return reason if reason in _SYNC_FAILURE_REASON_CODES else 'other'


def _sync_assignment_failure_subtype(error: object) -> str:
    if isinstance(error, SyncAssignmentConflict):
        return bounded_sync_assignment_subtype(error.subtype)
    return 'none'


def _record_sync_segment_outcome(
    outcome: TranscriptionOutcome,
    *,
    provider: str,
    model: str,
    lane: str,
    retryable: bool,
    job_id: str | None = None,
    segment_key: str | None = None,
    phase: str | None = None,
    exception: BaseException | str | None = None,
    attempt_ref: str | None = None,
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
    log = logger.info if outcome in _NON_ERROR_SEGMENT_OUTCOMES else logger.error
    reason = _sync_failure_reason(None if outcome in _NON_ERROR_SEGMENT_OUTCOMES else phase, exception)
    log(
        'event=sync_transcription_segment outcome=%s provider=%s model=%s lane=%s retryable=%s '
        'phase=%s exception_type=%s job_ref=%s attempt_ref=%s%s',
        outcome_label(outcome.value, reason),
        bounded_provider(provider),
        _bounded_sync_model(model),
        _bounded_sync_lane(lane),
        str(retryable).lower(),
        'none' if phase is None and outcome in _NON_ERROR_SEGMENT_OUTCOMES else _bounded_sync_phase(phase or 'unknown'),
        bounded_exception_class(exception),
        _bounded_correlation_ref(job_id),
        _bounded_correlation_ref(attempt_ref),
        '' if reason is SyncFailureReason.NONE else f' failure_reason={reason.value}',
    )
    try:
        record_sync_transcription_outcome(
            kind='segment',
            provider=provider,
            model=model,
            lane=lane,
            outcome=outcome,
            failure_reason=reason,
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
    phase: str | None = None,
    exception: BaseException | str | None = None,
    attempt_ref: str | None = None,
) -> None:
    if job_id and failure.outcome.value in empty_success_guard.PROVIDER_CLASS_OUTCOMES:
        # Durable per-job provider-failure evidence for the empty-success guard:
        # survives Cloud Tasks redelivery onto another instance. Best effort —
        # the failure recording itself must never depend on the marker.
        try:
            try_mark_once(job_id, empty_success_guard.PRIOR_PROVIDER_FAILURE_TAG)
        except Exception:
            logger.warning('event=sync_transcription_metric outcome=marker_failed kind=prior_provider_failure')
    if record_metric:
        _record_sync_segment_outcome(
            failure.outcome,
            provider=failure.provider,
            model=model,
            lane=lane,
            retryable=failure.retryable,
            job_id=job_id,
            segment_key=segment_key,
            phase=phase,
            exception=exception,
            attempt_ref=attempt_ref,
        )
    with lock:
        errors.append(failure.error_code)


def _record_empty_segment_as_silence(
    *,
    provider: str,
    model: str,
    lane: str,
    deferred_outcome: dict | None,
    job_id: str | None = None,
    segment_key: str | None = None,
    attempt_ref: str | None = None,
) -> None:
    """Record a speech-free segment as a valid empty result, not a failure.

    Records the outcome exactly as the success path does but appends nothing to
    the job's error list, so a job whose every segment is speech-free finalizes
    completed rather than failed and the client stops re-uploading it.
    """
    _set_deferred_segment_outcome(
        deferred_outcome,
        outcome=TranscriptionOutcome.EXPECTED_SILENCE,
        provider=provider,
        model=model,
        retryable=False,
    )
    if deferred_outcome is None:
        _record_sync_segment_outcome(
            TranscriptionOutcome.EXPECTED_SILENCE,
            provider=provider,
            model=model,
            lane=lane,
            retryable=False,
            job_id=job_id,
            segment_key=segment_key,
            attempt_ref=attempt_ref,
        )


def _set_deferred_segment_outcome(
    deferred_outcome: dict | None,
    *,
    outcome: TranscriptionOutcome,
    provider: str,
    model: str,
    retryable: bool,
    phase: str | None = None,
    exception_type: str | None = None,
    failure_subtype: str | None = None,
) -> None:
    """Keep v2 outcome data local until its durable checkpoint commits."""
    if deferred_outcome is not None:
        deferred_outcome.update(
            outcome=outcome,
            provider=provider,
            model=model,
            retryable=retryable,
        )
        if phase is not None:
            deferred_outcome['phase'] = phase
        if exception_type is not None:
            deferred_outcome['exception_type'] = exception_type
        if failure_subtype is not None:
            deferred_outcome['failure_subtype'] = bounded_sync_assignment_subtype(failure_subtype)


def _record_sync_job_outcome(
    outcome: TranscriptionOutcome,
    *,
    provider: str,
    model: str,
    lane: str,
    job_id: str | None = None,
    failure_reason: SyncFailureReason = SyncFailureReason.NONE,
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
            failure_reason=failure_reason,
        )
    except Exception:
        logger.warning('event=sync_transcription_metric outcome=emit_failed kind=job')


class SyncConversationPersistenceFenced(RuntimeError):
    """Conversation lifecycle rejected this worker's stale processing result."""


def _require_current_conversation_persistence(persisted: bool) -> None:
    """Turn a lifecycle fence into the worker's terminal supersession signal."""
    if not persisted:
        raise SyncConversationPersistenceFenced('sync conversation persistence fenced')


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
    attempt_ref: str | None = None,
    failure_phase: str | None = None,
    failure_class: str | None = None,
    failure_subtype: str | None = None,
    failure_key: str | None = None,
    failure_fingerprint: str | None = None,
    failure_reason: SyncFailureReason = SyncFailureReason.NONE,
) -> Optional[Dict]:
    """Publish one truthful failure and then make its retry claim available.

    This synchronous boundary is shared by async workers and the polling stale
    reaper. A run-token owner fences the Redis terminal transition first; only
    that winning owner may release the durable retry claim afterward.
    """
    if failure_reason is not SyncFailureReason.NONE and error_code in {'stt_upstream_error', 'stt_timeout'}:
        # A task-mode failure reaches here through sync_failure_from_exception; keep its
        # internal cause instead of publishing a vendor error code.
        error_code = sync_failure_error_code(failure_reason, failure_phase or 'finalize')
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
        failure_kwargs = {'failure_key': failure_key} if failure_key else {}
        if failure_fingerprint:
            failure_kwargs['failure_fingerprint'] = failure_fingerprint
        if run_lock_token is None:
            # The pre-cutover protocol has no epoch binding. Keep all ledger
            # operations tokenless while legacy revisions may still exist.
            release_sync_content_claim(uid, content_id, job_id, **failure_kwargs)
        else:
            # The fenced Redis terminal transition already succeeded. A lease
            # can expire between that CAS and Firestore release, so use the
            # deliberately retired-job transaction rather than treating this
            # as a live write.
            release_sync_content_claim_after_job_retired(uid, content_id, job_id, **failure_kwargs)
    if run_lock_token is not None:
        delete_sync_job_run_lock_epoch(job_id)
    logger.error(
        'event=sync_transcription_job outcome=%s status=failed provider=%s model=%s lane=%s reason_code=%s '
        'job_ref=%s attempt_ref=%s failure_phase=%s failure_class=%s failure_subtype=%s failure_reason=%s',
        outcome_label(outcome.value, failure_reason),
        bounded_provider(provider),
        _bounded_sync_model(model),
        _bounded_sync_lane(lane),
        _bounded_sync_failure_reason(reason_code or error_code),
        _bounded_correlation_ref(job_id),
        _bounded_correlation_ref(attempt_ref),
        _bounded_sync_phase(failure_phase),
        bounded_exception_class(failure_class),
        bounded_sync_assignment_subtype(failure_subtype),
        SyncFailureReason(failure_reason).value,
    )
    _record_sync_job_outcome(
        outcome, provider=provider, model=model, lane=lane, job_id=job_id, failure_reason=failure_reason
    )
    return finalized


def _merge_and_cap_vad_segments(voice_segments: list) -> list:
    from utils.sync.vad_segments import merge_and_cap_vad_segments

    return merge_and_cap_vad_segments(voice_segments, MAX_VAD_SEGMENT_SECONDS)


@sync_phase('decode_vad')
def retrieve_vad_segments(
    path: str,
    segmented_paths: set,
    errors: list = None,
    source_frame_map: dict | None = None,
    segment_source_maps: dict | None = None,
    segment_source_lock: threading.Lock | None = None,
    keep_short: bool = False,
):
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
    # An estimated-clock run follows the audio into every derived segment.
    clock_prefix = segment_name_prefix(path)

    try:
        for i, segment in enumerate(segments):
            if (
                segment['end'] - segment['start'] < 1
                and not keep_short
                and not (source_frame_map or {}).get('coverage_trimmed')
            ):
                continue
            segment_timestamp = start_timestamp + segment['start']
            # Two distinct source files can independently compute the same absolute
            # timestamp (capture_start + vad_offset). Reserve the path under the lock
            # before export so a concurrent worker never silently overwrites it.
            with segment_source_lock or contextlib.nullcontext():
                segment_path = f'{path_dir}/{clock_prefix}{segment_timestamp}.wav'
                dup = 0
                while segment_path in segmented_paths:
                    dup += 1
                    segment_path = f'{path_dir}/dup{dup}_{clock_prefix}{segment_timestamp}.wav'
                segmented_paths.add(segment_path)
            segment_aseg = aseg[segment['start'] * 1000 : segment['end'] * 1000]
            try:
                segment_aseg.export(segment_path, format='wav')
            except OSError as error:
                raise_sync_storage_pressure(error)
                raise
            if segment_source_maps is not None:
                # Pydub's millisecond slice starts at this original WAV sample.
                # The derivative STT clock resets to zero; retain its bridge.
                with segment_source_lock or contextlib.nullcontext():
                    if segment_path in segment_source_maps:
                        segment_source_maps[segment_path] = None
                    elif source_frame_map is not None:
                        first = (
                            int(aseg.frame_count(ms=segment['start'] * 1000))
                            if source_frame_map.get('live_source_slice')
                            else int(segment['start'] * aseg.frame_rate)
                        )
                        segment_source_maps[segment_path] = (source_frame_map, first)
                    else:
                        segment_source_maps[segment_path] = None
            # Explicitly delete segment to free memory immediately
            del segment_aseg
    finally:
        # Explicitly delete main audio to free memory
        del aseg


def _run_conversation_created_webhook(uid: str, conversation: Conversation) -> None:
    """Load the webhook surface only in the post-processing worker that uses it."""
    from utils.webhooks import conversation_created_webhook

    asyncio.run(conversation_created_webhook(uid, conversation))


def _reprocess_conversation_after_update(uid: str, conversation_id: str, language: str):
    """
    Reprocess a conversation after new segments have been added.
    This checks if the conversation should still be discarded and regenerates
    the summary/structured data if it now has sufficient content.
    """
    # Fetch the updated conversation with all segments
    conversation_data = conversations_db.get_conversation(uid, conversation_id)
    context = PROCESS_CONTEXT.get()
    if conversation_data and conversation_data.get('deleted') and conversation_data.get('sync_merged_into'):
        if context is not None:
            canonical = conversations_db.resolve_sync_conversation_redirect(uid, conversation_id)
            # The outbox transfers custody atomically before acknowledging this donor.
            context['redirect_to' if canonical else 'defer_reason'] = canonical or 'redirect_unresolved'
            return
        conversation_data = conversations_db.get_sync_redirected_conversation(uid, conversation_id)
        if conversation_data:
            conversation_id = conversation_data['id']
    if not conversation_data or conversation_data.get('deleted'):
        if context is not None:
            if conversation_data and conversation_data.get('deleted'):
                context['discarded'] = True  # A real deletion is terminal, never regenerated.
            else:
                context['defer_reason'] = 'conversation_missing'
        logger.info('event=sync_reprocess_callback outcome=unavailable')
        return

    if repair_fenced(conversation_data):
        raise SummaryRepairSuperseded(
            'summary repair ownership changed',
            retry_revision=(
                conversation_data.get('sync_content_revision')
                if summary_repair_refusal(conversation_data) is None
                else None
            ),
        )
    if conversation_data.get('sync_live_target') and conversation_data.get('status') == 'in_progress':
        # Live finalization owns the open row. SYNC_UPDATE would mark it
        # completed while the socket is still adding speech, after which the
        # finalizer skips processing that later content.
        if context is not None:
            context['defer_reason'] = 'open_live_target'
        return

    # Intake already discarded a rule-settled fragment; skip the processing
    # spend. Everything else goes through the relevance step (SYNC_UPDATE),
    # which reassesses the whole merged transcript, so later speech promotes it.
    segments = conversation_data.get('transcript_segments', [])
    status = getattr(conversation_data.get('status'), 'value', conversation_data.get('status'))
    if (
        status == 'completed'
        and conversation_data.get('sync_relevance') == 'review'
        and not is_user_curated(conversation_data)
    ):
        verdict, rule = fragment_rule(segments)
        if verdict == 'discard':
            outcome = lifecycle_service.rule_discard_outcome(
                uid,
                conversation_id,
                sync_intake_decision(rule),
                expected_sync_content_revision=conversation_data.get('sync_content_revision'),
            )
            if outcome == 'discarded':
                record_conversation_relevance(trigger='sync_intake', verdict='discard', decided_by='rule', reason=rule)
            if outcome in ('discarded', 'already_discarded'):
                # The read predicate derives `discarded` for review rows, so only
                # the write's outcome can tell a stored discard from a refused one.
                context = PROCESS_CONTEXT.get()
                if context is not None:
                    context['discarded'] = True
            return

    if PROCESS_CONTEXT.get() is not None and not claim_from_snapshot(
        get_firestore_client(), uid, conversation_id, conversation_data
    ):
        raise SyncConversationPersistenceFenced('summary processing snapshot changed')

    # Convert to Conversation object
    conversation = deserialize_conversation(conversation_data)
    if language == _LINEAGE_RETRY_LANGUAGE:
        language = conversation.language or 'en'

    silent_redrive = is_silent_redrive(conversation_data)
    was_discarded = conversation.discarded
    prior_decision = conversation_data.get('relevance_decision')
    # process_conversation persists relevance_decision.trigger == 'sync_update'.
    # Intake only writes 'sync_intake' (or nothing). A later WAL segment re-enters
    # this function; that stored trigger is the already-processed signal.
    already_sync_processed = (
        isinstance(prior_decision, dict) and prior_decision.get('trigger') == ProcessingTrigger.SYNC_UPDATE.value
    )
    # Visible rows must not accept again. A prior discard is not a visible
    # finalization, so discarded -> visible still accepts once.
    already_visible_finalized = already_sync_processed and not was_discarded
    started = time.monotonic()
    processed_conversation = process_conversation(
        uid=uid,
        language_code=language or 'en',
        conversation=conversation,
        trigger=ProcessingTrigger.SYNC_UPDATE,
        defer_derived_effects=silent_redrive,
        user_kept=is_user_curated(conversation_data) or REPAIR_CONTEXT.get() is not None,
        persistence_observer=_require_current_conversation_persistence,
        # Deserialize drops relevance_decision. The raw row still has it:
        # sync_update means a previous enrichment, sync_intake or absence does not.
        prior_relevance_decision=prior_decision if isinstance(prior_decision, dict) else None,
    )
    elapsed = time.monotonic() - started
    # Persistence is guaranteed here: a fenced write raises before return.
    # client_platform is the Conversation field set at sync intake; None -> unknown.
    client_kind = resolve_client_kind(x_app_platform=getattr(conversation, 'client_platform', None), user_agent=None)
    if processed_conversation.discarded:
        if not already_sync_processed:
            record_client_journey_terminal('conversation_finalization', client_kind, 'cancelled', elapsed)
    elif not already_visible_finalized:
        record_client_journey_accepted('conversation_finalization', client_kind)
        record_client_journey_terminal('conversation_finalization', client_kind, 'success', elapsed)

    # Limitless uploads commonly begin as a short discarded fragment and only
    # become a real conversation after later WAL segments are merged. The
    # initial discarded pass is not a useful creation event, while the generic
    # reprocess path deliberately suppresses webhooks. Emit exactly at the
    # discarded -> visible transition so pendant conversations reach developer
    # integrations without duplicating events on ordinary later reprocessing.
    if (
        not silent_redrive
        and conversation.source == ConversationSource.limitless
        and was_discarded
        and not processed_conversation.discarded
    ):
        submit_with_context(postprocess_executor, _run_conversation_created_webhook, uid, processed_conversation)

    logger.info(f'Successfully reprocessed conversation {conversation_id}')
    return processed_conversation


def _speaker_identity_dependencies() -> SpeakerIdentityDependencies:
    return SpeakerIdentityDependencies(
        users_db=users_db,
        get_user_name=get_user_name,
        usable_person_voiceprint=usable_person_voiceprint,
        speaker_embedding_configured=speaker_embedding_configured,
        collect_speaker_audio=collect_speaker_audio,
        extract_embedding_from_bytes=extract_embedding_from_bytes,
        mean_embedding=mean_embedding,
        compare_embeddings=compare_embeddings,
        select_speaker_match=select_speaker_match,
        detect_speaker_from_text=detect_speaker_from_text,
        process_speaker_assigned_segments=process_speaker_assigned_segments,
        speaker_decisions=SYNC_SPEAKER_DECISIONS,
        logger=logger,
    )


def build_person_embeddings_cache(uid: str) -> Dict[str, dict]:
    return _build_person_embeddings_cache(uid, dependencies=_speaker_identity_dependencies())


@sync_phase('gcs')
def _download_audio_bytes(url: str) -> Optional[bytes]:
    """Download audio from a signed URL. Returns WAV bytes or None on failure."""
    try:
        resp = httpx.get(url, timeout=60.0)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        logger.warning(f'Speaker ID: failed to download audio: {e}')
        return None


@sync_phase('speaker_id')
def identify_speakers_for_segments(
    transcript_segments: List['TranscriptSegment'],
    audio_bytes: Optional[bytes],
    person_embeddings_cache: Dict[str, dict],
    uid: str,
    language: Optional[str] = None,
    *,
    owner_reserved: bool = False,
) -> None:
    _identify_speakers_for_segments(
        transcript_segments,
        audio_bytes,
        person_embeddings_cache,
        uid,
        language,
        owner_reserved=owner_reserved,
        dependencies=_speaker_identity_dependencies(),
    )


ORDERED_ASSIGNMENT_WAIT_SECONDS = 600


class _OrderedTurnstile:
    """Serializes conversation assignment across parallel segment threads in timestamp order.

    Segments are transcribed concurrently, but each must wait its (chronological) turn
    before looking up / creating a conversation. Without this, timestamp-adjacent chunks
    race get_closest_conversation_to_timestamps() before any of them has persisted a
    conversation, so every chunk becomes its own conversation (#6551, #5747).
    """

    # Cross-job correctness lives in assign_sync_conversation; this turnstile
    # is only an in-job ordering optimization, never a persistence lock.

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


def _recover_empty_segment(
    path: str,
    uid: str,
    provider: str,
    lane: str,
    job_id: str | None,
    attempt_ref: str | None,
    cap_dispatch_lane: str = 'sync',
) -> tuple[list[TranscriptSegment], str, float] | None:
    def observe_inspection(duration: float | None, spans: list[dict] | None):
        logger.info(
            'event=sync_empty_strict_vad outcome=%s lane=%s provider=%s segment_ref=%s '
            'duration_seconds=%.3f vad_spans=%d speech_seconds=%.3f',
            'inspection_error' if spans is None else ('speech' if spans else 'silence'),
            _bounded_sync_lane(lane),
            bounded_provider(provider),
            compute_sync_segment_id(uid, path),
            duration or 0,
            len(spans or []),
            sum(span['end'] - span['start'] for span in spans or []),
        )

    def authorize_recovery():
        if provider != 'parakeet':
            # Positive VAD after multilingual double-empty is unresolved;
            # buying the same call again is not independent recovery.
            raise TranscriptionFailure(TranscriptionOutcome.EMPTY_UNEXPECTED, provider=provider)
        if cap_enabled(uid, cap_dispatch_lane) and not sync_allowed(uid, lane=cap_dispatch_lane):
            raise TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider='modulate')

    def multilingual_once(audio: bytes, **kwargs: Any):
        def dispatch():
            response = modulate_prerecorded_from_bytes(audio, **kwargs)
            if cap_enabled(uid, cap_dispatch_lane):
                allowance = funded_allowance(uid, lane=cap_dispatch_lane)
                record_cap_audio(
                    'sync',
                    'accepted',
                    'modulate',
                    (len(audio) - 44) / 32000,
                    allowance.reason == 'plan_allowance_exhausted',
                )
            return response

        try:
            return dispatch_empty_recovery_once(uid, compute_sync_segment_id(uid, path), dispatch)
        except (ValueError, TypeError):
            raise TranscriptionFailure(TranscriptionOutcome.UPSTREAM_ERROR, provider='modulate') from None
        except Exception as error:
            raise failure_from_exception(error, provider='modulate') from None

    words, recovered_language, duration, spans = empty_recovery.recover(
        path, transcribe=multilingual_once, authorize=authorize_recovery, observe=observe_inspection
    )
    logger.info(
        'event=sync_empty_recovery outcome=%s lane=%s duration_seconds=%.3f '
        'vad_spans=%d speech_seconds=%.3f job_ref=%s attempt_ref=%s',
        'speech' if spans else 'silence',
        _bounded_sync_lane(lane),
        duration,
        len(spans),
        sum(span['end'] - span['start'] for span in spans),
        _bounded_correlation_ref(job_id),
        _bounded_correlation_ref(attempt_ref),
    )
    if not spans:
        return None
    transcript_segments = postprocess_words(words, 0)
    if not transcript_segments:
        raise TranscriptionFailure(TranscriptionOutcome.EMPTY_UNEXPECTED, provider='modulate')
    if sync_safety_wal_enabled():
        for segment in transcript_segments:
            segment.stt_provider = 'velma-2'
    record_fallback(
        component='sync_dispatch',
        from_mode=provider,
        to_mode='modulate',
        reason='empty_streak',
        outcome='recovered',
        log=logger,
    )
    return transcript_segments, recovered_language, first_word_offset(words)


def _assign_segment_speakers(
    uid: str,
    audio_bytes: bytes | None,
    words: Any,
    transcript_segments: list[TranscriptSegment],
    person_embeddings_cache: dict | None,
    *,
    timestamp: float,
    speech_offset: float,
    segment_end_timestamp: float,
    speaker_scope: Optional[str],
    owner_reserved: bool,
    model: str,
    language: Any,
    sync_lane: str,
) -> tuple[list[TranscriptSegment], float]:
    """Run the sync final pass or speaker identification; failures keep the input segments."""
    try:
        final_segments = None
        if sync_enabled_for(uid) and audio_bytes is not None:
            from utils.conversations.final_pass_sync import run_sync_final_pass

            final_pass_started = time.monotonic()
            final_segments, final_outcome = run_sync_final_pass(
                uid,
                audio_bytes,
                words,
                transcript_segments,
                person_embeddings_cache or {},
                scope=speaker_scope or f'sync:{timestamp}',
                owner_reserved=owner_reserved,
            )
            logger.info(
                'event=sync_final_pass outcome=%s uid_hash=%s lane=%s duration_seconds=%.3f',
                final_outcome['outcome'],
                hashlib.sha256(('sync-final-pass:' + uid).encode()).hexdigest(),
                _bounded_sync_lane(sync_lane),
                time.monotonic() - final_pass_started,
            )
        if final_segments and sync_enabled_for(uid):
            transcript_segments = final_segments
            for segment in transcript_segments:
                segment.speaker_id_scope = speaker_scope or f'sync:{timestamp}'
                segment.stt_provider = model
            segment_end_timestamp = timestamp + speech_offset + max(segment.end for segment in transcript_segments)
        else:
            identify_speakers_for_segments(
                transcript_segments,
                audio_bytes if person_embeddings_cache else None,
                person_embeddings_cache if person_embeddings_cache is not None else PersonEmbeddingsCache(False),
                uid,
                language=language,
                owner_reserved=owner_reserved,
            )
    except Exception as e:
        logger.warning(
            'event=sync_speaker_id outcome=failed exception_type=%s uid_hash=%s',
            _bounded_exception_type(e),
            hashlib.sha256(('sync-final-pass:' + uid).encode()).hexdigest(),
        )
    return transcript_segments, segment_end_timestamp


def process_segment(  # pyright: ignore[reportGeneralTypeIssues] — segment pipeline sits at Pyright's analyzer complexity ceiling
    path: str,
    uid: str,
    response: dict,
    lock: threading.Lock,
    errors: list,
    source: ConversationSource = ConversationSource.omi,
    is_locked: bool = False,
    transcription_prefs: dict = None,
    person_embeddings_cache: dict = None,
    target_conversation_id: Optional[str] = None,
    turnstile: Optional[_OrderedTurnstile] = None,
    private_cloud_sync_enabled: bool = False,
    data_protection_level: Optional[str] = None,
    client_device_id: Optional[str] = None,
    client_platform: Optional[str] = None,
    sync_lane: str = SyncLane.FRESH.value,
    deferred_outcome: dict | None = None,
    geolocation: Optional[Geolocation] = None,
    speaker_scope: Optional[str] = None,
    job_id: str | None = None,
    segment_key: str | None = None,
    attempt_ref: str | None = None,
    source_position_map: tuple[dict, int] | None = None,
    lineage_binding: Optional[str] = None,
    cap_recovery: bool = False,
    cap_content_id: str | None = None,
    cap_recovery_service: tuple[str, str | None, str] | None = None,
    cap_recovery_checkpoint: dict | None = None,
    cap_dispatch_lane: str = 'sync',
    recording_session_id: str | None = None,
):
    if cap_dispatch_lane not in LANES:
        raise ValueError('unknown cap dispatch lane')

    def cap_enforced() -> bool:
        return (recovery_admission_enabled if cap_recovery else cap_enabled)(uid, cap_dispatch_lane)

    if cap_recovery and not cap_enforced():
        return False
    cap_context = {
        'source': getattr(source, 'value', source),
        'target_conversation_id': target_conversation_id,
        'private_cloud_sync_enabled': private_cloud_sync_enabled,
        'data_protection_level': data_protection_level,
        'client_device_id': client_device_id,
        'client_platform': client_platform,
        'geolocation': geolocation,
        'source_position_map': source_position_map,
        'recording_session_id': recording_session_id,
        'lineage_binding': lineage_binding,
        'sync_lane': sync_lane,
        'origin': cap_dispatch_lane,
        'content_id': cap_content_id,
        'job_id': job_id,
    }
    conversation_id = None
    conversation_turns: list[conversation_turn_lease.ConversationTurn | None] = []
    provider = 'unknown'
    model = 'unknown'
    phase = 'provider_select'
    if cap_enforced() and cap_recovery and deferred_outcome is not None:
        deferred_outcome['provider_called'] = False

    def hold_for_cap() -> bool:
        if not cap_recovery:
            from utils.sync.cap_hold import defer_segment

            defer_segment(uid, path, cap_context, response, lock)
        if deferred_outcome is not None:
            deferred_outcome['cap_held'] = True
        return False

    try:
        if ambiguous_binding_pending(uid, lineage_binding):
            phase = 'persistence'
            raise SyncAssignmentConflict('sync lineage ambiguous', subtype=Conflict.LINEAGE_OWNERSHIP_AMBIGUOUS)
        if cap_enforced():
            if not sync_allowed(uid, lane=cap_dispatch_lane):
                return hold_for_cap()
            # Queue-time locks do not survive execution-time authorization.
            is_locked = False
        url = get_syncing_file_temporal_signed_url(path)
        schedule_syncing_temporal_file_deletion(path)

        # Apply user transcription preferences (vocabulary, language, model)
        prefs = transcription_prefs or {}
        user_vocab = [w for w in dict.fromkeys(prefs.get('vocabulary', [])) if w != "Omi"]
        vocabulary = asyncio.run(keyterms(uid, ["Omi"] + user_vocab[:99]))
        user_language = prefs.get('language', '') or ''
        single_language_mode = prefs.get('single_language_mode', False)

        req_language = user_language if (single_language_mode and user_language) else 'multi'
        recovery_dispatch = {}
        if cap_enforced() and cap_recovery and cap_recovery_service is not None:
            # The durable pre-dispatch intent owns this provider/model. Pin
            # actual serving too, rather than reselecting after the checkpoint.
            provider, _, model = cap_recovery_service
            recovery_dispatch['selected_service'] = cap_recovery_service
        else:
            from utils.stt.batch_language import resolve_file
            from config.prerecorded_language import language_class, language_guard_enabled

            provider, _, model = resolve_file(
                req_language,
                path,
                selector=get_prerecorded_service,
                before_probe=lambda: not cap_enforced() or sync_allowed(uid, lane=cap_dispatch_lane),
                cohort_key=uid,
            )
            if language_guard_enabled() and language_class(req_language) == 'unknown':
                # Pin this segment's detected selection into the call as well as
                # its spend/outcome accounting; the URL client must not probe twice.
                recovery_dispatch['selected_service'] = (provider, req_language, model)

        # When single-language mode is active, trust the user's language choice
        # rather than Deepgram's detection (avoids overriding explicit selection).
        use_return_language = not (single_language_mode and user_language)

        # Retain the bounded confirmation retry. With strict recovery enabled,
        # recognizer emptiness cannot by itself authorize silence.
        def _log_empty_retry(outcome: str, words: int = 0, raw_empty: bool = False) -> None:
            logger.info(
                'event=sync_transcription_empty_retry outcome=%s provider=%s model=%s lane=%s '
                'raw_empty=%s words=%s detected_language=%s job_ref=%s attempt_ref=%s',
                outcome,
                bounded_provider(provider),
                _bounded_sync_model(model),
                _bounded_sync_lane(sync_lane),
                str(bool(raw_empty)).lower(),
                min(int(words), 100000),
                (
                    _bounded_retry_language(detected_language)
                    if outcome != 'started'
                    else _bounded_retry_language(req_language)
                ),
                _bounded_correlation_ref(job_id),
                _bounded_correlation_ref(attempt_ref),
            )

        empty_retried = False
        recovered_via_retry = False
        transcript_segments: List[TranscriptSegment] = []
        speech_offset = 0.0
        while True:
            phase = 'provider_call'
            if cap_recovery and not cap_enforced() or cap_enforced() and not sync_allowed(uid, lane=cap_dispatch_lane):
                return hold_for_cap()
            if cap_enforced() and cap_recovery and deferred_outcome is not None:
                # Explicit request-boundary signal survives later cap denial,
                # parse/ingest errors, and the bounded empty-result retry.
                deferred_outcome['provider_called'] = True
            words, detected_language = cap_recovery_provider.transcribe(
                uid,
                cap_recovery_checkpoint if cap_enforced() and cap_recovery else None,
                prerecorded,
                url,
                speakers_count=3,
                attempts=0,
                return_language=True,
                language=req_language,
                keywords=vocabulary if vocabulary else None,
                **recovery_dispatch,
            )
            if cap_enforced():
                allowance = funded_allowance(uid, lane=cap_dispatch_lane)
                record_cap_audio(
                    'sync', 'accepted', provider, get_wav_duration(path), allowance.reason == 'plan_allowance_exhausted'
                )
            language = user_language if (single_language_mode and user_language) else detected_language
            phase = 'parse'
            transcript_segments = postprocess_words(words, 0) if words else []
            speech_offset = first_word_offset(words)
            if sync_safety_wal_enabled():
                for segment in transcript_segments:
                    segment.stt_provider = model
            if transcript_segments:
                if empty_retried:
                    _log_empty_retry('recovered', words=len(words or []), raw_empty=not words)
                    recovered_via_retry = True
                break
            if cap_enforced() and cap_recovery and cap_recovery_checkpoint is not None:
                # A held piece gets at most two persisted application dispatch
                # attempts. Reconciliation owns the second, not this local retry.
                if deferred_outcome is not None:
                    deferred_outcome['recovery_ambiguous'] = True
                return False
            if empty_retried:
                _log_empty_retry('still_empty', words=len(words or []), raw_empty=not words)
                if empty_recovery.enabled():
                    phase = 'provider_call'
                    recovered = _recover_empty_segment(
                        path, uid, provider, sync_lane, job_id, attempt_ref, cap_dispatch_lane
                    )
                    if recovered is not None:
                        transcript_segments, recovered_language, speech_offset = recovered
                        provider, model = 'modulate', 'velma-2'
                        language = user_language if (single_language_mode and user_language) else recovered_language
                        recovered_via_retry = True
                        break
                held, _guard_reason = empty_success_guard.settle(path, provider=provider, job_id=job_id)
                if held:
                    # Speech-positive audio that a degraded provider chain returned
                    # empty stays retryable; completing it as silence is the
                    # provider-failure-ends-as-success class (2026-10-23 soak).
                    raise TranscriptionFailure(TranscriptionOutcome.EMPTY_UNEXPECTED, provider=provider)
                _record_empty_segment_as_silence(
                    provider=provider,
                    model=model,
                    lane=sync_lane,
                    deferred_outcome=deferred_outcome,
                    job_id=job_id,
                    segment_key=segment_key,
                    attempt_ref=attempt_ref,
                )
                return False
            empty_retried = True
            _log_empty_retry('started', words=len(words or []), raw_empty=not words)

        # refactor: superseded by utils.stt.transcript_admission when MEDIA_NOISE_MODE=serve
        transcript_segments = admit_segments(uid, transcript_segments, origin='sync')
        if not transcript_segments:
            held_after_admission, _guard_reason = empty_success_guard.settle(path, provider=provider, job_id=job_id)
            if held_after_admission:
                # Admission discarded every word on speech-positive audio after a
                # degraded chain; completing as silence hides the same loss.
                raise TranscriptionFailure(TranscriptionOutcome.EMPTY_UNEXPECTED, provider=provider)
            _record_empty_segment_as_silence(
                provider=provider,
                model=model,
                lane=sync_lane,
                deferred_outcome=deferred_outcome,
                job_id=job_id,
                segment_key=segment_key,
                attempt_ref=attempt_ref,
            )
            return False
        phase = 'assignment'
        if turnstile and not turnstile.wait_turn(path):
            logger.warning(f'sync: ordered assignment wait timed out for {path}, proceeding out of order')

        timestamp = get_timestamp_from_path(path)
        clock_run = clock_run_from_path(path)
        # Legacy callers retain a capture-time scope, never one shared by all WALs.
        for segment in transcript_segments:
            segment.speaker_id_scope = speaker_scope or f'sync:{timestamp}'
        # Lines are timed from the first word, speech_offset seconds into this file.
        segment_end_timestamp = timestamp + speech_offset + max(segment.end for segment in transcript_segments)
        target_conversation_id = target_conversation_id or covering_target(
            uid, source_position_map, path, device_id=client_device_id, recording_session_id=recording_session_id
        )
        closest_memory = (
            None
            if target_conversation_id
            else get_closest_conversation_to_timestamps(uid, timestamp, segment_end_timestamp)
        )
        candidate_id = target_conversation_id or (closest_memory['id'] if closest_memory else None)
        owner_reserved = False
        if candidate_id:
            try:
                owner_reserved = manual_owner_reserved(conversations_db.get_manual_speaker_receipt(uid, candidate_id))
            except Exception as error:
                # A receipt read failure cannot authorize an automatic owner.
                owner_reserved = True
                logger.warning('event=sync_speaker_receipt outcome=failed exception_type=%s', type(error).__name__)

        # Download once for matching and optional private-cloud chunk storage.
        phase = 'download'
        audio_bytes = (
            _download_audio_bytes(url)
            if (person_embeddings_cache or private_cloud_sync_enabled or sync_enabled_for(uid))
            else None
        )
        try:
            transcript_segments, segment_end_timestamp = _assign_segment_speakers(
                uid,
                audio_bytes,
                words,
                transcript_segments,
                person_embeddings_cache,
                timestamp=timestamp,
                speech_offset=speech_offset,
                segment_end_timestamp=segment_end_timestamp,
                speaker_scope=speaker_scope,
                owner_reserved=owner_reserved,
                model=model,
                language=language,
                sync_lane=sync_lane,
            )
        finally:
            if audio_bytes is not None and not private_cloud_sync_enabled:
                audio_bytes = None
        shift_to_vad_file_clock(transcript_segments, speech_offset)
        started_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        create_memory = CreateConversation(
            started_at=started_at,
            finished_at=datetime.fromtimestamp(segment_end_timestamp, tz=timezone.utc),
            transcript_segments=transcript_segments,
            source=source,
            language=language,
            is_locked=is_locked,
            private_cloud_sync_enabled=private_cloud_sync_enabled,
            client_device_id=client_device_id,
            client_platform=client_platform,
            geolocation=geolocation,
        )
        incoming = Conversation(
            id=chunk_identity(
                uid,
                source,
                client_device_id,
                is_locked,
                timestamp,
                **(
                    {'capture_partition': cap_recovery_checkpoint['capture_partition']}
                    if cap_recovery_checkpoint and cap_recovery_checkpoint.get('capture_partition')
                    else {}
                ),
                **({'clock_run': clock_run} if clock_run else {}),
            ),
            created_at=started_at,
            structured=build_deterministic_minimum_structured(create_memory, uid=uid),
            **create_memory.model_dump(),
        ).model_dump()
        incoming['data_protection_level'] = data_protection_level
        if clock_run:
            incoming[SYNC_CLOCK_RUN_FIELD] = clock_run
        apply_capture_evidence_dark_write(incoming, source_position_map, transcript_segments)
        annotate_identity(incoming, client_device_id, recording_session_id)
        if lineage_binding is not None and target_conversation_id:
            incoming['_sync_lineage_binding'] = lineage_binding
        phase = 'persistence'
        conversation_turns.append(conversation_turn_lease.acquire(uid, candidate_id, sync_lane))
        from utils.conversations.lifecycle import ingest_sync_conversation

        assigned, created, survivors = ingest_sync_conversation(
            uid,
            incoming,
            candidate_id=closest_memory['id'] if closest_memory else None,
            target_id=target_conversation_id,
            **(
                {'recovery_checkpoint': cap_recovery_checkpoint}
                if cap_enforced() and cap_recovery and cap_recovery_checkpoint is not None
                else {}
            ),
        )
        if assigned['id'] != candidate_id:
            # Assignment redirected; hold the conversation the bridge will finalize into too.
            conversation_turns.append(conversation_turn_lease.acquire(uid, assigned['id'], sync_lane))
        if sync_safety_wal_enabled() and assigned.get('sync_live_target'):
            removed = len(transcript_segments) - len(survivors)
            SEGMENTS_DEDUPED.labels(reason='live_overlap').inc(removed)
            if removed and audio_bytes and private_cloud_sync_enabled:
                AUDIO_BYTES_NOT_STORED.labels(reason='transcript_overlap').inc(
                    suppressed_pcm_bytes(audio_bytes, survivors)
                )
        if recovered_via_retry:
            # The 'recovered' event fires at the provider boundary; this one
            # confirms the recovered segment actually persisted. Measured
            # durable recovery is the input a gate/kill decision needs — do
            # not price the retry from 'recovered' alone.
            logger.info(
                'event=sync_transcription_empty_retry outcome=durable_recovered provider=%s model=%s lane=%s '
                'segments=%s job_ref=%s attempt_ref=%s',
                bounded_provider(provider),
                _bounded_sync_model(model),
                _bounded_sync_lane(sync_lane),
                len(transcript_segments),
                _bounded_correlation_ref(job_id),
                _bounded_correlation_ref(attempt_ref),
            )
        record_capture_evidence_metric(incoming)
        record_sync(
            uid,
            incoming,
            assigned,
            source_position_map,
            path,
            device_id=client_device_id,
            recording_session_id=recording_session_id,
            survivors=survivors,
        )

        def mark_finalize():
            nonlocal phase
            phase = 'finalize'

        conversation_id = assigned['id']
        complete_sync_intake(
            uid=uid,
            assigned=assigned,
            created=created,
            survivors=survivors,
            response=response,
            lock=lock,
            language=language,
            audio_enabled=bool(private_cloud_sync_enabled and survivors),
            store_audio=partial(
                _store_intake_audio,
                uid,
                timestamp,
                audio_bytes,
                data_protection_level,
                survivors,
                len(transcript_segments),
                private_cloud_sync_enabled,
            ),
            finish=finish_sync_segment,
            mark_finalize=mark_finalize,
            acknowledge=partial(
                acknowledge_processed_segment,
                deferred_outcome,
                provider=provider,
                model=model,
                lane=sync_lane,
                job_id=job_id,
                segment_key=segment_key,
                attempt_ref=attempt_ref,
                set_outcome=_set_deferred_segment_outcome,
                record_outcome=_record_sync_segment_outcome,
            ),
        )
        return True
    except SyncAssignmentSuperseded:
        # Acknowledge user authority without failing the WAL or dropping siblings.
        # False excludes this segment from content usage; the zero-error job still
        # commits its durable completion ledger before the client sees completed.
        if conversation_id:
            with lock:
                response['new_memories'].discard(conversation_id)
                response['updated_memories'].discard(conversation_id)
                response.get('_merged', {}).pop(conversation_id, None)
        logger.info('event=sync_assignment outcome=superseded')
        _set_deferred_segment_outcome(
            deferred_outcome, outcome=TranscriptionOutcome.SUCCESS, provider=provider, model=model, retryable=False
        )
        return False
    except SyncConversationPersistenceFenced:
        raise
    except Exception as e:
        if is_destructive_operation_in_progress(e):
            raise
        if phase == 'persistence':
            # Preserve a bounded code-defined subtype for incident diagnosis;
            # never log exception text, document IDs, paths, or transcript.
            logger.error(
                'event=sync_persistence_exception exception_type=%s firestore_error=%s firestore_doc_kind=%s '
                'job_ref=%s attempt_ref=%s',
                _bounded_exception_type(e),
                _firestore_error_class(e),
                _firestore_doc_kind(e),
                _bounded_correlation_ref(job_id),
                _bounded_correlation_ref(attempt_ref),
            )
        if phase == 'finalize':
            logger.error(
                'event=sync_finalize_exception exception_type=%s site=%s firestore_error=%s',
                _bounded_exception_type(e),
                finalize_exception_site(e),
                _firestore_error_class(e),
            )
        fingerprint = _persistence_failure_fingerprint(e, phase, sync_lane)
        if phase in ('persistence', 'finalize'):
            failure = TranscriptionFailure(
                TranscriptionOutcome.UPSTREAM_ERROR,
                provider=None,
                retryable=fingerprint is None,
            )
            failure.error_code = sync_failure_error_code(_sync_failure_reason(phase, e), phase)
            model = 'unknown'
        else:
            failure = failure_from_exception(e, provider=provider)
        _set_deferred_segment_outcome(
            deferred_outcome,
            outcome=failure.outcome,
            provider=failure.provider,
            model=model,
            retryable=failure.retryable,
            phase=phase,
            exception_type=bounded_exception_class(e),
            failure_subtype=_sync_assignment_failure_subtype(e),
        )
        if deferred_outcome is not None and fingerprint:
            deferred_outcome['repeat_failure_key'] = 'persistent_persistence'
            deferred_outcome['repeat_failure_fingerprint'] = fingerprint
        elif (
            deferred_outcome is not None
            and phase in ('provider_call', 'parse')
            and failure.outcome == TranscriptionOutcome.INVALID_INPUT
        ):
            deferred_outcome['provider_invalid_input'] = True
        _record_sync_segment_failure(
            failure,
            model=model,
            lane=sync_lane,
            lock=lock,
            errors=errors,
            record_metric=deferred_outcome is None,
            job_id=job_id,
            segment_key=segment_key,
            phase=phase,
            exception=e,
            attempt_ref=attempt_ref,
        )
        return False
    finally:
        for turn in conversation_turns:
            conversation_turn_lease.release(turn)
        if turnstile:
            turnstile.complete(path)


def _reprocess_merged_conversations(
    uid: str,
    response: dict,
    on_fenced: Optional[Callable[[], None]] = None,
    *,
    user_selected: bool = False,
):
    """Regenerate summary/structured data for conversations that gained segments this batch.

    The merge path in process_segment only appends transcript segments; without this the
    enriched fields (summary, structured, speakers) remain stale.  Fences are isolated
    per conversation: a replaced/reopened conversation must not block siblings in the
    same batch.
    """
    from config.sync_reprocess import coalesce_enabled

    from config.demand_processing import enabled as demand_enabled

    coalescing = (coalesce_enabled() or demand_enabled(uid)) and not user_selected
    merged = response.pop('_merged', {})
    if coalescing:
        # Partial-result IDs survive a crash after append/checkpoint but before
        # this outbox mark, even when lineage enrichment recovery is disabled.
        # Re-enroll that durable debt; exact-input dedupe handles completed
        # replays without depending on a transient per-attempt _merged map.
        recovered = set(response.get('new_memories') or []) | set(response.get('updated_memories') or [])
        recovered -= set(response.get(_RESPONSE_FENCED_CONVERSATION_IDS) or [])
        for conversation_id in recovered:
            merged.setdefault(conversation_id, _LINEAGE_RETRY_LANGUAGE)
    if user_selected:
        # Rule-discard intake does not enroll enrichment. Process Now is an
        # explicit keep choice, so include those retained rows too. Apply it
        # only after all chunks have joined: curating each chunk during intake
        # would prevent later chunks from merging into the same recording.
        for conversation_id in response.get('new_memories', set()) | response.get('updated_memories', set()):
            merged.setdefault(conversation_id, _LINEAGE_RETRY_LANGUAGE)
    fenced_ids = set()
    for conversation_id, language in merged.items():
        try:
            if user_selected and not lifecycle_service.restore_discarded(uid, conversation_id):
                raise SyncConversationPersistenceFenced('selected recording no longer exists')
            if coalescing:
                from utils.sync.reprocess import mark

                mark(uid, conversation_id, language)
            else:
                _reprocess_conversation_after_update(uid, conversation_id, language)
                if user_selected:
                    from utils.conversations.demand_processing import promote_conversation_effects

                    promote_conversation_effects(uid, conversation_id)
        except SyncConversationPersistenceFenced:
            fenced_ids.add(conversation_id)
            response.setdefault(_RESPONSE_FENCED_CONVERSATION_IDS, set()).add(conversation_id)
            response.get('updated_memories', set()).discard(conversation_id)
            response.get('new_memories', set()).discard(conversation_id)
            if on_fenced:
                on_fenced()
            logger.info('event=sync_conversation_reprocess outcome=fenced conversation_id=%s', conversation_id)
        except Exception as e:
            if coalescing or user_selected or is_destructive_operation_in_progress(e):
                raise
            logger.error(f'sync: failed to reprocess merged conversation {conversation_id}: {e}')
    # A task-mode worker whose every conversation was superseded by a newer
    # ingest must not publish an empty success: re-raise so the Cloud Tasks
    # lane terminally ACKs the delivery as superseded (never retried). The
    # v1 inline lane keeps the absorb behavior (no on_fenced checkpoint there).
    if (
        fenced_ids
        and on_fenced is not None
        and not response.get('new_memories')
        and not response.get('updated_memories')
    ):
        raise SyncConversationPersistenceFenced('all merged conversations fenced')


def _wav_bytes_to_pcm16_16k(audio_bytes: Optional[bytes]) -> Optional[bytes]:
    """Decode WAV bytes to raw PCM16, 16 kHz mono — the format upload_audio_chunk
    expects (it opus-encodes internally) and the audio merge is hardcoded to."""
    if not audio_bytes:
        return None
    seg = AudioSegment.from_wav(io.BytesIO(audio_bytes))
    seg = seg.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    return seg.raw_data


def _store_intake_audio(
    uid: str,
    timestamp: float,
    audio_bytes: Optional[bytes],
    data_protection_level: str,
    survivors: list,
    transcript_segment_count: int,
    private_cloud_sync_enabled: bool,
    conversation_id: str,
) -> None:
    store_intake_audio(
        uid,
        timestamp,
        audio_bytes,
        data_protection_level,
        survivors,
        transcript_segment_count,
        private_cloud_sync_enabled,
        conversation_id,
        store_full=_store_sync_audio_chunk,
        store_partial=store_partial_merge_survivor_audio,
    )


def _store_sync_audio_chunk(
    uid: str,
    conversation_id: str,
    timestamp: float,
    audio_bytes: Optional[bytes],
    data_protection_level: Optional[str],
):
    """Reuse stable private-cloud chunk naming; audio storage remains best-effort."""
    store_sync_audio_chunk(
        uid,
        conversation_id,
        timestamp,
        audio_bytes,
        data_protection_level,
        decode_audio=_wav_bytes_to_pcm16_16k,
        upload_audio=upload_audio_chunk,
    )


@sync_phase('firestore')
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


def _cleanup_files(file_paths: Iterable[str]):
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


def finalize_recovered_sync_segment(uid: str, response: dict, private: bool) -> None:
    """Use the same enrichment/audio finalization as ordinary sync intake."""
    _reprocess_merged_conversations(uid, response)
    if private:
        _finalize_sync_audio_files(uid, response)


def cleanup_recovered_sync_files(paths: list[str]) -> None:
    """Coverage replay borrows the ordinary sync cleanup boundary."""
    _cleanup_files(paths)
