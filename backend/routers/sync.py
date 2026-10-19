from database import sync_redrive
from utils.sync import redrive_policy
from utils.observability.sync_phases import sync_attempt, set_sync_metrics_lane
import asyncio
import json
import logging
import os
import shutil
import threading
import time
import uuid as _uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, Request, Response, Header
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from config.summary_guarantee import repair_enabled as summary_repair_enabled
from services import summary_debt_repair
from config.batch_pipeline import enabled_for as batch_enabled_for
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.batch_pipeline.intake import (
    accept_upload as accept_batch_upload,
    get_durable_job_status,
    privacy_blocked_response,
)
from models.sync_job_status import (
    SyncJobStartResponse,
    SyncJobStatusResponse,
    SyncCaptureManifestRequest,
    SyncCaptureManifestResponse,
)
from routers.batch_pipeline import enrichment_response
from database import conversations as conversations_db
from database import fair_use as fair_use_db
from database import sync_dead_letters
from database import sync_backfill_sequencer
from database import users as users_db
from database.memories import historical_scan_memo_scope
from database.firestore_read_metrics import FirestoreReadSite
from database.firestore_read_origin import read_origin
from database.sync_jobs import (
    SyncLedgerFenceMode,
    TERMINAL_STATUSES,
    create_sync_job,
    delete_sync_job,
    delete_sync_job_run_lock_epoch,
    fenced_mark_job_queued_for_retry,
    get_sync_ledger_fence_mode,
    get_sync_job,
    is_sync_job_stale,
    mark_job_completed,
    mark_job_failed,
    mark_job_queued_for_retry,
    sync_job_uses_ledger_fence,
    try_acquire_sync_job_run_lock,
    try_acquire_job_run_lock,
    release_job_run_lock,
    update_sync_job,
)
from database.sync_ledger import (
    claim_sync_content,
    release_sync_content_claim,
    release_sync_content_claim_after_job_retired,
)
from models.conversation_enums import ConversationSource
from models.sync_contract import SYNC_LOCAL_FILES_V2_RESPONSES
from models.geolocation import geolocation_from_private_header
from models.sync_audio import AudioPrecacheResponse, AudioUrlsResponse
from routers.listen.contracts import persisted_started_seconds
from config.stt_cap_dispatch import execution_admission_enabled as cap_dispatch_enabled
from utils.sync.cap_hold import hold_capture_if_exhausted
from utils.sync.admission_responses import sync_content_in_progress_response
from utils.analytics import record_sync_v1_usage as record_usage
from utils.other import endpoints as auth
from utils.account_cutover.access import should_skip_background_account_mutation
from utils.other.storage import (
    archive_mobile_batch_raw_files,
    link_archive_captures,
    get_playback_artifact_signed_url,
    upload_playback_artifact,
    mark_playback_unavailable,
    compute_audio_files_fingerprint,
    get_conversation_playback_signed_url,
    upload_conversation_playback_artifact,
    mark_conversation_playback_unavailable,
)
from utils.byok import has_byok_keys
from utils.cloud_tasks import (
    enqueue_sync_job,
    enqueue_audio_merge_job_deferred,
    get_sync_tasks_max_attempts,
    is_cloud_tasks_dispatch_enabled,
    verify_audio_merge_cloud_tasks_oidc,
    verify_cloud_tasks_oidc,
)
from utils.executors import (
    critical_executor,
    db_executor,
    storage_executor,
    sync_executor,
    run_blocking,
    start_background_task,
)
from utils.fair_use import (
    FAIR_USE_ENABLED,
    FAIR_USE_RESTRICT_DAILY_DG_MS,
    check_soft_caps,
    get_enforcement_stage,
    get_hard_restriction_status,
    get_rolling_speech_ms,
    is_daily_audio_ceiling_exceeded,
    is_dg_budget_exhausted,
    record_dg_usage_ms,
    record_speech_ms,
    trigger_classifier_if_needed,
)
from utils.observability.fallback import record_fallback
from utils.multipart import MultipartMaxPartSizeRoute, SYNC_AUDIO_MAX_PART_SIZE, max_part_size
from utils.metrics import (
    OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL,
    OMI_SYNC_JOB_POLL_REQUESTS_TOTAL,
    OMI_SYNC_JOB_POLL_THROTTLED_TOTAL,
    OMI_SYNC_LANE_JOBS_TOTAL,
    OMI_SYNC_LANE_ADMISSIONS_TOTAL,
    OMI_SYNC_QUEUE_WAIT_SECONDS,
    OMI_SYNC_RECORDING_AGE_SECONDS,
)
from utils.sync.poll_limit import SYNC_POLL_WINDOW_SECONDS, admit_sync_job_poll, with_poll_hint
from config.repeat_work import playback_on_demand
from contextlib import nullcontext
from utils.sync.repeat_work_metrics import PLAYBACK_BUILD_SECONDS, PLAYBACK_BUILDS, record_playback_ready
from utils.product_metrics import record_product_event, sanitize_app_build
from utils.journey_metrics_contract import resolve_client_kind
from utils.client_device import resolve_client_device, resolve_client_device_from_request
from utils.subscription import (
    TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS,
    has_transcription_credits,
    resolve_transcription_allowance,
)
from utils.sync import playback as sync_playback
from config.capture_evidence import capture_evidence_dark_write_enabled
from config.rollout_cohorts import warm_rollout_cohorts
from utils.capture_evidence import parse_sync_file_claims
from utils.sync.files import (
    decode_files_to_wav,
    detect_source_from_filenames,
    get_timestamp_from_path,
    get_wav_duration,
    retrieve_file_paths,
)
from utils.sync.pipeline import (
    _OrderedTurnstile,
    _cleanup_files,
    _delete_staged_blobs_async,
    _download_staged_files,
    _finalize_sync_job_failure,
    finalize_sync_job_failure_now,
    finalize_sync_job_superseded,
    SyncJobRunLeaseLost,
    bind_or_converge_sync_ledger_completion,
    _finalize_sync_audio_files,
    _reprocess_merged_conversations,
    _RESPONSE_FENCED_CONVERSATION_IDS,
    _retrieve_file_paths_v2,
    _run_full_pipeline_background_async,
    _stage_files_to_gcs,
    build_person_embeddings_cache,
    process_segment,
    retrieve_vad_segments,
    SyncConversationPersistenceFenced,
)
from utils.stt.outcomes import TranscriptionOutcome, sync_failure_from_exception
from utils.speaker_learning_jobs import schedule_person_voice_learning_retries
from utils.sync.rate_limit import (
    FAIR_USE_RATE_LIMIT_CODE,
    bounded_fair_use_retry_after,
    build_sync_rate_limit_event,
    emit_sync_rate_limit_event,
    fair_use_rate_limit_headers,
    retry_after_until_next_utc_day,
    validated_correlation_id,
)
from utils.sync.backfill import (
    release_backfill_slot,
    reserve_backfill_speech,
    retry_after_next_utc_day,
    try_acquire_backfill_slot,
)
from utils.batch_pipeline.live_upload import RecordUploadRoute, registered_record_response
from utils.sync.content_id import compute_sync_content_id
from utils.sync.capture_manifest import (
    claim_conversation_manifest,
    issue_capture_manifest,
    manifest_claims_match_paths,
    verify_capture_manifest,
)
from utils.sync.lanes import CaptureTimeTrust, SyncLane, classify_sync_lane
from utils.sync import backfill_cutover, legacy_dark, stage as sync_stage, uid_sequencer
from config.sync_owner_concurrency import preparation_width
from utils.sync.owner_prefetch import warm_owner
from utils.sync.provenance import capture_matches_server_conversation as _capture_matches_server_conversation

from utils.sync import cap_hold_redrive

logger = logging.getLogger(__name__)

# Audio constants
AUDIO_SAMPLE_RATE = 16000

_V1_DEPRECATION_HEADERS = {'Deprecation': 'true', 'Link': '</v2/sync-local-files>; rel="successor-version"'}

router = APIRouter(route_class=MultipartMaxPartSizeRoute, dependencies=[Depends(sync_stage.require_http_stage)])


@router.post('/v2/sync-capture-manifest', response_model=SyncCaptureManifestResponse)
async def create_sync_capture_manifest(
    payload: SyncCaptureManifestRequest,
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
    x_device_id_hash: Optional[str] = Header(None, alias='X-Device-Id-Hash'),
    x_app_version: Optional[str] = Header(None, alias='X-App-Version'),
):
    device = resolve_client_device(
        x_app_platform=x_app_platform,
        x_device_id_hash=x_device_id_hash,
        x_app_version=x_app_version,
    )
    filenames = [item.name for item in payload.files]
    trusted = await run_blocking(
        db_executor,
        _capture_matches_server_conversation,
        uid,
        payload.conversation_id,
        filenames,
        device.client_device_id,
    )
    if not trusted:
        raise HTTPException(status_code=403, detail='Fresh capture provenance could not be verified')
    claims = [item.model_dump() for item in payload.files]
    try:
        claimed = await run_blocking(
            db_executor,
            claim_conversation_manifest,
            uid,
            payload.conversation_id,
            claims,
        )
    except Exception as e:
        logger.error('sync capture manifest claim unavailable uid=%s error=%s', uid, type(e).__name__)
        raise HTTPException(status_code=503, detail='Fresh capture provenance is temporarily unavailable') from e
    if not claimed:
        raise HTTPException(status_code=409, detail='Conversation fresh content was already claimed')
    manifest = issue_capture_manifest(
        uid,
        device.client_device_id,
        payload.conversation_id,
        claims,
    )
    record_product_event(
        'sync_job_enqueued',
        client_kind=resolve_client_kind(x_app_platform=x_app_platform, user_agent=None),
        app_build=sanitize_app_build(x_app_version),
        uid=uid,
    )
    return SyncCaptureManifestResponse(manifest=manifest)


class AudioDownloadPendingResponse(BaseModel):
    status: str
    poll_after_ms: int


def _get_sync_rate_limit_telemetry_fields(uid: str) -> Dict[str, object]:
    """Load rejection-only account metadata without affecting the response path on read failures."""
    fields: Dict[str, object] = {
        'subscription_plan': 'unknown',
        'subscription_status': 'unknown',
        'fair_use_stage': 'unknown',
        'classifier_type': 'unknown',
    }
    try:
        state = fair_use_db.get_fair_use_state(uid)
        fields['fair_use_stage'] = state.get('stage')
        fields['classifier_type'] = state.get('last_classifier_type')
    except Exception as e:
        logger.warning('sync_rate_limit_telemetry fair_use_state_read_failed error=%s', type(e).__name__)

    try:
        subscription = users_db.get_existing_user_subscription(uid)
        if subscription is None:
            # This is the same effective default as get_user_subscription(), without
            # creating a Firestore record from a telemetry-only rejection path.
            fields['subscription_plan'] = 'basic'
            fields['subscription_status'] = 'active'
        else:
            fields['subscription_plan'] = subscription.plan
            fields['subscription_status'] = subscription.status
    except Exception as e:
        logger.warning('sync_rate_limit_telemetry subscription_read_failed error=%s', type(e).__name__)

    return fields


async def _fair_use_restriction_response(
    *,
    uid: str,
    retry_after: int | None,
    client_platform: object,
    device_hash: object,
    app_version: object,
    request_id: object = None,
    cloud_trace_context: object = None,
    base_headers: Optional[Dict[str, str]] = None,
    extra_content: Optional[Dict[str, object]] = None,
) -> JSONResponse:
    telemetry = await run_blocking(db_executor, _get_sync_rate_limit_telemetry_fields, uid)
    correlation_id = (
        validated_correlation_id(request_id) or validated_correlation_id(cloud_trace_context) or str(_uuid.uuid4())
    )
    safe_retry_after = bounded_fair_use_retry_after(retry_after)
    event = build_sync_rate_limit_event(
        uid=uid,
        device_hash=device_hash,
        app_platform=client_platform,
        app_version=app_version,
        subscription_plan=telemetry['subscription_plan'],
        subscription_status=telemetry['subscription_status'],
        fair_use_stage=telemetry['fair_use_stage'],
        classifier_type=telemetry['classifier_type'],
        retry_after=safe_retry_after,
        backend_revision=os.getenv('K_REVISION') or os.getenv('DD_VERSION'),
        correlation_id=correlation_id,
    )
    try:
        emit_sync_rate_limit_event(event)
    except Exception as e:
        logger.warning('sync_rate_limit_telemetry emit_failed error=%s', type(e).__name__)

    headers = fair_use_rate_limit_headers(safe_retry_after, base_headers)
    headers['X-Request-ID'] = correlation_id
    content: Dict[str, object] = {
        'code': FAIR_USE_RATE_LIMIT_CODE,
        'detail': 'Account temporarily restricted due to fair-use policy',
    }
    if extra_content:
        content.update(extra_content)
    return JSONResponse(status_code=429, headers=headers, content=content)


@router.post("/v1/sync/audio/{conversation_id}/precache", response_model=AudioPrecacheResponse, tags=['v1'])
def precache_conversation_audio_endpoint(
    conversation_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Warm the audio cache for a conversation.
    Returns immediately - caching happens in background.
    """
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    return sync_playback.precache_audio_files(
        uid,
        conversation_id,
        conversation.get('audio_files', []),
        **(
            {'playback_epoch': conversation['playback_eager_epoch']} if conversation.get('playback_eager_epoch') else {}
        ),
    )


@router.get("/v1/sync/audio/{conversation_id}/urls", response_model=AudioUrlsResponse, tags=['v1'])
def get_audio_signed_urls_endpoint(
    conversation_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Get signed URLs for all audio files in a conversation.
    Synchronously caches the first uncached file for immediate playback.
    Remaining files are cached in background.

    Returns:
        List of audio file info with signed_url (if cached) or status "pending"
    """
    conversation = conversations_db.get_conversation(
        uid, conversation_id, read_site=FirestoreReadSite.SYNC_AUDIO_URLS_POLL
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    return sync_playback.get_audio_signed_urls(
        uid, conversation_id, conversation.get('audio_files', []), conversation=conversation
    )


# **********************************************
# ********** AUDIO DOWNLOAD ENDPOINT ***********
# **********************************************


@router.get(
    "/v1/sync/audio/{conversation_id}/{audio_file_id}",
    tags=['v1'],
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Audio stream.",
            "content": {
                "audio/wav": {"schema": {"type": "string", "format": "binary"}},
                "audio/mpeg": {"schema": {"type": "string", "format": "binary"}},
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        202: {
            "description": "Audio artifact is being prepared.",
            "model": AudioDownloadPendingResponse,
        },
        206: {
            "description": "Partial audio stream.",
            "content": {
                "audio/wav": {"schema": {"type": "string", "format": "binary"}},
                "audio/mpeg": {"schema": {"type": "string", "format": "binary"}},
                "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
            },
        },
    },
)
def download_audio_file_endpoint(
    conversation_id: str,
    audio_file_id: str,
    request: Request,
    format: str = Query(default="wav", regex="^(wav|pcm)$"),
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Download audio file from private cloud sync in the specified format.
    Merges chunks on-demand.

    Args:
        conversation_id: ID of the conversation
        audio_file_id: ID of the audio file within the conversation
        request: FastAPI Request object (for Range header)
        format: Output format - 'wav' or 'pcm' (raw) (default: wav)
        uid: User ID (from authentication)

    Returns:
        StreamingResponse with the audio file in the requested format.
        Returns 206 Partial Content for Range requests, 200 OK for full file.
    """
    # Verify user owns the conversation
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    # Find the audio file in the conversation
    audio_files = conversation.get('audio_files', [])
    audio_file = None
    for af in audio_files:
        if af.get('id') == audio_file_id or audio_file_id in (af.get('legacy_ids') or []):
            audio_file = af
            break

    if not audio_file:
        raise HTTPException(status_code=404, detail="Audio file not found in conversation")

    return sync_playback.download_audio_file_response(
        uid,
        conversation_id,
        audio_file['id'],
        audio_file,
        request,
        format,
        **(
            {'playback_epoch': conversation['playback_eager_epoch']} if conversation.get('playback_eager_epoch') else {}
        ),
    )


# **********************************************
# ************ SYNC LOCAL FILES ****************
# **********************************************


# response_model omitted: deprecated v1 endpoint with mixed dict + JSONResponse returns;
# the v2 typed equivalent (SyncJobStatusResponse) covers the contract.
@router.post("/v1/sync-local-files", deprecated=True, status_code=410)
async def sync_local_files(uid: str = Depends(auth.get_current_user_uid)):
    """Retired (legacy-retire C6): zero calls in the 7-day census to 2026-10-19; v2 is the successor."""
    return JSONResponse(
        status_code=410,
        headers=_V1_DEPRECATION_HEADERS,
        content={
            'code': 'sync_v1_retired',
            'detail': 'Use /v2/sync-local-files; local audio was not consumed',
        },
    )


@router.post(  # v2 async sync-local-files
    "/v2/sync-local-files",
    status_code=202,
    response_model=SyncJobStartResponse,
    responses=SYNC_LOCAL_FILES_V2_RESPONSES,
)
@max_part_size(SYNC_AUDIO_MAX_PART_SIZE)
async def sync_local_files_v2(
    files: List[UploadFile] = File(...),
    uid: str = Depends(auth.get_current_user_uid),
    conversation_id: str = Query(
        None, description="Target conversation ID to attach audio to (auto-sync from live capture)"
    ),
    recording_session_id: Optional[str] = Query(
        None,
        description=(
            "Client recording session id. When conversation_id is omitted and one "
            "conversation for this user, source, and device already carries this id, "
            "attach the audio to that conversation."
        ),
    ),
    audio_start_seconds: Optional[float] = Query(None),
    audio_end_seconds: Optional[float] = Query(None),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
    x_device_id_hash: Optional[str] = Header(None, alias='X-Device-Id-Hash'),
    x_app_version: Optional[str] = Header(None, alias='X-App-Version'),
    x_request_id: Optional[str] = Header(None, alias='X-Request-ID'),
    x_cloud_trace_context: Optional[str] = Header(None, alias='X-Cloud-Trace-Context'),
    x_omi_sync_capture_manifest: Optional[str] = Header(None, alias='X-Omi-Sync-Capture-Manifest'),
    x_omi_capture_evidence: Optional[str] = Header(None, alias='X-Omi-Capture-Evidence', include_in_schema=False),
    x_omi_firmware_version: Optional[str] = Header(None, alias='X-Omi-Firmware-Version'),
    x_omi_device_model: Optional[str] = Header(None, alias='X-Omi-Device-Model'),
    x_omi_conversation_geolocation: Optional[str] = Header(None, alias='X-Omi-Conversation-Geolocation'),
):
    """
    Async version of sync-local-files. Saves raw files and returns 202
    immediately, then runs the full pipeline (decode → VAD → STT → LLM) as
    an async background task. The app polls GET /v2/sync-local-files/{job_id}.
    """
    if isinstance(recording_session_id, str):
        recording_session_id = recording_session_id.strip() or None
    else:
        recording_session_id = None
    ledger_fence_mode = await run_blocking(db_executor, get_sync_ledger_fence_mode)
    if ledger_fence_mode is SyncLedgerFenceMode.STANDBY:
        # The one-time hard-revision-retirement cutover intentionally blocks
        # before app-managed raw-file persistence or a content claim. Clients
        # retain their WAL/audio and retry after the services become active.
        return JSONResponse(
            status_code=503,
            headers={'Retry-After': '60'},
            content={
                'code': 'sync_ledger_fence_cutover',
                'detail': 'Sync is briefly pausing safely; local audio was not consumed',
            },
        )

    # Browser/mobile clients carry capture provenance in these request headers.
    # It must survive both the inline and Cloud Tasks pipeline branches.
    client_device_context = resolve_client_device(
        x_app_platform=x_app_platform if isinstance(x_app_platform, str) else None,
        x_device_id_hash=x_device_id_hash if isinstance(x_device_id_hash, str) else None,
        x_app_version=x_app_version if isinstance(x_app_version, str) else None,
    )
    geolocation = geolocation_from_private_header(x_omi_conversation_geolocation)

    filenames = [f.filename or '' for f in files]
    capture_claims = (
        parse_sync_file_claims(x_omi_capture_evidence, filenames) if capture_evidence_dark_write_enabled() else {}
    )
    manifest_claims = verify_capture_manifest(
        x_omi_sync_capture_manifest,
        uid,
        client_device_context.client_device_id,
        conversation_id,
        filenames,
    )
    record_snapshot = {}
    has_server_capture_proof = manifest_claims is not None and await run_blocking(
        db_executor,
        _capture_matches_server_conversation,
        uid,
        conversation_id,
        filenames,
        client_device_context.client_device_id,
        snapshot_out=record_snapshot,
    )
    lane_decision = classify_sync_lane(
        filenames,
        client_device_id=client_device_context.client_device_id if has_server_capture_proof else None,
    )
    # Fresh is optional for LEGACY uploads: a live-only refusal must preserve
    # their existing backfill acceptance. Resolve before recording the final lane.
    fresh_refused = False
    retry_after = None
    if lane_decision.lane == SyncLane.FRESH:
        hard_restricted, retry_after = await run_blocking(critical_executor, get_hard_restriction_status, uid)
        refusal_reason = None
        if hard_restricted:
            refusal_reason = 'legacy_fresh_hard_restricted'
        elif await run_blocking(db_executor, is_daily_audio_ceiling_exceeded, uid):
            logger.info('sync_v2: daily audio ceiling reached uid=%s', uid)
            refusal_reason = 'legacy_fresh_daily_ceiling'
            retry_after = retry_after_until_next_utc_day()
        if refusal_reason:
            if lane_decision.trust == CaptureTimeTrust.LEGACY:
                lane_decision = replace(lane_decision, lane=SyncLane.BACKFILL, reason=refusal_reason)
            else:
                fresh_refused = True

    try:
        OMI_SYNC_LANE_ADMISSIONS_TOTAL.labels(
            lane=lane_decision.lane.value, trust=lane_decision.trust.value, reason=lane_decision.reason
        ).inc()
    except Exception:
        pass
    logger.info(
        'sync_lane_admission uid=%s device_hash=%s platform=%s app_version=%s lane=%s trust=%s age_seconds=%s reason=%s',
        uid,
        client_device_context.device_hash,
        client_device_context.platform,
        client_device_context.app_version,
        lane_decision.lane.value,
        lane_decision.trust.value,
        lane_decision.maximum_age_seconds,
        lane_decision.reason,
    )
    if lane_decision.lane == SyncLane.BACKFILL and os.getenv('SYNC_BACKFILL_ENABLED', 'true').lower() != 'true':
        return JSONResponse(
            status_code=503,
            headers={'Retry-After': '3600', 'X-Omi-Rate-Limit-Reason': 'backfill_capacity'},
            content={
                'code': 'backfill_capacity',
                'detail': 'Historical recovery is paused; local audio was not consumed',
            },
        )
    if not lane_decision.automatic_recovery_allowed:
        return JSONResponse(
            status_code=422,
            content={
                'code': 'backfill_lookback_exceeded',
                'detail': 'Recording is older than the automatic recovery window; local audio was not consumed',
                'lane': lane_decision.lane.value,
            },
        )
    try:
        OMI_SYNC_RECORDING_AGE_SECONDS.labels(lane=lane_decision.lane.value).observe(
            lane_decision.maximum_age_seconds or 0
        )
    except Exception:
        pass

    if fresh_refused:
        return await _fair_use_restriction_response(
            uid=uid,
            retry_after=retry_after,
            client_platform=client_device_context.platform,
            device_hash=client_device_context.device_hash,
            app_version=client_device_context.app_version,
            request_id=x_request_id if isinstance(x_request_id, str) else None,
            cloud_trace_context=x_cloud_trace_context if isinstance(x_cloud_trace_context, str) else None,
        )

    # A lookup failure must not durably lock: unlike gating the live listen socket, nothing
    # routinely re-checks is_locked later, so a transient blip would paywall it forever (#15232).
    has_credits = await run_blocking(critical_executor, has_transcription_credits, uid)
    should_lock = False
    if not has_credits:
        allowance = await run_blocking(critical_executor, resolve_transcription_allowance, uid)
        should_lock = (
            allowance.reason not in TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS
            and allowance.reason != 'usage_budget_exhausted'
        )

    # Detect source
    source = detect_source_from_filenames([f.filename for f in files])

    byok_enabled = has_byok_keys()

    # Create job_id early so we have it for the directory
    job_id = str(_uuid.uuid4())
    job_dir = f'syncing/{uid}/{job_id}'

    backfill_slot_acquired = False
    # V2 admission never acquires the historical Redis slot. The kill switch
    # changes worker dispatch only; neither setting can pace uploads with 429.

    paths = []
    content_id: Optional[str] = None
    sequencer_registration_started = False

    try:
        # --- Fast path: save raw files only (< 2s typical) ---
        # Use sync_executor, NOT storage_executor — storage is saturated with
        # background pipeline cleanup/GCS work and would queue the 202 response.
        paths = await run_blocking(sync_executor, _retrieve_file_paths_v2, files, uid, job_id)

        if manifest_claims is not None and not await run_blocking(
            sync_executor, manifest_claims_match_paths, manifest_claims, paths
        ):
            if backfill_slot_acquired:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
                backfill_slot_acquired = False
            return JSONResponse(
                status_code=422,
                content={
                    'code': 'capture_manifest_mismatch',
                    'detail': 'Fresh capture manifest did not match the uploaded audio',
                },
            )

        # Keep original bytes before any 202, content-cache hit, decode or VAD.
        # An archive failure leaves the client responsible for retrying its WAL.
        archive_paths = await run_blocking(
            sync_executor,
            archive_mobile_batch_raw_files,
            uid,
            paths,
            {
                'app_version': client_device_context.app_version,
                'firmware': x_omi_firmware_version if isinstance(x_omi_firmware_version, str) else None,
                'device_model': x_omi_device_model if isinstance(x_omi_device_model, str) else None,
                'conversation_id': conversation_id if isinstance(conversation_id, str) else None,
                'sync_job_id': job_id,
            },
        )

        content_id = await run_blocking(sync_executor, compute_sync_content_id, uid, paths)

        record_response = await registered_record_response(
            uid=uid,
            conversation_id=conversation_id if isinstance(conversation_id, str) else None,
            content_id=content_id,
            paths=paths,
            source=source.value,
            client_device_id=client_device_context.client_device_id,
            byok_enabled=byok_enabled,
            recording_session_id=recording_session_id,
            loaded_conversation=record_snapshot if record_snapshot.get('record_lane_owner') else None,
        )
        if isinstance(record_response, JSONResponse):
            return record_response

        if record_response is RecordUploadRoute.BATCH or (
            record_response is not RecordUploadRoute.LEGACY and batch_enabled_for(uid)
        ):
            # Route ownership is durable before any acceptance; neither errors
            # nor rollback may start a legacy twin or release this batch claim.
            sequencer_registration_started = True
            batch_response = await accept_batch_upload(
                uid=uid,
                job_id=job_id,
                content_id=content_id,
                paths=paths,
                lane=lane_decision.lane.value,
                recording_age_seconds=lane_decision.maximum_age_seconds,
                source=source.value,
                should_lock=should_lock,
                conversation_id=conversation_id if isinstance(conversation_id, str) else None,
                client_device_id=client_device_context.client_device_id,
                client_platform=client_device_context.platform,
                byok_enabled=byok_enabled,
                intake_context={
                    'recording_session_id': recording_session_id,
                    'audio_start_seconds': (
                        audio_start_seconds if isinstance(audio_start_seconds, (int, float)) else None
                    ),
                    'audio_end_seconds': audio_end_seconds if isinstance(audio_end_seconds, (int, float)) else None,
                    'geolocation': geolocation.model_dump(mode='json') if geolocation else None,
                    'filenames': filenames,
                    'capture_evidence_claims': capture_claims,
                    'raw_capture_paths': archive_paths,
                },
                record_router=registered_record_response,
            )
            if batch_response is not None:
                return batch_response
            sequencer_registration_started = False

        # C9 (legacy-retire): legacy admission is gone. Content legacy already
        # owns is answered by the fence; anything else keeps its audio (409).
        ledger_row = await run_blocking(db_executor, legacy_dark.read_ledger_row, uid, content_id)
        decision = legacy_dark.fence_decision(ledger_row, legacy_dark.LegacySyncMode.DARK)
        await run_blocking(sync_executor, shutil.rmtree, job_dir, True)
        return (
            legacy_dark.fence_response(decision, total_files=len(files), lane=lane_decision.lane.value)
            or legacy_dark.admission_refused_response()
        )
    except HTTPException:
        if backfill_slot_acquired:
            try:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
            except Exception:
                pass
        raise
    except Exception as e:
        logger.error('event=sync_ingest outcome=failed exception_type=%s', type(e).__name__)
        if content_id and not sequencer_registration_started:
            try:
                await run_blocking(db_executor, release_sync_content_claim, uid, content_id, job_id)
            except Exception:
                pass
        if backfill_slot_acquired:
            try:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
            except Exception:
                pass
        raise HTTPException(
            status_code=500,
            detail='Sync upload could not be accepted; local audio remains available.',
        )
    finally:
        _cleanup_files(paths)


def _sync_finalization_retrying() -> HTTPException:
    return HTTPException(
        status_code=503,
        detail='Sync recovery finalization is retrying; local audio remains available.',
        headers={'Retry-After': '10'},
    )


def _terminal_repeat_failure_kwargs(job: dict) -> dict[str, str]:
    """Carry a terminal job's strike through racing poll/task claim cleanup."""
    if job.get('status') not in {'failed', 'partial_failure'}:
        return {}
    if job.get('status') == 'failed' and job.get('reason_code') == 'sync_invalid_audio':
        return {'failure_key': 'invalid_audio'}
    result = job.get('result')
    if isinstance(result, dict) and result.get('repeat_failure_key') == 'persistent_persistence':
        return {
            'failure_key': 'persistent_persistence',
            'failure_fingerprint': result.get('repeat_failure_fingerprint'),
        }
    return {}


@router.get("/v2/sync-local-files/{job_id}", response_model=SyncJobStatusResponse, response_model_exclude_none=True)
def get_sync_job_status(job_id: str, uid: str = Depends(auth.get_current_user_uid), surface_open: bool = False):
    """Poll for the status of an async sync job."""
    OMI_SYNC_JOB_POLL_REQUESTS_TOTAL.inc()
    if not admit_sync_job_poll(uid):
        OMI_SYNC_JOB_POLL_THROTTLED_TOTAL.inc()
        raise HTTPException(
            status_code=429,
            detail='Sync job polling too frequent; retry later',
            headers={'Retry-After': str(SYNC_POLL_WINDOW_SECONDS)},
        )
    try:
        durable = get_durable_job_status(job_id, uid)
    except BatchPrivacyBlocked:
        return privacy_blocked_response()
    if durable is not None:
        return with_poll_hint(durable, surface_open=surface_open)
    job = get_sync_job(job_id)
    if job and job['uid'] != uid:
        raise HTTPException(status_code=403, detail="Not authorized to view this sync job")
    # A read can reconcile a proven content completion without rewriting Redis,
    # binding a run lease or competing with the worker's terminal authority.
    from utils.sync.completed_status import get_completed_legacy_status

    try:
        completed = get_completed_legacy_status(job_id, uid, job)
    except Exception as error:
        logger.error('event=sync_status_reconciliation outcome=retrying exception_type=%s', type(error).__name__)
        raise _sync_finalization_retrying()
    if completed is not None:
        record_fallback(
            component='sync_dispatch',
            from_mode='redis_status',
            to_mode='durable_completion',
            reason='unavailable',
            outcome='recovered',
        )
        return with_poll_hint(completed, surface_open=surface_open)
    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found or expired")

    # A stale state can only be finalized by the holder of the same run lease
    # as Cloud Tasks/inline execution. Re-read after acquiring it so an active
    # worker can never be failed by a concurrent status poll.
    # Inline work can include executor leaves that outlive coordinator
    # cancellation. Do not let a polling read become a competing terminal
    # owner: retained client audio remains recoverable if the inline worker
    # dies, and only Cloud Tasks jobs use the owned stale finalizer.
    fence_mode = get_sync_ledger_fence_mode()
    job_uses_fence = sync_job_uses_ledger_fence(job)
    if (
        fence_mode is not SyncLedgerFenceMode.STANDBY
        and not (job_uses_fence and fence_mode is not SyncLedgerFenceMode.ACTIVE)
        and is_sync_job_stale(job)
        and job.get('dispatch_mode') == 'cloud_tasks'
    ):
        acquire_stale_lock = try_acquire_sync_job_run_lock if job_uses_fence else try_acquire_job_run_lock
        stale_lock_token = acquire_stale_lock(job_id)
        if stale_lock_token:
            try:
                locked_job = get_sync_job(job_id)
                if (
                    locked_job
                    and locked_job.get('uid') == uid
                    and locked_job.get('dispatch_mode') == 'cloud_tasks'
                    and is_sync_job_stale(locked_job)
                ):
                    locked_job_uses_fence = sync_job_uses_ledger_fence(locked_job)
                    finalized = None
                    if locked_job_uses_fence:
                        finalized = bind_or_converge_sync_ledger_completion(
                            job_id=job_id,
                            uid=uid,
                            content_id=locked_job.get('content_id'),
                            run_lock_token=stale_lock_token,
                        )
                    if finalized is None:
                        finalized = finalize_sync_job_failure_now(
                            job_id=job_id,
                            uid=uid,
                            content_id=locked_job.get('content_id'),
                            error_code=(
                                'sync_dispatch_lost' if locked_job.get('status') == 'queued' else 'sync_worker_stale'
                            ),
                            outcome=TranscriptionOutcome.UPSTREAM_ERROR,
                            provider=locked_job.get('stt_provider', 'unknown'),
                            model=locked_job.get('stt_model', 'unknown'),
                            lane=locked_job.get('lane', SyncLane.FRESH.value),
                            run_lock_token=stale_lock_token if locked_job_uses_fence else None,
                        )
                    if finalized is not None:
                        job = finalized
                    if finalized is not None and locked_job.get('lane') == SyncLane.BACKFILL.value:
                        try:
                            release_backfill_slot(uid, job_id)
                        except Exception as error:
                            logger.error(
                                'event=sync_stale_finalize outcome=release_slot_failed exception_type=%s',
                                type(error).__name__,
                            )
            except SyncJobRunLeaseLost:
                # A newer epoch owns the durable ledger; polling must leave its
                # retry material and Redis state untouched rather than 500.
                logger.warning('event=sync_stale_finalize outcome=lease_lost retry_material=preserved')
            finally:
                release_job_run_lock(job_id, stale_lock_token)

    if (
        job.get('status') in ('failed', 'partial_failure')
        and sync_job_uses_ledger_fence(job)
        and isinstance(job.get('content_id'), str)
    ):
        # Do not expose an ACKable terminal result until the retry claim is
        # recoverable again: otherwise a WAL re-upload receives ``busy`` for
        # the ledger stale window and looks permanently stuck to the client.
        try:
            release_sync_content_claim_after_job_retired(
                uid, job['content_id'], job_id, **_terminal_repeat_failure_kwargs(job)
            )
        except Exception as error:
            logger.error('event=sync_terminal_cleanup outcome=retrying exception_type=%s', type(error).__name__)
            raise _sync_finalization_retrying()
        # Retaining an epoch counter after the durable claim is recoverable is
        # safe; never keep a client WAL pending solely for that optimization.
        delete_sync_job_run_lock_epoch(job_id)

    if job.get('status') in ('failed', 'partial_failure') and job.get('lane') == SyncLane.BACKFILL.value:
        try:
            dead_letter = sync_dead_letters.get_dead_letter(job_id)
        except Exception as error:
            logger.error('event=sync_dead_letter_check outcome=read_failed exception_type=%s', type(error).__name__)
            raise _sync_finalization_retrying()
        if dead_letter is None:
            # Every current terminal publisher writes the pending record before
            # Redis turns terminal, so a missing record means the job failed
            # before the ledger shipped and nothing else will ever write it.
            # Record it here (pending only: no confirmed-cohort event, and no
            # reader replays pending rows) instead of 503-looping forever.
            try:
                dead_letter = sync_dead_letters.record_dead_letter_pending(
                    job_id=job_id,
                    uid=uid,
                    conversation_id=job.get('conversation_id'),
                    failure_code=sync_dead_letters.dead_letter_failure_code(job.get('reason_code')),
                )
            except Exception as error:
                logger.error(
                    'event=sync_dead_letter_check outcome=legacy_record_failed exception_type=%s',
                    type(error).__name__,
                )
                raise _sync_finalization_retrying()
            logger.warning('event=sync_dead_letter_check outcome=legacy_recorded')
        if (
            dead_letter.get('job_id') != job_id
            or dead_letter.get('uid') != uid
            or dead_letter.get('status') not in ('pending', 'dead_letter')
        ):
            raise _sync_finalization_retrying()
        try:
            release_backfill_slot(uid, job_id)
        except Exception as error:
            logger.error(
                'event=sync_stale_finalize outcome=release_slot_failed exception_type=%s',
                type(error).__name__,
            )

    # Build response — include result only when terminal
    resp = {
        'job_id': job['job_id'],
        'status': job['status'],
        'total_segments': job.get('total_segments', 0),
        'processed_segments': job.get('processed_segments', 0),
        'successful_segments': job.get('successful_segments', 0),
        'failed_segments': job.get('failed_segments', 0),
        'lane': job.get('lane', SyncLane.FRESH.value),
        'reason_code': job.get('reason_code'),
        'retry_after': job.get('retry_after'),
        'recording_age_seconds': job.get('recording_age_seconds'),
    }

    if job['status'] in ('completed', 'partial_failure', 'failed'):
        if job.get('result'):
            resp['result'] = job['result']
        if job.get('error'):
            resp['error'] = job['error']

    return with_poll_hint(resp, surface_open=surface_open)


async def _maintain_uid_sequencer_lease(
    uid: str, job_id: str, epoch: int, stop: asyncio.Event, owner: asyncio.Task | None
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=sync_backfill_sequencer.HEARTBEAT_SECONDS)
            return
        except asyncio.TimeoutError:
            pass
        try:
            renewed = await run_blocking(db_executor, sync_backfill_sequencer.renew_job, uid, job_id, epoch)
        except Exception as error:
            logger.error(
                'event=sync_uid_sequencer action=heartbeat outcome=error exception_type=%s', type(error).__name__
            )
            renewed = False
        if not renewed:
            logger.error('event=sync_uid_sequencer action=heartbeat outcome=lease_lost')
            if owner is not None:
                owner.cancel()
            return


@router.post('/v2/sync-backfill-sequencer/sweep', include_in_schema=False)
@read_origin('job:sync_backfill_sequencer')
async def sweep_sync_backfill_sequencer(_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    # Legacy-dark: ``dark`` stops claiming/dispatching only. Enrichment repair and
    # summary-debt repair below keep running until C4 moves them (lead ruling 10-19).
    if legacy_dark.sequencer_dispatch_allowed():
        outcomes = await run_blocking(db_executor, uid_sequencer.sweep)
    else:
        legacy_dark.record_dark_ack(legacy_dark.LegacyDarkReason.SEQUENCER_DARK)
        outcomes = {'legacy_dark': 1}
    from utils.sync import reprocess

    if reprocess.owns_runtime():
        try:
            repair = await run_blocking(db_executor, reprocess.sweep)
        except Exception as error:
            logger.error('event=sync_reprocess action=sweep outcome=error exception_type=%s', type(error).__name__)
            repair = {'repaired': 0, 'error': 1}
        outcomes['reprocess_repaired'] = repair['repaired']
        outcomes['reprocess_repair_errors'] = repair['error']
        if summary_repair_enabled():
            # Only the scheduled two-minute owner scans conversation debt.
            # Batch pumps replay the outbox without paying a per-pump cursor read.
            try:
                summary = await run_blocking(db_executor, summary_debt_repair.tick)
            except Exception as error:
                logger.error('event=summary_debt_repair outcome=error exception_type=%s', type(error).__name__)
                summary = {'scanned': 0, 'admitted': 0, 'errors': 1}
            outcomes['summary_debt_scanned'] = summary['scanned']
            outcomes['summary_debt_admitted'] = summary['admitted']
            outcomes['summary_debt_errors'] = summary['errors']
    return JSONResponse(status_code=500 if outcomes.get('error') else 200, content={'outcomes': outcomes})


@router.post('/v2/sync-backfill-sequencer/wake', include_in_schema=False)
async def wake_sync_backfill_uid(request: Request, _retry_count: int = Depends(verify_cloud_tasks_oidc)):
    payload = await request.json()
    uid = payload.get('uid') if isinstance(payload, dict) else None
    if not isinstance(uid, str) or not uid:
        return JSONResponse(status_code=400, content={'status': 'invalid_uid'})
    if not legacy_dark.sequencer_dispatch_allowed():
        return legacy_dark.sequencer_dark_response()
    try:
        dispatched = await run_blocking(db_executor, uid_sequencer.kick, uid)
    except Exception as error:
        logger.error(
            'event=sync_uid_sequencer action=wake outcome=error uid_hash=%s exception_type=%s',
            backfill_cutover.uid_hash(uid),
            type(error).__name__,
        )
        return JSONResponse(status_code=500, content={'status': 'retry'})
    return JSONResponse(status_code=200, content={'status': 'dispatched' if dispatched else 'deferred'})


@router.post("/v2/sync-jobs/run", include_in_schema=False)
async def run_sync_job(request: Request, task_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    """Persisted sequencer epochs survive the kill switch; old tasks keep their legacy path."""
    if await run_blocking(db_executor, uid_sequencer.production_fence_mode) is SyncLedgerFenceMode.STANDBY:
        return JSONResponse(status_code=503, content={'status': 'cutover_standby'})
    try:
        payload = await request.json()
    except Exception:
        return await _run_sync_job_body(request, task_retry_count)
    if isinstance(payload, dict) and isinstance(payload.get('uid'), str):
        await warm_rollout_cohorts(payload['uid'])
    if isinstance(payload, dict) and payload.get('kind') == 'sync_reprocess':
        return await enrichment_response(payload)
    epoch = payload.get('sequencer_epoch') if isinstance(payload, dict) else None
    if uid_sequencer.foreign_delivery(payload):
        return JSONResponse(status_code=200, content={'status': 'foreign_stage'})
    if epoch is None:
        # Sequencer off: direct work runs at once, in parallel with the drain of
        # already-sequenced entries, instead of queueing behind them.
        if (
            isinstance(payload, dict)
            and payload.get('lane') == SyncLane.BACKFILL.value
            and uid_sequencer.production_stage()
            and uid_sequencer.enabled()
            and legacy_dark.sequencer_registration_allowed()
            and isinstance(payload.get('uid'), str)
            and isinstance(payload.get('job_id'), str)
        ):
            legacy_job = await run_blocking(db_executor, get_sync_job, payload['job_id'])
            if legacy_job and legacy_job.get('status') == 'processing':
                active_owner = await run_blocking(db_executor, sync_backfill_sequencer.get_owner, payload['uid'])
                if active_owner.get('active_job_id'):
                    logger.error(
                        'event=sync_uid_sequencer action=cutover_overlap outcome=direct_and_sequenced '
                        'job_id=%s sequenced_job_id=%s uid_hash=%s',
                        payload['job_id'],
                        active_owner['active_job_id'],
                        backfill_cutover.uid_hash(payload['uid']),
                    )
                else:
                    logger.info(
                        'event=sync_uid_sequencer action=cutover_direct_active outcome=observed '
                        'job_id=%s uid_hash=%s',
                        payload['job_id'],
                        backfill_cutover.uid_hash(payload['uid']),
                    )
            if legacy_job and legacy_job.get('status') == 'queued':
                marked = await run_blocking(
                    db_executor, update_sync_job, payload['job_id'], {'dispatch_mode': 'sequenced'}
                )
                if marked is None:
                    return await _run_sync_job_body(request, task_retry_count)
                age = payload.get('recording_age_seconds')
                captured_at = (
                    float(payload.get('enqueued_at')) - float(age)
                    if isinstance(payload.get('enqueued_at'), (int, float)) and isinstance(age, (int, float))
                    else None
                )
                await run_blocking(
                    db_executor,
                    sync_backfill_sequencer.register_job,
                    payload['uid'],
                    payload['job_id'],
                    payload,
                    captured_at,
                )
                try:
                    await run_blocking(db_executor, uid_sequencer.kick, payload['uid'])
                except Exception as error:
                    logger.error(
                        'event=sync_uid_sequencer action=legacy_migration outcome=deferred exception_type=%s',
                        type(error).__name__,
                    )
                logger.info('event=sync_uid_sequencer action=legacy_migration outcome=registered')
                return JSONResponse(status_code=200, content={'status': 'sequenced_legacy_job'})
            if legacy_job and legacy_job.get('status') in ('queued', 'processing'):
                await run_blocking(db_executor, backfill_cutover.refresh_direct_run, payload['uid'], payload['job_id'])
        return await _run_sync_job_body(request, task_retry_count)
    uid = payload.get('uid')
    job_id = payload.get('job_id')
    if not isinstance(uid, str) or not isinstance(job_id, str) or not isinstance(epoch, int) or epoch <= 0:
        return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'invalid_sequencer_identity'})
    if not await run_blocking(db_executor, sync_backfill_sequencer.begin_job, uid, job_id, epoch):
        logger.info('event=sync_uid_sequencer action=delivery outcome=stale_epoch')
        return JSONResponse(status_code=200, content={'status': 'stale_sequencer_epoch'})
    stop = asyncio.Event()
    heartbeat = start_background_task(
        _maintain_uid_sequencer_lease(uid, job_id, epoch, stop, asyncio.current_task()),
        name=f'sync:uid-lease:{job_id}',
    )
    try:
        prior_job = await run_blocking(db_executor, get_sync_job, job_id)
        prior_attempt = prior_job.get('attempt', 0) if isinstance(prior_job, dict) else 0
        effective_retry_count = max(task_retry_count, prior_attempt if isinstance(prior_attempt, int) else 0)
        response = await _run_sync_job_body(request, effective_retry_count)
    finally:
        stop.set()
        await heartbeat
    if response.status_code < 300:
        job = await run_blocking(db_executor, get_sync_job, job_id)
        if job is not None and job.get('status') not in TERMINAL_STATUSES:
            logger.error('event=sync_uid_sequencer action=delivery outcome=nonterminal_ack')
            return JSONResponse(status_code=500, content={'status': 'nonterminal_ack'})
        outcome = job.get('status') if job else 'expired'
        released = await run_blocking(db_executor, sync_backfill_sequencer.finish_job, uid, job_id, epoch, outcome)
        if released:
            await run_blocking(db_executor, uid_sequencer.kick, uid)
    return response


@sync_attempt
async def _run_sync_job_body(request: Request, task_retry_count: int):
    """Cloud Tasks handler: runs one sync job inside the request.

    Auth is the Cloud Tasks OIDC token (verify_cloud_tasks_oidc), not Firebase.
    Response semantics drive the queue: 2xx consumes the task, 409 while the
    run-lock is held retries later, 500 retries with backoff.

    Idempotency: a per-job Redis run-lock serializes concurrent deliveries;
    terminal jobs are acked without re-running; segments completed by a prior
    attempt are skipped via the processed-segment ledger inside the pipeline.
    """
    runtime_fence_mode = await run_blocking(db_executor, get_sync_ledger_fence_mode)
    if runtime_fence_mode is SyncLedgerFenceMode.STANDBY:
        # Do not parse/download/acquire while the one-time cutover has paused
        # Cloud Tasks. A non-2xx response retains the task and staged audio.
        return JSONResponse(status_code=503, content={'status': 'cutover_standby'})

    release_lock = True
    try:
        payload = await request.json()
        job_id = payload['job_id']
        uid = payload['uid']
        blob_paths = list(payload['raw_blob_paths'])
        source = ConversationSource(payload.get('source') or 'omi')
        should_lock = bool(payload.get('should_lock', False))
        conversation_id = payload.get('conversation_id')
        recording_session_id = payload.get('recording_session_id')
        if isinstance(recording_session_id, str):
            recording_session_id = recording_session_id.strip() or None
        else:
            recording_session_id = None
        audio_start_seconds = payload.get('audio_start_seconds')
        audio_end_seconds = payload.get('audio_end_seconds')
        if not isinstance(audio_start_seconds, (int, float)) or isinstance(audio_start_seconds, bool):
            audio_start_seconds = None
        if not isinstance(audio_end_seconds, (int, float)) or isinstance(audio_end_seconds, bool):
            audio_end_seconds = None
        geolocation = geolocation_from_private_header(
            json.dumps(payload.get('geolocation')) if payload.get('geolocation') else None
        )
        client_device_id = payload.get('client_device_id')
        client_platform = payload.get('client_platform')
        raw_capture_paths = payload.get('raw_capture_paths') or []
        if (
            not isinstance(raw_capture_paths, list)
            or len(raw_capture_paths) > 20
            or any(
                not isinstance(path, str) or not path.startswith((f'raw-sync/{uid}/', f'raw-mobile-batch/{uid}/'))
                for path in raw_capture_paths
            )
        ):
            raise HTTPException(status_code=400, detail='Invalid raw capture linkage')
        capture_claims = payload.get('capture_evidence_claims')
        if not isinstance(capture_claims, dict) or len(capture_claims) > 20:
            capture_claims = {}
        sync_lane = payload.get('lane') if payload.get('lane') in ('fresh', 'backfill') else SyncLane.FRESH.value
        set_sync_metrics_lane(sync_lane)
        content_id = payload.get('content_id') if isinstance(payload.get('content_id'), str) else None
        payload_uses_fence = payload.get('ledger_fence_mode') == SyncLedgerFenceMode.ACTIVE.value
        enqueued_at = payload.get('enqueued_at')
        if not isinstance(client_device_id, str):
            client_device_id = None
        if not isinstance(client_platform, str):
            client_platform = None
        if isinstance(enqueued_at, (int, float)):
            try:
                OMI_SYNC_QUEUE_WAIT_SECONDS.labels(lane=sync_lane).observe(max(0.0, time.time() - enqueued_at))
            except Exception:
                pass
    except Exception as e:
        # A malformed payload will not fix itself on retry — consume it.
        logger.error(f'sync job handler: invalid payload, dropping task: {e}')
        return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'invalid_payload'})

    # The persisted job mode, not ambient configuration after admission,
    # selects the protocol. A payload mode covers the expired-job recovery
    # path where the Redis document is already gone.
    initial_job = await run_blocking(db_executor, get_sync_job, job_id)
    ledger_fence_active = (
        await run_blocking(db_executor, sync_job_uses_ledger_fence, initial_job) if initial_job else payload_uses_fence
    )
    if ledger_fence_active and runtime_fence_mode is not SyncLedgerFenceMode.ACTIVE:
        return JSONResponse(status_code=503, content={'status': 'fence_mode_mismatch'})

    # Fail-closed lock: Redis errors propagate → 500 → Cloud Tasks retries later.
    acquire_task_lock = try_acquire_sync_job_run_lock if ledger_fence_active else try_acquire_job_run_lock
    lock_token = await run_blocking(db_executor, acquire_task_lock, job_id)
    if not lock_token:
        logger.warning(f'sync job {job_id}: run-lock held by another attempt, deferring')
        return JSONResponse(status_code=409, content={'status': 'locked'})

    try:
        job = await run_blocking(db_executor, get_sync_job, job_id)
        if job:
            ledger_fence_active = await run_blocking(db_executor, sync_job_uses_ledger_fence, job)
            if ledger_fence_active and runtime_fence_mode is not SyncLedgerFenceMode.ACTIVE:
                return JSONResponse(status_code=503, content={'status': 'fence_mode_mismatch'})
        if not job and redrive_policy.enabled():
            custody = await run_blocking(db_executor, sync_redrive.preserve_missing_job, uid, job_id, payload)
            # ACK only after durable custody. Neither branch deletes staged
            # bytes or releases a partial ledger claim to blind provider retry.
            return JSONResponse(status_code=200, content={'status': custody})
        if not job:
            # Job TTL (24h) expired before dispatch — staged blobs are gone or
            # about to be (1-day lifecycle); the app re-uploads on 404.
            logger.warning(f'sync job {job_id}: job expired before dispatch, dropping task')
            await _delete_staged_blobs_async(blob_paths)
            if sync_lane == SyncLane.BACKFILL.value:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
            if content_id and ledger_fence_active:
                # The Redis job is gone and this handler holds its fresh
                # compare-delete token. Releasing only the matching old claim
                # restores the WAL's 404 -> re-upload recovery path.
                await run_blocking(db_executor, release_sync_content_claim_after_job_retired, uid, content_id, job_id)
            elif content_id:
                await run_blocking(db_executor, release_sync_content_claim, uid, content_id, job_id)
            if ledger_fence_active:
                await run_blocking(db_executor, delete_sync_job_run_lock_epoch, job_id)
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'job_expired'})

        if job['status'] in TERMINAL_STATUSES:
            # Duplicate delivery, stale-detector-failed job, or a prior attempt
            # that finished. Never re-run terminal jobs — the app may already be
            # re-uploading these files as a new job.
            terminal_backfill_failure = job.get('lane') == SyncLane.BACKFILL.value and job['status'] in (
                'failed',
                'partial_failure',
            )
            if terminal_backfill_failure:
                await run_blocking(
                    db_executor,
                    sync_dead_letters.ensure_dead_letter_confirmed,
                    job_id,
                    uid=job.get('uid'),
                    conversation_id=job.get('conversation_id'),
                    failure_code=job.get('reason_code') or 'unknown',
                )
            else:
                await _delete_staged_blobs_async(blob_paths)
            if job.get('lane') == SyncLane.BACKFILL.value:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
            if content_id and job['status'] in ('failed', 'partial_failure'):
                release_claim = (
                    release_sync_content_claim_after_job_retired if ledger_fence_active else release_sync_content_claim
                )
                await run_blocking(
                    db_executor, release_claim, uid, content_id, job_id, **_terminal_repeat_failure_kwargs(job)
                )
            if ledger_fence_active:
                await run_blocking(db_executor, delete_sync_job_run_lock_epoch, job_id)
            return JSONResponse(status_code=200, content={'status': 'acked', 'job_status': job['status']})

        converged = None
        if ledger_fence_active:
            converged = await run_blocking(
                db_executor,
                bind_or_converge_sync_ledger_completion,
                job_id=job_id,
                uid=uid,
                content_id=content_id,
                run_lock_token=lock_token,
            )
        elif redrive_policy.legacy_convergence_enabled():
            converged = await run_blocking(
                db_executor,
                sync_redrive.converge_legacy_completion,
                job_id=job_id,
                uid=uid,
                content_id=content_id,
                run_lock_token=lock_token,
            )
        if converged is not None:
            await _delete_staged_blobs_async(blob_paths)
            if sync_lane == SyncLane.BACKFILL.value:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
            return JSONResponse(status_code=200, content={'status': 'done', 'reconciled': True})

        if await run_blocking(db_executor, should_skip_background_account_mutation, uid):
            await _finalize_sync_job_failure(
                job_id=job_id,
                uid=uid,
                content_id=content_id,
                error_code='account_cutover',
                outcome=TranscriptionOutcome.UPSTREAM_ERROR,
                provider='unknown',
                model='unknown',
                lane=sync_lane,
                run_lock_token=lock_token if ledger_fence_active else None,
            )
            await _delete_staged_blobs_async(blob_paths)
            if sync_lane == SyncLane.BACKFILL.value:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
            if content_id:
                release_claim = (
                    release_sync_content_claim_after_job_retired if ledger_fence_active else release_sync_content_claim
                )
                await run_blocking(db_executor, release_claim, uid, content_id, job_id)
            logger.info('event=sync_transcription_job outcome=skipped reason=account_cutover lane=%s', sync_lane)
            return JSONResponse(status_code=200, content={'status': 'skipped', 'reason': 'account_cutover'})

        sequencer_epoch = payload.get('sequencer_epoch')
        if (
            sync_lane == SyncLane.BACKFILL.value
            and isinstance(sequencer_epoch, int)
            and sequencer_epoch > 0
            and preparation_width() > 1
        ):
            # Pure future downloads share this instance with a possible next
            # task. They hold no Cloud Tasks slot, job lock, ledger claim, or
            # conversation authority. A cross-instance delivery simply misses.
            start_background_task(
                run_blocking(storage_executor, warm_owner, uid, job_id, sequencer_epoch),
                name='sync:owner-prefetch',
            )
        if not await run_blocking(storage_executor, _download_staged_files, blob_paths):
            # Blobs deleted by the bucket's 1-day lifecycle (deep queue backlog).
            await _finalize_sync_job_failure(
                job_id=job_id,
                uid=uid,
                content_id=content_id,
                error_code='sync_staged_audio_expired',
                outcome=TranscriptionOutcome.UPSTREAM_ERROR,
                provider='unknown',
                model='unknown',
                lane=sync_lane,
                run_lock_token=lock_token if ledger_fence_active else None,
            )
            await _delete_staged_blobs_async(blob_paths)
            if sync_lane == SyncLane.BACKFILL.value:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'staged_audio_expired'})

        job_dir = f'syncing/{uid}/{job_id}'
        try:
            # One memo per locked task attempt, in the pipeline's async context.
            # run_blocking copies this context into each executor leaf; scope exit
            # closes inherited memo references even if a cancelled leaf outlives us.
            with historical_scan_memo_scope(uid):
                await _run_full_pipeline_background_async(
                    job_id,
                    uid,
                    blob_paths,
                    source,
                    should_lock,
                    job_dir,
                    conversation_id,
                    geolocation=geolocation,
                    task_mode=True,
                    client_device_id=client_device_id,
                    client_platform=client_platform,
                    sync_lane=sync_lane,
                    content_id=content_id,
                    run_lock_token=lock_token if ledger_fence_active else None,
                    content_run_bound=ledger_fence_active,
                    ledger_fence_active=ledger_fence_active,
                    **({'raw_capture_paths': raw_capture_paths} if raw_capture_paths else {}),
                    **({'capture_evidence_claims': capture_claims} if capture_claims else {}),
                    recording_session_id=recording_session_id,
                    audio_start_seconds=audio_start_seconds,
                    audio_end_seconds=audio_end_seconds,
                )
        except SyncConversationPersistenceFenced:
            latest_job = await run_blocking(db_executor, get_sync_job, job_id) or job
            await finalize_sync_job_superseded(
                job_id=job_id,
                run_lock_token=lock_token if ledger_fence_active else None,
                lane=sync_lane,
                provider=latest_job.get('stt_provider') or 'unknown',
                model=latest_job.get('stt_model') or 'unknown',
            )
            if sync_lane == SyncLane.BACKFILL.value:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
            if content_id:
                release_claim = (
                    release_sync_content_claim_after_job_retired if ledger_fence_active else release_sync_content_claim
                )
                await run_blocking(db_executor, release_claim, uid, content_id, job_id)
            await _delete_staged_blobs_async(blob_paths)
            logger.info('event=sync_transcription_job outcome=superseded lane=%s', sync_lane)
            return JSONResponse(status_code=200, content={'status': 'superseded'})
        except SyncJobRunLeaseLost as error:
            latest_job = await run_blocking(db_executor, get_sync_job, job_id)
            if latest_job and latest_job.get('status') in TERMINAL_STATUSES:
                logger.error(
                    'event=sync_transcription_job status=terminal_cleanup_retry job_status=%s exception_type=%s',
                    latest_job.get('status'),
                    type(error).__name__,
                )
                return JSONResponse(
                    status_code=500,
                    content={'status': 'terminal_cleanup_retry', 'job_status': latest_job.get('status')},
                )
            release_lock = False
            logger.warning('event=sync_transcription_job outcome=lease_lost retry_material=preserved')
            return JSONResponse(status_code=409, content={'status': 'locked'})
        except Exception as e:
            max_attempts = get_sync_tasks_max_attempts()
            latest_job = await run_blocking(db_executor, get_sync_job, job_id) or job
            if latest_job.get('status') in TERMINAL_STATUSES:
                # A terminal Redis transition can succeed before a subsequent
                # durable-claim release/cleanup fails. Never turn that proven
                # result back into a queued retry or a second failure. A 500
                # is deliberate: Cloud Tasks redelivers into the terminal
                # branch, which retries only exact-job cleanup and never
                # downloads or transcribes the audio again.
                logger.error(
                    'event=sync_transcription_job status=terminal_cleanup_retry job_status=%s exception_type=%s',
                    latest_job.get('status'),
                    type(e).__name__,
                )
                return JSONResponse(
                    status_code=500,
                    content={'status': 'terminal_cleanup_retry', 'job_status': latest_job.get('status')},
                )
            if ledger_fence_active and task_retry_count >= max_attempts - 1:
                # A pipeline leaf can durably complete the content ledger and
                # then fail before it publishes the matching Redis terminal
                # result. This must win even on the task's final delivery:
                # there may be no later Cloud Tasks retry to converge it.
                try:
                    converged = await run_blocking(
                        db_executor,
                        bind_or_converge_sync_ledger_completion,
                        job_id=job_id,
                        uid=uid,
                        content_id=content_id,
                        run_lock_token=lock_token,
                    )
                except SyncJobRunLeaseLost:
                    release_lock = False
                    logger.warning('event=sync_transcription_job outcome=lease_lost retry_material=preserved')
                    return JSONResponse(status_code=409, content={'status': 'locked'})
                if converged is not None:
                    logger.info('event=sync_transcription_job outcome=reconciled_after_pipeline_exception')
                    await _delete_staged_blobs_async(blob_paths)
                    if sync_lane == SyncLane.BACKFILL.value:
                        await run_blocking(db_executor, release_backfill_slot, uid, job_id)
                    return JSONResponse(status_code=200, content={'status': 'done', 'reconciled': True})
            failure = sync_failure_from_exception(e, provider=latest_job.get('stt_provider'))
            sync_model = latest_job.get('stt_model')
            if not failure.retryable or task_retry_count >= max_attempts - 1:
                logger.error(
                    'event=sync_transcription_job outcome=%s status=failed_final lane=%s '
                    'attempt=%d exception_type=%s',
                    failure.outcome.value,
                    sync_lane,
                    task_retry_count + 1,
                    type(e).__name__,
                )
                await _finalize_sync_job_failure(
                    job_id=job_id,
                    uid=uid,
                    content_id=content_id,
                    error_code=failure.error_code,
                    outcome=failure.outcome,
                    provider=failure.provider,
                    model=sync_model,
                    lane=sync_lane,
                    run_lock_token=lock_token if ledger_fence_active else None,
                )
                await _delete_staged_blobs_async(blob_paths)
                if sync_lane == SyncLane.BACKFILL.value:
                    await run_blocking(db_executor, release_backfill_slot, uid, job_id)
                return JSONResponse(status_code=200, content={'status': 'failed_final'})
            # Reset to 'queued' so the stale detector cannot terminally fail the
            # job while the Cloud Tasks retry backoff elapses. Blobs are kept.
            logger.warning(
                'event=sync_transcription_job outcome=%s status=retrying lane=%s ' 'attempt=%d exception_type=%s',
                failure.outcome.value,
                sync_lane,
                task_retry_count + 1,
                type(e).__name__,
            )
            if ledger_fence_active:
                retry_mutation = await run_blocking(
                    db_executor,
                    fenced_mark_job_queued_for_retry,
                    job_id,
                    lock_token,
                    task_retry_count + 1,
                    failure.error_code,
                )
                if not retry_mutation.applied:
                    latest_job = await run_blocking(db_executor, get_sync_job, job_id) or job
                    if latest_job.get('status') in TERMINAL_STATUSES:
                        logger.error(
                            'event=sync_transcription_job status=terminal_cleanup_retry job_status=%s '
                            'exception_type=%s',
                            latest_job.get('status'),
                            type(e).__name__,
                        )
                        return JSONResponse(
                            status_code=500,
                            content={'status': 'terminal_cleanup_retry', 'job_status': latest_job.get('status')},
                        )
                    release_lock = False
                    logger.warning('event=sync_transcription_job outcome=lease_lost stage=retry_reset')
                    return JSONResponse(status_code=409, content={'status': 'locked'})
            else:
                retried = await run_blocking(
                    db_executor,
                    mark_job_queued_for_retry,
                    job_id,
                    task_retry_count + 1,
                    failure.error_code,
                )
                if retried is None:
                    logger.warning('event=sync_transcription_job outcome=retry_reset_missing_job')
                    return JSONResponse(status_code=500, content={'status': 'retry'})
            return JSONResponse(status_code=500, content={'status': 'retry'})

        # Pipeline returned normally: completed, or it marked the job failed
        # itself (decode/VAD/DG-budget) — terminal either way, staging is done.
        await _delete_staged_blobs_async(blob_paths)
        if sync_lane == SyncLane.BACKFILL.value:
            await run_blocking(db_executor, release_backfill_slot, uid, job_id)
        return JSONResponse(status_code=200, content={'status': 'done'})
    except SyncJobRunLeaseLost as error:
        latest_job = await run_blocking(db_executor, get_sync_job, job_id)
        if latest_job and latest_job.get('status') in TERMINAL_STATUSES:
            # ``INVALID_STATE`` can race with a terminal transition after a
            # worker's last check. Preserve the terminal result and retry only
            # its exact-job cleanup on the next delivery.
            logger.error(
                'event=sync_transcription_job status=terminal_cleanup_retry job_status=%s exception_type=%s',
                latest_job.get('status'),
                type(error).__name__,
            )
            return JSONResponse(
                status_code=500,
                content={'status': 'terminal_cleanup_retry', 'job_status': latest_job.get('status')},
            )
        release_lock = False
        logger.warning('event=sync_transcription_job outcome=lease_lost retry_material=preserved')
        return JSONResponse(status_code=409, content={'status': 'locked'})
    except asyncio.CancelledError:
        # A Cloud Run/Tasks timeout may cancel this coordinator while an
        # executor leaf is still mutating state. Preserve the token until TTL
        # so a retry cannot run concurrently with that leaf.
        release_lock = False
        logger.warning('event=sync_transcription_job outcome=cancelled lock=preserved')
        raise
    finally:
        if release_lock:
            await run_blocking(db_executor, release_job_run_lock, job_id, lock_token)


# A destructive operation (explicit memory deletion, retention cleanup) owns the
# account gate for seconds to a few minutes. Queue retries land inside that
# window, use up every attempt, and leave the file marked merge_failed, so
# playback is never built. A deferred, delayed copy waits the gate out instead,
# without a 5xx or a spent attempt. Delays run 60, 120, 240, 480, 900, 900 s,
# about 45 min in total.
AUDIO_MERGE_DESTRUCTIVE_DEFERRALS_MAX = 6


async def _defer_merge_for_destructive_operation(payload: dict):
    """Return a 200 'deferred' response after re-enqueueing, or None to keep the
    caller's existing retry and final-attempt handling (deferrals exhausted, or
    the re-enqueue itself failed)."""
    deferrals = int(payload.get('destructive_deferrals') or 0)
    if deferrals >= AUDIO_MERGE_DESTRUCTIVE_DEFERRALS_MAX:
        return None
    delay = min(60 * 2**deferrals, 900)
    try:
        await run_blocking(
            db_executor, enqueue_audio_merge_job_deferred, {**payload, 'destructive_deferrals': deferrals + 1}, delay
        )
    except Exception as e:
        logger.warning(f'audio_merge: destructive deferral enqueue failed exception_type={type(e).__name__}')
        return None
    logger.info(f'audio_merge: deferred reason=destructive_operation deferral={deferrals + 1} delay_s={delay}')
    return JSONResponse(status_code=200, content={'status': 'deferred', 'reason': 'destructive_operation'})


# response_model omitted: include_in_schema=False Cloud Tasks handler; JSONResponse status
# codes (200/409/500) drive the queue protocol, not a typed client-facing body.
@router.post("/v2/audio-merge-jobs/run", include_in_schema=False)
async def run_audio_merge_job(request: Request, task_retry_count: int = Depends(verify_audio_merge_cloud_tasks_oidc)):
    from database.legal_holds import (
        DestructiveOperationInProgress,
    )  # deferred: sync.py imported with database stubbed in test isolation

    """Cloud Tasks handler: build one playback MP3 artifact inside the request.

    Response semantics drive the queue: 2xx consumes the task, 409 while the
    run-lock is held retries later, 500 retries with backoff. Idempotency:
    named tasks dedupe enqueues, the run-lock serializes duplicate deliveries,
    and an existing artifact is acked without rebuilding.
    """
    try:
        payload = await request.json()
        schema_version = payload.get('schema_version')
        if schema_version != 2:
            uid = payload['uid']
            conversation_id = payload['conversation_id']
            audio_file_id = payload['audio_file_id']
            timestamps = list(payload['timestamps'])
    except Exception as e:
        logger.error(f'audio_merge handler: invalid payload, dropping task: {e}')
        return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'invalid_payload'})

    # The v2 conversation-merge dispatch runs OUTSIDE the payload-parse guard so its
    # transient GCS/Firestore failures (during the doc read, artifact upload, or doc
    # stamp) propagate to FastAPI (500 -> Cloud Tasks retry) instead of being masked
    # as 'invalid_payload' and acked 200. A masked ack permanently loses the playback
    # artifact: the named task's tombstone makes the /urls re-enqueue a no-op, so the
    # artifact is never rebuilt until audio_files change. _run_conversation_merge_job
    # validates its own payload and returns 200-dropped for genuinely malformed input.
    if playback_on_demand() and not payload.get('on_demand'):
        # ACK burns this eager name. Persist an opaque recovery namespace first;
        # open/play readers reuse their already loaded row to escape that name
        # after rollback. Update-only: no read, transcript write or resurrection.
        try:
            await run_blocking(
                db_executor,
                conversations_db.mark_playback_deferred,
                payload['uid'],
                payload['conversation_id'],
                _uuid.uuid4().hex,
            )
        except Exception as e:
            logger.warning('audio_merge: playback deferral stamp failed exception_type=%s', type(e).__name__)
            return JSONResponse(status_code=503, content={'status': 'retry'})
        PLAYBACK_BUILDS.labels('conversation' if schema_version == 2 else 'file', 'deferred').inc()
        return JSONResponse(status_code=200, content={'status': 'deferred_until_playback'})
    if schema_version == 2:
        return await _run_conversation_merge_job(payload, task_retry_count)

    lock_key = f'audio:{conversation_id}:{audio_file_id}'
    lock_token = await run_blocking(db_executor, try_acquire_job_run_lock, lock_key)
    if not lock_token:
        return JSONResponse(status_code=409, content={'status': 'locked'})

    try:
        if await run_blocking(db_executor, should_skip_background_account_mutation, uid):
            return JSONResponse(status_code=200, content={'status': 'skipped', 'reason': 'account_cutover'})

        conversation = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
        if not conversation or conversation.get('deleted', False):
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'deleted_conversation'})

        existing = await run_blocking(
            storage_executor, get_playback_artifact_signed_url, uid, conversation_id, audio_file_id
        )
        if existing:
            if playback_on_demand():
                PLAYBACK_BUILDS.labels('file', 'reused').inc()
            return JSONResponse(status_code=200, content={'status': 'exists'})

        try:
            with PLAYBACK_BUILD_SECONDS.labels('file').time() if playback_on_demand() else nullcontext():
                mp3_data = await run_blocking(
                    sync_executor,
                    sync_playback.build_playback_artifact,
                    uid,
                    conversation_id,
                    timestamps,
                    **({'source_fingerprint': payload.get('source_fingerprint')} if payload.get('on_demand') else {}),
                )
        except FileNotFoundError:
            logger.warning(f'audio_merge: chunks missing conv={conversation_id} file={audio_file_id}, dropping')
            # Persist the verdict or /urls reports pending forever and clients
            # poll to exhaustion (named-task tombstones block re-enqueues too)
            try:
                await run_blocking(
                    storage_executor, mark_playback_unavailable, uid, conversation_id, audio_file_id, 'chunks_missing'
                )
            except DestructiveOperationInProgress:
                logger.info(
                    f'audio_merge: unavailable marker deferred reason=destructive_operation '
                    f'conv={conversation_id} file={audio_file_id}'
                )
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'chunks_missing'})
        except Exception as e:
            if isinstance(e, DestructiveOperationInProgress):
                deferred = await _defer_merge_for_destructive_operation(payload)
                if deferred is not None:
                    return deferred
            max_attempts = get_sync_tasks_max_attempts()
            if task_retry_count >= max_attempts - 1:
                logger.error(f'audio_merge_failed_final conv={conversation_id} file={audio_file_id}: {e}')
                # Same pending-forever trap as chunks_missing: a consumed task
                # leaves a tombstone that blocks re-enqueue. Mark unavailable so
                # clients stop polling; the 30-day lifecycle grants a retry.
                try:
                    await run_blocking(
                        storage_executor, mark_playback_unavailable, uid, conversation_id, audio_file_id, 'merge_failed'
                    )
                except DestructiveOperationInProgress:
                    logger.info(
                        f'audio_merge: unavailable marker deferred reason=destructive_operation '
                        f'conv={conversation_id} file={audio_file_id}'
                    )
                return JSONResponse(status_code=200, content={'status': 'failed_final'})
            logger.warning(
                f'audio_merge: attempt {task_retry_count + 1} failed conv={conversation_id} '
                f'file={audio_file_id}, will retry: {e}'
            )
            return JSONResponse(status_code=500, content={'status': 'retry'})

        if not mp3_data:
            logger.warning(f'audio_merge: no audio data conv={conversation_id} file={audio_file_id}, dropping')
            try:
                await run_blocking(
                    storage_executor, mark_playback_unavailable, uid, conversation_id, audio_file_id, 'empty_audio'
                )
            except DestructiveOperationInProgress:
                logger.info(
                    f'audio_merge: unavailable marker deferred reason=destructive_operation '
                    f'conv={conversation_id} file={audio_file_id}'
                )
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'empty_audio'})

        try:
            await run_blocking(
                storage_executor, upload_playback_artifact, uid, conversation_id, audio_file_id, mp3_data
            )
        except Exception as e:
            if isinstance(e, DestructiveOperationInProgress):
                deferred = await _defer_merge_for_destructive_operation(payload)
                if deferred is not None:
                    return deferred
            # The upload fence raises DestructiveOperationInProgress while a
            # destructive operation owns the account. Leaving it unhandled
            # reports that frame to Error Reporting. The unavailable marker is
            # the same fenced GCS write, so the final attempt must catch a
            # second fence and still return failed_final.
            max_attempts = get_sync_tasks_max_attempts()
            if task_retry_count >= max_attempts - 1:
                logger.error(f'audio_merge_failed_final conv={conversation_id} file={audio_file_id}: {e}')
                try:
                    await run_blocking(
                        storage_executor, mark_playback_unavailable, uid, conversation_id, audio_file_id, 'merge_failed'
                    )
                except DestructiveOperationInProgress:
                    logger.info(
                        f'audio_merge: unavailable marker deferred reason=destructive_operation '
                        f'conv={conversation_id} file={audio_file_id}'
                    )
                return JSONResponse(status_code=200, content={'status': 'failed_final'})
            logger.warning(
                f'audio_merge: attempt {task_retry_count + 1} failed conv={conversation_id} '
                f'file={audio_file_id}, will retry: {e}'
            )
            return JSONResponse(status_code=500, content={'status': 'retry'})
        if playback_on_demand():
            PLAYBACK_BUILDS.labels('file', 'built').inc()
            record_playback_ready(payload, 'file')
        logger.info(f'audio_merge: built artifact conv={conversation_id} file={audio_file_id} size={len(mp3_data)}')
        return JSONResponse(status_code=200, content={'status': 'done'})
    finally:
        await run_blocking(db_executor, release_job_run_lock, lock_key, lock_token)


async def _run_conversation_merge_job(payload: dict, task_retry_count: int):
    from database.legal_holds import (
        DestructiveOperationInProgress,
    )  # deferred: sync.py imported with database stubbed in test isolation

    """schema_version 2: build the conversation-level dense MP3 + spans and stamp
    the doc (conversation_audio). Upload precedes the stamp so a stamped
    fingerprint always implies a servable blob. Freshness is re-checked from the
    doc, not the payload: if audio_files changed since enqueue, a newer
    fingerprint-named task exists and this one is acked as superseded.
    """
    try:
        uid = payload['uid']
        conversation_id = payload['conversation_id']
        payload_fingerprint = payload.get('fingerprint')
        demand = payload.get('on_demand') is True
    except Exception as e:
        logger.error(f'audio_merge handler: invalid v2 payload, dropping task: {e}')
        return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'invalid_payload'})

    lock_key = f'audio:{conversation_id}:conversation'
    lock_token = await run_blocking(db_executor, try_acquire_job_run_lock, lock_key)
    if not lock_token:
        return JSONResponse(status_code=409, content={'status': 'locked'})

    try:
        if await run_blocking(db_executor, should_skip_background_account_mutation, uid):
            return JSONResponse(status_code=200, content={'status': 'skipped', 'reason': 'account_cutover'})

        conversation = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
        if not conversation or conversation.get('deleted', False):
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'deleted_conversation'})
        if not conversation.get('audio_files'):
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'no_audio_files'})
        audio_files = conversation['audio_files']
        if demand:
            fingerprint = compute_audio_files_fingerprint(
                audio_files,
                origin=conversation.get('started_at') or conversation.get('created_at'),
                source_identity=True,
            )
        else:
            fingerprint = compute_audio_files_fingerprint(audio_files)
        if payload_fingerprint and payload_fingerprint != fingerprint:
            return JSONResponse(status_code=200, content={'status': 'superseded'})

        stamp = conversation.get('conversation_audio') or {}
        if stamp.get('audio_files_fingerprint') == fingerprint:
            existing = await run_blocking(
                storage_executor,
                get_conversation_playback_signed_url,
                uid,
                conversation_id,
                **({'fingerprint': fingerprint} if demand else {}),
            )
            if existing:
                if demand:
                    PLAYBACK_BUILDS.labels('conversation', 'reused').inc()
                return JSONResponse(status_code=200, content={'status': 'exists'})

        started_at_ts = persisted_started_seconds(conversation.get('started_at') or conversation.get('created_at'))
        if started_at_ts is None:
            chunk_starts = [
                min(af['chunk_timestamps']) for af in audio_files if isinstance(af, dict) and af.get('chunk_timestamps')
            ]
            started_at_ts = min(chunk_starts) if chunk_starts else 0.0

        try:
            with PLAYBACK_BUILD_SECONDS.labels('conversation').time() if demand else nullcontext():
                mp3_data, spans = await run_blocking(
                    sync_executor,
                    sync_playback.build_conversation_playback_artifact,
                    uid,
                    conversation_id,
                    audio_files,
                    started_at_ts,
                    **({'strict_sources': True} if demand else {}),
                )
        except FileNotFoundError:
            logger.warning(f'audio_merge: conversation chunks missing conv={conversation_id}, dropping')
            try:
                await run_blocking(
                    storage_executor,
                    mark_conversation_playback_unavailable,
                    uid,
                    conversation_id,
                    fingerprint,
                    'chunks_missing',
                )
            except DestructiveOperationInProgress:
                logger.info(
                    f'audio_merge: unavailable marker deferred reason=destructive_operation conv={conversation_id}'
                )
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'chunks_missing'})
        except Exception as e:
            if isinstance(e, DestructiveOperationInProgress):
                deferred = await _defer_merge_for_destructive_operation(payload)
                if deferred is not None:
                    return deferred
            max_attempts = get_sync_tasks_max_attempts()
            if task_retry_count >= max_attempts - 1:
                logger.error(f'audio_merge_failed_final conversation artifact conv={conversation_id}: {e}')
                try:
                    await run_blocking(
                        storage_executor,
                        mark_conversation_playback_unavailable,
                        uid,
                        conversation_id,
                        fingerprint,
                        'merge_failed',
                    )
                except DestructiveOperationInProgress:
                    logger.info(
                        f'audio_merge: unavailable marker deferred reason=destructive_operation conv={conversation_id}'
                    )
                return JSONResponse(status_code=200, content={'status': 'failed_final'})
            logger.warning(
                f'audio_merge: conversation attempt {task_retry_count + 1} failed conv={conversation_id}, will retry: {e}'
            )
            return JSONResponse(status_code=500, content={'status': 'retry'})

        try:
            await run_blocking(
                storage_executor,
                upload_conversation_playback_artifact,
                uid,
                conversation_id,
                mp3_data,
                **({'fingerprint': fingerprint} if demand else {}),
            )
        except Exception as e:
            if isinstance(e, DestructiveOperationInProgress):
                deferred = await _defer_merge_for_destructive_operation(payload)
                if deferred is not None:
                    return deferred
            # Same contract as the build: a destructive-operation fence on the
            # upload must retry (or mark unavailable on the final attempt)
            # instead of escaping as an unhandled legal_holds traceback. The
            # marker write is fenced too, so a second fence is logged and the
            # task still completes as failed_final.
            max_attempts = get_sync_tasks_max_attempts()
            if task_retry_count >= max_attempts - 1:
                logger.error(f'audio_merge_failed_final conversation artifact conv={conversation_id}: {e}')
                try:
                    await run_blocking(
                        storage_executor,
                        mark_conversation_playback_unavailable,
                        uid,
                        conversation_id,
                        fingerprint,
                        'merge_failed',
                    )
                except DestructiveOperationInProgress:
                    logger.info(
                        f'audio_merge: unavailable marker deferred reason=destructive_operation conv={conversation_id}'
                    )
                return JSONResponse(status_code=200, content={'status': 'failed_final'})
            logger.warning(
                f'audio_merge: conversation attempt {task_retry_count + 1} failed conv={conversation_id}, will retry: {e}'
            )
            return JSONResponse(status_code=500, content={'status': 'retry'})
        if demand:
            PLAYBACK_BUILDS.labels('conversation', 'built').inc()
        mp3_size = len(mp3_data)
        del mp3_data

        captured_duration = round(sum(s['len'] for s in spans), 3)
        wall_duration = round(spans[-1]['wall_offset'] + spans[-1]['len'], 3)
        await run_blocking(
            db_executor,
            conversations_db.update_conversation,
            uid,
            conversation_id,
            {
                'conversation_audio': {
                    'audio_files_fingerprint': fingerprint,
                    'duration': wall_duration,
                    'captured_duration': captured_duration,
                    'spans': spans,
                    'content_type': 'audio/mpeg',
                    'built_at': datetime.now(timezone.utc),
                }
            },
        )
        if demand:
            record_playback_ready(payload, 'conversation')
        logger.info(
            f'audio_merge: built conversation artifact conv={conversation_id} size={mp3_size} spans={len(spans)}'
        )
        return JSONResponse(status_code=200, content={'status': 'done'})
    finally:
        await run_blocking(db_executor, release_job_run_lock, lock_key, lock_token)


@router.post('/v2/cap-hold-recovery/sweep', include_in_schema=False)
@read_origin('job:cap_hold_recovery')
async def sweep_cap_hold_recovery(_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    return await cap_hold_redrive.sweep()
