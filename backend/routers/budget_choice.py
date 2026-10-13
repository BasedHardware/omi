"""At-cap choice API. Dark until both server flag and client capability are present."""

from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool

from config.held_content import HELD_CONTENT_CAPABILITY, budget_period, capture_state
from database import budget_choice as choices_db
from utils import held_content_flags
from utils.executors import db_executor, run_blocking
from utils.other import endpoints as auth
from utils.subscription import resolve_transcription_allowance

router = APIRouter()


class BudgetChoiceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    period: str
    choice: Literal['on_device', 'upgrade']
    dont_ask_again: StrictBool = False


class BudgetChoiceRecord(BudgetChoiceRequest):
    pass


class BudgetChoiceResponse(BaseModel):
    period: str
    state: Literal['managed', 'unavailable', 'on_device', 'held_pending_choice']
    choice: BudgetChoiceRecord | None
    ask: bool


class BudgetChoiceWriteResponse(BaseModel):
    period: str
    choice: BudgetChoiceRecord
    ask: Literal[False] = False


choice_uid = auth.with_rate_limit(auth.get_current_user_uid_no_byok_validation, 'users:budget_choice', fail_closed=True)


def require_capability(x_omi_held_content: str | None = Header(None, alias=HELD_CONTENT_CAPABILITY)) -> None:
    if not held_content_flags.capable(x_omi_held_content):
        raise HTTPException(status_code=404, detail='held_content_unavailable')


@router.get('/v1/users/budget-choice', response_model=BudgetChoiceResponse, dependencies=[Depends(require_capability)])
async def get_budget_choice(
    uid: str = Depends(choice_uid), x_app_platform: str | None = Header(None, alias='X-App-Platform')
):
    period = budget_period()
    allowance = await run_blocking(db_executor, resolve_transcription_allowance, uid, x_app_platform)
    choice = await run_blocking(db_executor, choices_db.get_choice, uid, period)
    exhausted = allowance.reason == 'plan_allowance_exhausted'
    return {
        'period': period,
        'state': capture_state(managed=allowance.managed, exhausted=exhausted, choice=choice),
        'choice': choice,
        'ask': exhausted and choice is None,
    }


@router.put(
    '/v1/users/budget-choice', response_model=BudgetChoiceWriteResponse, dependencies=[Depends(require_capability)]
)
async def put_budget_choice(
    body: BudgetChoiceRequest,
    uid: str = Depends(choice_uid),
    x_app_platform: str | None = Header(None, alias='X-App-Platform'),
):
    period = budget_period()
    if body.period != period:
        raise HTTPException(status_code=409, detail='budget_period_changed')
    allowance = await run_blocking(db_executor, resolve_transcription_allowance, uid, x_app_platform)
    if allowance.reason != 'plan_allowance_exhausted':
        raise HTTPException(status_code=409, detail='budget_not_exhausted')
    try:
        choice = await run_blocking(db_executor, choices_db.set_choice, uid, period, body.choice, body.dont_ask_again)
    except choices_db.BudgetChoiceConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {'period': period, 'choice': choice, 'ask': False}
