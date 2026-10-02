"""OCR-only admission; pixels continue through the existing desktop Gemini proxy."""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from utils.executors import db_executor, llm_executor, run_blocking
from utils.llm.screen_task_gate import decide_screen_task
from utils.other.endpoints import get_current_user_uid, with_rate_limit
from utils.subscription import is_desktop_trial_paywalled

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
    uid: str = Depends(with_rate_limit(get_current_user_uid, 'screen_activity:sync')),
) -> ScreenTaskGateResponse:
    if await run_blocking(db_executor, is_desktop_trial_paywalled, uid, 'desktop'):
        raise HTTPException(status_code=402, detail='trial_expired')
    existing = '\n'.join(task[:512] for task in body.related_tasks)
    state = (
        f'User: {body.user_context}. App: {body.app_name}.\nEXISTING TASKS:\n{existing}\n'
        'LAYOUT: left messages incoming, right/colored outgoing. Ignore sidebar lists.\n'
        f'SCREEN OCR:\n{body.ocr_text}'
    )
    decision = await run_blocking(llm_executor, decide_screen_task, state)
    # One bounded decision event; never log OCR, task context, titles, IDs or scores.
    logger.info('screen_task_gate gate_outcome=%s audit_sample=%s', decision.outcome, decision.audit_sample)
    return ScreenTaskGateResponse(
        should_extract=decision.should_extract, gate_outcome=decision.outcome, audit_sample=decision.audit_sample
    )
