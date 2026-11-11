"""Authenticated in-app surfaces and value signals for EXP-005."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from config.first_value_recovery import recovery_enabled
from database import first_value_recovery as recovery
from utils.other import endpoints as auth
from utils.product_telemetry import emit_product_event

logger = logging.getLogger(__name__)
router = APIRouter()


class ResultOpenRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_-]+$')


def _event(uid: str, variant: str, kind: str, stage: str, outcome: str) -> None:
    emit_product_event(
        uid=uid,
        event='First Value Recovery Delivery' if stage == 'delivery' else 'First Value Recovery Eligibility',
        properties={
            'experiment_id': recovery.EXPERIMENT_ID,
            'variant': variant,
            'kind': kind,
            'channel': 'in_app',
            'outcome': outcome,
        },
    )


@router.get('/v1/first-value/recovery/prompt')
def get_recovery_prompt(
    navigation: bool = False,
    kind: Literal['result'] | None = None,
    uid: str = Depends(auth.get_current_user_uid),
    first_value_protocol: str | None = Header(None, alias='X-Omi-First-Value-Protocol'),
    notification_permission: str | None = Header(None, alias='X-Omi-Notification-Permission'),
    time_zone: str | None = Header(None, alias='X-Omi-Time-Zone'),
) -> dict[str, Any]:
    """Claim one next-open prompt, or resolve an already-claimed ready push."""

    if not recovery_enabled() or first_value_protocol != '1':
        return {'prompt': None}
    now = datetime.now(timezone.utc)
    try:
        starts = recovery.recent_starts(uid, now=now)
        for candidate in starts:
            start = candidate
            if not navigation:
                start = recovery.record_client_capability(
                    uid,
                    candidate['start_id'],
                    start,
                    notifications_authorized=notification_permission == 'granted',
                    time_zone=time_zone or '',
                    now=now,
                )
            start = recovery.probe_start(uid, candidate['start_id'], start, now=now)
            if navigation:
                if kind is None:
                    continue
                prompt = recovery.resolve_push_navigation(uid, candidate['start_id'], start, kind, now=now)
                if prompt is not None and recovery_enabled():
                    return {'prompt': prompt}
                continue
            for prompt_kind in recovery.iter_candidate_kinds(start, now=now):
                prompt = recovery.claim_prompt(uid, candidate['start_id'], start, prompt_kind, 'in_app', now=now)
                if prompt is not None and recovery_enabled():
                    _event(uid, str(start.get('variant')), prompt_kind, 'delivery', 'claimed')
                    return {'prompt': prompt}
    except Exception as error:
        # Unknown coverage never becomes an eligible empty response by design.
        logger.warning('first-value in-app prompt failed error_type=%s', type(error).__name__)
    return {'prompt': None}


@router.post('/v1/first-value/recovery/result-open')
def record_result_open(request: ResultOpenRequest, uid: str = Depends(auth.get_current_user_uid)) -> dict[str, int]:
    if not recovery_enabled():
        return {'recorded': 0}
    return {'recorded': recovery.record_result_open(uid, request.conversation_id, now=datetime.now(timezone.utc))}


@router.post('/v1/first-value/recovery/pendant-connection')
def record_pendant_connection(
    uid: str = Depends(auth.get_current_user_uid),
    first_value_protocol: str | None = Header(None, alias='X-Omi-First-Value-Protocol'),
    notification_permission: str | None = Header(None, alias='X-Omi-Notification-Permission'),
    time_zone: str | None = Header(None, alias='X-Omi-Time-Zone'),
) -> dict[str, bool]:
    if not recovery_enabled() or first_value_protocol != '1':
        return {'recorded': False}
    now = datetime.now(timezone.utc)
    for candidate in recovery.recent_starts(uid, now=now):
        recovery.record_client_capability(
            uid,
            candidate['start_id'],
            candidate,
            notifications_authorized=notification_permission == 'granted',
            time_zone=time_zone or '',
            now=now,
        )
    return {'recorded': recovery.record_pendant_connection(uid, now=now)}
