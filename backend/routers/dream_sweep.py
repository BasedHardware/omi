"""Internal Scheduler entrypoint; never expose per-user dream reports."""

import logging
from collections import Counter

from fastapi import APIRouter, Depends

from utils import dream_agent
from utils.cloud_tasks import verify_cloud_tasks_oidc

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post('/v2/dream-agent/sweep', include_in_schema=False)
async def sweep_dream_agent(_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    reports = await dream_agent.drain()
    counts = {
        status: sum(report['status'] == status for report in reports)
        for status in (
            'complete',
            'failed',
            'not_admitted',
            'deadline',
        )
    }
    # Counts and exception type names only: the sweep is otherwise unobservable without reading user data.
    failures = Counter(str(report.get('error_type', 'unknown')) for report in reports if report['status'] == 'failed')
    logger.info(
        'Dream sweep candidates=%d %s failure_types=%s',
        len(reports),
        ' '.join(f'{status}={count}' for status, count in counts.items()),
        ','.join(f'{name}:{count}' for name, count in sorted(failures.items())) or 'none',
    )
    return counts
