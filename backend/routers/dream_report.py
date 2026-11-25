"""Firebase-authenticated self-report and bounded manual pass for the caller only."""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from config.dream_agent import PASS_TIMEOUT_SECONDS, DRAIN_TIMEOUT_SECONDS

from database.dream_store import AdmissionDenied
from models.dream_report import DreamRun, DreamRunRequest, DreamRunsResponse
from utils import dream_agent, dream_report
from utils.executors import db_executor, run_blocking
from utils.other import endpoints as auth
from utils.other.list_budget import ListReadBudgetExhausted, finish_list_budget, list_read_budget_for_request

router = APIRouter()
MANUAL_DEADLINE_SECONDS = 85


@router.get('/v1/dream/runs', response_model=DreamRunsResponse)
async def get_runs(
    request: Request,
    response: Response,
    limit: int = Query(default=10, ge=1, le=20),
    uid: str = Depends(auth.get_current_user_uid),
):
    # Every Firestore read on this path runs with the request budget's per-RPC
    # timeout and no retry, so one stalled op ends the list with the runs already
    # projected plus X-Omi-List-Truncated rather than a bodyless 90 s middleware
    # 504. The eligibility gate cannot report partial eligibility, so its
    # deadline is a retryable 503 instead. No docstring: the released OpenAPI
    # description is pinned, and this route's wire contract does not change.
    budget = list_read_budget_for_request(request, route='GET /v1/dream/runs')
    try:
        await run_blocking(db_executor, dream_report.require_owner, uid, budget=budget)
    except ListReadBudgetExhausted:
        raise HTTPException(503, detail='dream_report_unavailable', headers={'Retry-After': '5'}) from None
    runs = await run_blocking(db_executor, dream_report.list_runs, uid, limit, budget=budget)
    finish_list_budget(response, budget)
    return runs


@router.post('/v1/dream/runs', response_model=DreamRun)
async def run_now(body: DreamRunRequest, uid: str = Depends(auth.get_current_user_uid)):
    try:
        async with asyncio.timeout(DRAIN_TIMEOUT_SECONDS):
            await run_blocking(db_executor, dream_report.require_owner, uid)
            report = await dream_agent.run_pass(uid, trigger='manual', timeout_seconds=PASS_TIMEOUT_SECONDS)
            if report.get('run_id'):
                return await run_blocking(db_executor, dream_report.finished_run, uid, report['run_id'])
            if report.get('status') == 'waiting':
                raise HTTPException(
                    503, detail=report.get('reason', 'reserved_capacity'), headers={'Retry-After': '120'}
                )
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
