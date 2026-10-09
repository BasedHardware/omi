"""Internal Scheduler entrypoint; never expose per-user dream reports."""

from fastapi import APIRouter, Depends

from utils import dream_agent
from utils.cloud_tasks import verify_cloud_tasks_oidc

router = APIRouter()


@router.post('/v2/dream-agent/sweep', include_in_schema=False)
async def sweep_dream_agent(_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    reports = await dream_agent.drain()
    return {
        status: sum(report['status'] == status for report in reports)
        for status in (
            'complete',
            'failed',
            'not_admitted',
            'deadline',
        )
    }
