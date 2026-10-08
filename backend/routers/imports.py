"""
Import endpoints for importing data from external sources.
"""

import asyncio
import logging
import os
import re

from datetime import datetime, timezone
from typing import List, Optional

from utils.executors import db_executor, storage_executor, run_blocking, start_background_task, submit_with_context

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from redis.exceptions import RedisError

import database.import_jobs as import_jobs_db
import database.import_quotas as import_quotas_db
from models.import_job import ImportJobResponse, ImportJobStatus, ImportSourceType
from utils.other import endpoints as auth
from utils.imports.limitless import create_import_job, process_limitless_import
from utils.imports.transcript_files import (
    TRANSCRIPT_ORIGINS,
    UPLOAD_EXTENSIONS,
    create_transcript_import_job,
    process_transcript_import,
)
from utils.multipart import (
    IMPORT_MAX_PART_SIZE,
    MultipartMaxPartSizeRoute,
    max_part_size,
    multipart_limits,
    single_file_limits,
)

router = APIRouter(route_class=MultipartMaxPartSizeRoute)

logger = logging.getLogger(__name__)

# Temp directory for uploaded files
TEMP_DIR = '_temp'


def _job_source_type(job: dict) -> Optional[ImportSourceType]:
    """The importer that created a stored job; unknown or missing values stay unset."""
    try:
        return ImportSourceType(job.get('source_type'))
    except (ValueError, TypeError):
        return None


class DeleteLimitlessConversationsResponse(BaseModel):
    deleted_count: int
    message: str


@router.post(
    '/v1/import/limitless',
    response_model=ImportJobResponse,
    tags=['import'],
)
@max_part_size(IMPORT_MAX_PART_SIZE)
async def import_limitless_data(
    file: UploadFile = File(...),
    language: str = 'en',
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Start a Limitless data import from a ZIP file export.

    The import runs in the background. Use GET /v1/import/jobs/{job_id} to check status.

    Args:
        file: ZIP file containing Limitless data export
        language: Language code for conversation processing (default: 'en')

    Returns:
        ImportJobResponse with job_id and initial status
    """
    # Validate file type
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    # Create import job
    job = await run_blocking(db_executor, create_import_job, uid, ImportSourceType.limitless)

    # Save uploaded file to temp directory
    os.makedirs(TEMP_DIR, exist_ok=True)
    zip_path = os.path.join(TEMP_DIR, f"{job.id}_{file.filename}")

    try:
        # Stream the file to disk to avoid loading it all into memory
        f = await run_blocking(storage_executor, open, zip_path, 'wb')
        try:
            while contents := await file.read(1024 * 1024):  # Read in 1MB chunks
                await run_blocking(storage_executor, f.write, contents)
        finally:
            f.close()
    except Exception as e:
        # Clean up on error
        await run_blocking(
            db_executor,
            import_jobs_db.update_import_job,
            job.id,
            {'status': ImportJobStatus.failed.value, 'error': f"Failed to save uploaded file: {str(e)}"},
        )
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

    # Start background processing
    storage_executor.submit(process_limitless_import, job.id, uid, zip_path, language)

    return ImportJobResponse(
        job_id=job.id,
        status=ImportJobStatus.pending,
        source_type=ImportSourceType.limitless,
    )


@router.post(
    '/v1/import/transcripts',
    response_model=ImportJobResponse,
    tags=['import'],
)
@max_part_size(IMPORT_MAX_PART_SIZE)
# The form is parsed before auth and the rate limit: one file part and no fields, in a
# body no larger than that file allows, bound what any request can make the server spool.
@multipart_limits(single_file_limits(IMPORT_MAX_PART_SIZE))
async def import_transcript_files(
    file: UploadFile = File(...),
    language: str = 'en',
    tz: str = 'UTC',
    origin: str = 'other',
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'import:upload', fail_closed=True)),
):
    """
    Start importing transcripts exported from other tools.

    Accepts one ``.srt``, ``.vtt`` or ``.txt`` transcript, or a ``.zip`` of them. Each
    transcript becomes a completed conversation (no AI processing); re-importing the
    same file is skipped. ``tz`` reads dates in file names, and ``origin`` is ``plaud``
    or ``other``. Poll GET /v1/import/jobs/{job_id} for progress.
    """
    language = language.strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,16}', language):
        language = 'en'
    # A file or origin we will not import must not spend a monthly upload slot.
    filename = os.path.basename((file.filename or '').replace('\\', '/'))
    if not filename.lower().endswith(UPLOAD_EXTENSIONS):
        raise HTTPException(status_code=400, detail="Upload a .zip, .srt, .vtt or .txt file")
    if origin not in TRANSCRIPT_ORIGINS:
        raise HTTPException(status_code=400, detail=f"origin must be one of: {', '.join(sorted(TRANSCRIPT_ORIGINS))}")

    try:
        admitted = await run_blocking(db_executor, import_quotas_db.reserve_import_quota, uid, 'upload', 1)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail='Import quota unavailable') from exc
    if admitted is None:
        raise HTTPException(status_code=429, detail='Monthly transcript upload limit reached. Try again later.')

    try:
        job = await run_blocking(db_executor, create_transcript_import_job, uid)
    except asyncio.CancelledError:
        submit_with_context(db_executor, _release_admitted_upload, uid, admitted)
        raise
    except Exception:
        await run_blocking(db_executor, _release_admitted_upload, uid, admitted)
        raise
    os.makedirs(TEMP_DIR, exist_ok=True)
    # Staged under the job ID: a user's file name can exceed the file-system name limit.
    upload_path = os.path.join(TEMP_DIR, f"{job.id}{os.path.splitext(filename)[1].lower()}")
    try:
        f = await run_blocking(storage_executor, open, upload_path, 'wb')
        try:
            while contents := await file.read(1024 * 1024):
                await run_blocking(storage_executor, f.write, contents)
        finally:
            f.close()
    except asyncio.CancelledError:
        # The request deadline cancelled the handler. Under that cancellation every
        # further await is interrupted too, so the cleanup goes to a pool unawaited.
        submit_with_context(
            db_executor, _abandon_transcript_import, job.id, upload_path, 'Failed to save uploaded file'
        )
        submit_with_context(db_executor, _release_admitted_upload, uid, admitted)
        raise
    except Exception as e:
        logger.error('transcript import upload not staged job_id=%s error_class=%s', job.id, type(e).__name__)
        try:
            await run_blocking(
                db_executor, _abandon_transcript_import, job.id, upload_path, 'Failed to save uploaded file'
            )
        finally:
            await run_blocking(db_executor, _release_admitted_upload, uid, admitted)
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    # An async coordinator, not a pool task: it borrows a thread per step (one file,
    # one job write) instead of holding a slot for the whole import.
    worker = process_transcript_import(
        job.id,
        uid,
        upload_path,
        original_filename=filename,
        language_code=language,
        tz=tz,
        origin=origin,
    )
    try:
        start_background_task(worker, name=f'transcript_import:{job.id}')
    except Exception as e:
        worker.close()
        logger.error('transcript import could not be queued job_id=%s error_class=%s', job.id, type(e).__name__)
        try:
            await run_blocking(
                db_executor,
                _abandon_transcript_import,
                job.id,
                upload_path,
                'The import could not be started. Please try again.',
            )
        finally:
            await run_blocking(db_executor, _release_admitted_upload, uid, admitted)
        raise HTTPException(status_code=503, detail="The import could not be started. Try again shortly.")
    return ImportJobResponse(job_id=job.id, status=ImportJobStatus.pending, source_type=job.source_type)


def _discard_staged_upload(upload_path: str) -> None:
    try:
        os.remove(upload_path)
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.error('transcript import staged upload cleanup failed error_class=%s', type(e).__name__)


def _release_admitted_upload(uid: str, reservation: str) -> None:
    """Return a monthly upload slot when the request never starts an import.

    Redis errors stay in the log and the slot remains spent: a lost release must
    not let the handler look successful.
    """
    try:
        import_quotas_db.release_import_quota(uid, 'upload', reservation)
    except Exception as exc:
        logger.error('transcript import upload quota release failed error_class=%s', type(exc).__name__)


def _abandon_transcript_import(job_id: str, upload_path: str, error: str) -> None:
    """Fail a job whose upload will never reach the worker, so it is not left pending, and drop the file.

    The file goes even when the job update raises.
    """
    try:
        import_jobs_db.update_import_job_unless_cancelled(
            job_id,
            {
                'status': ImportJobStatus.failed.value,
                'error': error,
                'completed_at': datetime.now(timezone.utc).isoformat(),
            },
        )
    finally:
        _discard_staged_upload(upload_path)


@router.get(
    '/v1/import/jobs',
    response_model=List[ImportJobResponse],
    tags=['import'],
)
def get_import_jobs(
    uid: str = Depends(auth.get_current_user_uid),
    limit: int = 50,
) -> List[ImportJobResponse]:
    """
    Get all import jobs for the current user.

    Returns:
        List of import jobs ordered by creation date (newest first)
    """
    # Clamp pagination so a negative value cannot reach Firestore (which raises -> HTTP 500) and an
    # oversized limit cannot stream the whole collection.
    limit = max(1, min(limit, 1000))
    jobs = import_jobs_db.get_import_jobs(uid, limit=limit)

    # Build each response individually so one malformed/legacy job (missing id, or a status value not in
    # the ImportJobStatus enum) doesn't fail the whole list with a 500.
    result: List[ImportJobResponse] = []
    for job in jobs:
        try:
            result.append(
                ImportJobResponse(
                    job_id=job['id'],
                    status=ImportJobStatus(job['status']),
                    source_type=_job_source_type(job),
                    total_files=job.get('total_files'),
                    processed_files=job.get('processed_files'),
                    conversations_created=job.get('conversations_created'),
                    conversations_skipped=job.get('conversations_skipped'),
                    created_at=job.get('created_at'),
                    error=job.get('error'),
                )
            )
        except (KeyError, ValueError) as e:
            logger.warning(f"Skipping malformed import job for uid {uid}: {e}")
            continue
    return result


@router.get(
    '/v1/import/jobs/{job_id}',
    response_model=ImportJobResponse,
    tags=['import'],
)
def get_import_job_status(
    job_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Get the status of a specific import job.

    Args:
        job_id: The import job ID

    Returns:
        ImportJobResponse with current job status and progress
    """
    job = import_jobs_db.get_import_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")

    # Verify ownership
    if job['uid'] != uid:
        raise HTTPException(status_code=403, detail="Not authorized to view this import job")

    # Coerce an out-of-enum/missing stored status to failed instead of 500ing the request
    try:
        status_val = ImportJobStatus(job.get('status'))
    except (ValueError, TypeError):
        status_val = ImportJobStatus.failed

    return ImportJobResponse(
        job_id=job['id'],
        status=status_val,
        source_type=_job_source_type(job),
        total_files=job.get('total_files'),
        processed_files=job.get('processed_files'),
        conversations_created=job.get('conversations_created'),
        conversations_skipped=job.get('conversations_skipped'),
        created_at=job.get('created_at'),
        error=job.get('error'),
    )


@router.post('/v1/import/jobs/{job_id}/cancel', response_model=ImportJobResponse, tags=['import'])
def cancel_import_job(job_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Cancel a pending or processing import job."""
    job = import_jobs_db.get_import_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    if job['uid'] != uid:
        raise HTTPException(status_code=403, detail="Not authorized to modify this import job")
    if not import_jobs_db.cancel_import_job_if_active(job_id):
        if import_jobs_db.get_import_job(job_id) is None:
            raise HTTPException(status_code=404, detail='Import job not found')
        raise HTTPException(status_code=409, detail='Only a pending or processing import can be cancelled')
    return ImportJobResponse(
        job_id=job['id'],
        status=ImportJobStatus.cancelled,
        source_type=_job_source_type(job),
        total_files=job.get('total_files'),
        processed_files=job.get('processed_files'),
        conversations_created=job.get('conversations_created'),
        conversations_skipped=job.get('conversations_skipped'),
        created_at=job.get('created_at'),
        error='Cancelled by user',
    )


class DeleteImportJobResponse(BaseModel):
    status: str
    job_id: str


@router.delete('/v1/import/jobs/{job_id}', response_model=DeleteImportJobResponse, tags=['import'])
def delete_import_job(job_id: str, uid: str = Depends(auth.get_current_user_uid)):
    """Delete a finished (completed, failed, or cancelled) import job."""
    job = import_jobs_db.get_import_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    if job['uid'] != uid:
        raise HTTPException(status_code=403, detail="Not authorized to modify this import job")
    if job.get('status') in (ImportJobStatus.pending.value, ImportJobStatus.processing.value):
        raise HTTPException(status_code=409, detail="Cancel the in-progress import before deleting it")

    import_jobs_db.delete_import_job(job_id)
    return {'status': 'ok', 'job_id': job_id}


@router.delete(
    '/v1/import/limitless/conversations',
    response_model=DeleteLimitlessConversationsResponse,
    tags=['import'],
)
def delete_limitless_conversations(
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Delete all conversations imported from Limitless.

    Returns:
        Number of deleted conversations
    """
    # Selective delete is not implemented here yet. Conversations created by the
    # Limitless ZIP import path are stamped with imported=True (see Conversation
    # and persist_imported_conversation). Do not delete by source=limitless alone —
    # that also matches pendant/sync uploads.

    return {'deleted_count': 0, 'message': 'Successfully deleted 0 Limitless conversations'}
