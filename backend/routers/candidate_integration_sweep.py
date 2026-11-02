"""Internal Scheduler entrypoint for the candidate integration outbox sweep."""

import logging

from fastapi import APIRouter, Depends

from database.firestore_read_origin import read_origin
from utils.cloud_tasks import verify_cloud_tasks_oidc
from utils.task_intelligence.candidate_integration_sweeper import (
    sweep_candidate_integrations as run_candidate_integration_sweep,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post('/v2/candidate-integrations/sweep', include_in_schema=False)
@read_origin('job:candidate_integration_sweep')
async def sweep_candidate_integrations(_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    # The sweep awaits executor offload for Firestore and the provider sync.
    counts = await run_candidate_integration_sweep()
    logger.info(
        'candidate integration sweep %s',
        ' '.join(f'{key}={value}' for key, value in sorted(counts.items())),
    )
    return counts
