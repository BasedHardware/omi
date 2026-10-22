from database import sync_redrive
from utils.sync import minimal_redrive, redrive_policy, playback_build
from utils.capture.coverage_endpoint import router as coverage_router
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
from config.policy import resolve_batch_policy
from config.policy.ramp import audio_span
from database.batch_ramp import ramp_admission_policy
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
    RUN_LOCK_TTL_SECONDS,
    QUEUED_DISPATCH_STALE_SECONDS,
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
    release_job_run_lock_strict,
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
from utils.sync.admission_responses import sync_content_in_progress_response, sync_finalization_retrying
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
    mark_conversation_playback_unavailable,
)
from utils.byok import has_byok_keys
from google.api_core import exceptions as google_api_exceptions
from utils.cloud_tasks import (
    DISPATCH_DEADLINE_SECONDS,
    enqueue_sync_job,
    enqueue_sync_job_budget_replacement,
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
from utils.sync.retired_handle_ack import acknowledge_retired_handle
from config.repeat_work import playback_on_demand
from contextlib import nullcontext
from utils.sync.repeat_work_metrics import (
    PLAYBACK_WRITES,
    PLAYBACK_BUILD_SECONDS,
    PLAYBACK_BUILDS,
    record_playback_ready,
)
from utils.product_metrics import record_product_event, sanitize_app_build
from utils.journey_metrics_contract import resolve_client_kind
from utils.client_device import resolve_client_device, resolve_client_device_from_request
from utils.subscription import (
    TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS,
    has_transcription_credits,
    resolve_transcription_allowance,
)
from utils.sync import playback as sync_playback
from utils.sync.input_limits import BackfillInputLimitExceeded, BackfillStoragePressure, validate_backfill_uploads
from config.rollout_cohorts import warm_rollout_cohorts
from utils.sync.recording_lineage import parse_s1_upload_claims
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
from utils.sync.failure_reason import stamped_failure_kwargs
from utils.sync.capture_manifest import (
    claim_conversation_manifest,
    issue_capture_manifest,
    manifest_claims_match_paths,
    verify_capture_manifest,
)
from utils.sync.lanes import CaptureTimeTrust, SyncLane, classify_sync_lane
from utils.sync import backfill_cutover, legacy_dark, legacy_fresh, stage as sync_stage, uid_sequencer
from config.sync_owner_concurrency import preparation_width
from utils.sync.owner_prefetch import warm_owner
from utils.sync.provenance import capture_matches_server_conversation as _capture_matches_server_conversation

from utils.sync import cap_hold_redrive

logger = logging.getLogger(__name__)

# Audio constants
AUDIO_SAMPLE_RATE = 16000

_V1_DEPRECATION_HEADERS = {'Deprecation': 'true', 'Link': '</v2/sync-local-files>; rel="successor-version"'}


async def _offer_shadow_upload(**kwargs) -> None:
    # The shadow is best effort: its import or handoff must never fail a legacy upload.
    try:
        from utils.batch_pipeline.shadow_intake import offer_upload

        await offer_upload(**kwargs)
    except Exception as error:
        logger.info('event=batch_shadow_intake outcome=error exception_type=%s', type(error).__name__)


router = APIRouter(route_class=MultipartMaxPartSizeRoute, dependencies=[Depends(sync_stage.require_http_stage)])
router.include_router(coverage_router)


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
    if not conversation or conversation.get('deleted', False):
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
    if not conversation or conversation.get('deleted', False):
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
    if not conversation or conversation.get('deleted', False):
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
    hard_restricted, retry_after = await run_blocking(critical_executor, get_hard_restriction_status, uid)
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
    if lane_decision.lane == SyncLane.FRESH and await run_blocking(db_executor, is_daily_audio_ceiling_exceeded, uid):
        logger.info(f'sync: daily audio ceiling reached uid={uid}')
        return await _fair_use_restriction_response(
            uid=uid,
            retry_after=retry_after_until_next_utc_day(),
            client_platform=client_device_context.platform,
            device_hash=client_device_context.device_hash,
            app_version=client_device_context.app_version,
            request_id=request.headers.get('x-request-id'),
            cloud_trace_context=request.headers.get('x-cloud-trace-context'),
            base_headers=_V1_DEPRECATION_HEADERS,
        )

    # Legacy exhaustion retains the installed-client path below.

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

    # Detect source from filenames
    source = detect_source_from_filenames([f.filename for f in files])

    paths = []
    wav_paths = []
    segmented_paths = set()
    backfill_slot_token: Optional[str] = None
    if lane_decision.lane == SyncLane.BACKFILL:
        backfill_slot_token = f'v1-{_uuid.uuid4()}'
        try:
            if not await run_blocking(db_executor, try_acquire_backfill_slot, uid, backfill_slot_token):
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
            paths = await run_blocking(sync_executor, retrieve_file_paths, files, uid)
            archive_paths = await run_blocking(
                sync_executor,
                archive_mobile_batch_raw_files,
                uid,
                paths,
                {
                    'app_version': client_device_context.app_version,
                    'firmware': request.headers.get('x-omi-firmware-version'),
                    'device_model': request.headers.get('x-omi-device-model'),
                },
            )
            await _offer_shadow_upload(
                uid=uid,
                content_id=None,
                paths=paths,
                lane=lane_decision.lane.value,
                age=lane_decision.maximum_age_seconds,
                conversation_id=conversation_id,
                source=source.value,
                device_id=client_device_context.client_device_id,
                byok=has_byok_keys(),
                policy=resolve_batch_policy(uid),
                should_lock=should_lock,
            )
            wav_paths = await run_blocking(sync_executor, decode_files_to_wav, paths)
        except HTTPException as e:
            raise HTTPException(status_code=e.status_code, detail=e.detail, headers=_V1_DEPRECATION_HEADERS)

        cap_held = False
        cap_admission: dict = {}
        if cap_dispatch_enabled(uid, 'sync'):
            cap_held = await hold_capture_if_exhausted(
                uid,
                wav_paths,
                source,
                admission=cap_admission,
                target_conversation_id=conversation_id,
                client_device_id=client_device_context.client_device_id,
                client_platform=client_device_context.platform,
            )
        if cap_held:
            return JSONResponse(
                status_code=200,
                headers=_V1_DEPRECATION_HEADERS,
                content={
                    'new_memories': [],
                    'updated_memories': [],
                    'credits_exhausted': cap_admission.get('reason')
                    in {'plan_allowance_exhausted', 'usage_budget_exhausted'},
                    'held_audio': True,
                    'held_files': len(wav_paths),
                },
            )
        vad_errors = []
        vad_segment_lock = threading.Lock()

        def _run_vad(path):
            retrieve_vad_segments(path, segmented_paths, vad_errors, segment_source_lock=vad_segment_lock)

        await asyncio.gather(*[run_blocking(sync_executor, _run_vad, path) for path in wav_paths])

        # Clean up original wav files after VAD segmentation (segments are now in segmented_paths)
        await run_blocking(sync_executor, _cleanup_files, wav_paths)
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
            reservation = await run_blocking(
                db_executor,
                reserve_backfill_speech,
                uid,
                backfill_slot_token or f'v1-{_uuid.uuid4()}',
                total_speech_ms,
            )
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
            await run_blocking(db_executor, record_speech_ms, uid, total_speech_ms, source=meter_source)
            if lane_decision.lane == SyncLane.FRESH:
                fair_use_sub = await run_blocking(db_executor, users_db.get_existing_user_subscription, uid)
                fair_use_plan = fair_use_sub.plan if fair_use_sub else None
                speech_totals = await run_blocking(db_executor, get_rolling_speech_ms, uid)
                triggered_caps = check_soft_caps(uid, speech_totals=speech_totals, plan=fair_use_plan)
                if triggered_caps:
                    logger.info(f'sync: soft caps triggered for {uid}: {triggered_caps}')
                    start_background_task(
                        trigger_classifier_if_needed(uid, triggered_caps), name=f'sync_fair_use_classifier:{uid}'
                    )

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
                fair_use_stage = await run_blocking(db_executor, get_enforcement_stage, uid)
                if fair_use_stage == 'restrict' and FAIR_USE_RESTRICT_DAILY_DG_MS > 0:
                    fair_use_restrict_dg = True
                    dg_budget_blocked = await run_blocking(db_executor, is_dg_budget_exhausted, uid)
            except Exception as e:
                logger.error(f'sync: DG budget check error for {uid}: {e}')

        if dg_budget_blocked:
            logger.info(f'sync: DG budget exhausted, skipping {total_segments} segments uid={uid}')
            await run_blocking(sync_executor, _cleanup_files, list(segmented_paths))
            return await _fair_use_restriction_response(
                uid=uid,
                retry_after=retry_after_until_next_utc_day(),
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

        cap_holds = response.get('_cap_holds', {}) if cap_dispatch_enabled(uid, 'sync') else {}
        cap_held_seconds = sum(item['seconds'] for item in cap_holds.values())

        await run_blocking(sync_executor, _reprocess_merged_conversations, uid, response)
        if private_cloud_sync_enabled:
            await run_blocking(sync_executor, _finalize_sync_audio_files, uid, response)
        schedule_person_voice_learning_retries(uid, response, _RESPONSE_FENCED_CONVERSATION_IDS)

        # Record DG usage after successful processing (not before, to avoid charging on retries)
        if fair_use_restrict_dg:
            try:
                dg_ms = int(total_speech_seconds * 1000)
                if cap_holds:
                    dg_ms = int(max(0, total_speech_seconds - cap_held_seconds) * 1000)
                if dg_ms > 0:
                    await run_blocking(db_executor, record_dg_usage_ms, uid, dg_ms)
            except Exception as e:
                logger.error(f'sync: DG usage record error for {uid}: {e}')

        if archive_paths:
            await run_blocking(
                storage_executor,
                link_archive_captures,
                uid,
                archive_paths,
                sorted(set(response['new_memories']) | set(response['updated_memories'])),
            )

        # Build JSON-serializable response
        result = {
            'new_memories': sorted(response['new_memories']),
            'updated_memories': sorted(response['updated_memories']),
        }
        if cap_holds:
            result.update(
                held_audio=True,
                credits_exhausted=any(item.get('reason') == 'plan_allowance_exhausted' for item in cap_holds.values()),
                held_segments=len(cap_holds),
            )

        failed_segments = len(segment_errors)
        successful_segments = total_segments - failed_segments
        if cap_holds:
            successful_segments -= len(cap_holds)

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
            if not cap_holds:
                raise HTTPException(
                    status_code=500,
                    detail=f"All {total_segments} segment(s) failed processing: {'; '.join(segment_errors[:3])}",
                    headers=_V1_DEPRECATION_HEADERS,
                )

        # Record subscription usage only when at least one segment succeeded
        try:
            usage_seconds = int(total_speech_seconds)
            if cap_holds:
                usage_seconds = int(max(0, total_speech_seconds - cap_held_seconds)) if successful_segments > 0 else 0
            if usage_seconds > 0:
                await run_blocking(
                    db_executor, record_usage, uid, transcription_seconds=usage_seconds, speech_seconds=usage_seconds
                )
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
        await run_blocking(
            sync_executor, _cleanup_files, paths
        )  # .bin files (in case decode_files_to_wav didn't finish)
        await run_blocking(sync_executor, _cleanup_files, wav_paths)  # Original wav files (if VAD didn't complete)
        await run_blocking(sync_executor, _cleanup_files, segmented_paths)  # Segmented wav files after processing
        if backfill_slot_token:
            try:
                await run_blocking(db_executor, release_backfill_slot, uid, backfill_slot_token)
            except Exception as e:
                logger.warning('sync: failed to release v1 backfill slot uid=%s error=%s', uid, type(e).__name__)


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
    sync_app_build = sanitize_app_build(x_app_version)
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
    geolocation = geolocation_from_private_header(x_omi_conversation_geolocation)

    filenames = [f.filename or '' for f in files]
    capture_claims = parse_s1_upload_claims(x_omi_capture_evidence, filenames)
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
    # Off the event loop, a cold process gives its first ramp read a bounded wait, so a
    # fresh instance cannot admit legacy work on the 'on' default after the ramp went
    # draining/dark (M3 review; batch intake reads the mode the same way).
    legacy_mode = await run_blocking(db_executor, legacy_dark.current_mode)
    legacy_allowed = legacy_dark.legacy_admission_allowed(legacy_mode)
    legacy_mode_read_at = time.monotonic()
    lane_decision = classify_sync_lane(
        filenames,
        client_device_id=client_device_context.client_device_id if has_server_capture_proof else None,
        # Legacy-dark: the legacy fresh budget is never consulted outside ``on``.
        allow_legacy_fresh=legacy_allowed and legacy_fresh.enabled_for(uid),
    )
    if legacy_allowed and lane_decision.reason == 'recent_legacy_capture':
        lane_decision = await run_blocking(db_executor, legacy_fresh.admit, uid, lane_decision, [f.size for f in files])
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
    if lane_decision.lane is SyncLane.BACKFILL:
        await run_blocking(sync_executor, validate_backfill_uploads, files)
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

    cloud_tasks_dispatch_enabled = is_cloud_tasks_dispatch_enabled()
    byok_enabled = has_byok_keys()
    cloud_task_eligible = cloud_tasks_dispatch_enabled and not byok_enabled

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

        candidate_policy = resolve_batch_policy(uid)
        batch_policy = await run_blocking(
            db_executor,
            ramp_admission_policy,
            uid,
            candidate_policy,
            content_id=content_id,
            conversation_id=conversation_id if isinstance(conversation_id, str) else None,
            incoming_audio_seconds=audio_span(
                {'audio_start_seconds': audio_start_seconds, 'audio_end_seconds': audio_end_seconds}
            ),
        )
        record_response = await registered_record_response(
            uid=uid,
            conversation_id=conversation_id if isinstance(conversation_id, str) else None,
            content_id=content_id,
            paths=paths,
            source=source.value,
            client_device_id=client_device_context.client_device_id,
            byok_enabled=byok_enabled,
            recording_session_id=recording_session_id,
            policy=batch_policy,
            loaded_conversation=record_snapshot if record_snapshot.get('record_lane_owner') else None,
            # A legacy_final_pass_v1 owner is re-homed to batch once legacy is
            # draining/dark (final_pass_rehome); the route answers BATCH then.
            legacy_mode=legacy_mode,
        )
        if isinstance(record_response, JSONResponse):
            return record_response

        batch_attempted = False
        if record_response is RecordUploadRoute.BATCH:
            # This conversation already has a durable batch-sync owner. New
            # owner-load narrowing cannot transfer its later WAL to legacy.
            batch_policy = replace(candidate_policy, batch_enabled=True)

        if record_response is RecordUploadRoute.BATCH or (
            record_response is not RecordUploadRoute.LEGACY and candidate_policy.batch_enabled
        ):
            # Route ownership is durable before any acceptance; neither errors
            # nor rollback may start a legacy twin or release this batch claim.
            sequencer_registration_started = True
            batch_attempted = True
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
                policy=batch_policy,
            )
            if batch_response is not None:
                return batch_response
            sequencer_registration_started = False

        if legacy_allowed and time.monotonic() - legacy_mode_read_at > legacy_dark.ADMISSION_REVALIDATE_SECONDS:
            # A legacy job is created only on a young mode read: a request that read 'on'
            # and then stalled (a long batch decode, a slow fallback) must not carry it past
            # a draining re-home of the same conversation (final_pass_rehome's flip grace).
            legacy_mode = await run_blocking(db_executor, legacy_dark.current_mode)
            legacy_allowed = legacy_dark.legacy_admission_allowed(legacy_mode)

        if not legacy_allowed:
            # Legacy-dark (contract (h)): never create a legacy job. Content legacy
            # already owns is answered by the fence; anything else keeps its audio.
            ledger_row = await run_blocking(db_executor, legacy_dark.read_ledger_row, uid, content_id)
            owner_job_present = await run_blocking(db_executor, legacy_dark.legacy_owner_job_present, ledger_row)
            decision = legacy_dark.fence_decision(ledger_row, legacy_mode, owner_job_present=owner_job_present)
            if record_response is RecordUploadRoute.LEGACY and decision.action is not legacy_dark.FenceAction.ACK:
                # The conversation's durable legacy_final_pass_v1 owner holds this recording
                # (h, invariant 4), even with no content-ledger row: acknowledge it as batch
                # intake does, never a 409 retry loop and never a new legacy job (M3 review).
                decision = legacy_dark.FenceDecision(
                    legacy_dark.FenceAction.ACK,
                    legacy_dark.LegacyDarkReason.LEGACY_ACTIVE,
                    legacy_dark.LegacyOwnership.ACTIVE,
                )
            await run_blocking(sync_executor, _cleanup_files, paths)
            await run_blocking(sync_executor, shutil.rmtree, job_dir, True)
            return (
                legacy_dark.fence_response(decision, total_files=len(files), lane=lane_decision.lane.value)
                or legacy_dark.admission_refused_response()
            )
        if record_response is RecordUploadRoute.LEGACY:
            admission_reason = legacy_dark.LegacyAdmissionReason.LEGACY_RECORD_OWNER
        elif batch_attempted:
            admission_reason = legacy_dark.LegacyAdmissionReason.INTAKE_FALLBACK
        else:
            admission_reason = legacy_dark.LegacyAdmissionReason.BATCH_NOT_ENABLED
        legacy_dark.record_legacy_admission(admission_reason, legacy_mode)

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
            dispatch_mode=(
                'sequenced'
                if cloud_task_eligible and lane_decision.lane == SyncLane.BACKFILL and uid_sequencer.enabled()
                else 'cloud_tasks' if cloud_task_eligible else 'inline'
            ),
            policy=batch_policy,
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
        if claim.get('outcome') in {'completed', 'held'}:
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
        if claim.get('outcome') == 'capped':
            # Keep the ordinary 202 -> failed-job contract: the shipped WAL
            # reconciler retries this content with its per-file budget. An
            # upload 400 strands it, while a scoped 503 pauses the whole account.
            await run_blocking(
                db_executor,
                mark_job_failed,
                job_id,
                'Repeated content failure paused',
                reason_code='sync_repeat_failure_paused',
            )
            if backfill_slot_acquired:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
                backfill_slot_acquired = False
            failure_key = claim.get('failure_key')
            logger.warning(
                'event=sync_repeat_failure_cap outcome=paused lane=%s failure_key=%s device_hash=%s',
                lane_decision.lane.value,
                failure_key if failure_key in {'invalid_audio', 'persistent_persistence'} else 'unknown',
                client_device_context.client_device_id[-8:] if client_device_context.client_device_id else 'none',
            )
            return JSONResponse(
                status_code=202,
                content={
                    'job_id': job_id,
                    'status': 'failed',
                    'total_files': len(files),
                    'total_segments': 0,
                    'poll_after_ms': 0,
                    'lane': lane_decision.lane.value,
                },
            )
        if claim.get('outcome') == 'busy':
            await run_blocking(db_executor, delete_sync_job, job_id)
            if backfill_slot_acquired:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
                backfill_slot_acquired = False
            return sync_content_in_progress_response(claim.get('job_id'))
        try:
            OMI_SYNC_LANE_JOBS_TOTAL.labels(
                lane=lane_decision.lane.value,
                trust=lane_decision.trust.value,
                outcome='admitted',
            ).inc()
        except Exception:
            pass

        # Transfer ownership of raw paths to the background task
        await _offer_shadow_upload(
            uid=uid,
            content_id=content_id,
            paths=paths,
            lane=lane_decision.lane.value,
            age=lane_decision.maximum_age_seconds,
            conversation_id=conversation_id if isinstance(conversation_id, str) else None,
            source=source.value,
            device_id=client_device_context.client_device_id,
            byok=byok_enabled,
            policy=batch_policy,
            should_lock=should_lock,
        )
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
            if backfill_slot_acquired:
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
                **({'raw_capture_paths': archive_paths} if archive_paths else {}),
                **({'capture_evidence_claims': capture_claims} if capture_claims else {}),
                'source': source.value,
                'should_lock': should_lock,
                'conversation_id': conversation_id,
                'recording_session_id': recording_session_id,
                'audio_start_seconds': audio_start_seconds,
                'audio_end_seconds': audio_end_seconds,
                'geolocation': geolocation.model_dump(mode='json') if geolocation else None,
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
            if (
                lane_decision.lane == SyncLane.BACKFILL
                and uid_sequencer.enabled()
                and legacy_dark.sequencer_registration_allowed(legacy_mode)
            ):
                # The Firestore record, not a Cloud Task acknowledgement, is
                # the durable 202 boundary. Waiting jobs hold no HTTP worker.
                # An ambiguous Firestore acknowledgement may already have
                # committed. Never release its content claim on that path.
                sequencer_registration_started = True
                try:
                    await run_blocking(
                        db_executor,
                        sync_backfill_sequencer.register_job,
                        uid,
                        job_id,
                        enqueue_payload,
                        lane_decision.oldest_capture_at,
                    )
                except Exception as error:
                    # A committed Firestore transaction can lose its reply.
                    # An authoritative read converts that to a safe 202.
                    # If the read also fails, keep all recovery material and
                    # refuse to assert that the job was accepted.
                    registered = await run_blocking(db_executor, sync_backfill_sequencer.is_registered, uid, job_id)
                    if not registered:
                        # A fast worker may have consumed the last pending
                        # document and cleared its active owner before this read.
                        observed_job = await run_blocking(db_executor, get_sync_job, job_id)
                        registered = bool(observed_job and observed_job.get('status') in TERMINAL_STATUSES)
                    if not registered:
                        sequencer_registration_started = False
                        await _delete_staged_blobs_async(owned_paths)
                        await run_blocking(sync_executor, _cleanup_files, owned_paths)
                        await _finalize_sync_job_failure(
                            job_id=job_id,
                            uid=uid,
                            content_id=content_id,
                            error_code='sync_sequencer_registration_failed',
                            outcome=TranscriptionOutcome.UPSTREAM_ERROR,
                            provider='unknown',
                            model='unknown',
                            lane=lane_decision.lane.value,
                        )
                        logger.error(
                            'event=sync_uid_sequencer action=registered outcome=failed exception_type=%s',
                            type(error).__name__,
                        )
                        return JSONResponse(
                            status_code=503,
                            headers={'Retry-After': '30'},
                            content={
                                'code': 'sync_dispatch_unavailable',
                                'detail': 'Historical recovery is temporarily unavailable',
                            },
                        )
                try:
                    await run_blocking(db_executor, uid_sequencer.kick, uid)
                except Exception as error:
                    # The accepted record is durable. A Scheduler tick will
                    # rediscover it; returning 503 here would trigger a second
                    # phone upload for the same content.
                    logger.error(
                        'event=sync_uid_sequencer action=kick outcome=deferred exception_type=%s',
                        type(error).__name__,
                    )
                dispatched = True
            enqueue_error = None
            if lane_decision.lane == SyncLane.BACKFILL and not dispatched:
                # Register the direct path before its task can run. A later
                # flag-on revision waits for this bounded direct-work window.
                await run_blocking(db_executor, backfill_cutover.note_direct_admission, uid, job_id)
            for enqueue_attempt in range(0 if dispatched else 2):
                try:
                    await run_blocking(db_executor, enqueue_sync_job, enqueue_payload)
                    dispatched = True
                    break
                except Exception as e:
                    enqueue_error = e

            if dispatched:
                try:
                    OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL.labels(mode='cloud_tasks', app_build=sync_app_build).inc()
                except Exception:
                    pass
                record_product_event(
                    'sync_job_enqueued',
                    client_kind=resolve_client_kind(x_app_platform=x_app_platform, user_agent=None),
                    app_build=sync_app_build,
                    uid=uid,
                )
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
                    OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL.labels(mode='enqueue_uncertain', app_build=sync_app_build).inc()
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
                    OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL.labels(mode='inline', app_build=sync_app_build).inc()
                except Exception:
                    pass
                record_product_event(
                    'sync_job_enqueued',
                    client_kind=resolve_client_kind(x_app_platform=x_app_platform, user_agent=None),
                    app_build=sync_app_build,
                    uid=uid,
                )
            elif byok_enabled:
                record_fallback(
                    component='sync_dispatch',
                    from_mode='cloud_tasks',
                    to_mode='inline',
                    reason='byok',
                    outcome='recovered',
                )
                try:
                    OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL.labels(mode='inline', app_build=sync_app_build).inc()
                except Exception:
                    pass
                record_product_event(
                    'sync_job_enqueued',
                    client_kind=resolve_client_kind(x_app_platform=x_app_platform, user_agent=None),
                    app_build=sync_app_build,
                    uid=uid,
                )

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
                            geolocation=geolocation,
                            client_device_id=client_device_context.client_device_id,
                            client_platform=client_device_context.platform,
                            sync_lane=lane_decision.lane.value,
                            content_id=content_id,
                            run_lock_token=inline_run_lock_token if ledger_fence_active else None,
                            inline_run_lock_token=inline_run_lock_token,
                            content_run_bound=ledger_fence_active,
                            ledger_fence_active=ledger_fence_active,
                            **({'raw_capture_paths': archive_paths} if archive_paths else {}),
                            **({'capture_evidence_claims': capture_claims} if capture_claims else {}),
                            recording_session_id=recording_session_id,
                            audio_start_seconds=audio_start_seconds,
                            audio_end_seconds=audio_end_seconds,
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
    from utils.sync.completed_status import get_completed_legacy_status

    try:
        completed = get_completed_legacy_status(job_id, uid, job)
    except Exception as error:
        logger.error('event=sync_status_reconciliation outcome=retrying exception_type=%s', type(error).__name__)
        raise sync_finalization_retrying()
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
        retired = acknowledge_retired_handle(job_id, uid)  # custody-held expiry-retired handles
        if retired is not None:
            return with_poll_hint(retired, surface_open=surface_open)
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
            raise sync_finalization_retrying()
        # Retaining an epoch counter after the durable claim is recoverable is
        # safe; never keep a client WAL pending solely for that optimization.
        delete_sync_job_run_lock_epoch(job_id)

    if job.get('status') in ('failed', 'partial_failure') and job.get('lane') == SyncLane.BACKFILL.value:
        try:
            dead_letter = sync_dead_letters.get_dead_letter(job_id)
        except Exception as error:
            logger.error('event=sync_dead_letter_check outcome=read_failed exception_type=%s', type(error).__name__)
            raise sync_finalization_retrying()
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
                raise sync_finalization_retrying()
            logger.warning('event=sync_dead_letter_check outcome=legacy_recorded')
        if (
            dead_letter.get('job_id') != job_id
            or dead_letter.get('uid') != uid
            or dead_letter.get('status') not in ('pending', 'dead_letter')
        ):
            raise sync_finalization_retrying()
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
    # One absolute budget deadline for the whole request, anchored at the
    # middleware's request-start stamp (the same omi_request_started_monotonic
    # utils.other.list_budget derives read deadlines from; TimeoutMiddleware
    # writes it before call_next, so verify_cloud_tasks_oidc time is charged
    # against this wall — a stalled dependency cannot push the budget past the
    # middleware cap). Callers without the stamp fall back to route entry.
    # The dict rides every path — direct deliveries pass it into the attempt
    # body, whose own budget anchors at the same absolute deadline; sequenced
    # deliveries also use it for the bounded completion drain after the
    # response is produced. Each wrapper closes before the attempt body is
    # awaited: the body brings its own budget anchored at this same deadline,
    # and two timeout contexts armed at the same instant would deliver a
    # second cancellation into the body's post-expiry recovery work.
    middleware_request_start = getattr(getattr(request, 'state', None), 'omi_request_started_monotonic', None)
    budget_anchor = middleware_request_start if isinstance(middleware_request_start, float) else time.monotonic()
    entry_state: dict = {'budget_deadline_monotonic': budget_anchor + SYNC_JOB_HANDLER_BUDGET_SECONDS}
    route_deadline = entry_state['budget_deadline_monotonic']
    try:
        async with asyncio.timeout_at(route_deadline):
            fence_mode = await run_blocking(db_executor, uid_sequencer.production_fence_mode)
    except TimeoutError:
        logger.warning('event=sync_transcription_job outcome=handler_preamble_expired phase=fence_read')
        return _budget_deferral_fallback('preamble_timeout', 'degraded')
    if fence_mode is SyncLedgerFenceMode.STANDBY:
        return JSONResponse(status_code=503, content={'status': 'cutover_standby'})
    try:
        async with asyncio.timeout_at(route_deadline):
            payload = await request.json()
    except TimeoutError:
        logger.warning('event=sync_transcription_job outcome=handler_preamble_expired phase=parse')
        return _budget_deferral_fallback('preamble_timeout', 'degraded')
    except Exception:
        return await _run_sync_job_body(request, task_retry_count, entry_state)
    if isinstance(payload, dict) and isinstance(payload.get('uid'), str):
        try:
            async with asyncio.timeout_at(route_deadline):
                await warm_rollout_cohorts(payload['uid'])
        except TimeoutError:
            logger.warning('event=sync_transcription_job outcome=handler_preamble_expired phase=cohort_warm')
            return _budget_deferral_fallback('preamble_timeout', 'degraded')
    if isinstance(payload, dict) and payload.get('kind') == 'sync_reprocess':
        return await enrichment_response(payload)
    if minimal_redrive.parse_mode(payload) and not minimal_redrive.enabled():
        # Kill switch, before the sequencer lease and any lock, download or paid
        # call: the task, staged audio and ledger claim stay retained.
        logger.warning('event=sync_minimal_redrive outcome=refused reason=disabled')
        return JSONResponse(status_code=409, content={'status': 'minimal_redrive_disabled'})
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
            and not legacy_dark.sequencer_registration_allowed()
            and isinstance(payload.get('uid'), str)
            and isinstance(payload.get('job_id'), str)
        ):
            # Legacy-dark (draining/dark): an epoch-less backfill delivery can no
            # longer migrate into the sequencer, so it must not start a second
            # transcriber for a uid whose sequencer owner is live (M1 review L10-1).
            try:
                async with asyncio.timeout_at(route_deadline):
                    registered = await run_blocking(
                        db_executor, sync_backfill_sequencer.is_registered, payload['uid'], payload['job_id']
                    )
                    owner = (
                        {}
                        if registered
                        else await run_blocking(db_executor, sync_backfill_sequencer.get_owner, payload['uid'])
                    )
            except TimeoutError:
                logger.warning('event=sync_transcription_job outcome=handler_preamble_expired phase=dark_owner_probe')
                return _budget_deferral_fallback('preamble_timeout', 'degraded')
            if registered and legacy_dark.sequencer_dispatch_allowed():
                # The draining sweep dispatches this job; acking keeps it the only dispatcher.
                legacy_dark.record_dark_ack(legacy_dark.LegacyDarkReason.SEQUENCER_OWNS_JOB)
                return JSONResponse(status_code=200, content={'status': 'sequenced_legacy_job'})
            active_job_id = owner.get('active_job_id')
            if isinstance(active_job_id, str) and active_job_id and active_job_id != payload['job_id']:
                # Never 503/429 from a task target (contract d): the queue retries
                # until the live owner finishes, the client keeps its audio.
                legacy_dark.record_dark_ack(legacy_dark.LegacyDarkReason.SEQUENCER_OWNER_ACTIVE)
                return JSONResponse(status_code=409, content={'status': 'locked', 'reason': 'sequencer_owner_active'})
        if (
            isinstance(payload, dict)
            and payload.get('lane') == SyncLane.BACKFILL.value
            and uid_sequencer.production_stage()
            and uid_sequencer.enabled()
            and legacy_dark.sequencer_registration_allowed()
            and isinstance(payload.get('uid'), str)
            and isinstance(payload.get('job_id'), str)
        ):
            legacy_job = None
            active_owner: dict = {}
            try:
                async with asyncio.timeout_at(route_deadline):
                    legacy_job = await run_blocking(db_executor, get_sync_job, payload['job_id'])
                    if legacy_job and legacy_job.get('status') == 'processing':
                        active_owner = await run_blocking(
                            db_executor, sync_backfill_sequencer.get_owner, payload['uid']
                        )
            except TimeoutError:
                logger.warning('event=sync_transcription_job outcome=handler_preamble_expired phase=legacy_probe')
                return _budget_deferral_fallback('preamble_timeout', 'degraded')
            if legacy_job and legacy_job.get('status') == 'processing':
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
                try:
                    async with asyncio.timeout_at(route_deadline):
                        marked = await run_blocking(
                            db_executor, update_sync_job, payload['job_id'], {'dispatch_mode': 'sequenced'}
                        )
                        if marked is None:
                            return await _run_sync_job_body(request, task_retry_count, entry_state)
                        enqueued_at = payload.get('enqueued_at')
                        age = payload.get('recording_age_seconds')
                        captured_at = (
                            float(enqueued_at) - float(age)
                            if isinstance(enqueued_at, (int, float)) and isinstance(age, (int, float))
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
                except TimeoutError:
                    logger.warning(
                        'event=sync_transcription_job outcome=handler_preamble_expired phase=legacy_migration'
                    )
                    return _budget_deferral_fallback('preamble_timeout', 'degraded')
                try:
                    async with asyncio.timeout_at(route_deadline):
                        await run_blocking(db_executor, uid_sequencer.kick, payload['uid'])
                except TimeoutError:
                    # Registration already committed: a 409 would redeliver a
                    # payload that no longer needs the queue.
                    logger.warning('event=sync_transcription_job outcome=handler_preamble_expired phase=legacy_kick')
                except Exception as error:
                    logger.error(
                        'event=sync_uid_sequencer action=legacy_migration outcome=deferred exception_type=%s',
                        type(error).__name__,
                    )
                logger.info('event=sync_uid_sequencer action=legacy_migration outcome=registered')
                return JSONResponse(status_code=200, content={'status': 'sequenced_legacy_job'})
            if legacy_job and legacy_job.get('status') in ('queued', 'processing'):
                try:
                    async with asyncio.timeout_at(route_deadline):
                        await run_blocking(
                            db_executor, backfill_cutover.refresh_direct_run, payload['uid'], payload['job_id']
                        )
                except TimeoutError:
                    logger.warning('event=sync_transcription_job outcome=handler_preamble_expired phase=direct_refresh')
                    return _budget_deferral_fallback('preamble_timeout', 'degraded')
                except Exception as error:
                    logger.error(
                        'event=sync_transcription_job outcome=direct_refresh_failed exception_type=%s',
                        type(error).__name__,
                    )
        return await _run_sync_job_body(request, task_retry_count, entry_state)
    uid = payload.get('uid')
    job_id = payload.get('job_id')
    if not isinstance(uid, str) or not isinstance(job_id, str) or not isinstance(epoch, int) or epoch <= 0:
        return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'invalid_sequencer_identity'})
    # One absolute budget deadline for the whole sequenced request (entry_state,
    # captured and enforced at route entry): the fence read, payload parsing,
    # begin_job, and the prior-job read below each run inside a timeout_at
    # against that deadline, so a stall in any of them ends the request through
    # the queue-owned 409 instead of carrying it past the Cloud Tasks dispatch
    # deadline or the middleware cap this change exists to stay under.
    sequenced_attempt_state: dict = entry_state
    try:
        async with asyncio.timeout_at(route_deadline):
            began = await run_blocking(db_executor, sync_backfill_sequencer.begin_job, uid, job_id, epoch)
    except TimeoutError:
        logger.warning('event=sync_transcription_job outcome=handler_preamble_expired phase=begin_job')
        return _budget_deferral_fallback('preamble_timeout', 'degraded')
    if not began:
        logger.info('event=sync_uid_sequencer action=delivery outcome=stale_epoch')
        return JSONResponse(status_code=200, content={'status': 'stale_sequencer_epoch'})
    stop = asyncio.Event()
    heartbeat = start_background_task(
        _maintain_uid_sequencer_lease(uid, job_id, epoch, stop, asyncio.current_task()),
        name=f'sync:uid-lease:{job_id}',
    )
    try:
        try:
            async with asyncio.timeout_at(route_deadline):
                prior_job = await run_blocking(db_executor, get_sync_job, job_id)
        except TimeoutError:
            logger.warning('event=sync_transcription_job outcome=handler_preamble_expired phase=prior_read')
            return _budget_deferral_fallback('preamble_timeout', 'degraded')
        prior_attempt = prior_job.get('attempt', 0) if isinstance(prior_job, dict) else 0
        effective_retry_count = max(task_retry_count, prior_attempt if isinstance(prior_attempt, int) else 0)
        # One state dict carries the post-budget deadline from the deferral
        # into this finally block: the marker clear inside the deferral and
        # this heartbeat drain must share one absolute cleanup deadline
        # (post_budget_deadline + SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS)
        # instead of each spending a fresh margin-sized timeout whose sum
        # reaches the attempt wall before the response is serialized.
        response = await _run_sync_job_body(request, effective_retry_count, sequenced_attempt_state)
    finally:
        stop.set()
        # Setting stop cannot interrupt a renewal already blocked inside its
        # Firestore run_blocking, and this join sits between the attempt's
        # response and its return: without a bound, a stuck renewal holds the
        # request open past every wall the handler budget exists to stay
        # under. wait_for cancels the heartbeat at the bound; the orphaned
        # renewal finishing later only logs lease_lost or renews an epoch the
        # response has already left behind.
        post_budget_deadline = sequenced_attempt_state.get('post_budget_deadline')
        shared_drain_bound = (
            post_budget_deadline + SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS
            if isinstance(post_budget_deadline, float)
            else None
        )
        if shared_drain_bound is not None:
            # One absolute bound for both cleanup waits: the marker clear in
            # the deferral already consumed up to this deadline, so the drain
            # takes only what remains — never a fresh margin-sized timeout on
            # top. The standalone bound stays the ceiling so a large explicit
            # enqueue-timeout override cannot extend the drain past its own
            # contract.
            drain_timeout = min(
                SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS,
                max(0.0, shared_drain_bound - time.monotonic()),
            )
        else:
            drain_timeout = SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS
        try:
            await asyncio.wait_for(heartbeat, drain_timeout)
        except TimeoutError:
            logger.warning('event=sync_uid_sequencer action=heartbeat_drain outcome=cancelled')
    if response.status_code < 300 and not _is_handler_budget_deferral(response):
        # A budget deferral is an ack, not a completion claim: the epoch still
        # owns the job and the delayed replacement (or the sweep's lease-expiry
        # redrive) re-enters it, so the owner must not be finished here — and
        # the nonterminal check below must not turn it into a retry-burning 500.
        # The completion drain is bounded by the same absolute request
        # deadline plus the post-attempt cleanup headroom the heartbeat drain
        # uses: a slow Redis/Firestore call here must not consume the
        # remaining response margin and let the middleware or Cloud Tasks
        # deadline terminate the request before its response is returned.
        # Fencing stays intact — finish_job's transaction re-checks the lease
        # — so an expired bound only skips the release; the next sweep's
        # lease-expiry path releases the owner instead.
        completion_bound = sequenced_attempt_state.get('budget_deadline_monotonic')
        completion_timeout = (
            max(
                0.0,
                (completion_bound + SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS) - time.monotonic(),
            )
            if isinstance(completion_bound, float)
            else SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS
        )
        try:
            async with asyncio.timeout(completion_timeout):
                job = await run_blocking(db_executor, get_sync_job, job_id)
                if job is not None and job.get('status') not in TERMINAL_STATUSES:
                    logger.error('event=sync_uid_sequencer action=delivery outcome=nonterminal_ack')
                    return JSONResponse(status_code=500, content={'status': 'nonterminal_ack'})
                outcome = job.get('status') if job else 'expired'
                released = await run_blocking(
                    db_executor, sync_backfill_sequencer.finish_job, uid, job_id, epoch, outcome
                )
                if released:
                    await run_blocking(db_executor, uid_sequencer.kick, uid)
        except TimeoutError:
            logger.warning('event=sync_uid_sequencer action=delivery outcome=completion_drain_cancelled')
    return response


# The TimeoutMiddleware cap (HTTP_SYNC_JOBS_RUN_TIMEOUT, default 1500s) answers
# 504 without cancelling the pipeline coroutine, so on Starlette's
# BaseHTTPMiddleware the request stays open until the pipeline returns and
# Cloud Run terminates it at the service's maximum request timeout instead.
# The handler must end the attempt itself, below every wall that can end it
# first: the middleware cap, the dispatch deadline every named task carries
# (utils/cloud_tasks.py DISPATCH_DEADLINE_SECONDS — past it the queue retries
# while this handler still runs), and the run lock's TTL (past it a retry can
# reacquire the lock the budget still holds). The budget below therefore
# defaults to the earliest of those walls minus a fixed response margin; an
# explicit env override still wins (the local stacks set 20s under a 30s route
# timeout), but any budget that is not strictly below all three fails at
# startup — that configuration reproduces the exact lingering-request path
# this cap exists to prevent.
SYNC_JOB_RESPONSE_MARGIN_SECONDS = 120.0
SYNC_JOB_ROUTE_TIMEOUT_SECONDS = float(os.environ.get('HTTP_SYNC_JOBS_RUN_TIMEOUT') or 1500)


def _resolve_sync_job_handler_budget(
    route_timeout_seconds: float,
    override: Optional[str],
    *,
    dispatch_deadline_seconds: float = DISPATCH_DEADLINE_SECONDS,
    run_lock_ttl_seconds: float = RUN_LOCK_TTL_SECONDS,
) -> float:
    attempt_cap_seconds = min(route_timeout_seconds, dispatch_deadline_seconds, run_lock_ttl_seconds)
    budget_seconds = (
        float(override) if override not in (None, '') else (attempt_cap_seconds - SYNC_JOB_RESPONSE_MARGIN_SECONDS)
    )
    if not 0 < budget_seconds < attempt_cap_seconds:
        raise ValueError(
            'SYNC_JOB_HANDLER_BUDGET_SECONDS must be positive and strictly below the '
            'earliest attempt wall — HTTP_SYNC_JOBS_RUN_TIMEOUT, the Cloud Tasks '
            f'dispatch deadline ({dispatch_deadline_seconds!r}s), and the run lock TTL '
            f'({run_lock_ttl_seconds!r}s), i.e. below {attempt_cap_seconds!r}s — '
            f'otherwise the queue retries the attempt while this handler still owns '
            f'it and the lingering-request path returns (got {budget_seconds!r})'
        )
    return budget_seconds


SYNC_JOB_HANDLER_BUDGET_SECONDS = _resolve_sync_job_handler_budget(
    SYNC_JOB_ROUTE_TIMEOUT_SECONDS, os.environ.get('SYNC_JOB_HANDLER_BUDGET_SECONDS')
)

# A budget expiry preserves the run lock for its full TTL (RUN_LOCK_TTL_SECONDS,
# 1800s), which outlives every queue-level Cloud Tasks retry: with the
# five-attempt queue contract (provisioned as --max-attempts=5 by
# .github/actions/sync-backfill-lifecycle/action.yml and mirrored by
# utils/cloud_tasks.py get_sync_tasks_max_attempts) and the queue's
# seconds-to-minutes backoff, a 409 would spend all remaining attempts
# deferring against the held lock and exhaust the task before any delivery could
# reacquire it, leaving the job nonterminal. The expired attempt therefore acks
# and schedules one replacement named task for after the lock is guaranteed gone;
# the 409 stays only as the fallback when no replacement could be scheduled.
SYNC_JOB_BUDGET_REPLACEMENT_DELAY_SECONDS = RUN_LOCK_TTL_SECONDS + 60


def _resolve_sync_job_replacement_enqueue_timeout(
    route_timeout_seconds: float,
    budget_seconds: float,
    *,
    dispatch_deadline_seconds: float = DISPATCH_DEADLINE_SECONDS,
    run_lock_ttl_seconds: float = RUN_LOCK_TTL_SECONDS,
) -> float:
    # The replacement enqueue runs after the budget has expired, so it must fit
    # inside the margin the configured budget actually leaves below the earliest
    # attempt wall — the same minimum of route cap, dispatch deadline, and run
    # lock TTL that caps the budget, with the other half as response headroom —
    # rather than a fixed fraction of the default margin that an explicit
    # override can exceed, or a route cap above the dispatch deadline, which
    # would let post-budget work cross the wall Cloud Tasks ends the attempt at.
    attempt_cap_seconds = min(route_timeout_seconds, dispatch_deadline_seconds, run_lock_ttl_seconds)
    return (attempt_cap_seconds - budget_seconds) / 2


SYNC_JOB_BUDGET_REPLACEMENT_ENQUEUE_TIMEOUT_SECONDS = _resolve_sync_job_replacement_enqueue_timeout(
    SYNC_JOB_ROUTE_TIMEOUT_SECONDS, SYNC_JOB_HANDLER_BUDGET_SECONDS
)
# Cleanup that must still run after the attempt's deadline-bearing work has
# ended — clearing the deferral marker when the replacement enqueue failed,
# draining the sequencer heartbeat before its response is returned — gets half
# of the response headroom (the enqueue deadline above already spent the first
# half of the margin), so this work cannot hold the response to the
# middleware/dispatch wall the budget exists to stay under.
SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS = SYNC_JOB_BUDGET_REPLACEMENT_ENQUEUE_TIMEOUT_SECONDS / 2
SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS = 'deferred_handler_budget'
# Each replacement is a fresh named task whose queue-level retry count starts
# at zero, so the chain carries its own count: once a job has spent the queue's
# attempt contract in whole-budget attempts, no further replacement is
# scheduled and the task ends through the queue instead of chaining until the
# staged audio expires.
SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY = 'budget_deferrals'


def _is_handler_budget_deferral(response: JSONResponse) -> bool:
    try:
        return json.loads(response.body).get('status') == SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS
    except Exception:
        return False


def _budget_deferral_fallback(reason: str, outcome: str) -> JSONResponse:
    """The 409 keeps the queue — not this handler — owning the retry; record the
    switch so the deferred-recovery path cannot fail dark."""
    record_fallback(
        component='sync_dispatch',
        from_mode='budget_replacement',
        to_mode='queue_retry',
        reason=reason,
        outcome=outcome,
    )
    return JSONResponse(status_code=409, content={'status': 'locked'})


def _consume_detached_outcome(task: asyncio.Future) -> None:
    """Retrieve a detached task's eventual outcome once it settles, so a late
    failure of work its handler has stopped waiting on cannot resurface as an
    unretrieved-exception warning."""
    if not task.done():
        task.add_done_callback(_consume_detached_outcome)
        return
    if not task.cancelled():
        task.exception()


def _is_uncertain_enqueue_error(error: BaseException) -> bool:
    """Whether a failed replacement enqueue leaves the task's existence unknown.

    A Cloud Tasks transport/deadline failure cannot prove the named task was
    not created: the create request may have been received and executed before
    the error surfaced. Those outcomes must keep the deferred marker guarding
    the poll window instead of clearing it as a proven non-creation.
    """
    if isinstance(error, (TimeoutError, ConnectionError)):
        return True
    return isinstance(
        error,
        (
            google_api_exceptions.ServiceUnavailable,
            google_api_exceptions.DeadlineExceeded,
            google_api_exceptions.GatewayTimeout,
            google_api_exceptions.InternalServerError,
        ),
    )


async def _clear_deferral_marker_after_failed_replacement(
    marker_write: Optional[asyncio.Future], job_id: str, post_budget_deadline: float
) -> None:
    """Clear a deferral marker whose replacement chain failed, ordered safely.

    The marker suppresses stale detection until the instant the replacement
    would have run; with no replacement scheduled that window is an
    unnecessary nonterminal stall outlasting the preserved lock, so clear it
    before handing the retry back to the queue. Best-effort and bounded by
    the remaining headroom on the one shared post-attempt cleanup deadline —
    a lost clear only keeps today's stall.

    The clear is ordered behind the marker write: an expiry cancels only the
    await, so the write's CAS can still be mid-flight in db_executor, and a
    clear that completed first would be overwritten by the late-applied
    marker — recreating the exact stall this clear exists to remove. A write
    that still has not settled by the cleanup deadline skips the clear: a
    racy clear buys nothing the surviving marker does not already cost.

    A marker write that already settled with an error is included: the EVAL
    can have applied on the server while the client lost the response, so a
    live ``deferred_until`` can survive a "failed" write with no replacement
    enqueued behind it.
    """
    if marker_write is not None and not marker_write.done():
        try:
            async with asyncio.timeout_at(post_budget_deadline + SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS):
                await asyncio.shield(marker_write)
        except Exception:
            # The write's own late failure also settles it — the clear below
            # is then ordered and safe to run. Only a write still running
            # past the cleanup deadline forces the skip.
            if not marker_write.done():
                _consume_detached_outcome(marker_write)
                logger.warning('event=sync_transcription_job outcome=handler_budget_deferral_marker_drain_failed')
                return
    try:
        async with asyncio.timeout_at(post_budget_deadline + SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS):
            cleared = await run_blocking(db_executor, update_sync_job, job_id, {'deferred_until': None})
        if cleared is None:
            raise RuntimeError('deferred marker clear did not apply')
    except Exception:
        # A surviving marker keeps stale recovery suppressed long after the
        # queue-owned retries exhaust — a materially worse state than the
        # clean re-arm the primary fallback reason implies, so it gets its
        # own bounded record rather than hiding behind a warning log.
        logger.warning('event=sync_transcription_job outcome=handler_budget_deferral_marker_clear_failed')
        record_fallback(
            component='sync_dispatch',
            from_mode='budget_replacement',
            to_mode='queue_retry',
            reason='marker_clear_failed',
            outcome='degraded',
        )


async def _defer_sync_job_after_handler_budget_expiry(
    request: Request,
    attempt_state: Optional[dict] = None,
    *,
    terminal_cleanup: bool = False,
    deadline: Optional[float] = None,
) -> JSONResponse:
    """Ack a budget-expired attempt against a replacement scheduled past the
    preserved run lock's TTL. Queue-level retries cannot outlive that lock, so
    spending them now would exhaust the task on lock-held 409s; when no
    replacement can be scheduled, the 409 fallback keeps the queue — not this
    handler — owning the retry.

    ``terminal_cleanup=True`` is the terminal-job variant used after a strict
    lock release could not be confirmed: the job is already terminal, so the
    deferred-marker write is both unnecessary (no stale status poll can
    terminalize a terminal job) and structurally impossible
    (``update_sync_job`` refuses to mutate terminal states), and the
    replacement's redelivery hits the terminal branch's retry-only cleanup
    either way — the deferral schedules that one replacement directly. The
    attempt-cap guard is bypassed exactly at its boundary for this variant:
    the cap bounds whole-budget re-runs, while this replacement only
    redelivers the terminal branch's cleanup.

    ``deadline`` optionally carries an existing absolute post-budget
    deadline (the terminal recovery's), so replacement creation and the
    cleanup drains it feeds through ``attempt_state`` share one wall instead
    of stacking fresh allowances against the route cap."""
    if not is_cloud_tasks_dispatch_enabled():
        return _budget_deferral_fallback('dispatch_disabled', 'degraded')
    try:
        payload = dict(await request.json())
        job_id = payload['job_id']
        uid = payload['uid']
        deferrals = payload.get(SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY, 0)
        if isinstance(deferrals, bool) or not isinstance(deferrals, int) or deferrals < 0:
            raise ValueError('budget deferral count must be a non-negative integer')
    except Exception as error:
        logger.warning(
            'event=sync_transcription_job outcome=handler_budget_replacement_failed exception_type=%s',
            type(error).__name__,
        )
        return _budget_deferral_fallback('malformed', 'degraded')
    if deferrals + 1 >= get_sync_tasks_max_attempts() and not terminal_cleanup:
        # Original delivery plus replacements have used the whole attempt
        # contract. Ending here through the queue leaves the lock preserved for
        # any live leaf; once it expires, the stale self-heal on the status
        # poll finalizes the job through the owned finalizer. The
        # terminal-cleanup variant is exempt exactly at this boundary: its
        # replacement never re-runs a whole budget — it redelivers the
        # terminal branch's retry-only cleanup — and without it a direct
        # backfill job's unconfirmed-release 409s would spend the cap with no
        # cleanup retry ever landing and the per-UID slot held to its TTL
        # (direct deliveries have no sequencer sweep to fail the job later).
        logger.error(
            'event=sync_transcription_job outcome=handler_budget_deferrals_exhausted deferrals=%d',
            deferrals,
        )
        return _budget_deferral_fallback('deferrals_exhausted', 'exhausted')
    # One absolute deadline for all post-budget work — the sequencer
    # owner-count write, run-lock acquire drain, marker, and replacement
    # enqueue: each block getting its own margin-sized timeout would sum to
    # the whole route margin, letting the middleware 504 fire before the
    # deferral response is returned. The same deadline object is carried into
    # the post-attempt cleanup waits (marker drain and clear, heartbeat drain)
    # through attempt_state, so a slow enqueue cannot buy each cleanup wait a
    # fresh margin-sized timeout either.
    post_budget_deadline = (
        deadline if deadline is not None else time.monotonic() + SYNC_JOB_BUDGET_REPLACEMENT_ENQUEUE_TIMEOUT_SECONDS
    )
    if attempt_state is not None:
        attempt_state['post_budget_deadline'] = post_budget_deadline
    if payload.get('sequencer_epoch') is not None:
        # Sequenced deliveries only, and REQUIRED BEFORE anything schedules a
        # replacement: the sweep's lease-expiry redrive re-dispatches the
        # owner's original payload, which carries no chain count — the
        # owner-side copy is the only bound on that path. The replacement is
        # scheduled past the lease (RUN_LOCK_TTL + 60s), so a redrive can
        # always arrive before it; without the count persisted first, that
        # redrive restarts the chain at zero and invalidates the
        # already-scheduled epoch. A write that fails or cannot settle inside
        # the shared deadline therefore aborts the deferral BEFORE the marker
        # or enqueue exists — the queue-owned 409 keeps the task, and no
        # unbounded whole-budget sequence can be restored behind a lost
        # count. Only an owner that has moved on (completed/released, or a
        # newer epoch) makes the write inert: nothing left can redrive this
        # job from the owner, so the deferral may proceed.
        owner_count_write = asyncio.ensure_future(
            run_blocking(
                db_executor,
                sync_backfill_sequencer.note_budget_deferral,
                uid,
                job_id,
                int(payload['sequencer_epoch']),
                deferrals + 1,
            )
        )
        try:
            async with asyncio.timeout_at(post_budget_deadline):
                owner_count_written = await asyncio.shield(owner_count_write)
        except Exception as error:
            logger.warning(
                'event=sync_transcription_job outcome=handler_budget_owner_deferral_write_failed exception_type=%s',
                type(error).__name__,
            )
            # The timeout cancels only the await: the Firestore transaction
            # can still be running in db_executor and commit later. An
            # abandoned leaf that lands records active_budget_deferrals with
            # no marker or replacement behind it — the sequencer sweep then
            # reads the count plus absent marker as an exhausted chain and
            # terminally fails the job a whole attempt short. Drain the
            # retained write within the cleanup allowance: a settled True
            # rescues the deferral (the count the sweep will see is exactly
            # the one this chain carries), a settled False/exception is the
            # plain failure below, and a write that cannot settle skips the
            # rescue and keeps the queue-owned 409 — with the leaf's possible
            # late commit fenced by the sweep's own lease-expiry recheck of
            # the owner it would read.
            rescued: Optional[bool] = None
            try:
                async with asyncio.timeout_at(post_budget_deadline + SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS):
                    rescued = await asyncio.shield(owner_count_write)
            except Exception:
                _consume_detached_outcome(owner_count_write)
                logger.warning('event=sync_transcription_job outcome=handler_budget_owner_deferral_drain_failed')
            if rescued is None:
                return _budget_deferral_fallback('owner_write_failed', 'degraded')
            # A settled False is the inert owner (moved on, nothing written)
            # — the same proceed-outcome as the settled path; only a write
            # that cannot settle at all keeps the queue-owned 409.
            owner_count_written = rescued
            # The drain consumed the original enqueue window, so the rescued
            # deferral's remaining work (acquire drain, marker, replacement
            # enqueue) runs against the drain's absolute wall — the one
            # cleanup allowance past the original deadline that the wrapper's
            # heartbeat drain also bounds itself by — instead of the
            # already-expired deadline, whose instant expiry would turn every
            # rescue into a marker_timeout/enqueue_failed 409 and leave the
            # late commit the drain just rescued with no replacement behind
            # it. attempt_state carries the extended wall so the wrapper's
            # post-response drains share it instead of stacking a fresh
            # allowance on top.
            post_budget_deadline += SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS
            if attempt_state is not None:
                attempt_state['post_budget_deadline'] = post_budget_deadline
            logger.info('event=sync_transcription_job outcome=handler_budget_owner_deferral_late_commit_rescued')
        if owner_count_written is False:
            logger.info('event=sync_transcription_job outcome=handler_budget_owner_deferral_inert')
    # The expiry that reached here may have cancelled only the await of the run
    # lock acquire: its executor leaf can still land the TTL'd SET minutes
    # later, so a schedule computed from now can come due while that lock is
    # held and spend the replacement's whole short-backoff attempt contract on
    # 409s. The replacement is therefore anchored to a confirmed acquisition —
    # the drained acquire's completion upper-bounds the instant Redis started
    # the TTL — and an acquire that cannot be settled inside the shared
    # deadline leaves that start unbounded: no schedule is provably past the
    # lock, so the deferral refuses to guess and keeps the queue-owned 409.
    acquire = attempt_state.get('run_lock_acquire') if attempt_state is not None else None
    acquired_at: Optional[float] = None
    if acquire is not None:
        try:
            async with asyncio.timeout_at(post_budget_deadline):
                await asyncio.shield(acquire)
            acquired_at = time.time()
        except Exception as error:
            logger.warning(
                'event=sync_transcription_job outcome=handler_budget_deferral_acquire_unsettleable exception_type=%s',
                type(error).__name__,
            )
            _consume_detached_outcome(acquire)
            return _budget_deferral_fallback('acquire_unsettled', 'degraded')
    schedule_at = int(
        (acquired_at if acquired_at is not None else time.time()) + SYNC_JOB_BUDGET_REPLACEMENT_DELAY_SECONDS
    )
    payload[SYNC_JOB_BUDGET_DEFERRALS_PAYLOAD_KEY] = deferrals + 1
    enqueue_started = False
    marker_write: Optional[asyncio.Future] = None
    if terminal_cleanup:
        # The terminal-job variant skips the marker entirely: the write's
        # stale-poll protection is moot on a job whose status poll is already
        # answered, and update_sync_job's terminal-state refusal would turn
        # this deferral into a permanent marker_failed 409 loop — spending
        # every short-backoff queue retry against the surviving lock with no
        # scheduled replacement behind them.
        logger.info(
            'event=sync_transcription_job outcome=handler_budget_terminal_cleanup_replacement_deferred '
            'job_status=terminal deferrals=%d',
            deferrals + 1,
        )
        try:
            async with asyncio.timeout_at(post_budget_deadline):
                await run_blocking(db_executor, enqueue_sync_job_budget_replacement, payload, schedule_at)
        except Exception as error:
            uncertain_enqueue = _is_uncertain_enqueue_error(error)
            logger.warning(
                'event=sync_transcription_job outcome=handler_budget_terminal_cleanup_replacement_failed '
                'exception_type=%s uncertain=%s',
                type(error).__name__,
                int(uncertain_enqueue),
            )
            if uncertain_enqueue:
                return _budget_deferral_fallback('enqueue_uncertain', 'degraded')
            return _budget_deferral_fallback('enqueue_failed', 'degraded')
        logger.info(
            'event=sync_transcription_job outcome=handler_budget_deferred replacement_at=%d deferrals=%d',
            schedule_at,
            deferrals + 1,
        )
        return JSONResponse(status_code=200, content={'status': SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS})
    try:
        async with asyncio.timeout_at(post_budget_deadline):
            # Marker first, and required: the preserved run lock expires before
            # the replacement is due, so without the marker a status poll in
            # that unlocked gap can terminally fail the job before its
            # continuation runs. A failed marker write therefore falls back to
            # the queue-owned 409 rather than acking against an unprotected
            # poll window.
            # A budget-deferred job's protection must outlast the replacement's
            # scheduled time: the backfill lane is concurrency-capped, so a
            # replacement can sit queued well past its schedule_at before a
            # worker picks it up. The stale poller's own congestion allowance
            # (QUEUED_DISPATCH_STALE_SECONDS) is exactly the horizon to reuse —
            # the marker expires only after the job would already be
            # dispatch-lost by normal queued-staleness had it never deferred.
            # The write runs as a retained, shielded task: the deadline expiry
            # cancels only the await below while the CAS keeps running in
            # db_executor, and the retained task is what the cleanup path
            # drains before any clear — a late-applied marker can then never
            # land after the clear that exists to remove it.
            marker_write = asyncio.ensure_future(
                run_blocking(
                    db_executor,
                    update_sync_job,
                    job_id,
                    {'deferred_until': schedule_at + QUEUED_DISPATCH_STALE_SECONDS},
                )
            )
            try:
                # update_sync_job's failure sentinel on a non-None check: a
                # missing/nonmutable job or a CAS that lost every retry. The
                # marker is not on the job, so the deferral must not continue
                # as if it were. The EVAL can still have applied server-side
                # while the client lost the response, so the fallback below
                # performs the same ordered drain-and-clear as the timeout
                # class instead of returning while a live marker survives.
                if await asyncio.shield(marker_write) is None:
                    raise RuntimeError('deferred marker write did not apply')
            except Exception as error:
                logger.warning(
                    'event=sync_transcription_job outcome=handler_budget_deferral_marker_failed exception_type=%s',
                    type(error).__name__,
                )
                await _clear_deferral_marker_after_failed_replacement(marker_write, job_id, post_budget_deadline)
                return _budget_deferral_fallback('marker_failed', 'degraded')
            # Flagged before the enqueue call, not after: a deadline expiry
            # while the marker write itself is still awaiting must be
            # classified as a marker failure (the enqueue never ran and no
            # replacement can exist), not as an uncertain enqueue whose
            # marker-retention semantics assume a possibly-created task.
            enqueue_started = True
            await run_blocking(db_executor, enqueue_sync_job_budget_replacement, payload, schedule_at)
    except Exception as error:
        uncertain_enqueue = enqueue_started and _is_uncertain_enqueue_error(error)
        logger.warning(
            'event=sync_transcription_job outcome=handler_budget_replacement_failed ' 'exception_type=%s uncertain=%s',
            type(error).__name__,
            int(uncertain_enqueue),
        )
        if uncertain_enqueue:
            # An exception here is not proof of non-creation: a transport or
            # deadline failure may have left the named task alive, and the
            # marker's whole purpose is to guard the poll window until a
            # scheduled continuation runs. Clearing it would let a status poll
            # terminally stale-finalize the job in the gap before a replacement
            # that may still arrive, so the marker stays and the fallback keeps
            # queue-owned retries against it.
            return _budget_deferral_fallback('enqueue_uncertain', 'degraded')
        if not enqueue_started:
            # The deadline expired before the enqueue call began — most
            # plausibly while the marker write itself was still awaiting its
            # Redis executor call. No replacement can exist, so this is the
            # marker-failure class: the marker clear below removes any
            # late-applied marker (with no replacement it is the exact
            # nonterminal stall that clear exists to prevent), and the
            # recorded reason distinguishes it from a failed create call.
            fallback_reason = 'marker_timeout'
        else:
            fallback_reason = 'enqueue_failed'
        await _clear_deferral_marker_after_failed_replacement(marker_write, job_id, post_budget_deadline)
        return _budget_deferral_fallback(fallback_reason, 'degraded')
    logger.info(
        'event=sync_transcription_job outcome=handler_budget_deferred replacement_at=%d deferrals=%d',
        schedule_at,
        deferrals + 1,
    )
    return JSONResponse(status_code=200, content={'status': SYNC_JOB_HANDLER_BUDGET_DEFERRED_STATUS})


async def _release_expired_attempt_run_lock(
    attempt_state: dict, *, deadline: Optional[float] = None, strict: bool = False
) -> bool:
    """Release a budget-expired attempt's run lock once its job is terminal.

    A terminal Redis transition is the pipeline's proven result: the
    redelivery's terminal branch only retries exact-job cleanup and never
    re-transcribes, so the preserved lock no longer protects anything this
    attempt owns. Best-effort — a failed release keeps the lock until its TTL
    and the redelivery defers against it, exactly the lease-loss path. The
    optional deadline bounds the release to the remaining response headroom;
    expiry skips it, again leaving the lock to its TTL.

    ``strict=True`` demands a confirmed release: the caller returns 500 so
    the queue redelivers into the terminal branch's retry-only cleanup, and
    an unconfirmed release must not stand behind that obligation. With the
    lock surviving to its TTL, every short-backoff queue retry would deflect
    off the still-held 30-minute lock as a 409 — spending the task's whole
    attempt contract without one cleanup retry landing; a direct backfill
    job's per-UID slot would then stay held for its ~2-day TTL because no
    later terminal poll releases it. Those callers fall back to the
    preserved-lock deferral instead, which acks and schedules one
    replacement past the lock's TTL.
    """
    job_id = attempt_state.get('job_id')
    lock_token = attempt_state.get('lock_token')
    if not isinstance(job_id, str) or not isinstance(lock_token, str) or not lock_token:
        return False
    release = release_job_run_lock_strict if strict else release_job_run_lock
    try:
        if deadline is None:
            return bool(await run_blocking(db_executor, release, job_id, lock_token))
        async with asyncio.timeout_at(deadline):
            return bool(await run_blocking(db_executor, release, job_id, lock_token))
    except Exception as error:
        logger.warning(
            'event=sync_transcription_job outcome=terminal_expiry_lock_release_failed exception_type=%s',
            type(error).__name__,
        )
        return False


async def _run_sync_job_body(request: Request, task_retry_count: int, attempt_state: Optional[dict] = None):
    """Run one Cloud Tasks attempt inside the in-request budget.

    The budget anchors here, at handler entry, so payload parsing, lock
    admission, staged-file downloads, and the pipeline share one deadline
    instead of the pipeline budget starting only after pre-pipeline I/O. On
    expiry the attempt is cancelled exactly like a lost lease: the run lock
    and staged audio stay held, so a replacement attempt can never overlap an
    executor leaf that cancellation cannot stop. Because that lock outlives
    every queue-level retry, the attempt acks and schedules one delayed
    replacement instead of returning a 409 that would burn the task's retry
    budget against the preserved lock. An expiry before lock admission owns
    nothing — no lock to outlive, no leaf to overlap — and keeps the
    queue-owned 409 retry instead of that replacement delay. (Post-attempt
    sequencer cleanup in the caller stays outside the budget on purpose: once
    an attempt has produced its response, expiring there must not rewrite it.)
    """
    # Set by _run_sync_job_attempt immediately before it first reaches the run
    # lock: only then does an expiry have a preserved lock whose TTL the
    # replacement delay must outlive. A caller-provided state dict (the
    # sequenced wrapper) also receives the shared post-budget deadline so its
    # post-attempt cleanup waits cannot each spend a fresh margin.
    state = attempt_state if attempt_state is not None else {}
    # The sequenced wrapper performs fence/begin/prior-read I/O before this
    # point; a deadline captured there anchors the budget to route entry so
    # that preamble time is charged against the same single wall. Direct
    # deliveries pass no anchor and get a fresh full budget.
    anchored_deadline = state.get('budget_deadline_monotonic')
    remaining = (
        max(0.0, anchored_deadline - time.monotonic())
        if isinstance(anchored_deadline, float)
        else SYNC_JOB_HANDLER_BUDGET_SECONDS
    )
    budget = asyncio.timeout(remaining)
    try:
        async with budget:
            return await _run_sync_job_attempt(request, task_retry_count, state)
    except TimeoutError:
        if not budget.expired():
            raise
        if not state.get('run_lock_reached'):
            logger.warning('event=sync_transcription_job outcome=handler_budget_expired lock=none')
            return _budget_deferral_fallback('pre_lock_expiry', 'degraded')
        # A pipeline that already published a terminal result can be cancelled
        # while its staged-blob/backfill-slot cleanup is still awaiting. The
        # deferral cannot write its marker (update_sync_job rejects terminal
        # jobs), so its 409 would burn the queue's retries against the
        # preserved lock and hold the per-UID backfill slot until slot TTL.
        # The established terminal_cleanup_retry 500 redelivers into the
        # terminal branch, which retries only the exact-job cleanup and never
        # re-transcribes, with the run lock released now that no leaf of this
        # attempt owns it.
        job_id = state.get('job_id')
        if isinstance(job_id, str):
            # Bounded by the same post-budget deadline contract as the
            # deferral's marker/enqueue work: this Redis read and the lock
            # release below run after the budget expired, so without a bound a
            # backlogged db_executor or a stalling Redis could consume the
            # whole response margin and let the middleware or the Cloud Tasks
            # dispatch deadline terminate the request first — recreating the
            # lingering-attempt behavior this budget exists to prevent.
            # Expiry falls back conservatively: skip the recovery and defer,
            # exactly as when the read fails.
            recovery_deadline = time.monotonic() + SYNC_JOB_POST_ATTEMPT_CLEANUP_TIMEOUT_SECONDS
            try:
                async with asyncio.timeout_at(recovery_deadline):
                    expired_job = await run_blocking(db_executor, get_sync_job, job_id)
            except Exception as error:
                logger.warning(
                    'event=sync_transcription_job outcome=handler_budget_expired_terminal_read_failed '
                    'exception_type=%s',
                    type(error).__name__,
                )
                expired_job = None
            if expired_job is not None and expired_job.get('status') in TERMINAL_STATUSES:
                logger.error(
                    'event=sync_transcription_job status=terminal_cleanup_retry job_status=%s '
                    'outcome=handler_budget_expired',
                    expired_job.get('status'),
                )
                # The 500 below hands the queue a retry-only obligation (the
                # redelivery's terminal branch never re-transcribes), so the
                # release behind it must be confirmed: an unconfirmed release
                # leaves the lock held to its TTL while every short-backoff
                # retry deflects off it as a 409 — the task exhausts without
                # one cleanup retry landing, and a direct backfill job's
                # per-UID slot then sticks for its ~2-day TTL. An
                # unconfirmable release keeps the preserved-lock contract
                # instead: ack and schedule one replacement past the lock's
                # TTL, exactly like a nonterminal budget expiry.
                if not await _release_expired_attempt_run_lock(state, deadline=recovery_deadline, strict=True):
                    logger.warning(
                        'event=sync_transcription_job outcome=terminal_cleanup_retry_release_unconfirmed '
                        'job_status=%s',
                        expired_job.get('status'),
                    )
                    # The deferral inherits this recovery's absolute deadline
                    # (not a fresh enqueue allowance) so replacement creation
                    # and the heartbeat drain it feeds stay inside the one
                    # post-budget wall the route margin was sized for.
                    return await _defer_sync_job_after_handler_budget_expiry(
                        request, state, terminal_cleanup=True, deadline=recovery_deadline
                    )
                return JSONResponse(
                    status_code=500,
                    content={'status': 'terminal_cleanup_retry', 'job_status': expired_job.get('status')},
                )
        logger.warning('event=sync_transcription_job outcome=handler_budget_expired lock=preserved')
        return await _defer_sync_job_after_handler_budget_expiry(request, state)


@sync_attempt
async def _run_sync_job_attempt(request: Request, task_retry_count: int, attempt_state: dict):
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
        redrive_mode = minimal_redrive.parse_mode(payload)
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
    # Marked before the acquire is issued, not after it returns: an expiry that
    # lands mid-acquire can still leave the lock held inside the executor, so it
    # must take the preserved-lock deferral rather than the pre-lock branch.
    attempt_state['run_lock_reached'] = True
    # The expiry handler needs the identity of the lock it may have to release
    # (terminal-during-cleanup recovery) — recorded before the acquire for the
    # same mid-acquire-expiry reason.
    attempt_state['job_id'] = job_id
    acquire_task_lock = try_acquire_sync_job_run_lock if ledger_fence_active else try_acquire_job_run_lock
    # Flagged before the acquisition call, not after: a cancellation landing
    # mid-acquire can still leave the Redis lock held, so the expiry handler
    # must already treat this attempt as lock-owning (conservative deferral).
    attempt_state['run_lock_reached'] = True
    # The acquire itself runs as a retained, shielded task: a budget expiry
    # cancels only the await — the executor leaf can still land the TTL'd SET
    # afterwards — so the pending task is left on attempt_state for the
    # deferral to drain and anchor the replacement's schedule to the confirmed
    # acquisition. A settle here (token or empty) leaves nothing to drain, and
    # the entry is removed before the attempt continues.
    acquire = asyncio.ensure_future(run_blocking(db_executor, acquire_task_lock, job_id))
    attempt_state['run_lock_acquire'] = acquire
    lock_token = await asyncio.shield(acquire)
    attempt_state.pop('run_lock_acquire', None)
    attempt_state['lock_token'] = lock_token
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
            start_background_task(
                run_blocking(storage_executor, warm_owner, uid, job_id, sequencer_epoch),
                name='sync:owner-prefetch',
            )
        if sync_lane == SyncLane.BACKFILL.value:
            staged = await run_blocking(storage_executor, _download_staged_files, blob_paths, bounded_backfill=True)
        else:
            staged = await run_blocking(storage_executor, _download_staged_files, blob_paths)
        if not staged:
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
            # The in-request budget (see _run_sync_job_body) wraps this whole
            # attempt; on expiry the coordinator is cancelled like a lease loss
            # and the wrapper preserves the run lock for the redelivery.
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
                    **({'redrive_mode': redrive_mode} if redrive_mode else {}),
                )
        except BackfillStoragePressure:
            raise
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
                    **stamped_failure_kwargs(e),  # internal cause, not upstream_error
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
    except (BackfillInputLimitExceeded, BackfillStoragePressure) as error:
        # Defer capacity pressure without a terminal invalid-input result. Reset
        # processing so the stale detector cannot fail it during task backoff.
        if ledger_fence_active:
            mutation = await run_blocking(
                db_executor,
                fenced_mark_job_queued_for_retry,
                job_id,
                lock_token,
                task_retry_count + 1,
                'sync_resource_limit',
            )
            queued = mutation.applied
        else:
            queued = await run_blocking(
                db_executor, mark_job_queued_for_retry, job_id, task_retry_count + 1, 'sync_resource_limit'
            )
        if not queued:
            release_lock = False
            return JSONResponse(status_code=409, content={'status': 'locked'})
        # 409, not 503: a fast 503 reads as target overload and slows the whole
        # queue, and over-limit legacy input fails identically on every attempt.
        logger.warning(
            'event=sync_transcription_job outcome=deferred reason=%s',
            'backfill_input_limit' if isinstance(error, BackfillInputLimitExceeded) else 'backfill_storage_pressure',
        )
        return JSONResponse(status_code=409, content={'status': 'locked'})
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

        if conversation.get('audio_files') and not any(
            af.get('id') == audio_file_id for af in conversation['audio_files']
        ):
            PLAYBACK_WRITES.labels('skipped').inc()
            return JSONResponse(status_code=200, content={'status': 'superseded'})

        existing = await run_blocking(
            storage_executor, get_playback_artifact_signed_url, uid, conversation_id, audio_file_id
        )
        if existing:
            PLAYBACK_WRITES.labels('cache_hit').inc()
            return JSONResponse(status_code=200, content={'status': 'exists'})

        try:
            with PLAYBACK_BUILD_SECONDS.labels('file').time() if playback_on_demand() else nullcontext():
                mp3_data = await run_blocking(
                    sync_executor,
                    sync_playback.build_playback_artifact,
                    uid,
                    conversation_id,
                    timestamps,
                    **(
                        {'source_fingerprint': payload.get('source_fingerprint')}
                        if payload.get('source_fingerprint')
                        else {}
                    ),
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
            PLAYBACK_WRITES.labels('skipped').inc()
            return JSONResponse(status_code=200, content={'status': 'superseded'})

        artifact_fingerprint = compute_audio_files_fingerprint(
            audio_files, origin=conversation.get('started_at') or conversation.get('created_at'), source_identity=True
        )
        stamp = conversation.get('conversation_audio') or {}
        if stamp.get('audio_files_fingerprint') in (fingerprint, artifact_fingerprint) and (
            not conversation.get('conversation_audio_artifact_fingerprint')
            or conversation['conversation_audio_artifact_fingerprint'] == artifact_fingerprint
        ):
            existing = await run_blocking(
                storage_executor,
                get_conversation_playback_signed_url,
                uid,
                conversation_id,
                **(
                    {'fingerprint': conversation.get('conversation_audio_artifact_fingerprint') or fingerprint}
                    if demand or conversation.get('conversation_audio_artifact_fingerprint')
                    else {}
                ),
            )
            if existing:
                PLAYBACK_WRITES.labels('cache_hit').inc()
                return JSONResponse(status_code=200, content={'status': 'exists'})

        started_at_ts = persisted_started_seconds(conversation.get('started_at') or conversation.get('created_at'))
        if started_at_ts is None:
            chunk_starts = [
                min(af['chunk_timestamps']) for af in audio_files if isinstance(af, dict) and af.get('chunk_timestamps')
            ]
            started_at_ts = min(chunk_starts) if chunk_starts else 0.0

        try:
            with PLAYBACK_BUILD_SECONDS.labels('conversation').time() if demand else nullcontext():
                mp3_size, spans = await run_blocking(
                    sync_executor,
                    playback_build.ensure_conversation_artifact,
                    uid,
                    conversation_id,
                    audio_files,
                    started_at_ts,
                    artifact_fingerprint,
                    strict_sources=demand,
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

        captured_duration = round(sum(s['len'] for s in spans), 3)
        wall_duration = round(spans[-1]['wall_offset'] + spans[-1]['len'], 3)
        await run_blocking(
            db_executor,
            conversations_db.update_conversation,
            uid,
            conversation_id,
            {
                'conversation_audio_artifact_fingerprint': artifact_fingerprint,
                'conversation_audio': {
                    'audio_files_fingerprint': artifact_fingerprint,
                    'duration': wall_duration,
                    'captured_duration': captured_duration,
                    'spans': spans,
                    'content_type': 'audio/mpeg',
                    'built_at': datetime.now(timezone.utc),
                },
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
