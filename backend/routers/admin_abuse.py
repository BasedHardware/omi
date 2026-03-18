"""Admin endpoints for fair-use abuse management."""

import hashlib
import hmac
import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

import database.fair_use as fair_use_db
from database._client import db
from utils.other.endpoints import get_current_user_uid
from utils.fair_use import (
    get_rolling_speech_ms,
    invalidate_enforcement_cache,
    FAIR_USE_ENABLED,
    FAIR_USE_DAILY_SPEECH_MS,
    FAIR_USE_3DAY_SPEECH_MS,
    FAIR_USE_WEEKLY_SPEECH_MS,
)

logger = logging.getLogger(__name__)

router = APIRouter()

ADMIN_KEY = os.getenv('ADMIN_KEY', '')


def _verify_admin_key(x_admin_key: str = Header(..., alias='X-Admin-Key')) -> str:
    """Validate admin key from request header using constant-time comparison.

    Returns a short hash of the key for audit logging (not the key itself).
    """
    if not ADMIN_KEY or not hmac.compare_digest(x_admin_key, ADMIN_KEY):
        raise HTTPException(status_code=403, detail='Invalid admin key')
    return f'admin:{hashlib.sha256(x_admin_key.encode()).hexdigest()[:8]}'


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


@router.get('/v1/admin/fair-use/flagged', tags=['admin'])
def get_flagged_users(
    admin_id: str = Depends(_verify_admin_key),
    stage: Optional[str] = None,
    limit: int = Query(default=50, le=200),
):
    """Get users with active fair-use enforcement."""
    users = fair_use_db.get_flagged_users(stage_filter=stage, limit=limit)
    return {'users': users, 'fair_use_enabled': FAIR_USE_ENABLED}


@router.get('/v1/admin/fair-use/user/{uid}', tags=['admin'])
def get_user_fair_use_detail(uid: str, admin_id: str = Depends(_verify_admin_key)):
    """Get detailed fair-use state and events for a specific user."""
    state = fair_use_db.get_fair_use_state(uid)
    events = fair_use_db.get_fair_use_events(uid, limit=50)
    speech = get_rolling_speech_ms(uid)

    return {
        'uid': uid,
        'state': state,
        'events': events,
        'current_speech_ms': speech,
    }


# ---------------------------------------------------------------------------
# Admin actions
# ---------------------------------------------------------------------------


@router.post('/v1/admin/fair-use/user/{uid}/resolve-event/{event_id}', tags=['admin'])
def resolve_event(uid: str, event_id: str, admin_id: str = Depends(_verify_admin_key), notes: str = Query(default='')):
    """Mark a fair-use event as resolved."""
    fair_use_db.resolve_fair_use_event(uid, event_id, admin_uid=admin_id, notes=notes)
    return {'status': 'resolved'}


@router.post('/v1/admin/fair-use/user/{uid}/reset', tags=['admin'])
def reset_user_fair_use(uid: str, admin_id: str = Depends(_verify_admin_key)):
    """Reset a user's fair-use state to clean."""
    fair_use_db.reset_fair_use_state(uid, admin_uid=admin_id)
    invalidate_enforcement_cache(uid)
    return {'status': 'reset'}


@router.post('/v1/admin/fair-use/user/{uid}/set-stage', tags=['admin'])
def set_user_stage(uid: str, stage: str = Query(...), admin_id: str = Depends(_verify_admin_key)):
    """Manually set a user's enforcement stage."""
    valid_stages = {'none', 'warning', 'throttle', 'restrict'}
    if stage not in valid_stages:
        raise HTTPException(status_code=400, detail=f'Invalid stage. Must be one of: {valid_stages}')

    updates = {'stage': stage}
    if stage == 'none':
        updates['vad_threshold_delta'] = 0.0
        updates['throttle_until'] = None
        updates['restrict_until'] = None

    fair_use_db.update_fair_use_state(uid, updates)
    invalidate_enforcement_cache(uid)
    return {'status': 'updated', 'stage': stage}


@router.get('/v1/admin/fair-use/case/{case_ref}', tags=['admin'])
def lookup_case(case_ref: str, admin_id: str = Depends(_verify_admin_key)):
    """Look up a fair-use event by case reference (for support team)."""
    # Search across all users' events for this case_ref
    query = db.collection_group('fair_use_events').where('case_ref', '==', case_ref).limit(1)
    for doc in query.stream():
        data = doc.to_dict()
        path_parts = doc.reference.path.split('/')
        if len(path_parts) >= 2:
            data['uid'] = path_parts[1]
        data['event_id'] = doc.id
        return data
    raise HTTPException(status_code=404, detail=f'Case {case_ref} not found')


SUPPORT_EMAIL = 'team@basedhardware.com'


# ---------------------------------------------------------------------------
# Public: unauthenticated case status lookup (for tracking page)
# ---------------------------------------------------------------------------


@router.get('/v1/fair-use/case/{case_ref}/status', tags=['fair_use'])
def get_public_case_status(case_ref: str):
    """Public unauthenticated endpoint: look up case status by reference.

    Returns only non-sensitive info: stage, message, timestamps, support email.
    No usage data or user identity exposed.
    """
    query = db.collection_group('fair_use_events').where('case_ref', '==', case_ref).limit(1)
    for doc in query.stream():
        data = doc.to_dict()
        # Extract uid to get current enforcement stage
        path_parts = doc.reference.path.split('/')
        uid = path_parts[1] if len(path_parts) >= 2 else None

        stage = 'none'
        if uid:
            state = fair_use_db.get_fair_use_state(uid)
            stage = state.get('stage', 'none')

        created_at = data.get('created_at')
        updated_at = data.get('resolved_at') or created_at

        return {
            'case_ref': case_ref,
            'stage': stage,
            'message': _user_facing_message(stage, case_ref),
            'created_at': str(created_at) if created_at else None,
            'updated_at': str(updated_at) if updated_at else None,
            'support_email': SUPPORT_EMAIL,
        }
    raise HTTPException(status_code=404, detail='Case not found')


# ---------------------------------------------------------------------------
# Support: user-facing endpoint to see their own fair-use status
# ---------------------------------------------------------------------------


@router.get('/v1/fair-use/status', tags=['fair_use'])
def get_my_fair_use_status(uid: str = Depends(get_current_user_uid)):
    """User-facing endpoint: see your own fair-use status and speech usage."""
    state = fair_use_db.get_fair_use_state(uid)
    speech = get_rolling_speech_ms(uid)

    stage = state.get('stage', 'none')
    case_ref = state.get('last_case_ref', '')

    daily_ms = speech.get('daily_ms', 0)
    three_day_ms = speech.get('three_day_ms', 0)
    weekly_ms = speech.get('weekly_ms', 0)

    return {
        'stage': stage,
        'case_ref': case_ref,
        'speech_hours_today': round(daily_ms / 3600000, 2),
        'speech_hours_3day': round(three_day_ms / 3600000, 2),
        'speech_hours_weekly': round(weekly_ms / 3600000, 2),
        'limits': {
            'daily_hours': round(FAIR_USE_DAILY_SPEECH_MS / 3600000, 2),
            'three_day_hours': round(FAIR_USE_3DAY_SPEECH_MS / 3600000, 2),
            'weekly_hours': round(FAIR_USE_WEEKLY_SPEECH_MS / 3600000, 2),
        },
        'usage_pct': {
            'daily': round(daily_ms / FAIR_USE_DAILY_SPEECH_MS * 100, 1) if FAIR_USE_DAILY_SPEECH_MS else 0,
            'three_day': round(three_day_ms / FAIR_USE_3DAY_SPEECH_MS * 100, 1) if FAIR_USE_3DAY_SPEECH_MS else 0,
            'weekly': round(weekly_ms / FAIR_USE_WEEKLY_SPEECH_MS * 100, 1) if FAIR_USE_WEEKLY_SPEECH_MS else 0,
        },
        'message': _user_facing_message(stage, case_ref),
    }


def _user_facing_message(stage: str, case_ref: str = '') -> str:
    ref_note = f' Your case reference is {case_ref}.' if case_ref else ''
    messages = {
        'none': 'Your usage is within normal limits.',
        'warning': (
            'Your usage is higher than typical. Omi is designed for personal conversations. '
            f'If non-personal content transcription continues, your service may be adjusted.{ref_note}'
        ),
        'throttle': (
            'Your transcription quality has been temporarily reduced due to high non-personal usage. '
            'This will reset automatically. Contact support at team@basedhardware.com if you believe this is an error. '
            f'Please quote your case reference when contacting support.{ref_note}'
        ),
        'restrict': (
            'Your cloud transcription is temporarily limited. On-device transcription continues normally. '
            'Contact support at team@basedhardware.com to discuss your usage and resolve this. '
            f'Please quote your case reference when contacting support.{ref_note}'
        ),
    }
    return messages.get(stage, messages['none'])
