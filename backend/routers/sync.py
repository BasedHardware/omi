import asyncio
import logging
import os
import shutil
import threading
import time
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, Request, Response, Header
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from database import conversations as conversations_db
from database import fair_use as fair_use_db
from database import users as users_db
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
    mark_job_queued_for_retry,
    sync_job_uses_ledger_fence,
    try_acquire_sync_job_run_lock,
    try_acquire_job_run_lock,
    release_job_run_lock,
)
from database.sync_ledger import (
    claim_sync_content,
    release_sync_content_claim,
    release_sync_content_claim_after_job_retired,
)
from models.conversation_enums import ConversationSource
from models.sync_audio import AudioPrecacheResponse, AudioUrlsResponse
from utils.analytics import record_usage
from utils.other import endpoints as auth
from utils.other.storage import (
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
    get_sync_tasks_max_attempts,
    is_cloud_tasks_dispatch_enabled,
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
    OMI_SYNC_LANE_JOBS_TOTAL,
    OMI_SYNC_QUEUE_WAIT_SECONDS,
    OMI_SYNC_RECORDING_AGE_SECONDS,
)
from utils.client_device import resolve_client_device, resolve_client_device_from_request
from utils.subscription import has_transcription_credits
from utils.sync import playback as sync_playback
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
    SyncJobRunLeaseLost,
    bind_or_converge_sync_ledger_completion,
    _finalize_sync_audio_files,
    _reprocess_merged_conversations,
    _retrieve_file_paths_v2,
    _run_full_pipeline_background_async,
    _stage_files_to_gcs,
    build_person_embeddings_cache,
    process_segment,
    retrieve_vad_segments,
)
from utils.stt.outcomes import TranscriptionOutcome, failure_from_exception
from utils.sync.rate_limit import (
    FAIR_USE_RATE_LIMIT_CODE,
    bounded_fair_use_retry_after,
    build_sync_rate_limit_event,
    emit_sync_rate_limit_event,
    fair_use_rate_limit_headers,
    validated_correlation_id,
)
from utils.sync.backfill import (
    release_backfill_slot,
    reserve_backfill_speech,
    retry_after_next_utc_day,
    try_acquire_backfill_slot,
)
from utils.sync.content_id import compute_sync_content_id
from utils.sync.capture_manifest import (
    claim_conversation_manifest,
    issue_capture_manifest,
    manifest_claims_match_paths,
    verify_capture_manifest,
)
from utils.sync.lanes import SyncLane, capture_times_within_window, classify_sync_lane

logger = logging.getLogger(__name__)

# Audio constants
AUDIO_SAMPLE_RATE = 16000

_V1_DEPRECATION_HEADERS = {'Deprecation': 'true', 'Link': '</v2/sync-local-files>; rel="successor-version"'}

router = APIRouter(route_class=MultipartMaxPartSizeRoute)

_CAPTURE_PROVENANCE_SLOP_SECONDS = 30 * 60


def _capture_matches_server_conversation(
    uid: str,
    conversation_id: Optional[str],
    filenames: List[str],
    client_device_id: Optional[str],
) -> bool:
    """Bind fresh classification to a server-created conversation time window."""
    if not conversation_id or not client_device_id:
        return False
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        return False
    if conversation.get('client_device_id') != client_device_id:
        return False
    started_at = conversation.get('started_at')
    finished_at = conversation.get('finished_at') or started_at
    if not isinstance(started_at, datetime) or not isinstance(finished_at, datetime):
        return False
    lower = started_at.timestamp() - _CAPTURE_PROVENANCE_SLOP_SECONDS
    upper = finished_at.timestamp() + _CAPTURE_PROVENANCE_SLOP_SECONDS
    return capture_times_within_window(filenames, lower, upper)


class SyncLocalFilesResultResponse(BaseModel):
    new_memories: list[str] = Field(default_factory=list)
    updated_memories: list[str] = Field(default_factory=list)
    failed_segments: int = 0
    total_segments: int = 0
    errors: list[str] = Field(default_factory=list)


class SyncJobStartResponse(BaseModel):
    job_id: str
    status: str
    total_files: int
    total_segments: int
    poll_after_ms: int
    lane: str = SyncLane.FRESH.value


class SyncJobStatusResponse(BaseModel):
    job_id: str
    status: str
    total_segments: int = 0
    processed_segments: int = 0
    successful_segments: int = 0
    failed_segments: int = 0
    result: SyncLocalFilesResultResponse | None = None
    error: str | None = None
    lane: str = SyncLane.FRESH.value
    reason_code: str | None = None
    retry_after: int | None = None
    recording_age_seconds: int | None = None


class SyncCaptureManifestFile(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    sha256: str = Field(pattern=r'^[0-9a-fA-F]{64}$')


class SyncCaptureManifestRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128)
    files: List[SyncCaptureManifestFile] = Field(min_length=1, max_length=20)


class SyncCaptureManifestResponse(BaseModel):
    manifest: str


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


def _retry_after_until_next_utc_day() -> int:
    now = datetime.now(timezone.utc)
    next_day = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((next_day - now).total_seconds()))


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

    return sync_playback.precache_audio_files(uid, conversation_id, conversation.get('audio_files', []))


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
    conversation = conversations_db.get_conversation(uid, conversation_id)
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
        if af.get('id') == audio_file_id:
            audio_file = af
            break

    if not audio_file:
        raise HTTPException(status_code=404, detail="Audio file not found in conversation")

    return sync_playback.download_audio_file_response(uid, conversation_id, audio_file_id, audio_file, request, format)


# **********************************************
# ************ SYNC LOCAL FILES ****************
# **********************************************


# response_model omitted: deprecated v1 endpoint with mixed dict + JSONResponse returns;
# the v2 typed equivalent (SyncJobStatusResponse) covers the contract.
@router.post("/v1/sync-local-files", deprecated=True)
@max_part_size(SYNC_AUDIO_MAX_PART_SIZE)
async def sync_local_files(
    request: Request,
    response: Response,
    files: List[UploadFile] = File(...),
    uid: str = Depends(auth.get_current_user_uid),
    conversation_id: str = Query(
        None, description="Target conversation ID to attach audio to (auto-sync from live capture)"
    ),
):
    if await run_blocking(db_executor, get_sync_ledger_fence_mode) is SyncLedgerFenceMode.STANDBY:
        return JSONResponse(
            status_code=503,
            headers={**_V1_DEPRECATION_HEADERS, 'Retry-After': '60'},
            content={
                'code': 'sync_ledger_fence_cutover',
                'detail': 'Sync is briefly pausing safely; local audio was not consumed',
            },
        )
    logger.warning(
        f'sync: deprecated v1 sync-local-files called uid={uid} files={len(files)} '
        f'user_agent={request.headers.get("user-agent", "")}'
    )
    response.headers.update(_V1_DEPRECATION_HEADERS)
    client_device_context = resolve_client_device_from_request(request)
    filenames = [f.filename or '' for f in files]
    has_server_capture_proof = False
    lane_decision = classify_sync_lane(
        filenames,
        client_device_id=client_device_context.client_device_id if has_server_capture_proof else None,
    )
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
            headers={
                **_V1_DEPRECATION_HEADERS,
                'Retry-After': '3600',
                'X-Omi-Rate-Limit-Reason': 'backfill_capacity',
            },
            content={
                'code': 'backfill_capacity',
                'detail': 'Historical recovery is paused; local audio was not consumed',
            },
        )
    if lane_decision.lane == SyncLane.BACKFILL:
        # The deprecated inline endpoint has no isolated worker boundary.
        # Historical audio must use v2 so it can never consume fresh capacity.
        return JSONResponse(
            status_code=503,
            headers={
                **_V1_DEPRECATION_HEADERS,
                'Retry-After': '30',
                'X-Omi-Rate-Limit-Reason': 'backfill_capacity',
            },
            content={
                'code': 'backfill_capacity',
                'detail': 'Historical recovery requires the v2 isolated worker; local audio was not consumed',
            },
        )
    if not lane_decision.automatic_recovery_allowed:
        return JSONResponse(
            status_code=422,
            headers=_V1_DEPRECATION_HEADERS,
            content={
                'code': 'backfill_lookback_exceeded',
                'detail': 'Recording is older than the automatic recovery window; local audio was not consumed',
            },
        )

    # Pre-check gates (#5854)
    hard_restricted, retry_after = get_hard_restriction_status(uid)
    if lane_decision.lane == SyncLane.FRESH and hard_restricted:
        return await _fair_use_restriction_response(
            uid=uid,
            retry_after=retry_after,
            client_platform=client_device_context.platform,
            device_hash=client_device_context.device_hash,
            app_version=client_device_context.app_version,
            request_id=request.headers.get('x-request-id'),
            cloud_trace_context=request.headers.get('x-cloud-trace-context'),
            base_headers=_V1_DEPRECATION_HEADERS,
        )

    # Hard anti-abuse daily-audio ceiling (all plans): reject fresh sync once the user is
    # already over the rolling-24h total. Set high enough that no legitimate user hits it;
    # it exists to stop bulk-sync dumps. Backfill has its own separate pacing.
    if lane_decision.lane == SyncLane.FRESH and is_daily_audio_ceiling_exceeded(uid):
        logger.info(f'sync: daily audio ceiling reached uid={uid}')
        return await _fair_use_restriction_response(
            uid=uid,
            retry_after=_retry_after_until_next_utc_day(),
            client_platform=client_device_context.platform,
            device_hash=client_device_context.device_hash,
            app_version=client_device_context.app_version,
            request_id=request.headers.get('x-request-id'),
            cloud_trace_context=request.headers.get('x-cloud-trace-context'),
            base_headers=_V1_DEPRECATION_HEADERS,
        )

    # Check credits: if exhausted, still process but lock the conversation so user can pay to unlock
    should_lock = not has_transcription_credits(uid)

    # Detect source from filenames
    source = detect_source_from_filenames([f.filename for f in files])

    paths = []
    wav_paths = []
    segmented_paths = set()
    backfill_slot_token: Optional[str] = None
    if lane_decision.lane == SyncLane.BACKFILL:
        backfill_slot_token = f'v1-{_uuid.uuid4()}'
        try:
            if not try_acquire_backfill_slot(uid, backfill_slot_token):
                return JSONResponse(
                    status_code=429,
                    headers={
                        **_V1_DEPRECATION_HEADERS,
                        'Retry-After': '30',
                        'X-Omi-Rate-Limit-Reason': 'backfill_paced',
                    },
                    content={'code': 'backfill_paced', 'detail': 'Another historical recovery job is in flight'},
                )
        except Exception:
            return JSONResponse(
                status_code=503,
                headers={
                    **_V1_DEPRECATION_HEADERS,
                    'Retry-After': '30',
                    'X-Omi-Rate-Limit-Reason': 'backfill_capacity',
                },
                content={'code': 'backfill_capacity', 'detail': 'Historical recovery is temporarily unavailable'},
            )

    try:
        try:
            paths = retrieve_file_paths(files, uid)
            wav_paths = decode_files_to_wav(paths)
        except HTTPException as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail, headers=_V1_DEPRECATION_HEADERS)

        vad_errors = []

        def _run_vad(path):
            retrieve_vad_segments(path, segmented_paths, vad_errors)

        await asyncio.gather(*[run_blocking(sync_executor, _run_vad, path) for path in wav_paths])

        # Clean up original wav files after VAD segmentation (segments are now in segmented_paths)
        _cleanup_files(wav_paths)
        wav_paths = []  # Clear to avoid double cleanup in finally

        # Check for VAD errors - if any failed, abort to prevent data loss
        if vad_errors:
            error_detail = f"VAD processing failed for {len(vad_errors)} file(s): {'; '.join(vad_errors[:3])}"
            if len(vad_errors) > 3:
                error_detail += f" (and {len(vad_errors) - 3} more)"
            raise HTTPException(status_code=500, detail=error_detail, headers=_V1_DEPRECATION_HEADERS)

        # Fair-use speech tracking from raw VAD segments (#5854)
        # Compute duration from raw segments BEFORE merging (silence gaps not counted)
        total_speech_seconds = sum(get_wav_duration(p) for p in segmented_paths)
        total_speech_ms = int(total_speech_seconds * 1000)
        logger.info(
            f'sync_local_files len(segmented_paths) {len(segmented_paths)} speech_seconds={int(total_speech_seconds)}'
        )

        if lane_decision.lane == SyncLane.BACKFILL:
            reservation = reserve_backfill_speech(uid, backfill_slot_token or f'v1-{_uuid.uuid4()}', total_speech_ms)
            if not reservation.allowed:
                return JSONResponse(
                    status_code=429,
                    headers={
                        **_V1_DEPRECATION_HEADERS,
                        'Retry-After': str(reservation.retry_after or retry_after_next_utc_day()),
                        'X-Omi-Rate-Limit-Reason': reservation.reason or 'backfill_paced',
                    },
                    content={
                        'code': reservation.reason or 'backfill_paced',
                        'detail': 'Historical recovery is paced; local audio should be retained',
                    },
                )

        if FAIR_USE_ENABLED and total_speech_ms > 0:
            meter_source = 'sync_backfill' if lane_decision.lane == SyncLane.BACKFILL else 'sync_fresh'
            record_speech_ms(uid, total_speech_ms, source=meter_source)
            if lane_decision.lane == SyncLane.FRESH:
                fair_use_sub = await run_blocking(db_executor, users_db.get_existing_user_subscription, uid)
                fair_use_plan = fair_use_sub.plan if fair_use_sub else None
                speech_totals = get_rolling_speech_ms(uid)
                triggered_caps = check_soft_caps(uid, speech_totals=speech_totals, plan=fair_use_plan)
                if triggered_caps:
                    logger.info(f'sync: soft caps triggered for {uid}: {triggered_caps}')
                    asyncio.create_task(trigger_classifier_if_needed(uid, triggered_caps))

        is_locked = should_lock

        response = {'updated_memories': set(), 'new_memories': set()}
        segment_errors = []
        segment_lock = threading.Lock()
        total_segments = len(segmented_paths)

        # DG budget gate: throttle cloud STT for restrict-stage users (#6083)
        # Check budget first; only record usage after successful processing.
        dg_budget_blocked = False
        fair_use_restrict_dg = False
        if FAIR_USE_ENABLED and lane_decision.lane == SyncLane.FRESH:
            try:
                fair_use_stage = get_enforcement_stage(uid)
                if fair_use_stage == 'restrict' and FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
                    fair_use_restrict_dg = True
                    dg_budget_blocked = is_dg_budget_exhausted(uid)
            except Exception as e:
                logger.error(f'sync: DG budget check error for {uid}: {e}')

        if dg_budget_blocked:
            logger.info(f'sync: DG budget exhausted, skipping {total_segments} segments uid={uid}')
            _cleanup_files(list(segmented_paths))
            return await _fair_use_restriction_response(
                uid=uid,
                retry_after=_retry_after_until_next_utc_day(),
                client_platform=client_device_context.platform,
                device_hash=client_device_context.device_hash,
                app_version=client_device_context.app_version,
                request_id=request.headers.get('x-request-id'),
                cloud_trace_context=request.headers.get('x-cloud-trace-context'),
                base_headers=_V1_DEPRECATION_HEADERS,
                extra_content={
                    'new_memories': [],
                    'updated_memories': [],
                    'credits_exhausted': should_lock,
                    'dg_budget_exhausted': True,
                    'skipped_segments': total_segments,
                },
            )

        # Fetch user transcription preferences once before spawning threads
        transcription_prefs = await run_blocking(db_executor, users_db.get_user_transcription_preferences, uid)
        private_cloud_sync_enabled = bool(
            await run_blocking(db_executor, users_db.get_user_private_cloud_sync_enabled, uid)
        )
        data_protection_level = (
            await run_blocking(db_executor, users_db.get_data_protection_level, uid)
            if private_cloud_sync_enabled
            else None
        )

        # Build speaker embeddings cache once for all segments (voice + text identification)
        try:
            person_embeddings_cache = await run_blocking(db_executor, build_person_embeddings_cache, uid)
            if person_embeddings_cache:
                logger.info(f'sync: loaded {len(person_embeddings_cache)} person embeddings for speaker ID uid={uid}')
        except Exception as e:
            logger.warning(f'sync: failed to load person embeddings, skipping speaker ID uid={uid}: {e}')
            person_embeddings_cache = {}

        # Chronological order + turnstile: STT runs in parallel, but conversation
        # assignment is serialized oldest-first so adjacent chunks merge instead of
        # racing into separate conversations (#6551, #5747).
        ordered_paths = sorted(segmented_paths, key=get_timestamp_from_path)
        assignment_turnstile = _OrderedTurnstile(ordered_paths)
        await asyncio.gather(
            *[
                run_blocking(
                    sync_executor,
                    process_segment,
                    path,
                    uid,
                    response,
                    segment_lock,
                    segment_errors,
                    source,
                    is_locked,
                    transcription_prefs,
                    person_embeddings_cache,
                    conversation_id,
                    assignment_turnstile,
                    private_cloud_sync_enabled=private_cloud_sync_enabled,
                    data_protection_level=data_protection_level,
                    client_device_id=client_device_context.client_device_id,
                    client_platform=client_device_context.platform,
                )
                for path in ordered_paths
            ]
        )

        await run_blocking(sync_executor, _reprocess_merged_conversations, uid, response)
        if private_cloud_sync_enabled:
            await run_blocking(sync_executor, _finalize_sync_audio_files, uid, response)

        # Record DG usage after successful processing (not before, to avoid charging on retries)
        if fair_use_restrict_dg:
            try:
                dg_ms = int(total_speech_seconds * 1000)
                if dg_ms > 0:
                    record_dg_usage_ms(uid, dg_ms)
            except Exception as e:
                logger.error(f'sync: DG usage record error for {uid}: {e}')

        # Build JSON-serializable response
        result = {
            'new_memories': sorted(response['new_memories']),
            'updated_memories': sorted(response['updated_memories']),
        }

        failed_segments = len(segment_errors)
        successful_segments = total_segments - failed_segments

        if failed_segments > 0:
            result['failed_segments'] = failed_segments
            result['total_segments'] = total_segments
            result['errors'] = segment_errors[:10]  # Cap error details to avoid huge responses
            logger.error(
                f'sync_local_files partial failure uid={uid} '
                f'success={successful_segments}/{total_segments} errors={segment_errors[:3]}'
            )

        if total_segments > 0 and successful_segments == 0:
            # All segments failed — return 500 (consistent with VAD error behavior)
            raise HTTPException(
                status_code=500,
                detail=f"All {total_segments} segment(s) failed processing: {'; '.join(segment_errors[:3])}",
                headers=_V1_DEPRECATION_HEADERS,
            )

        # Record subscription usage only when at least one segment succeeded
        try:
            usage_seconds = int(total_speech_seconds)
            if usage_seconds > 0:
                record_usage(uid, transcription_seconds=usage_seconds, speech_seconds=usage_seconds)
        except Exception as e:
            logger.error(f'sync: usage record error for {uid}: {e}')

        if failed_segments > 0:
            # Partial failure — return 207 Multi-Status so old clients retry the batch
            return JSONResponse(
                status_code=207,
                headers=_V1_DEPRECATION_HEADERS,
                content=result,
            )

        return result
    finally:
        # Clean up any remaining temporary files
        _cleanup_files(paths)  # .bin files (in case decode_files_to_wav didn't finish)
        _cleanup_files(wav_paths)  # Original wav files (if VAD didn't complete)
        _cleanup_files(segmented_paths)  # Segmented wav files after processing
        if backfill_slot_token:
            try:
                release_backfill_slot(uid, backfill_slot_token)
            except Exception as e:
                logger.warning('sync: failed to release v1 backfill slot uid=%s error=%s', uid, type(e).__name__)


# ---------------------------------------------------------------------------
# v2 async sync-local-files
# ---------------------------------------------------------------------------
# v1 processes segments synchronously (80-180s for large payloads → 504).
# v2 returns 202 immediately after saving raw files, then runs the full
# pipeline (decode → VAD → fair-use → STT → LLM) in a background thread.
# The app polls GET /v2/sync-local-files/{job_id} until the job reaches
# a terminal status.
# ---------------------------------------------------------------------------


@router.post("/v2/sync-local-files", status_code=202, response_model=SyncJobStartResponse)
@max_part_size(SYNC_AUDIO_MAX_PART_SIZE)
async def sync_local_files_v2(
    files: List[UploadFile] = File(...),
    uid: str = Depends(auth.get_current_user_uid),
    conversation_id: str = Query(
        None, description="Target conversation ID to attach audio to (auto-sync from live capture)"
    ),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
    x_device_id_hash: Optional[str] = Header(None, alias='X-Device-Id-Hash'),
    x_app_version: Optional[str] = Header(None, alias='X-App-Version'),
    x_request_id: Optional[str] = Header(None, alias='X-Request-ID'),
    x_cloud_trace_context: Optional[str] = Header(None, alias='X-Cloud-Trace-Context'),
    x_omi_sync_capture_manifest: Optional[str] = Header(None, alias='X-Omi-Sync-Capture-Manifest'),
):
    """
    Async version of sync-local-files. Saves raw files and returns 202
    immediately, then runs the full pipeline (decode → VAD → STT → LLM) as
    an async background task. The app polls GET /v2/sync-local-files/{job_id}.
    """
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
    ledger_fence_active = ledger_fence_mode is SyncLedgerFenceMode.ACTIVE

    # Browser/mobile clients carry capture provenance in these request headers.
    # It must survive both the inline and Cloud Tasks pipeline branches.
    client_device_context = resolve_client_device(
        x_app_platform=x_app_platform if isinstance(x_app_platform, str) else None,
        x_device_id_hash=x_device_id_hash if isinstance(x_device_id_hash, str) else None,
        x_app_version=x_app_version if isinstance(x_app_version, str) else None,
    )

    filenames = [f.filename or '' for f in files]
    manifest_claims = verify_capture_manifest(
        x_omi_sync_capture_manifest,
        uid,
        client_device_context.client_device_id,
        conversation_id,
        filenames,
    )
    has_server_capture_proof = manifest_claims is not None and await run_blocking(
        db_executor,
        _capture_matches_server_conversation,
        uid,
        conversation_id,
        filenames,
        client_device_context.client_device_id,
    )
    lane_decision = classify_sync_lane(
        filenames,
        client_device_id=client_device_context.client_device_id if has_server_capture_proof else None,
    )
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

    # Live restrictions apply only to the realtime/fresh domain. Historical
    # recovery has independent admission and spend caps below.
    if lane_decision.lane == SyncLane.FRESH:
        hard_restricted, retry_after = await run_blocking(critical_executor, get_hard_restriction_status, uid)
        if hard_restricted:
            return await _fair_use_restriction_response(
                uid=uid,
                retry_after=retry_after,
                client_platform=client_device_context.platform,
                device_hash=client_device_context.device_hash,
                app_version=client_device_context.app_version,
                request_id=x_request_id if isinstance(x_request_id, str) else None,
                cloud_trace_context=x_cloud_trace_context if isinstance(x_cloud_trace_context, str) else None,
            )

    should_lock = not await run_blocking(critical_executor, has_transcription_credits, uid)

    # Detect source
    source = detect_source_from_filenames([f.filename for f in files])

    cloud_tasks_dispatch_enabled = is_cloud_tasks_dispatch_enabled()
    byok_enabled = has_byok_keys()
    cloud_task_eligible = cloud_tasks_dispatch_enabled and not byok_enabled

    # Create job_id early so we have it for the directory
    job_id = str(_uuid.uuid4())
    job_dir = f'syncing/{uid}/{job_id}'

    backfill_slot_acquired = False
    if lane_decision.lane == SyncLane.BACKFILL:
        try:
            backfill_slot_acquired = await run_blocking(db_executor, try_acquire_backfill_slot, uid, job_id)
        except Exception as e:
            logger.error('sync_v2: backfill admission unavailable uid=%s error=%s', uid, type(e).__name__)
            return JSONResponse(
                status_code=503,
                headers={'Retry-After': '30', 'X-Omi-Rate-Limit-Reason': 'backfill_capacity'},
                content={'code': 'backfill_capacity', 'detail': 'Historical recovery is temporarily unavailable'},
            )
        if not backfill_slot_acquired:
            try:
                OMI_SYNC_LANE_JOBS_TOTAL.labels(
                    lane=lane_decision.lane.value,
                    trust=lane_decision.trust.value,
                    outcome='paced',
                ).inc()
            except Exception:
                pass
            return JSONResponse(
                status_code=429,
                headers={'Retry-After': '30', 'X-Omi-Rate-Limit-Reason': 'backfill_paced'},
                content={'code': 'backfill_paced', 'detail': 'Another historical recovery job is still in flight'},
            )

    paths = []
    content_id: Optional[str] = None

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

        content_id = await run_blocking(sync_executor, compute_sync_content_id, uid, paths)

        # Create Redis job — total_segments=0 until VAD completes in background
        await run_blocking(
            db_executor,
            create_sync_job,
            uid,
            total_files=len(files),
            total_segments=0,
            job_id=job_id,
            lane=lane_decision.lane.value,
            capture_time_trust=lane_decision.trust.value,
            recording_age_seconds=lane_decision.maximum_age_seconds,
            content_id=content_id,
            # A named enqueue can lose its acknowledgement after Cloud Tasks
            # accepts it. Mark eligible jobs as Cloud Tasks-owned before that
            # call so the ambiguity never starts an unfenced inline twin.
            dispatch_mode='cloud_tasks' if cloud_task_eligible else 'inline',
            ledger_fence_mode=(
                SyncLedgerFenceMode.ACTIVE.value if ledger_fence_active else SyncLedgerFenceMode.LEGACY.value
            ),
        )
        claim = await run_blocking(
            db_executor,
            claim_sync_content,
            uid,
            content_id,
            job_id,
            lane_decision.lane.value,
        )
        if claim.get('outcome') == 'completed':
            cached_result = claim.get('result') or {}
            await run_blocking(db_executor, mark_job_completed, job_id, cached_result)
            if backfill_slot_acquired:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
                backfill_slot_acquired = False
            return JSONResponse(
                status_code=202,
                content={
                    'job_id': job_id,
                    'status': 'completed',
                    'total_files': len(files),
                    'total_segments': cached_result.get('total_segments', 0),
                    'poll_after_ms': 0,
                    'lane': lane_decision.lane.value,
                },
            )
        if claim.get('outcome') == 'busy':
            await run_blocking(db_executor, delete_sync_job, job_id)
            if backfill_slot_acquired:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
                backfill_slot_acquired = False
            return JSONResponse(
                status_code=409,
                headers={'Retry-After': '10'},
                content={'code': 'sync_content_in_progress', 'detail': 'The same audio is already processing'},
            )
        try:
            OMI_SYNC_LANE_JOBS_TOTAL.labels(
                lane=lane_decision.lane.value,
                trust=lane_decision.trust.value,
                outcome='admitted',
            ).inc()
        except Exception:
            pass

        # Transfer ownership of raw paths to the background task
        owned_paths = list(paths)
        paths = []  # Prevent finally cleanup of files now owned by bg task

        if lane_decision.lane == SyncLane.BACKFILL and not cloud_task_eligible:
            # Fail closed: backfill may run only on the dedicated queue/service.
            # BYOK cannot be serialized into Cloud Tasks, so it is retained on
            # device until an isolated BYOK path exists.
            await run_blocking(sync_executor, _cleanup_files, owned_paths)
            await _finalize_sync_job_failure(
                job_id=job_id,
                uid=uid,
                content_id=content_id,
                error_code='sync_backfill_dispatch_unavailable',
                outcome=TranscriptionOutcome.CONFIG_ERROR,
                provider='unknown',
                model='unknown',
                lane=lane_decision.lane.value,
            )
            await run_blocking(db_executor, release_backfill_slot, uid, job_id)
            backfill_slot_acquired = False
            return JSONResponse(
                status_code=503,
                headers={'Retry-After': '30', 'X-Omi-Rate-Limit-Reason': 'backfill_capacity'},
                content={
                    'code': 'backfill_capacity',
                    'detail': 'Historical recovery is temporarily unavailable; local audio was not consumed',
                },
            )

        dispatched = False
        # Fresh BYOK requests retain the legacy inline path. Backfill was
        # rejected above because it may never consume fresh capacity.
        if cloud_task_eligible:
            try:
                # sync_executor, NOT storage_executor — same reasoning as the
                # file save above (#7372): a saturated storage pool would queue
                # the staging upload and delay the 202.
                await run_blocking(sync_executor, _stage_files_to_gcs, owned_paths)
            except Exception as e:
                logger.error(
                    'event=sync_dispatch outcome=staging_failed lane=%s exception_type=%s',
                    lane_decision.lane.value,
                    type(e).__name__,
                )
                # Staging failed before any task was submitted, so it is safe
                # to remove partial blobs, terminalize, and free the claim for
                # a client WAL retry.
                await _delete_staged_blobs_async(owned_paths)
                await run_blocking(sync_executor, _cleanup_files, owned_paths)
                await _finalize_sync_job_failure(
                    job_id=job_id,
                    uid=uid,
                    content_id=content_id,
                    error_code='sync_dispatch_staging_failed',
                    outcome=TranscriptionOutcome.UPSTREAM_ERROR,
                    provider='unknown',
                    model='unknown',
                    lane=lane_decision.lane.value,
                )
                if backfill_slot_acquired:
                    await run_blocking(db_executor, release_backfill_slot, uid, job_id)
                    backfill_slot_acquired = False
                return JSONResponse(
                    status_code=503,
                    headers={'Retry-After': '30'},
                    content={
                        'code': 'sync_dispatch_unavailable',
                        'detail': 'Sync dispatch is temporarily unavailable; local audio was not consumed',
                    },
                )

            enqueue_payload = {
                'schema_version': 1,
                'job_id': job_id,
                'uid': uid,
                'raw_blob_paths': owned_paths,
                'source': source.value,
                'should_lock': should_lock,
                'conversation_id': conversation_id,
                'client_device_id': client_device_context.client_device_id,
                'client_platform': client_device_context.platform,
                'enqueued_at': time.time(),
                'lane': lane_decision.lane.value,
                'capture_time_trust': lane_decision.trust.value,
                'recording_age_seconds': lane_decision.maximum_age_seconds,
                'content_id': content_id,
                'ledger_fence_mode': (
                    SyncLedgerFenceMode.ACTIVE.value if ledger_fence_active else SyncLedgerFenceMode.LEGACY.value
                ),
            }
            enqueue_error = None
            for enqueue_attempt in range(2):
                try:
                    await run_blocking(db_executor, enqueue_sync_job, enqueue_payload)
                    dispatched = True
                    break
                except Exception as e:
                    enqueue_error = e

            if dispatched:
                try:
                    OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL.labels(mode='cloud_tasks').inc()
                except Exception:
                    pass
            else:
                # A lost Cloud Tasks acknowledgement is ambiguous: the named
                # task may already exist and can be executing. Preserve every
                # durable worker input and claim, and never start inline work.
                logger.error(
                    'event=sync_dispatch outcome=enqueue_uncertain lane=%s enqueue_attempts=2 exception_type=%s',
                    lane_decision.lane.value,
                    type(enqueue_error).__name__ if enqueue_error is not None else 'Exception',
                )
                try:
                    OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL.labels(mode='enqueue_uncertain').inc()
                except Exception:
                    pass
                try:
                    await run_blocking(sync_executor, _cleanup_files, owned_paths)
                    await run_blocking(sync_executor, shutil.rmtree, job_dir, True)
                except Exception as e:
                    logger.error(
                        'event=sync_post_enqueue_cleanup outcome=failed exception_type=%s',
                        type(e).__name__,
                    )
                return JSONResponse(
                    status_code=202,
                    content={
                        'job_id': job_id,
                        'status': 'queued',
                        'total_files': len(files),
                        'total_segments': 0,
                        'poll_after_ms': 3000,
                        'lane': lane_decision.lane.value,
                    },
                )

            if dispatched:
                try:
                    # The handler instance downloads from GCS; local copies are done
                    await run_blocking(sync_executor, _cleanup_files, owned_paths)
                    await run_blocking(sync_executor, shutil.rmtree, job_dir, True)
                except Exception as e:
                    logger.error(
                        'event=sync_post_enqueue_cleanup outcome=failed exception_type=%s',
                        type(e).__name__,
                    )

        if not dispatched:
            if not cloud_tasks_dispatch_enabled:
                record_fallback(
                    component='sync_dispatch',
                    from_mode='cloud_tasks',
                    to_mode='inline',
                    reason='dispatch_disabled',
                    outcome='recovered',
                )
                try:
                    OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL.labels(mode='inline').inc()
                except Exception:
                    pass
            elif byok_enabled:
                record_fallback(
                    component='sync_dispatch',
                    from_mode='cloud_tasks',
                    to_mode='inline',
                    reason='byok',
                    outcome='recovered',
                )
                try:
                    OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL.labels(mode='inline').inc()
                except Exception:
                    pass

            # Inline work needs the same lease as Cloud Tasks. Without it, a
            # long healthy inline worker looks stale to a polling client and its
            # durable retry claim can be released underneath it.
            acquire_inline_lock = try_acquire_sync_job_run_lock if ledger_fence_active else try_acquire_job_run_lock
            inline_run_lock_token = await run_blocking(db_executor, acquire_inline_lock, job_id)
            if inline_run_lock_token:
                converged = None
                can_start = True
                if ledger_fence_active:
                    try:
                        converged = await run_blocking(
                            db_executor,
                            bind_or_converge_sync_ledger_completion,
                            job_id=job_id,
                            uid=uid,
                            content_id=content_id,
                            run_lock_token=inline_run_lock_token,
                        )
                    except SyncJobRunLeaseLost:
                        # A higher epoch is now the durable owner. Drop our
                        # unused Redis lease so the winner is not blocked for
                        # the full lock TTL, and keep local material for retry.
                        can_start = False
                        logger.warning('event=sync_inline outcome=ledger_lease_lost')
                        try:
                            await run_blocking(db_executor, release_job_run_lock, job_id, inline_run_lock_token)
                        except Exception:
                            pass
                        inline_run_lock_token = None
                if can_start:
                    if converged is not None:
                        await run_blocking(sync_executor, _cleanup_files, owned_paths)
                        await run_blocking(sync_executor, shutil.rmtree, job_dir, True)
                        await run_blocking(db_executor, release_job_run_lock, job_id, inline_run_lock_token)
                        return JSONResponse(
                            status_code=202,
                            content={
                                'job_id': job_id,
                                'status': 'completed',
                                'total_files': len(files),
                                'total_segments': converged.get('total_segments', 0),
                                'poll_after_ms': 0,
                                'lane': lane_decision.lane.value,
                            },
                        )
                    # Async coordinator: runs on event loop, offloads blocking work to pools.
                    # No thread pool slot held for the full pipeline duration (fixes #7361).
                    start_background_task(
                        _run_full_pipeline_background_async(
                            job_id,
                            uid,
                            owned_paths,
                            source,
                            should_lock,
                            job_dir,
                            conversation_id,
                            client_device_id=client_device_context.client_device_id,
                            client_platform=client_device_context.platform,
                            sync_lane=lane_decision.lane.value,
                            content_id=content_id,
                            run_lock_token=inline_run_lock_token if ledger_fence_active else None,
                            inline_run_lock_token=inline_run_lock_token,
                            content_run_bound=ledger_fence_active,
                            ledger_fence_active=ledger_fence_active,
                        ),
                        name=f'sync_pipeline:{job_id}',
                    )
            else:
                logger.warning('event=sync_inline outcome=lease_unavailable')

        return JSONResponse(
            status_code=202,
            content={
                'job_id': job_id,
                'status': 'queued',
                'total_files': len(files),
                'total_segments': 0,
                'poll_after_ms': 3000,
                'lane': lane_decision.lane.value,
            },
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
        if content_id:
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


@router.get("/v2/sync-local-files/{job_id}", response_model=SyncJobStatusResponse, response_model_exclude_none=True)
def get_sync_job_status(job_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Poll for the status of an async sync job."""
    job = get_sync_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found or expired")
    if job['uid'] != uid:
        raise HTTPException(status_code=403, detail="Not authorized to view this sync job")

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
                            error_code='sync_worker_stale',
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
                # A newer epoch owns the durable ledger. Polling is a
                # read-side recovery path, so it must leave that owner's
                # retry material and Redis state untouched rather than turn
                # the ownership handoff into a client-visible 500.
                logger.warning('event=sync_stale_finalize outcome=lease_lost retry_material=preserved')
            finally:
                release_job_run_lock(job_id, stale_lock_token)

    if (
        job.get('status') in ('failed', 'partial_failure')
        and sync_job_uses_ledger_fence(job)
        and isinstance(job.get('content_id'), str)
    ):
        # A fenced terminal write can land before its exact-job ledger release
        # transiently fails (notably for inline/stale recovery, which has no
        # Cloud Tasks duplicate delivery). Do not expose an ACKable terminal
        # result until the retry claim is recoverable again: otherwise a WAL
        # re-upload receives ``busy`` for the ledger stale window and looks
        # permanently stuck to the client.
        try:
            release_sync_content_claim_after_job_retired(uid, job['content_id'], job_id)
        except Exception as error:
            logger.error(
                'event=sync_terminal_cleanup outcome=retrying exception_type=%s',
                type(error).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail='Sync recovery finalization is retrying; local audio remains available.',
                headers={'Retry-After': '10'},
            )
        # Retaining an epoch counter after the durable claim is recoverable is
        # safe; never keep a client WAL pending solely for that optimization.
        delete_sync_job_run_lock_epoch(job_id)

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

    return resp


# response_model omitted: include_in_schema=False Cloud Tasks handler; JSONResponse status
# codes (200/409/500) drive the queue protocol, not a typed client-facing body.
@router.post("/v2/sync-jobs/run", include_in_schema=False)
async def run_sync_job(request: Request, task_retry_count: int = Depends(verify_cloud_tasks_oidc)):
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
        client_device_id = payload.get('client_device_id')
        client_platform = payload.get('client_platform')
        sync_lane = payload.get('lane') if payload.get('lane') in ('fresh', 'backfill') else SyncLane.FRESH.value
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
            await _delete_staged_blobs_async(blob_paths)
            if sync_lane == SyncLane.BACKFILL.value:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
            if content_id and job['status'] in ('failed', 'partial_failure'):
                release_claim = (
                    release_sync_content_claim_after_job_retired if ledger_fence_active else release_sync_content_claim
                )
                await run_blocking(db_executor, release_claim, uid, content_id, job_id)
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
        if converged is not None:
            await _delete_staged_blobs_async(blob_paths)
            if sync_lane == SyncLane.BACKFILL.value:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
            return JSONResponse(status_code=200, content={'status': 'done', 'reconciled': True})

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
            await _run_full_pipeline_background_async(
                job_id,
                uid,
                blob_paths,
                source,
                should_lock,
                job_dir,
                conversation_id,
                task_mode=True,
                client_device_id=client_device_id,
                client_platform=client_platform,
                sync_lane=sync_lane,
                content_id=content_id,
                run_lock_token=lock_token if ledger_fence_active else None,
                content_run_bound=ledger_fence_active,
                ledger_fence_active=ledger_fence_active,
            )
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
            failure = failure_from_exception(e, provider=latest_job.get('stt_provider'))
            sync_model = latest_job.get('stt_model')
            if task_retry_count >= max_attempts - 1:
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


# response_model omitted: include_in_schema=False Cloud Tasks handler; JSONResponse status
# codes (200/409/500) drive the queue protocol, not a typed client-facing body.
@router.post("/v2/audio-merge-jobs/run", include_in_schema=False)
async def run_audio_merge_job(request: Request, task_retry_count: int = Depends(verify_cloud_tasks_oidc)):
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
    if schema_version == 2:
        return await _run_conversation_merge_job(payload, task_retry_count)

    lock_key = f'audio:{conversation_id}:{audio_file_id}'
    lock_token = await run_blocking(db_executor, try_acquire_job_run_lock, lock_key)
    if not lock_token:
        return JSONResponse(status_code=409, content={'status': 'locked'})

    try:
        existing = await run_blocking(
            storage_executor, get_playback_artifact_signed_url, uid, conversation_id, audio_file_id
        )
        if existing:
            return JSONResponse(status_code=200, content={'status': 'exists'})

        try:
            mp3_data = await run_blocking(
                sync_executor, sync_playback.build_playback_artifact, uid, conversation_id, timestamps
            )
        except FileNotFoundError:
            logger.warning(f'audio_merge: chunks missing conv={conversation_id} file={audio_file_id}, dropping')
            # Persist the verdict or /urls reports pending forever and clients
            # poll to exhaustion (named-task tombstones block re-enqueues too)
            await run_blocking(
                storage_executor, mark_playback_unavailable, uid, conversation_id, audio_file_id, 'chunks_missing'
            )
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'chunks_missing'})
        except Exception as e:
            max_attempts = get_sync_tasks_max_attempts()
            if task_retry_count >= max_attempts - 1:
                logger.error(f'audio_merge_failed_final conv={conversation_id} file={audio_file_id}: {e}')
                # Same pending-forever trap as chunks_missing: a consumed task
                # leaves a tombstone that blocks re-enqueue. Mark unavailable so
                # clients stop polling; the 30-day lifecycle grants a retry.
                await run_blocking(
                    storage_executor, mark_playback_unavailable, uid, conversation_id, audio_file_id, 'merge_failed'
                )
                return JSONResponse(status_code=200, content={'status': 'failed_final'})
            logger.warning(
                f'audio_merge: attempt {task_retry_count + 1} failed conv={conversation_id} '
                f'file={audio_file_id}, will retry: {e}'
            )
            return JSONResponse(status_code=500, content={'status': 'retry'})

        if not mp3_data:
            logger.warning(f'audio_merge: no audio data conv={conversation_id} file={audio_file_id}, dropping')
            await run_blocking(
                storage_executor, mark_playback_unavailable, uid, conversation_id, audio_file_id, 'empty_audio'
            )
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'empty_audio'})

        await run_blocking(storage_executor, upload_playback_artifact, uid, conversation_id, audio_file_id, mp3_data)
        logger.info(f'audio_merge: built artifact conv={conversation_id} file={audio_file_id} size={len(mp3_data)}')
        return JSONResponse(status_code=200, content={'status': 'done'})
    finally:
        await run_blocking(db_executor, release_job_run_lock, lock_key, lock_token)


async def _run_conversation_merge_job(payload: dict, task_retry_count: int):
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
    except Exception as e:
        logger.error(f'audio_merge handler: invalid v2 payload, dropping task: {e}')
        return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'invalid_payload'})

    lock_key = f'audio:{conversation_id}:conversation'
    lock_token = await run_blocking(db_executor, try_acquire_job_run_lock, lock_key)
    if not lock_token:
        return JSONResponse(status_code=409, content={'status': 'locked'})

    try:
        conversation = await run_blocking(db_executor, conversations_db.get_conversation, uid, conversation_id)
        if not conversation or not conversation.get('audio_files'):
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'no_audio_files'})
        audio_files = conversation['audio_files']
        fingerprint = compute_audio_files_fingerprint(audio_files)
        if payload_fingerprint and payload_fingerprint != fingerprint:
            return JSONResponse(status_code=200, content={'status': 'superseded'})

        stamp = conversation.get('conversation_audio') or {}
        if stamp.get('audio_files_fingerprint') == fingerprint:
            existing = await run_blocking(storage_executor, get_conversation_playback_signed_url, uid, conversation_id)
            if existing:
                return JSONResponse(status_code=200, content={'status': 'exists'})

        started_at = conversation.get('started_at') or conversation.get('created_at')
        started_at_ts = started_at.timestamp()

        try:
            mp3_data, spans = await run_blocking(
                sync_executor,
                sync_playback.build_conversation_playback_artifact,
                uid,
                conversation_id,
                audio_files,
                started_at_ts,
            )
        except FileNotFoundError:
            logger.warning(f'audio_merge: conversation chunks missing conv={conversation_id}, dropping')
            await run_blocking(
                storage_executor,
                mark_conversation_playback_unavailable,
                uid,
                conversation_id,
                fingerprint,
                'chunks_missing',
            )
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'chunks_missing'})
        except Exception as e:
            max_attempts = get_sync_tasks_max_attempts()
            if task_retry_count >= max_attempts - 1:
                logger.error(f'audio_merge_failed_final conversation artifact conv={conversation_id}: {e}')
                await run_blocking(
                    storage_executor,
                    mark_conversation_playback_unavailable,
                    uid,
                    conversation_id,
                    fingerprint,
                    'merge_failed',
                )
                return JSONResponse(status_code=200, content={'status': 'failed_final'})
            logger.warning(
                f'audio_merge: conversation attempt {task_retry_count + 1} failed conv={conversation_id}, will retry: {e}'
            )
            return JSONResponse(status_code=500, content={'status': 'retry'})

        await run_blocking(storage_executor, upload_conversation_playback_artifact, uid, conversation_id, mp3_data)
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
        logger.info(
            f'audio_merge: built conversation artifact conv={conversation_id} size={mp3_size} spans={len(spans)}'
        )
        return JSONResponse(status_code=200, content={'status': 'done'})
    finally:
        await run_blocking(db_executor, release_job_run_lock, lock_key, lock_token)
