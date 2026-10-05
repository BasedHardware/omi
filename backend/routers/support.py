"""Private, read-only support harness authenticated by the caller's Firebase token."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from firebase_admin import auth
from pydantic import EmailStr, TypeAdapter, ValidationError

from config.plan_catalog import allocation_limit
from database import conversations, fair_use, support, user_usage, users
from models.support import SupportLookupResponse, SupportTraceResponse
from utils.support_auth import get_support_caller_uid
from utils.support_trace import project_support_trace

router = APIRouter(prefix='/v1/support', tags=['support'], include_in_schema=False)


def normalize_support_email(email: str) -> str:
    normalized = email.strip().lower()
    if not normalized or ',' in normalized or '*' in normalized:
        raise HTTPException(status_code=422, detail='A single exact email is required')
    try:
        TypeAdapter(EmailStr).validate_python(normalized)
    except ValidationError:
        raise HTTPException(status_code=422, detail='A single exact email is required') from None
    return normalized


def resolve_support_target(email: str) -> str:
    try:
        return auth.get_user_by_email(email).uid
    except auth.UserNotFoundError:
        raise HTTPException(status_code=404, detail='Account not found') from None
    except Exception:
        raise HTTPException(status_code=503, detail='Support lookup unavailable') from None


def audit_or_fail(actor_uid: str, action: Literal['lookup', 'trace'], uid: str, email: str, **window: datetime) -> None:
    try:
        support.write_support_audit(actor_uid, action, uid, email, **window)
    except Exception:
        raise HTTPException(status_code=503, detail='Support audit unavailable') from None


@router.get('/lookup', response_model=SupportLookupResponse)
def lookup_support_account(email: str = Query(...), caller_uid: str = Depends(get_support_caller_uid)):
    email = normalize_support_email(email)
    uid = resolve_support_target(email)
    try:
        subscription = users.get_user_subscription(uid, read_only=True)
        activity = support.get_support_activity(uid)
        usage = user_usage.get_monthly_usage_stats(uid, datetime.now(timezone.utc))
        stage = fair_use.get_fair_use_state(uid).get('stage', 'none')
        limit = subscription.limits.transcription_seconds
        if limit is None:
            limit = allocation_limit(subscription.plan, 'transcription')
        used = usage.get('transcription_seconds', 0)
        response = SupportLookupResponse(
            uid=uid,
            email=email,
            plan=subscription.plan,
            last_active_at=activity.get('last_active_at'),
            last_active_platform=activity.get('last_active_platform'),
            transcription_seconds_used=used,
            transcription_seconds_limit=limit,
            transcription_seconds_remaining=None if limit is None else max(0, limit - used),
            fair_use_stage=stage,
        )
    except Exception:
        raise HTTPException(status_code=503, detail='Support lookup unavailable') from None
    audit_or_fail(caller_uid, 'lookup', uid, email)
    return response


@router.get('/trace', response_model=SupportTraceResponse)
def trace_support_recordings(
    email: str = Query(...),
    input_from: str = Query(..., alias='from'),
    input_to: str = Query(..., alias='to'),
    caller_uid: str = Depends(get_support_caller_uid),
):
    email = normalize_support_email(email)
    try:
        window_from = datetime.fromisoformat(input_from)
        window_to = datetime.fromisoformat(input_to)
    except ValueError:
        raise HTTPException(status_code=422, detail='ISO-8601 timestamps are required') from None
    if any(timestamp.tzinfo is None or timestamp.utcoffset() is None for timestamp in (window_from, window_to)):
        raise HTTPException(status_code=422, detail='Timezone-aware timestamps are required')
    window_from = window_from.astimezone(timezone.utc)
    window_to = window_to.astimezone(timezone.utc)
    if not timedelta(0) < window_to - window_from <= timedelta(days=7):
        raise HTTPException(status_code=422, detail='Window must be greater than zero and at most 7 days')
    uid = resolve_support_target(email)
    try:
        documents = conversations.get_conversations(
            uid,
            limit=51,
            include_discarded=True,
            start_date=window_from,
            end_date=window_to,
            date_field='started_at',
            metadata_only=True,
        )
        rows = [project_support_trace(document) for document in documents[:50]]
        response = SupportTraceResponse(
            email=email,
            uid=uid,
            window_from=window_from,
            window_to=window_to,
            truncated=len(documents) > 50,
            rows=rows,
        )
    except Exception:
        raise HTTPException(status_code=503, detail='Support trace unavailable') from None
    audit_or_fail(caller_uid, 'trace', uid, email, window_from=window_from, window_to=window_to)
    return response
