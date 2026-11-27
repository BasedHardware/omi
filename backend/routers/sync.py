"""Offline capture sync surface: manifest admission, /v2/sync-local-files intake,
the OIDC sync/audio-merge job runners, and playback URL serving.

Fresh and backfill traffic are deliberately split -- backfill never falls back
into fresh/inline capacity and fresh keeps only a bounded inline fallback -- and
job polling is window-admitted because an unbounded reconciler drain produced the
2026-10 edge 429 storm (app/docs/sync-poll-storm.md documents the mechanism).
"""

from database.sync_snapshot_resolve_cache import sync_snapshot_resolve_job
from utils import backfill_hours_cap
from utils.sync import future_capture_request, playback_build
from utils.sync.future_capture_request import Outcome as FutureCaptureOutcome
from utils.other.playback_identity import PlaybackSourceChanged
from utils.capture.coverage_endpoint import router as coverage_router
from utils.observability.sync_upload import compare_recovery_label, observe_hold_age
import asyncio
import logging
import os
import shutil
import time
import uuid as _uuid
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from config.request_clock import bounded_hold_state, started_at
from utils.batch_pipeline import upload_entitlement
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, Request, Response, Header
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from config.policy import resolve_batch_policy
from config.reliability_experiments import enabled as experiment, warm as warm_experiments
from config.policy.ramp import audio_span
from database.batch_ramp import ramp_admission_policy
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from utils.sync.recovery_source import recovery_source_conversation
from utils.sync.deleted_conversation import deleted_conversation_result, is_conversation_deleted
from utils.sync import designed_refusal
from database.account_deletion_marker import account_deletion_blocks_user_work
from utils.batch_pipeline.intake import (
    accept_upload as accept_batch_upload,
    get_durable_job_status,
    repair_upload_owner_matches,
    privacy_blocked_response,
)
from utils.batch_pipeline.intake_outcome import IntakeRouteEvidence, record_upload_outcome
from models.sync_job_status import (
    SyncJobStartResponse,
    SyncReceiptsWaitRequest,
    SyncReceiptsWaitResponse,
    SyncJobStatusResponse,
    SyncCaptureManifestRequest,
    SyncCaptureManifestResponse,
    SyncCaptureEndRequest,
    SyncCaptureEndResponse,
    SyncUploadHoldReleaseResponse,
)
from routers.enrichment import enrichment_response
from database import conversations as conversations_db
from database import record_audio as record_audio_db
from config import record_seal_rules as record_lease
from utils.sync import record_token_lease as custody_lease
from utils.sync import capture_end
from database import capture_end as capture_end_db
from database import pipeline_ledger
from database import fair_use as fair_use_db
from database import sync_dead_letters
from database import users as users_db
from database.firestore_transaction_retry import is_transaction_retry_failure
from database.firestore_read_metrics import FirestoreReadSite
from database.firestore_read_origin import read_origin
from database.sync_jobs import (
    SyncLedgerFenceMode,
    delete_sync_job_run_lock_epoch,
    get_sync_ledger_fence_mode,
    sync_ledger_fence_standby_configured,
    get_sync_job,
    is_sync_job_stale,
    sync_job_uses_ledger_fence,
    try_acquire_sync_job_run_lock,
    try_acquire_job_run_lock,
    release_job_run_lock,
)
from database.sync_ledger import release_sync_content_claim, release_sync_content_claim_after_job_retired
from models.sync_contract import SYNC_LOCAL_FILES_V2_RESPONSES
from models.geolocation import geolocation_from_private_header
from models.sync_audio import AudioPrecacheResponse, AudioUrlsResponse
from routers.listen.contracts import persisted_started_seconds
from utils.sync.admission_responses import sync_finalization_retrying
from utils.other import endpoints as auth
from utils.account_cutover.access import should_skip_background_account_mutation
from utils.other.storage import (
    archive_mobile_batch_raw_files,
    get_playback_artifact_signed_url,
    upload_playback_artifact,
    mark_playback_unavailable,
    compute_audio_files_fingerprint,
    get_conversation_playback_signed_url,
    mark_conversation_playback_unavailable,
)
from utils.byok import has_byok_keys
from utils.cloud_tasks import (
    enqueue_audio_merge_job_deferred,
    get_sync_tasks_max_attempts,
    is_cloud_tasks_dispatch_enabled,
    verify_audio_merge_cloud_tasks_oidc,
    verify_cloud_tasks_oidc,
)
from utils.executors import (
    critical_executor,
    db_executor,
    postprocess_executor,
    storage_executor,
    sync_executor,
    run_blocking,
)
from utils.fair_use import get_hard_restriction_status, is_daily_audio_ceiling_exceeded
from utils.observability.fallback import record_fallback
from utils.multipart import MultipartMaxPartSizeRoute, SYNC_AUDIO_MAX_PART_SIZE, max_part_size
from utils.metrics import (
    OMI_SYNC_JOB_POLL_REQUESTS_TOTAL,
    OMI_SYNC_JOB_POLL_THROTTLED_TOTAL,
    OMI_SYNC_LANE_ADMISSIONS_TOTAL,
    OMI_SYNC_RECORDING_AGE_SECONDS,
)
from utils.sync.poll_limit import SYNC_POLL_WINDOW_SECONDS, admit_sync_job_poll, with_custody_hold_poll_hint
from utils.sync.retired_handle_ack import acknowledge_retired_handle
from config.repeat_work import playback_on_demand
from contextlib import nullcontext
from utils.sync.repeat_work_metrics import (
    PLAYBACK_WRITES,
    PLAYBACK_BUILD_SECONDS,
    PLAYBACK_BUILDS,
    record_demand_playback_outcome,
    record_playback_ready,
)
from utils.product_metrics import record_product_event, sanitize_app_build
from utils.journey_metrics_contract import resolve_client_kind
from utils.client_device import resolve_client_device
from config.firestore_read_levers import lever_enabled
from utils.subscription import (
    TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS,
    has_transcription_credits,
    resolve_transcription_allowance,
)
from utils.sync import playback as sync_playback
from utils.sync.input_limits import BackfillInputLimitExceeded, validate_backfill_uploads, validate_backfill_paths
from config.rollout_cohorts import warm_rollout_cohorts
from utils.sync.recording_lineage import parse_s1_upload_claims
from utils.sync.files import detect_source_from_filenames, get_timestamp_from_path
from utils.sync.ledger_completion import SyncJobRunLeaseLost, bind_or_converge_sync_ledger_completion
from utils.sync.legacy_segment_core import (
    _cleanup_files,
    finalize_sync_job_failure_now,
    _record_capture_time_admission,
    _retrieve_file_paths_v2,
)
from utils.sync.empty_upload import EmptySyncUpload, prepare_sync_uploads, nonempty_manifest_claims
from utils.sync.job_retry_policy import terminal_repeat_failure_kwargs
from utils.sync.capture_clock import (
    INVALID_CAPTURE_TIME_CODE,
    INVALID_CAPTURE_TIME_DETAIL,
    SyncCaptureTimeRejected,
    capture_clock_offset,
    capture_time_rejection,
    future_capture_clamp_enabled,
    is_early_capture_time,
    is_implausible_future_capture_time,
)
from utils.sync.clock_run import capture_clock_run_from_path
from utils.sync.receipt_clock import (
    POLICY as RECEIPT_CLOCK_POLICY,
    ESTIMATED_POLICY,
    FutureCaptureRefused,
    require_future_upload,
    retained_source_offsets,
)
from utils.stt.outcomes import TranscriptionOutcome
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
)
from utils.batch_pipeline.live_upload import (
    RecordUploadRoute,
    has_conversation_wait_hint,
    memoized_record_wait,
    registered_record_response,
)
from utils.sync.content_id import compute_sync_content_id
from utils.sync.capture_manifest import (
    claim_conversation_manifest,
    issue_capture_manifest,
    issue_retry_handle,
    valid_retry_handle,
    manifest_claims_match_paths,
    verify_capture_manifest,
)
from utils.sync.lanes import CaptureTimeTrust, SyncLane, classify_sync_lane
from utils.sync import legacy_dark, stage as sync_stage
from utils.sync.provenance import capture_matches_server_conversation as _capture_matches_server_conversation

from utils.sync import batch_census, cap_hold_redrive

logger = logging.getLogger(__name__)

# Give short account-operation fences a chance to clear before asking the
# client to pause. Persistent holds use a short, bounded in-request recheck.
SYNC_DISPATCH_HOLD_RETRY_AFTER_SECONDS = 60
SYNC_DISPATCH_HOLD_RECHECK_SECONDS = 2.0
SYNC_DISPATCH_HOLD_RECHECK_INTERVAL_SECONDS = 0.1


# Audio constants
AUDIO_SAMPLE_RATE = 16000

_V1_DEPRECATION_HEADERS = {'Deprecation': 'true', 'Link': '</v2/sync-local-files>; rel="successor-version"'}

# How far past the newest admitted filename start a claimed session end may
# run: one live-capture chunk of trailing audio, mirroring the trailing
# allowance recording-session binding itself grants (recording_session_target).
# Decode has not run at the staging seam, so the last file's duration is the
# one admitted-audio fact this slack stands in for.
SESSION_CLAIM_TRAILING_SLACK_SECONDS = 60.0


router = APIRouter(route_class=MultipartMaxPartSizeRoute, dependencies=[Depends(sync_stage.require_http_stage)])
router.include_router(coverage_router)


async def _renew_custody_lease(uid, conversation_id):
    if not record_lease.token_lease_serving(uid):
        return
    try:
        await run_blocking(
            db_executor,
            record_audio_db.renew_record_token_lease,
            uid,
            conversation_id,
            source='custody_append',
        )
    except Exception as error:
        logger.warning('event=record_token_lease_renewal outcome=unavailable exception_type=%s', type(error).__name__)
        raise HTTPException(status_code=503, detail='Retain local audio and retry custody admission') from error


@router.post('/v2/sync-capture-manifest', response_model=SyncCaptureManifestResponse)
async def create_sync_capture_manifest(
    payload: SyncCaptureManifestRequest,
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
    x_device_id_hash: Optional[str] = Header(None, alias='X-Device-Id-Hash'),
    x_app_version: Optional[str] = Header(None, alias='X-App-Version'),
    retry_handle: Optional[str] = Header(None, alias='X-Omi-Wal-Retry', include_in_schema=False),
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
    await _renew_custody_lease(uid, payload.conversation_id)
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
    # This service may differ from backend-sync. Invite a probe only while a
    # memo exists. All manifest effects above still happen on their normal route.
    if valid_retry_handle(retry_handle, uid, device.client_device_id, payload.conversation_id, claims):
        try:
            if await has_conversation_wait_hint(uid, payload.conversation_id):
                return JSONResponse(content={'manifest': manifest}, headers={'X-Omi-Wal-Retry': 'check'})
        except Exception:
            pass
    return SyncCaptureManifestResponse(manifest=manifest)


@router.put(
    '/v2/sync-local-files',
    status_code=204,
    response_class=Response,
    responses={503: {'description': 'Only a typed record_capture_pending response defers the multipart upload'}},
)
async def check_sync_retry(
    payload: SyncCaptureManifestRequest,
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
    x_device_id_hash: Optional[str] = Header(None, alias='X-Device-Id-Hash'),
    retry_handle: Optional[str] = Header(None, alias='X-Omi-Wal-Retry'),
):
    """Check a live wait after manifest admission. A 204 directs the client to upload."""
    device = resolve_client_device(x_app_platform=x_app_platform, x_device_id_hash=x_device_id_hash)
    claims = [item.model_dump() for item in payload.files]
    if valid_retry_handle(retry_handle, uid, device.client_device_id, payload.conversation_id, claims):
        try:
            wait = await memoized_record_wait(uid, payload.conversation_id)
        except Exception:
            wait = None
        if wait is not None and valid_retry_handle(
            retry_handle, uid, device.client_device_id, payload.conversation_id, claims
        ):
            return wait
    return Response(status_code=204)


def _store_capture_end(uid: str, recording_session_id: str, marker: dict) -> str:
    outcome, conversation_id = capture_end_db.store(uid, recording_session_id, marker)
    if outcome == 'stored' and conversation_id:
        # Fail-open measurement: the marker is already durable on the session.
        pipeline_ledger.record_end(
            uid,
            conversation_id,
            end_type=marker['end_type'],
            end_at=marker['end_at'],
            end_observed_at=marker['end_observed_at'],
            last_speech_at=marker['last_speech_at'],
        )
    return outcome


@router.post('/v2/sync-capture-end', response_model=SyncCaptureEndResponse)
async def record_sync_capture_end(
    payload: SyncCaptureEndRequest,
    uid: str = Depends(auth.get_current_user_uid),
):
    """The phone states that a recording ended and how much of it is uploaded.

    Stored on the recording's own session document. It lets notes start once
    the recording's speech has landed, without the arrival-quiet wait. It never
    changes custody and never deletes or finalizes anything itself.
    """
    if not capture_end.enabled():
        capture_end.record_received(payload.end_type, 'disabled')
        return SyncCaptureEndResponse(accepted=False)
    try:
        marker = capture_end.normalize(
            end_type=payload.end_type,
            last_speech_at=payload.last_speech_at,
            end_decided_at=payload.end_decided_at,
            sent_at=payload.sent_at,
            pending_wals=payload.pending_wals,
            received_at=time.time(),
        )
    except ValueError as e:
        capture_end.record_received(payload.end_type, 'invalid')
        raise HTTPException(status_code=422, detail='Invalid capture end') from e
    try:
        outcome = await run_blocking(db_executor, _store_capture_end, uid, payload.recording_session_id, marker)
    except Exception as e:
        logger.error('sync capture end unavailable uid=%s error=%s', uid, type(e).__name__)
        raise HTTPException(status_code=503, detail='Capture end is temporarily unavailable') from e
    capture_end.record_received(marker['end_type'], outcome)
    # No session yet: no upload for this recording has been bound. The phone's
    # resend after its last accepted file covers that case.
    return SyncCaptureEndResponse(accepted=outcome != 'unbound', retry=outcome == 'unbound')


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
@router.post("/v1/sync-local-files", deprecated=True, status_code=410)
def sync_local_files(uid: str = Depends(auth.get_current_user_uid)):
    """Retired by legacy-retire C6; v2 is the successor and the client retains local audio."""
    return JSONResponse(
        status_code=410,
        headers=_V1_DEPRECATION_HEADERS,
        content={
            'code': 'sync_v1_retired',
            'detail': 'Use /v2/sync-local-files; local audio was not consumed',
        },
    )


def _backfill_day_cap_defers(uid: str, lane: SyncLane, repair_identity: Optional[str], allowance: Any) -> bool:
    """Whether the unlimited_v2 backfill day cap defers this upload (historical lane only, never repairs)."""
    if lane is not SyncLane.BACKFILL or repair_identity is not None or not backfill_hours_cap.cap_enabled():
        return False
    return backfill_hours_cap.defers_upload(uid, allowance)


@router.post(  # v2 async sync-local-files
    "/v2/sync-local-files",
    status_code=202,
    response_model=SyncJobStartResponse,
    responses=SYNC_LOCAL_FILES_V2_RESPONSES,
)
@max_part_size(SYNC_AUDIO_MAX_PART_SIZE)
@designed_refusal.records_designed_refusals
@custody_lease.custody_upload
@future_capture_request.observe_upload
@designed_refusal.designed_refusal_outcome
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
    repair_job_id: Optional[str] = Query(None, description='Original batch job for an exact custody repair bundle'),
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
    x_omi_wal_retry: Optional[str] = Header(None, alias='X-Omi-Wal-Retry', include_in_schema=False),
    x_omi_upload_trace: Optional[str] = Header(None, alias='X-Omi-Upload-Trace', include_in_schema=False),
    x_omi_upload_hold: Optional[str] = Header(None, alias='X-Omi-Upload-Hold', include_in_schema=False),
    x_omi_upload_recovered: Optional[str] = Header(None, alias='X-Omi-Upload-Recovered', include_in_schema=False),
    x_omi_upload_journal_recovery: Optional[str] = Header(
        None, alias='X-Omi-Upload-Journal-Recovery', include_in_schema=False
    ),
    x_omi_upload_hold_age_ms: Optional[str] = Header(None, alias='X-Omi-Upload-Hold-Age-Ms', include_in_schema=False),
    x_app_build: Optional[str] = Header(None, alias='X-App-Build', include_in_schema=False),
):
    """
    Save raw files and admit supported uploads to the batch pipeline.
    Legacy-owned content is answered by its durable fence; new legacy jobs are retired.
    The app polls GET /v2/sync-local-files/{job_id}.
    """
    # Empty/torn-header clips contain no audio frames. Acknowledge them before
    # clock/age admission; a bogus date on zero audio has nothing to recover.
    upload_filenames = [f.filename or '' for f in files]
    supplied_conversation_id = conversation_id  # Authenticate original custody proof before ignoring a stale target.
    repair_identity = repair_job_id if isinstance(repair_job_id, str) else None
    capture_received_at = time.time()
    upload_arrived_at = started_at.get()
    if upload_arrived_at is None:
        upload_arrived_at = capture_received_at  # Direct/internal adapter without HTTP middleware.
    # Measurement only: how long the oldest file waited on the phone, and why.
    capture_end.observe_trace(
        x_omi_upload_trace if isinstance(x_omi_upload_trace, str) else None,
        received_at=capture_received_at,
        client_headers={
            'x-app-platform': x_app_platform if isinstance(x_app_platform, str) else None,
            'x-app-version': x_app_version if isinstance(x_app_version, str) else None,
            'x-app-build': x_app_build if isinstance(x_app_build, str) else None,
        },
    )
    try:
        files = await run_blocking(sync_executor, prepare_sync_uploads, files, uid)
    except EmptySyncUpload:
        if repair_identity is not None:
            return JSONResponse(
                status_code=409,
                content={
                    'code': 'sync_repair_bundle_changed',
                    'detail': 'The original complete upload is required; retain local audio',
                },
            )
        return JSONResponse(status_code=200, content={'new_memories': [], 'updated_memories': []})
    compare_recovery_label(
        x_omi_upload_journal_recovery if isinstance(x_omi_upload_journal_recovery, str) else None,
        x_omi_upload_recovered,
        x_omi_upload_hold,
    )
    clamp_enabled = future_capture_clamp_enabled()
    if clamp_enabled:
        future_capture_request.classify_upload((file.filename or '' for file in files), capture_received_at)
    try:
        recovery_hint = clamp_enabled and any(
            is_implausible_future_capture_time(get_timestamp_from_path(file.filename or ''), now=capture_received_at)
            or (
                capture_clock_run_from_path(file.filename or '')
                and not is_early_capture_time(get_timestamp_from_path(file.filename or ''))
            )
            for file in files
        )
    except (IndexError, ValueError):
        recovery_hint = False  # Ordinary staging still returns the typed malformed-name refusal.
    recovery_source_id = None
    if recovery_hint:
        try:
            recovery_source_id = await run_blocking(
                db_executor, recovery_source_conversation, uid, supplied_conversation_id
            )
        except BatchPrivacyBlocked as error:
            future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
            return (
                JSONResponse(status_code=200, content=deleted_conversation_result(0))
                if is_conversation_deleted(error)
                else privacy_blocked_response()
            )
        conversation_id = None  # No stale record wait, live-owner lookup or explicit binding for unknown time.
    if repair_identity is None and (recent_wait := await memoized_record_wait(uid, conversation_id)) is not None:
        # The same conversation-level custody wait answered moments ago: repeat
        # it before saving, archiving or decoding these bytes (audio retained).
        future_capture_request.mark(FutureCaptureOutcome.PRIOR_CUSTODY)
        return recent_wait
    if isinstance(recording_session_id, str):
        recording_session_id = recording_session_id.strip() or None
    else:
        recording_session_id = None
    sync_app_build = sanitize_app_build(x_app_version)
    ledger_fence_mode = await run_blocking(db_executor, get_sync_ledger_fence_mode)
    if ledger_fence_mode is SyncLedgerFenceMode.STANDBY:
        future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
        # An invalid setting also fails closed to STANDBY; only a configured cutover is designed.
        if await run_blocking(db_executor, sync_ledger_fence_standby_configured):
            designed_refusal.mark_designed_refusal(uid, 'sync_ledger_fence_cutover', x_cloud_trace_context)
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
        supplied_conversation_id,
        upload_filenames,
    )
    manifest_claims = nonempty_manifest_claims(manifest_claims, filenames)
    record_snapshot = {}
    has_server_capture_proof = (
        not recovery_hint
        and manifest_claims is not None
        and await run_blocking(
            db_executor,
            _capture_matches_server_conversation,
            uid,
            conversation_id,
            filenames,
            client_device_context.client_device_id,
            snapshot_out=record_snapshot,
        )
    )
    # Off the event loop, a cold process gives its first ramp read a bounded wait, so a
    # fresh instance cannot admit legacy work on the 'on' default after the ramp went
    # draining/dark (M3 review; batch intake reads the mode the same way).
    legacy_mode = await run_blocking(db_executor, legacy_dark.current_mode, uid)
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
    if lane_decision.lane is SyncLane.BACKFILL:
        try:
            await run_blocking(sync_executor, validate_backfill_uploads, files)
        except HTTPException:
            future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
            raise
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
        future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
        designed_refusal.mark_designed_refusal(uid, 'backfill_disabled', x_cloud_trace_context)
        return JSONResponse(
            status_code=503,
            headers={'Retry-After': '3600', 'X-Omi-Rate-Limit-Reason': 'backfill_capacity'},
            content={
                'code': 'backfill_capacity',
                'detail': 'Historical recovery is paused; local audio was not consumed',
            },
        )
    try:
        OMI_SYNC_RECORDING_AGE_SECONDS.labels(lane=lane_decision.lane.value).observe(
            lane_decision.maximum_age_seconds or 0
        )
    except Exception:
        pass

    if not lane_decision.automatic_recovery_allowed and repair_identity is None:
        future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
        return JSONResponse(
            status_code=422,
            content={
                'code': 'backfill_lookback_exceeded',
                'detail': 'Recording is older than the automatic recovery window; local audio was not consumed',
                'lane': lane_decision.lane.value,
            },
        )
    if fresh_refused:
        future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
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
    # Reuse the first answer. At 0, preserve the old wrapper + conditional second lookup,
    # including its different lock decision if allowance state changes between calls.
    if lever_enabled('sync_allowance_single_resolve', uid):
        allowance = await run_blocking(critical_executor, resolve_transcription_allowance, uid)
        has_credits = allowance.managed
    else:
        has_credits = await run_blocking(critical_executor, has_transcription_credits, uid)
        allowance = None
    should_lock = False
    if not has_credits:
        if allowance is None:
            allowance = await run_blocking(critical_executor, resolve_transcription_allowance, uid)
        should_lock = (
            allowance.reason not in TRANSCRIPTION_ALLOWANCE_TRANSIENT_REASONS
            and allowance.reason != 'usage_budget_exhausted'
        )

    # The unlimited_v2 backfill day cap is enforced here and only here: an over-cap
    # historical upload is refused retryably before any audio is consumed, so the
    # phone keeps it and retries after the UTC day rolls. No server hold is created.
    if backfill_hours_cap.cap_enabled() and lane_decision.lane is SyncLane.BACKFILL and repair_identity is None:
        if allowance is None:
            allowance = await run_blocking(critical_executor, resolve_transcription_allowance, uid)
        if await run_blocking(
            critical_executor, _backfill_day_cap_defers, uid, lane_decision.lane, repair_identity, allowance
        ):
            future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
            designed_refusal.mark_designed_refusal(uid, 'backfill_day_cap', x_cloud_trace_context)
            return JSONResponse(
                status_code=503,
                headers={
                    'Retry-After': str(retry_after_until_next_utc_day()),
                    'X-Omi-Rate-Limit-Reason': 'backfill_capacity',
                },
                content={
                    'code': 'backfill_capacity',
                    'detail': 'Daily historical recovery limit reached; local audio was not consumed',
                },
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
        await custody_lease.begin_upload(uid, conversation_id, job_id, recording_session_id=recording_session_id)
        # --- Fast path: save raw files only (< 2s typical) ---
        # Use sync_executor, NOT storage_executor — storage is saturated with
        # background pipeline cleanup/GCS work and would queue the 202 response.
        try:
            paths = await run_blocking(sync_executor, _retrieve_file_paths_v2, files, uid, job_id, probe_future=True)
        except SyncCaptureTimeRejected:
            future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
            logger.info('sync_upload_refused uid=%s status=400 reason=invalid_capture_time', uid)
            # Typed 400 for implausible capture times (beyond the shared
            # future-skew tolerance or before 2024). Released clients only see
            # the status + detail; new clients can act on the code.
            return JSONResponse(
                status_code=400,
                content={'code': INVALID_CAPTURE_TIME_CODE, 'detail': INVALID_CAPTURE_TIME_DETAIL},
            )

        retained_capture_offsets = await run_blocking(
            db_executor,
            retained_source_offsets,
            paths,
            uid=uid,
            device_id=client_device_context.client_device_id,
            received_at=capture_received_at,
        )
        # Staging a future clock is only a probe. New 600s-to-24h stamps and
        # disabled recovery still get today's typed 400; retained source proof
        # alone can carry an admitted file through that band on a later retry.
        for path in paths:
            stamp = get_timestamp_from_path(path)
            rejection = capture_time_rejection(
                datetime.fromtimestamp(stamp, timezone.utc),
                now=datetime.fromtimestamp(capture_received_at, timezone.utc),
            )
            if path not in retained_capture_offsets and rejection is not None:
                future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
                _record_capture_time_admission(rejection, ahead_seconds=max(0, stamp - capture_received_at))
                raise FutureCaptureRefused()
        retained_capture = bool(retained_capture_offsets)
        if retained_capture:
            try:
                await run_blocking(sync_executor, validate_backfill_paths, paths)
            except BackfillInputLimitExceeded:
                future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
                raise
            if os.getenv('SYNC_BACKFILL_ENABLED', 'true').lower() != 'true':
                future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
                designed_refusal.mark_designed_refusal(uid, 'retained_recovery_disabled', x_cloud_trace_context)
                raise HTTPException(503, detail='Historical recovery is paused; retain local audio')
            lane_decision = replace(
                lane_decision,
                lane=SyncLane.BACKFILL,
                trust=CaptureTimeTrust.UNTRUSTED,
                reason='retained_capture_recovery',
                maximum_age_seconds=None,
            )
        early_capture_received_at = (
            capture_received_at if any(is_early_capture_time(get_timestamp_from_path(path)) for path in paths) else None
        )
        future_capture = any(
            is_implausible_future_capture_time(get_timestamp_from_path(path), now=capture_received_at) for path in paths
        )
        estimated_capture = future_capture_clamp_enabled() and any(
            capture_clock_run_from_path(path) and not is_early_capture_time(get_timestamp_from_path(path))
            for path in paths
        )
        if future_capture or estimated_capture or retained_capture:
            try:
                recovery_source_id = await run_blocking(
                    db_executor, recovery_source_conversation, uid, supplied_conversation_id
                )
            except BatchPrivacyBlocked as error:
                future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
                return (
                    JSONResponse(status_code=200, content=deleted_conversation_result(0))
                    if is_conversation_deleted(error)
                    else privacy_blocked_response()
                )
            # Old WALs may carry a live conversation stamp. Keep custody proof
            # authenticated against the submitted ID, but never use it as a
            # temporal target for this isolated recovery source.
            conversation_id = None
            record_snapshot = {}
        capture_clock_policy = (
            RECEIPT_CLOCK_POLICY if retained_capture else ESTIMATED_POLICY if estimated_capture else None
        )
        if future_capture:
            future_paths = [
                path
                for path in paths
                if is_implausible_future_capture_time(get_timestamp_from_path(path), now=capture_received_at)
            ]
            require_future_upload(future_paths, received_at=capture_received_at)
            if (
                any(capture_clock_run_from_path(path) for path in future_paths)
                and not client_device_context.client_device_id
            ):
                future_capture_request.mark(FutureCaptureOutcome.IDENTITY_REQUIRED)
                designed_refusal.mark_designed_refusal(uid, 'capture_clock_identity_required', x_cloud_trace_context)
                return JSONResponse(
                    status_code=503,
                    headers={'Retry-After': '30'},
                    content={'code': 'capture_clock_identity_required', 'detail': 'Retain local audio and retry'},
                )
            # Future clocks are a batch-only extension. Legacy and early-clock
            # admission/placement keep main's existing context and behavior.
            capture_clock_policy = RECEIPT_CLOCK_POLICY
        # One server-clock offset per request shifts the client's
        # recording-session audio bounds onto the server clock before any
        # temporal comparison (recording-session binding compares them against
        # server-clock conversation rows). Admitted data only: at this staging
        # seam decode has not run, so the basis is the staged filename starts
        # alone — the pipeline recomputes the offset from decoded durations
        # after VAD — and a claimed end past the admitted span plus one
        # live-capture chunk of slack (the same trailing allowance session
        # binding grants) is clipped to it, so an inflated client claim can
        # neither widen the claimed span nor move the session matching
        # interval. Files keep their raw capture-clock names and keys.
        if isinstance(audio_start_seconds, (int, float)) and isinstance(audio_end_seconds, (int, float)):
            admitted_file_starts = []
            for filename in filenames:
                try:
                    admitted_file_starts.append(float(get_timestamp_from_path(filename)))
                except (IndexError, ValueError):
                    continue  # Admission above rejects unparseable names with the typed 400.
            if admitted_file_starts:
                if early_capture_received_at is not None or future_capture or estimated_capture or retained_capture:
                    # Reset clocks prove no server-clock interval. Do not use
                    # a possibly years-wide client claim for session lookup;
                    # source-frame custody evidence keeps its original meaning.
                    audio_start_seconds = audio_end_seconds = None
                else:
                    admitted_end = max(admitted_file_starts) + SESSION_CLAIM_TRAILING_SLACK_SECONDS
                    audio_start_seconds = float(audio_start_seconds)
                    audio_end_seconds = min(float(audio_end_seconds), admitted_end)
                    session_clock_offset = capture_clock_offset(max(admitted_file_starts))
                    if session_clock_offset > 0:
                        audio_start_seconds -= session_clock_offset
                        audio_end_seconds -= session_clock_offset

        if manifest_claims is not None and not await run_blocking(
            sync_executor, manifest_claims_match_paths, manifest_claims, paths
        ):
            if backfill_slot_acquired:
                await run_blocking(db_executor, release_backfill_slot, uid, job_id)
                backfill_slot_acquired = False
            future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
            return JSONResponse(
                status_code=422,
                content={
                    'code': 'capture_manifest_mismatch',
                    'detail': 'Fresh capture manifest did not match the uploaded audio',
                },
            )

        content_id = await run_blocking(sync_executor, compute_sync_content_id, uid, paths)
        if repair_identity is not None and not await run_blocking(
            db_executor, repair_upload_owner_matches, uid, content_id, repair_identity
        ):
            # Already accepted bytes may outlive the new-upload lookback. Only
            # the exact original owner may cross that boundary; a changed or
            # foreign bundle cannot write an archive or enter fresh admission.
            future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
            return JSONResponse(
                status_code=409,
                content={'code': 'sync_repair_bundle_changed', 'detail': 'Retain the original complete local upload'},
            )

        archive_paths = None

        async def archive_originals():
            nonlocal archive_paths
            if archive_paths is not None:
                return
            # Keep original bytes before any 202, content-cache hit, decode or VAD.
            # An archive failure leaves the client responsible for retrying its WAL.
            archive_paths = await custody_lease.archive(
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

            custody_lease.stored(paths, archive_paths)

        candidate_policy = resolve_batch_policy(uid)
        intake_evidence = IntakeRouteEvidence()
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
            evidence=intake_evidence,
        )
        if repair_identity is not None:
            # Exact repair ownership is checked by batch admission before it
            # can accept. Never let a changed repair bundle take a fresh or
            # synchronous record route, even outside today's admission cohort.
            record_response = RecordUploadRoute.BATCH
        else:
            record_response = await registered_record_response(
                uid=uid,
                conversation_id=conversation_id if isinstance(conversation_id, str) else None,
                content_id=content_id,
                paths=paths,
                source=source.value,
                client_device_id=client_device_context.client_device_id,
                byok_enabled=byok_enabled,
                recording_session_id=(
                    None if future_capture or estimated_capture or retained_capture else recording_session_id
                ),
                policy=batch_policy,
                before_coverage=archive_originals,
                capture_claims=capture_claims,
                loaded_conversation=record_snapshot if record_snapshot.get('record_lane_owner') else None,
                # A legacy_final_pass_v1 owner is re-homed once legacy is dark.
                legacy_mode=legacy_mode,
                evidence=intake_evidence,
            )
        if isinstance(record_response, JSONResponse):
            # Only this branch has both checked the signed manifest against
            # staged bytes and identified the exact conversation memo writer.
            # An early memo hit has not verified the bytes. A coverage wait can
            # still require archive, lease, settlement and partial-wake work.
            if (
                x_omi_wal_retry == '1'
                and conversation_id
                and getattr(record_response, 'retry_conversation', None) == conversation_id
                and has_server_capture_proof
                and client_device_context.client_device_id
                and manifest_claims
                and filenames == upload_filenames
                and len(set(filenames)) == len(filenames)
                and not any(capture_clock_run_from_path(path) for path in paths)
                and all(get_timestamp_from_path(path) <= capture_received_at for path in paths)
            ):
                record_response.headers['X-Omi-Wal-Retry'] = issue_retry_handle(
                    uid, client_device_context.client_device_id, conversation_id, manifest_claims
                )
            future_capture_request.mark(FutureCaptureOutcome.PRIOR_CUSTODY)
            return record_response

        await archive_originals()

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
            upload_recovered = x_omi_upload_recovered == '1'
            batch_response = await accept_batch_upload(
                uid=uid,
                job_id=job_id,
                content_id=content_id,
                repair_job_id=repair_identity,
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
                    'upload_arrived_at': upload_arrived_at,
                    'upload_entitlement': await run_blocking(db_executor, upload_entitlement.classify, uid),
                    **(
                        {'upload_hold_state': bounded_hold_state(x_omi_upload_hold)}
                        if isinstance(x_omi_upload_hold, str)
                        else {}
                    ),
                    **({'upload_recovered': True} if upload_recovered else {}),
                    **({'capture_source_conversation_id': recovery_source_id} if recovery_source_id else {}),
                    **({'capture_clock_policy': capture_clock_policy} if capture_clock_policy is not None else {}),
                    **(
                        {
                            'retained_capture_offsets_by_name': {
                                os.path.basename(path): offset for path, offset in retained_capture_offsets.items()
                            }
                        }
                        if capture_clock_policy is not None
                        else {}
                    ),
                    **(
                        {
                            'capture_received_at': (
                                capture_received_at
                                if future_capture or estimated_capture or retained_capture
                                else early_capture_received_at
                            )
                        }
                        if early_capture_received_at is not None
                        or future_capture
                        or estimated_capture
                        or retained_capture
                        else {}
                    ),
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
                evidence=intake_evidence,
            )
            if batch_response is not None:
                # Count only a fresh admission this request (a re-ACK of prior
                # custody, a fence/unavailable response, or a rehomed final-pass
                # owner is a follow-on, not a batch landing).
                if intake_evidence.batch_accepted and not intake_evidence.final_pass_owner_followed:
                    record_upload_outcome('batch')
                    observe_hold_age(
                        x_omi_upload_hold_age_ms,
                        x_omi_upload_hold,
                        upload_recovered,
                        upload_trace=x_omi_upload_trace,
                        received_at=capture_received_at,
                    )
                return batch_response
            sequencer_registration_started = False

        if future_capture:
            if not batch_attempted:
                future_capture_request.mark(FutureCaptureOutcome.ROUTE_DECLINED)
            # A cohort/language/capacity decline retains the phone's files;
            # this policy can never fall through to a legacy reader.
            raise FutureCaptureRefused()

        if estimated_capture or retained_capture:
            # A repaired clock must retain its per-source isolation even when
            # the batch cohort/language/capacity path declines this upload.
            designed_refusal.mark_designed_refusal(uid, 'repaired_clock_batch_declined', x_cloud_trace_context)
            return JSONResponse(
                status_code=503,
                headers={'Retry-After': '30'},
                content={
                    'code': 'sync_batch_unavailable',
                    'detail': 'Sync is temporarily unavailable; retain local audio',
                },
            )

        # Legacy transcription is deleted (plan C C9-C11). Content legacy already
        # owns is answered by its durable fence; anything else keeps its audio.
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
    except FutureCaptureRefused:
        return JSONResponse(
            status_code=400, content={'code': INVALID_CAPTURE_TIME_CODE, 'detail': INVALID_CAPTURE_TIME_DETAIL}
        )
    except HTTPException as error:
        if error.status_code == 400:
            future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
            reason = error.detail.get('code', 'server_refused') if isinstance(error.detail, dict) else 'server_refused'
            logger.info('sync_upload_refused uid=%s status=400 reason=%s', uid, reason)
            return JSONResponse(status_code=400, content={'code': reason, 'detail': 'Invalid sync file format'})
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


@router.post('/v2/sync-local-files/{job_id}/release-hold', response_model=SyncUploadHoldReleaseResponse)
def release_sync_upload_hold(job_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Precise owner-authenticated user-open hint; no priority promotion.

    Generic polling, Home refresh and app foreground never call this operation.
    The normal per-owner limiter bounds repeated hints; wrong-owner and unknown
    handles have the same response. The producer kill switch does not gate it.
    """
    if not admit_sync_job_poll(uid):
        raise HTTPException(status_code=429, detail='Sync job polling too frequent; retry later')
    if not job_id.startswith('bp_') or len(job_id) > 128 or '/' in job_id:
        raise HTTPException(status_code=404, detail='Sync job not found')
    from database.batch_pipeline_coalescing import release_for_open
    from database.batch_pipeline_store import FirestoreStore
    from utils.sync.stage import current_stage

    try:
        release_for_open(FirestoreStore(f'batch_pipeline_{current_stage()}'), uid, job_id, time.time())
    except BatchPrivacyBlocked:
        return privacy_blocked_response()
    return {'accepted': True}


@router.get("/v2/sync-local-files/{job_id}", response_model=SyncJobStatusResponse, response_model_exclude_none=True)
def get_sync_job_status(
    job_id: str,
    uid: str = Depends(auth.get_current_user_uid),
    surface_open: bool = False,  # Retain the released query parameter.
    x_omi_custody_repair_protocol: Optional[str] = Header(None, alias='X-Omi-Custody-Repair-Protocol'),
):
    """Poll for the status of an async sync job."""
    OMI_SYNC_JOB_POLL_REQUESTS_TOTAL.inc()
    if not admit_sync_job_poll(uid):
        OMI_SYNC_JOB_POLL_THROTTLED_TOTAL.inc()
        raise HTTPException(
            status_code=429,
            detail='Sync job polling too frequent; retry later',
            headers={'Retry-After': str(SYNC_POLL_WINDOW_SECONDS)},
        )
    return _read_sync_job_status(job_id, uid, x_omi_custody_repair_protocol)


def _read_sync_job_status(job_id: str, uid: str, x_omi_custody_repair_protocol: Optional[str]):
    try:
        durable = (
            get_durable_job_status(job_id, uid, artifact_retry=True)
            if x_omi_custody_repair_protocol == '1'
            else get_durable_job_status(job_id, uid)
        )
    except BatchPrivacyBlocked:
        return privacy_blocked_response()
    except Exception as error:
        if not is_transaction_retry_failure(error):
            raise
        raise sync_finalization_retrying() from error
    if durable is not None:
        return with_custody_hold_poll_hint(durable)
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
        return with_custody_hold_poll_hint(completed)
    if not job:
        retired = acknowledge_retired_handle(job_id, uid)  # custody-held expiry-retired handles
        if retired is not None:
            return with_custody_hold_poll_hint(retired)
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
                uid, job['content_id'], job_id, **terminal_repeat_failure_kwargs(job)
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
        'completed_at': job.get('completed_at'),
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

    return with_custody_hold_poll_hint(resp)


# Bounds the account-deletion recheck so a hung marker read cannot outlive the client's request.
RECEIPT_DELETION_CHECK_TIMEOUT_SECONDS = 3


@router.post(
    '/v2/sync-local-files/receipts/wait',
    response_model=SyncReceiptsWaitResponse,
    response_model_exclude_none=True,
    include_in_schema=False,
)
async def wait_for_sync_receipts(
    body: SyncReceiptsWaitRequest, request: Request, uid: str = Depends(auth.get_current_user_uid)
):
    # Experiment receipt_long_poll. For an account it is off for, the path answers as an unknown route does.
    await warm_experiments(uid)
    if not experiment('receipt_long_poll', uid):
        raise HTTPException(status_code=404, detail='Not Found')
    if not await run_blocking(db_executor, admit_sync_job_poll, uid):
        raise HTTPException(
            status_code=429,
            detail='Receipt requests too frequent',
            headers={'Retry-After': str(SYNC_POLL_WINDOW_SECONDS)},
        )
    result = await _wait_for_sync_receipts(body, request, uid)
    if not result['receipts'] and not result['fallback']:
        return result
    # The auth fence ran before a wait of up to ~23s. Deletion can become pending meanwhile, and a
    # completed Redis job carries its raw result with no deletion check of its own. One uncached
    # marker read gates every answer that names a job; an unreadable marker answers no job.
    try:
        blocked = await asyncio.wait_for(
            run_blocking(db_executor, account_deletion_blocks_user_work, uid, fresh=True),
            RECEIPT_DELETION_CHECK_TIMEOUT_SECONDS,
        )
    except Exception as error:
        logger.error('event=sync_receipts_wait outcome=deletion_check_failed exception_type=%s', type(error).__name__)
        raise HTTPException(status_code=503, detail='Receipt waiter unavailable')
    if blocked:
        logger.info('event=sync_receipts_wait outcome=account_pending_deletion')
        return JSONResponse(status_code=503, content={'status': 'account_pending_deletion'})
    return result


async def _wait_for_sync_receipts(body: SyncReceiptsWaitRequest, request: Request, uid: str) -> dict:
    from database.redis_db import get_async_redis_client
    from database.sync_jobs import receipt_channel, receipt_note_key, TERMINAL_STATUSES

    jobs = set(body.job_ids)
    # Experiment receipt_finished_note: job state is read only for a job that a note or a wake
    # says finished. Off, every start, wake and expiry reads every listed job.
    noted = experiment('receipt_finished_note', uid)

    def snapshot(named=None):
        receipts, fallback = [], []
        for job_id in jobs if named is None else named:
            try:
                status = _read_sync_job_status(job_id, uid, None)
            except HTTPException as error:
                if error.status_code not in (403, 404, 503):
                    raise
                fallback.append(job_id)
                continue
            if not isinstance(status, dict) or status.get('reason_code') in (
                'batch_unit_held',
                'batch_artifact_missing',
                'source_alignment_pending',
            ):
                fallback.append(job_id)
            elif status.get('status') in TERMINAL_STATUSES:
                receipts.append(status)
            elif named is not None:
                # Named as finished but not final: the paced status polls own this handle.
                fallback.append(job_id)
        return {'receipts': receipts, 'fallback': fallback}

    channel = await run_blocking(db_executor, receipt_channel, uid)
    redis = await get_async_redis_client()
    async with redis.pubsub() as sub:
        await sub.subscribe(channel)
        # Wait for Redis to acknowledge subscription before reading job state.
        message = await sub.get_message(timeout=3)
        if not message or message['type'] != 'subscribe':
            raise HTTPException(status_code=503, detail='Receipt waiter unavailable')
        if noted:
            # A job that finished before the subscription left a note; a later one publishes a wake.
            listed = sorted(jobs)
            keys = await run_blocking(db_executor, lambda: [receipt_note_key(uid, job_id) for job_id in listed])
            notes = await redis.mget(keys)
            finished = [job_id for job_id, note in zip(listed, notes) if note]
            result = (
                await run_blocking(db_executor, snapshot, finished) if finished else {'receipts': [], 'fallback': []}
            )
        else:
            result = await run_blocking(db_executor, snapshot)
        deadline = time.monotonic() + 20
        while not result['receipts'] and not result['fallback']:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return result if noted else await run_blocking(db_executor, snapshot)
            if await request.is_disconnected():
                return result
            message = await sub.get_message(ignore_subscribe_messages=True, timeout=min(1, remaining))
            if message and message['data'] in jobs:
                result = await run_blocking(db_executor, snapshot, [message['data']] if noted else None)
        return result


@router.post("/v2/sync-jobs/run", include_in_schema=False)
@sync_snapshot_resolve_job
async def run_sync_job(request: Request, task_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    """Enrichment and batch final-pass tasks only: legacy transcription is deleted (plan C C9-C11).

    ``sync_reprocess`` and ``batch_final_pass`` tasks still ride this route. Any
    other task is a legacy transcription or sequencer job that was queued before
    deletion; legacy has been dark since 2026-11-04, its audio stays with the
    client or the content ledger's retry material, so it is acknowledged and
    dropped. Never 5xx: a retry cannot make it runnable.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = None
    if isinstance(payload, dict) and payload.get('kind') == 'batch_final_pass':
        from routers.enrichment import _task
        from utils.conversations.final_pass_retry import consume as consume_speaker_pass

        task = _task(payload)
        if task is None:
            return JSONResponse(status_code=400, content={'status': 'invalid_speaker_task'})
        return JSONResponse(
            status_code=200, content=await run_blocking(postprocess_executor, consume_speaker_pass, *task)
        )
    if isinstance(payload, dict) and payload.get('kind') == 'sync_reprocess':
        if isinstance(payload.get('uid'), str):
            await warm_rollout_cohorts(payload['uid'])
        return await enrichment_response(payload)
    legacy_dark.record_dark_ack(legacy_dark.LegacyDarkReason.LEGACY_RETIRED)
    logger.warning('event=sync_transcription_job outcome=dropped reason=legacy_retired')
    return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'legacy_retired'})


# A destructive operation (explicit memory deletion, retention cleanup) owns the
# account gate for seconds to a few minutes. Queue retries land inside that
# window, use up every attempt, and leave the file marked merge_failed, so
# playback is never built. A deferred, delayed copy waits the gate out instead,
# without a 5xx or a spent attempt. Delays run 60, 120, 240, 480, 900, 900 s,
# about 45 min in total.
AUDIO_MERGE_DESTRUCTIVE_DEFERRALS_MAX = 6


async def _refuse_changed_playback_source(payload: dict, *, fingerprint: str | None = None):
    """A replaced source cannot be repaired by retrying its old immutable key."""
    from database.legal_holds import DestructiveOperationInProgress

    try:
        if fingerprint is None:
            await run_blocking(
                storage_executor,
                mark_playback_unavailable,
                payload['uid'],
                payload['conversation_id'],
                payload['audio_file_id'],
                'source_changed',
            )
        else:
            await run_blocking(
                storage_executor,
                mark_conversation_playback_unavailable,
                payload['uid'],
                payload['conversation_id'],
                fingerprint,
                'source_changed',
            )
    except DestructiveOperationInProgress:
        deferred = await _defer_merge_for_destructive_operation(payload)
        if deferred is not None:
            return deferred
        return JSONResponse(status_code=503, content={'status': 'retry'})
    PLAYBACK_WRITES.labels('skipped').inc()
    logger.warning(
        'audio_merge: refused reason=source_manifest_changed kind=%s', 'file' if fingerprint is None else 'conversation'
    )
    return JSONResponse(status_code=200, content={'status': 'unavailable', 'reason': 'source_manifest_changed'})


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
    try:
        response = await _handle_audio_merge_job(request, task_retry_count)
    except Exception:
        await _record_demand_playback_outcome(request, None)
        raise
    await _record_demand_playback_outcome(request, response)
    return response


async def _record_demand_playback_outcome(request: Request, response) -> None:
    try:
        payload = await request.json()
    except Exception:
        return
    record_demand_playback_outcome(payload, None if response is None else response.body)


async def _handle_audio_merge_job(request: Request, task_retry_count: int):
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

    task_uid = payload.get('uid')
    if isinstance(task_uid, str) and await run_blocking(db_executor, account_deletion_blocks_user_work, task_uid):
        # Cloud Tasks retains the task; a restore can resume processing.
        return JSONResponse(status_code=503, content={'status': 'account_pending_deletion'})

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
        except PlaybackSourceChanged:
            return await _refuse_changed_playback_source(payload)
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
            record_playback_ready(payload, 'file')
        logger.debug(f'audio_merge: built artifact conv={conversation_id} file={audio_file_id} size={len(mp3_data)}')
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
        if await run_blocking(db_executor, playback_build.superseded_while_locked, payload):
            return JSONResponse(status_code=200, content={'status': 'superseded'})
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
        if conversation.get('recording_pieces') is not None:
            from utils.conversations.v3.audio import playback_snapshot

            conversation = await run_blocking(db_executor, playback_snapshot, uid, conversation)
        fingerprint = sync_playback.conversation_merge_fingerprint(conversation, demand=demand)
        if payload_fingerprint and payload_fingerprint != fingerprint:
            PLAYBACK_WRITES.labels('skipped').inc()
            return JSONResponse(status_code=200, content={'status': 'superseded'})

        artifact_fingerprint = (
            conversation['_v3_playback_fingerprint']
            if conversation.get('recording_pieces') is not None
            else compute_audio_files_fingerprint(
                audio_files,
                origin=conversation.get('started_at') or conversation.get('created_at'),
                source_identity=True,
            )
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
            # No stored origin: anchor the wall clock on each part's own basis
            # (normalized playback start when persisted, else raw chunk keys)
            # so skewed parts keep non-negative, truthful offsets.
            part_bases = [
                (
                    af['playback_start']
                    if isinstance(af.get('playback_start'), (int, float))
                    else (min(af['chunk_timestamps']) if af.get('chunk_timestamps') else None)
                )
                for af in audio_files
                if isinstance(af, dict)
            ]
            started_at_ts = min((base for base in part_bases if base is not None), default=0.0)

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
                    **({'conversation': conversation} if conversation.get('recording_pieces') is not None else {}),
                )
        except PlaybackSourceChanged:
            return await _refuse_changed_playback_source(payload, fingerprint=fingerprint)
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


@router.post('/v2/batch-census/run', include_in_schema=False)
@read_origin('job:batch_census')
async def run_batch_census(_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    """Exact per-stock counts and oldest ages for the batch census registry."""
    return JSONResponse(status_code=200, content=await batch_census.snapshot())
