"""
Calendar onboarding router.

Guides new users through Google Calendar connection during onboarding.
"""

from fastapi import APIRouter, Depends, Request

import database.users as users_db
from utils.auth_middleware import require_firebase

router = APIRouter(dependencies=[Depends(require_firebase)])


@router.get('/v1/calendar/onboarding/status', tags=['calendar_onboarding'])
def get_calendar_onboarding_status(request: Request):
    """Return whether the user has completed (or skipped) calendar onboarding."""
    uid = request.state.uid
    integration = users_db.get_integration(uid, 'google_calendar')
    connected = bool(integration and integration.get('connected'))
    skipped = bool(integration and integration.get('onboarding_skipped'))
    return {'connected': connected, 'onboarding_completed': connected or skipped}


@router.post('/v1/calendar/onboarding/skip', tags=['calendar_onboarding'])
def skip_calendar_onboarding(request: Request):
    """Mark calendar onboarding as skipped so the prompt is not shown again."""
    uid = request.state.uid
    users_db.set_integration(uid, 'google_calendar', {'onboarding_skipped': True})
    return {'skipped': True}
