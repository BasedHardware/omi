import asyncio
import logging
import os
import shutil
import threading
import time
import uuid as _uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Query, Request, Response, Header
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from database import conversations as conversations_db
from database import users as users_db
from database.sync_jobs import (
    TERMINAL_STATUSES,
    create_sync_job,
    get_sync_job,
    mark_job_failed,
    mark_job_queued_for_retry,
    try_acquire_job_run_lock,
    release_job_run_lock,
)
from models.conversation_enums import ConversationSource
from models.sync_audio import AudioPrecacheResponse, AudioUrlsResponse
from utils.analytics import record_usage
from utils.other import endpoints as auth
from utils.other.storage import (
    get_playback_artifact_signed_url,
    upload_playback_artifact,
    mark_playback_unavailable,
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
    is_dg_budget_exhausted,
    record_dg_usage_ms,
    record_speech_ms,
    trigger_classifier_if_needed,
)
from utils.observability.fallback import record_fallback
from utils.metrics import OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL
from utils.client_device import resolve_client_device, resolve_client_device_from_request
from utils.subscription import has_transcription_credits
from utils.sync import playback as sync_playback
from utils.sync.files import decode_files_to_wav, get_timestamp_from_path, get_wav_duration, retrieve_file_paths
from utils.sync.pipeline import (
    _OrderedTurnstile,
    _cleanup_files,
    _delete_staged_blobs_async,
    _download_staged_files,
    _finalize_sync_audio_files,
    _reprocess_merged_conversations,
    _retrieve_file_paths_v2,
    _run_full_pipeline_background_async,
    _stage_files_to_gcs,
    build_person_embeddings_cache,
    process_segment,
    retrieve_vad_segments,
)

logger = logging.getLogger(__name__)

# Audio constants
AUDIO_SAMPLE_RATE = 16000

_V1_DEPRECATION_HEADERS = {'Deprecation': 'true', 'Link': '</v2/sync-local-files>; rel="successor-version"'}

router = APIRouter()


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


class SyncJobStatusResponse(BaseModel):
    job_id: str
    status: str
    total_segments: int = 0
    processed_segments: int = 0
    successful_segments: int = 0
    failed_segments: int = 0
    result: SyncLocalFilesResultResponse | None = None
    error: str | None = None


class AudioDownloadPendingResponse(BaseModel):
    status: str
    poll_after_ms: int


def _hard_restriction_headers(retry_after: int | None, base_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = dict(base_headers or {})
    if retry_after is not None:
        headers['Retry-After'] = str(retry_after)
    return headers


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

    return sync_playback.get_audio_signed_urls(uid, conversation_id, conversation.get('audio_files', []))


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
async def sync_local_files(
    request: Request,
    response: Response,
    files: List[UploadFile] = File(...),
    uid: str = Depends(auth.get_current_user_uid),
    conversation_id: str = Query(
        None, description="Target conversation ID to attach audio to (auto-sync from live capture)"
    ),
):
    logger.warning(
        f'sync: deprecated v1 sync-local-files called uid={uid} files={len(files)} '
        f'user_agent={request.headers.get("user-agent", "")}'
    )
    response.headers.update(_V1_DEPRECATION_HEADERS)
    client_device_context = resolve_client_device_from_request(request)

    # Pre-check gates (#5854)
    hard_restricted, retry_after = get_hard_restriction_status(uid)
    if hard_restricted:
        raise HTTPException(
            status_code=429,
            detail="Account temporarily restricted due to fair-use policy",
            headers=_hard_restriction_headers(retry_after, _V1_DEPRECATION_HEADERS),
        )

    # Check credits: if exhausted, still process but lock the conversation so user can pay to unlock
    should_lock = not has_transcription_credits(uid)

    # Detect source from filenames
    source = ConversationSource.omi
    for f in files:
        if f.filename and 'limitless' in f.filename.lower():
            source = ConversationSource.limitless
            break

    paths = []
    wav_paths = []
    segmented_paths = set()

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

        if FAIR_USE_ENABLED and total_speech_ms > 0:
            record_speech_ms(uid, total_speech_ms, source='sync')
            speech_totals = get_rolling_speech_ms(uid)
            triggered_caps = check_soft_caps(uid, speech_totals=speech_totals)
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
        if FAIR_USE_ENABLED:
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
            return JSONResponse(
                status_code=429,
                headers=_V1_DEPRECATION_HEADERS,
                content={
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
async def sync_local_files_v2(
    files: List[UploadFile] = File(...),
    uid: str = Depends(auth.get_current_user_uid),
    conversation_id: str = Query(
        None, description="Target conversation ID to attach audio to (auto-sync from live capture)"
    ),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
    x_device_id_hash: Optional[str] = Header(None, alias='X-Device-Id-Hash'),
):
    """
    Async version of sync-local-files. Saves raw files and returns 202
    immediately, then runs the full pipeline (decode → VAD → STT → LLM) as
    an async background task. The app polls GET /v2/sync-local-files/{job_id}.
    """
    # Browser/mobile clients carry capture provenance in these request headers.
    # It must survive both the inline and Cloud Tasks pipeline branches.
    client_device_context = resolve_client_device(
        x_app_platform=x_app_platform if isinstance(x_app_platform, str) else None,
        x_device_id_hash=x_device_id_hash if isinstance(x_device_id_hash, str) else None,
    )

    # Pre-check gates (same as v1)
    hard_restricted, retry_after = await run_blocking(critical_executor, get_hard_restriction_status, uid)
    if hard_restricted:
        headers = _hard_restriction_headers(retry_after)
        raise HTTPException(
            status_code=429,
            detail="Account temporarily restricted due to fair-use policy",
            headers=headers,
        )

    should_lock = not await run_blocking(critical_executor, has_transcription_credits, uid)

    # Detect source
    source = ConversationSource.omi
    for f in files:
        if f.filename and 'limitless' in f.filename.lower():
            source = ConversationSource.limitless
            break

    # Create job_id early so we have it for the directory
    job_id = str(_uuid.uuid4())
    job_dir = f'syncing/{uid}/{job_id}'

    paths = []

    try:
        # --- Fast path: save raw files only (< 2s typical) ---
        # Use sync_executor, NOT storage_executor — storage is saturated with
        # background pipeline cleanup/GCS work and would queue the 202 response.
        paths = await run_blocking(sync_executor, _retrieve_file_paths_v2, files, uid, job_id)

        # Create Redis job — total_segments=0 until VAD completes in background
        await run_blocking(db_executor, create_sync_job, uid, total_files=len(files), total_segments=0, job_id=job_id)

        # Transfer ownership of raw paths to the background task
        owned_paths = list(paths)
        paths = []  # Prevent finally cleanup of files now owned by bg task

        dispatched = False
        # BYOK keys live only in this request's context and cannot follow a
        # Cloud Task, so BYOK requests always run inline.
        if is_cloud_tasks_dispatch_enabled() and not has_byok_keys():
            try:
                # sync_executor, NOT storage_executor — same reasoning as the
                # file save above (#7372): a saturated storage pool would queue
                # the staging upload and delay the 202.
                await run_blocking(sync_executor, _stage_files_to_gcs, owned_paths)
                await run_blocking(
                    db_executor,
                    enqueue_sync_job,
                    {
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
                    },
                )
                dispatched = True
                try:
                    OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL.labels(mode='cloud_tasks').inc()
                except Exception:
                    pass
            except Exception as e:
                logger.error(f'sync_v2: Cloud Tasks dispatch failed job={job_id}, falling back inline: {e}')
                record_fallback(
                    component='sync_dispatch',
                    from_mode='cloud_tasks',
                    to_mode='inline',
                    reason='enqueue_failed',
                    outcome='degraded',
                )
                try:
                    OMI_SYNC_DISPATCH_ATTEMPTS_TOTAL.labels(mode='inline').inc()
                except Exception:
                    pass
                start_background_task(_delete_staged_blobs_async(owned_paths), name=f'sync_unstage:{job_id}')

            if dispatched:
                try:
                    # The handler instance downloads from GCS; local copies are done
                    await run_blocking(sync_executor, _cleanup_files, owned_paths)
                    await run_blocking(sync_executor, shutil.rmtree, job_dir, True)
                except Exception as e:
                    logger.error(f'sync_v2: post-enqueue local cleanup failed job={job_id}: {e}')

        if not dispatched:
            if not is_cloud_tasks_dispatch_enabled():
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
            elif has_byok_keys():
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
                ),
                name=f'sync_pipeline:{job_id}',
            )

        return JSONResponse(
            status_code=202,
            content={
                'job_id': job_id,
                'status': 'queued',
                'total_files': len(files),
                'total_segments': 0,
                'poll_after_ms': 3000,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f'sync_v2 fast-path failed uid={uid}: {e}')
        raise HTTPException(status_code=500, detail=str(e))
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

    # Build response — include result only when terminal
    resp = {
        'job_id': job['job_id'],
        'status': job['status'],
        'total_segments': job.get('total_segments', 0),
        'processed_segments': job.get('processed_segments', 0),
        'successful_segments': job.get('successful_segments', 0),
        'failed_segments': job.get('failed_segments', 0),
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
        if not isinstance(client_device_id, str):
            client_device_id = None
        if not isinstance(client_platform, str):
            client_platform = None
    except Exception as e:
        # A malformed payload will not fix itself on retry — consume it.
        logger.error(f'sync job handler: invalid payload, dropping task: {e}')
        return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'invalid_payload'})

    # Fail-closed lock: Redis errors propagate → 500 → Cloud Tasks retries later.
    lock_token = await run_blocking(db_executor, try_acquire_job_run_lock, job_id)
    if not lock_token:
        logger.warning(f'sync job {job_id}: run-lock held by another attempt, deferring')
        return JSONResponse(status_code=409, content={'status': 'locked'})

    try:
        job = await run_blocking(db_executor, get_sync_job, job_id)
        if not job:
            # Job TTL (24h) expired before dispatch — staged blobs are gone or
            # about to be (1-day lifecycle); the app re-uploads on 404.
            logger.warning(f'sync job {job_id}: job expired before dispatch, dropping task')
            await _delete_staged_blobs_async(blob_paths)
            return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'job_expired'})

        if job['status'] in TERMINAL_STATUSES:
            # Duplicate delivery, stale-detector-failed job, or a prior attempt
            # that finished. Never re-run terminal jobs — the app may already be
            # re-uploading these files as a new job.
            await _delete_staged_blobs_async(blob_paths)
            return JSONResponse(status_code=200, content={'status': 'acked', 'job_status': job['status']})

        if not await run_blocking(storage_executor, _download_staged_files, blob_paths):
            # Blobs deleted by the bucket's 1-day lifecycle (deep queue backlog).
            await run_blocking(db_executor, mark_job_failed, job_id, 'Staged audio expired before processing')
            await _delete_staged_blobs_async(blob_paths)
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
            )
        except Exception as e:
            max_attempts = get_sync_tasks_max_attempts()
            if task_retry_count >= max_attempts - 1:
                logger.error(f'sync job {job_id}: final attempt {task_retry_count + 1} failed, consuming: {e}')
                await run_blocking(db_executor, mark_job_failed, job_id, f'Failed after {max_attempts} attempts: {e}')
                await _delete_staged_blobs_async(blob_paths)
                return JSONResponse(status_code=200, content={'status': 'failed_final'})
            # Reset to 'queued' so the stale detector cannot terminally fail the
            # job while the Cloud Tasks retry backoff elapses. Blobs are kept.
            logger.warning(f'sync job {job_id}: attempt {task_retry_count + 1} failed, will retry: {e}')
            await run_blocking(db_executor, mark_job_queued_for_retry, job_id, task_retry_count + 1, str(e))
            return JSONResponse(status_code=500, content={'status': 'retry'})

        # Pipeline returned normally: completed, or it marked the job failed
        # itself (decode/VAD/DG-budget) — terminal either way, staging is done.
        await _delete_staged_blobs_async(blob_paths)
        return JSONResponse(status_code=200, content={'status': 'done'})
    finally:
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
        uid = payload['uid']
        conversation_id = payload['conversation_id']
        audio_file_id = payload['audio_file_id']
        timestamps = list(payload['timestamps'])
    except Exception as e:
        logger.error(f'audio_merge handler: invalid payload, dropping task: {e}')
        return JSONResponse(status_code=200, content={'status': 'dropped', 'reason': 'invalid_payload'})

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
