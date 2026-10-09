"""Firebase-authenticated self-report and bounded manual pass for the caller only."""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from database.dream_store import AdmissionDenied
from models.dream_report import DreamRun, DreamRunRequest, DreamRunsResponse
from utils import dream_agent, dream_report
from utils.executors import db_executor, run_blocking
from utils.other import endpoints as auth

router = APIRouter()
MANUAL_DEADLINE_SECONDS = 85


@router.get('/v1/dream/runs', response_model=DreamRunsResponse)
async def get_runs(limit: int = Query(default=10, ge=1, le=20), uid: str = Depends(auth.get_current_user_uid)):
    await run_blocking(db_executor, dream_report.require_owner, uid)
    return await run_blocking(db_executor, dream_report.list_runs, uid, limit)


@router.post('/v1/dream/runs', response_model=DreamRun)
async def run_now(body: DreamRunRequest, uid: str = Depends(auth.get_current_user_uid)):
    try:
        async with asyncio.timeout(MANUAL_DEADLINE_SECONDS):
            await run_blocking(db_executor, dream_report.require_owner, uid)
            report = await dream_agent.run_pass(uid, trigger='manual', timeout_seconds=70)
            if report.get('run_id'):
                return await run_blocking(db_executor, dream_report.finished_run, uid, report['run_id'])
            return DreamRun(run_id='', created_at=datetime.now(timezone.utc), trigger='manual', status='idle')
    except AdmissionDenied as exc:
        code = 409 if exc.reason == 'dream_run_in_progress' else 429 if exc.reason == 'dream_manual_limit' else 503
        raise HTTPException(code, detail=exc.reason) from None
    except TimeoutError:
        # Persistent lease/reservation survive cancellation of ambiguous storage.
        return DreamRun(
            run_id='',
            created_at=datetime.now(timezone.utc),
            trigger='manual',
            status='deadline',
            error_type='TimeoutError',
        )
