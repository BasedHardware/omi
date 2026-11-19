"""Internal Scheduler entrypoint for the error-class sentinel sweep."""

import logging

from fastapi import APIRouter, Depends

from database.firestore_read_origin import read_origin
from services.error_class_sentinel import run_error_class_sweep
from utils.cloud_tasks import verify_cloud_tasks_oidc

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post('/v2/error-class-alerts/sweep', include_in_schema=False)
@read_origin('job:error_class_sweep')
async def sweep_error_classes(_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    summary = await run_error_class_sweep()
    logger.info('error class sweep %s', ' '.join(f'{key}={value}' for key, value in sorted(summary.items())))
    return summary
