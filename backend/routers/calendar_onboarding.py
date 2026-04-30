"""
Calendar onboarding router.

Guides new users through Google Calendar connection during onboarding.
"""

from fastapi import APIRouter, Depends

import database.users as users_db
from utils.other import endpoints as auth

router = APIRouter()


@router.get('/v1/calendar/onboarding/status', tags=['calendar_onboarding'])
def get_calendar_onboarding_status(uid: str = Depends(auth.get_current_user_uid)):
    """Return whether the user has completed (or skipped) calendar onboarding."""
    integration = users_db.get_integration(uid, 'google_calendar')
    connected = bool(integration and integration.get('connected'))
    return {'connected': connected, 'onboarding_completed': connected}


@router.post('/v1/calendar/onboarding/skip', tags=['calendar_onboarding'])
def skip_calendar_onboarding(uid: str = Depends(auth.get_current_user_uid)):
    """Mark calendar onboarding as skipped so the prompt is not shown again."""
    return {'skipped': True}
