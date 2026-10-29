"""Internal Scheduler entrypoint; never expose per-user dream reports."""

import logging
from collections import Counter

from fastapi import APIRouter, Depends, Request

from database.firestore_read_origin import read_origin
from utils import dream_agent, dream_canary, dream_telemetry
from utils.cloud_tasks import verify_cloud_tasks_oidc

router = APIRouter()
logger = logging.getLogger(__name__)
SWEEP_JOB = 'dream-agent-sweep-hourly'


@router.post('/v2/dream-agent/canary', include_in_schema=False)
@read_origin('job:dream_agent_canary')
async def canary_dream_agent(_retry_count: int = Depends(verify_cloud_tasks_oidc)):
    return await dream_canary.check()


@router.post('/v2/dream-agent/sweep', include_in_schema=False)
@read_origin('job:dream_agent_sweep')
async def sweep_dream_agent(request: Request, _retry_count: int = Depends(verify_cloud_tasks_oidc)):
    # Scheduler identity, not request data: the job name is allowlisted and the
    # schedule time is a timestamp, so a redelivered tick shows a repeated time.
    job = request.headers.get('x-cloudscheduler-jobname', '')
    sweep = {
        'retry_count': _retry_count,
        'caller': 'scheduler' if job == SWEEP_JOB else 'other' if job else 'none',
        'scheduled_at': request.headers.get('x-cloudscheduler-scheduletime', '')[:25],
    }
    reports = await dream_agent.drain(sweep=sweep)
    # Structured twin (owner-level counts, reasons, retry count); fails open.
    dream_telemetry.record_sweep(sweep, reports)
    counts = {
        status: sum(report['status'] == status for report in reports)
        for status in (
            'complete',
            'failed',
            'not_admitted',
            'deadline',
            'waiting',
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
