```python
# backend/routers/google_calendar.py

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from typing import Optional
import logging

# Ensure the custom logger is imported or available
logger = logging.getLogger(__name__)

async def _get_google_calendar_token(google_calendar: GoogleCalendarIntegration) -> str:
    if google_calendar.access_token is None:
        if google_calendar.refresh_token is None:
            raise HTTPException(
                status_code=400,
                detail="No access token found and no refresh token available."
            )
        try:
            # Attempt to refresh the token
            token = await google_calendar.get_access_token()
            return token
        except Exception as e:
            logger.error(f"Failed to refresh Google Calendar token: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Failed to refresh Google Calendar token."
            )
    return google_calendar.access_token

async def list_google_calendar_events(
    user: User = Depends()
) -> JSONResponse:
    try:
        calendar = await user.get_google_calendar()
        if calendar is None:
            raise HTTPException(
                status_code=400,
                detail="Google Calendar integration not found."
            )
        events = await calendar.list_events()
        return JSONResponse(content={"events": [_event_to_response(e) for e in events]})
    except GoogleAPIError as e:
        if "invalid_grant" in str(e) or "401" in str(e):
            raise HTTPException(
                status_code=401,
                detail="Google Calendar authentication failed. Please re-authenticate."
            )
        logger.error(f"Google Calendar API error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
    except HTTPStatusError as e:
        if "401" in str(e):
            raise HTTPException(
                status_code=401,
                detail="Google Calendar authentication failed. Please re-authenticate."
            )
        logger.error(f"HTTP error from Google Calendar: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

async def get_calendar_capture_gaps(
    user: User = Depends()
) -> JSONResponse:
    try:
        calendar = await user.get_google_calendar()
        if calendar is None:
            raise HTTPException(
                status_code=400,
                detail="Google Calendar integration not found."
            )
        gaps = await calendar.get_capture_gaps()
        return JSONResponse(content={"gaps": gaps})
    except GoogleAPIError as e:
        if "invalid_grant" in str(e) or "401" in str(e):
            raise HTTPException(
                status_code=401,
                detail="Google Calendar authentication failed. Please re-authenticate."
            )
        logger.error(f"Google Calendar API error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
    except HTTPStatusError as e:
        if "401" in str(e):
            raise HTTPException(
                status_code=401,
                detail="Google Calendar authentication failed. Please re-authenticate."
            )
        logger.error(f"HTTP error from Google Calendar: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

def _event_to_response(event: dict) -> dict:
    return {
        "title": event.get('summary', 'Untitled Event') or 'Untitled Event',
        "start": event.get('start'),
        "end": event.get('end'),
        "id": event.get('id'),
    }
```