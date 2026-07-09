"""
Import endpoints for importing data from external sources.
"""

import logging
import os
from typing import List

from utils.executors import db_executor, storage_executor, run_blocking

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

import database.import_jobs as import_jobs_db
from models.import_job import ImportJobResponse, ImportJobStatus, ImportSourceType
from utils.other import endpoints as auth
from utils.imports.limitless import create_import_job, process_limitless_import
from utils.multipart import IMPORT_MAX_PART_SIZE, MultipartMaxPartSizeRoute, max_part_size

router = APIRouter(route_class=MultipartMaxPartSizeRoute)

logger = logging.getLogger(__name__)

# Temp directory for uploaded files
TEMP_DIR = '_temp'


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
    )


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
                    total_files=job.get('total_files'),
                    processed_files=job.get('processed_files'),
                    conversations_created=job.get('conversations_created'),
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
        total_files=job.get('total_files'),
        processed_files=job.get('processed_files'),
        conversations_created=job.get('conversations_created'),
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
    if job.get('status') not in (ImportJobStatus.pending.value, ImportJobStatus.processing.value):
        raise HTTPException(status_code=409, detail="Only a pending or processing import can be cancelled")

    import_jobs_db.update_import_job(job_id, {'status': ImportJobStatus.cancelled.value, 'error': 'Cancelled by user'})
    return ImportJobResponse(
        job_id=job['id'],
        status=ImportJobStatus.cancelled,
        total_files=job.get('total_files'),
        processed_files=job.get('processed_files'),
        conversations_created=job.get('conversations_created'),
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
    # TODO: This deletes all the other conversations as well (which were created in omi using the pendant)
    # TODO: Add a flag to the conversation to indicate that it was imported
    # deleted_count = conversations_db.delete_conversations_by_source(uid, 'limitless')

    # return {'deleted_count': deleted_count, 'message': f'Successfully deleted {deleted_count} Limitless conversations'}

    return {'deleted_count': 0, 'message': 'Successfully deleted 0 Limitless conversations'}
