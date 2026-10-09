"""OCR-only admission; pixels continue through the existing desktop Gemini proxy."""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from utils.executors import db_executor, llm_executor, run_blocking
from utils.llm.screen_task_gate import decide_screen_task
from utils.other.endpoints import get_current_user_uid
from utils.managed_compute import authorize_managed_compute
from utils.llm.screen_task_admission import (
    check_screen_task_limit,
    screen_task_build_floor_refusal,
    screen_task_stopped,
)
from utils.subscription import is_desktop_trial_paywalled
from utils.metrics import SCREEN_TASK_GATE_FRAMES_TOTAL

logger = logging.getLogger(__name__)
router = APIRouter()


class ScreenTaskGateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ocr_text: str = Field(max_length=12000)
    user_context: str = Field(default='', max_length=1024)
    app_name: str = Field(default='', max_length=128)
    related_tasks: list[Annotated[str, Field(max_length=576)]] = Field(default_factory=list, max_length=4)


class ScreenTaskGateResponse(BaseModel):
    should_extract: bool
    gate_outcome: Literal['passed', 'rejected', 'fail_open']
    audit_sample: bool


@router.post('/v1/screen-task/gate', response_model=ScreenTaskGateResponse)
async def screen_task_gate(
    body: ScreenTaskGateRequest,
    request: Request,
    uid: str = Depends(get_current_user_uid),
) -> ScreenTaskGateResponse:
    if screen_task_stopped():
        SCREEN_TASK_GATE_FRAMES_TOTAL.labels(outcome='stopped').inc()
        raise HTTPException(
            status_code=409, detail={'error': 'screen_task_stopped'}, headers={'X-Omi-Retryable': 'false'}
        )
    # Below-floor clients fail open on this error into flagged extraction.
    # The proxy refusal is what moves that frame onto the legacy loop.
    build_floor = screen_task_build_floor_refusal(request.headers, 'gate')
    if build_floor is not None:
        raise build_floor
    # Separate burst and daily budgets, fail closed when Redis admission is unavailable.
    try:
        await run_blocking(db_executor, check_screen_task_limit, uid, 'screen_task:gate')
        await run_blocking(db_executor, check_screen_task_limit, uid, 'screen_task:gate_daily')
    except HTTPException as error:
        SCREEN_TASK_GATE_FRAMES_TOTAL.labels(
            outcome='gate_budget_exhausted' if error.status_code == 429 else 'admission_unavailable'
        ).inc()
        raise HTTPException(
            status_code=error.status_code,
            detail={'error': 'gate_budget_exhausted' if error.status_code == 429 else 'gate_admission_denied'},
            headers={**(error.headers or {}), 'X-Omi-Retryable': 'false'},
        ) from error
    decision = await run_blocking(db_executor, authorize_managed_compute, uid, 'screen_frame_judge', 'omi')
    if not decision.allowed:
        SCREEN_TASK_GATE_FRAMES_TOTAL.labels(outcome='plan_denied').inc()
        raise HTTPException(
            status_code=503 if decision.reason == 'authorization_unavailable' else 402,
            detail={'error': 'plan_gated', 'reason': decision.reason},
            headers={'X-Omi-Retryable': 'false'},
        )
    if await run_blocking(db_executor, is_desktop_trial_paywalled, uid, 'desktop'):
        SCREEN_TASK_GATE_FRAMES_TOTAL.labels(outcome='trial_expired').inc()
        raise HTTPException(status_code=402, detail='trial_expired', headers={'X-Omi-Retryable': 'false'})
    existing = '\n'.join(task[:512] for task in body.related_tasks)
    state = (
        f'User: {body.user_context}. App: {body.app_name}.\nEXISTING TASKS:\n{existing}\n'
        'LAYOUT: left messages incoming, right/colored outgoing. Ignore sidebar lists.\n'
        f'SCREEN OCR:\n{body.ocr_text}'
    )
    decision = await run_blocking(llm_executor, decide_screen_task, state)
    SCREEN_TASK_GATE_FRAMES_TOTAL.labels(outcome=decision.outcome).inc()
    # One bounded decision event; never log OCR, task context, titles, IDs or scores.
    logger.info(
        'screen_task_gate eligible_frames=1 client_bypass=0 gate_outcome=%s audit_sample=%s',
        decision.outcome,
        decision.audit_sample,
    )
    return ScreenTaskGateResponse(
        should_extract=decision.should_extract, gate_outcome=decision.outcome, audit_sample=decision.audit_sample
    )


class ScreenTaskAdmissionResponse(BaseModel):
    enabled: bool
    lease_seconds: int = 55


@router.get('/v1/screen-task/admission', response_model=ScreenTaskAdmissionResponse)
def screen_task_admission(request: Request, uid: str = Depends(get_current_user_uid)) -> ScreenTaskAdmissionResponse:
    # No provider work; a running client polls every 30 seconds. Failure expires its lease.
    if screen_task_stopped():
        return ScreenTaskAdmissionResponse(enabled=False)
    build_floor = screen_task_build_floor_refusal(request.headers, 'admission')
    if build_floor is not None:
        raise build_floor
    return ScreenTaskAdmissionResponse(enabled=True)
