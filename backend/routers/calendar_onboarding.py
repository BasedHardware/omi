"""
Calendar onboarding router.

Guides new users through Google Calendar connection during onboarding.
"""

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import database.users as users_db
from utils.other import endpoints as auth

router = APIRouter()


class CalendarOnboardingStatusResponse(BaseModel):
    connected: bool
    onboarding_completed: bool
    needs_reconnect: bool
    reauth_reason: Optional[str] = None
    state: str


class CalendarOnboardingSkipResponse(BaseModel):
    skipped: bool


def _calendar_onboarding_state(integration: Optional[dict]) -> dict:
    """Derive the calendar onboarding / reconnect state from the google_calendar integration.

    Adds needs_reconnect + reauth_reason so the app can distinguish a never-connected user (show
    "Connect calendar") from one whose OAuth token died (show "Reconnect calendar"). The backend
    already writes reauth_required/reauth_reason and deletes access_token when a token refresh fails,
    but no endpoint surfaced it. The existing connected / onboarding_completed semantics are unchanged.
    """
    integration = integration or {}
    connected = bool(integration.get('connected'))
    skipped = bool(integration.get('onboarding_skipped'))
    reauth_required = bool(integration.get('reauth_required'))
    has_token = bool(integration.get('access_token'))
    needs_reconnect = reauth_required or (connected and not has_token)
    reauth_reason = integration.get('reauth_reason') if reauth_required else None
    if needs_reconnect:
        state = 'needs_reconnect'
    elif connected:
        state = 'connected'
    elif skipped:
        state = 'skipped'
    else:
        state = 'not_started'
    return {
        'connected': connected,
        'onboarding_completed': connected or skipped,
        'needs_reconnect': needs_reconnect,
        'reauth_reason': reauth_reason,
        'state': state,
    }


@router.get(
    '/v1/calendar/onboarding/status',
    tags=['calendar_onboarding'],
    response_model=CalendarOnboardingStatusResponse,
)
def get_calendar_onboarding_status(uid: str = Depends(auth.get_current_user_uid)):
    """Return the calendar onboarding state, including whether a previously-connected calendar now
    needs reconnecting (its OAuth token expired)."""
    return _calendar_onboarding_state(users_db.get_integration(uid, 'google_calendar'))


@router.post(
    '/v1/calendar/onboarding/skip',
    tags=['calendar_onboarding'],
    response_model=CalendarOnboardingSkipResponse,
)
def skip_calendar_onboarding(uid: str = Depends(auth.get_current_user_uid)):
    """Mark calendar onboarding as skipped so the prompt is not shown again."""
    users_db.set_integration(uid, 'google_calendar', {'onboarding_skipped': True})
    return {'skipped': True}


class CalendarOnboardingResetResponse(BaseModel):
    reset: bool


@router.post(
    '/v1/calendar/onboarding/reset', response_model=CalendarOnboardingResetResponse, tags=['calendar_onboarding']
)
def reset_calendar_onboarding(uid: str = Depends(auth.get_current_user_uid)):
    """Clear the skipped / reauth flags so the connect-calendar prompt is shown again."""
    users_db.set_integration(
        uid, 'google_calendar', {'onboarding_skipped': False, 'reauth_required': False, 'reauth_reason': None}
    )
    return {'reset': True}
