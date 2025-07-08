import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from database.calendar import (
    get_user_calendar_integration,
    save_user_calendar_config,
    get_user_calendar_config,
    delete_user_calendar_integration,
    get_user_calendar_events
)
from models.calendar import CalendarConfig, CalendarEventCreate
from routers.custom_auth import get_current_user_uid
from utils.calendar import calendar_service

router = APIRouter(
    prefix="/v1/calendar",
    tags=["calendar"]
)

# Templates setup
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@router.get("/auth")
async def initiate_google_auth(uid: str = Depends(get_current_user_uid)):
    """Initiate Google Calendar OAuth flow."""
    try:
        auth_url = calendar_service.get_auth_url(uid)
        return {"auth_url": auth_url}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initiate OAuth: {str(e)}")


@router.get("/oauth/callback")
async def handle_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None)
):
    """Handle Google OAuth callback."""
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing authorization code or state")
    
    uid = state
    
    try:
        integration = calendar_service.exchange_code_for_tokens(code, uid)
        
        if integration:
            # Return success page or redirect
            success_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Calendar Integration Success</title>
                <style>
                    body { font-family: Arial, sans-serif; max-width: 600px; margin: 50px auto; text-align: center; }
                    .success { color: #4CAF50; }
                    .button { background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }
                </style>
            </head>
            <body>
                <h1 class="success">✅ Calendar Integration Successful!</h1>
                <p>Your Google Calendar has been successfully connected to Omi.</p>
                <p>You can now close this window and return to the Omi app.</p>
                <a href="/" class="button">Return to Omi</a>
            </body>
            </html>
            """
            return HTMLResponse(content=success_html)
        else:
            raise HTTPException(status_code=500, detail="Failed to complete OAuth flow")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth callback error: {str(e)}")


@router.get("/status")
async def get_calendar_status(uid: str = Depends(get_current_user_uid)):
    """Get user's calendar integration status."""
    integration = get_user_calendar_integration(uid)
    config = get_user_calendar_config(uid)
    
    return {
        "connected": integration is not None,
        "calendar_name": integration.calendar_name if integration else None,
        "timezone": integration.timezone if integration else None,
        "config": config.dict() if config else None,
        "last_updated": integration.updated_at.isoformat() if integration and integration.updated_at else None
    }


@router.get("/config")
async def get_calendar_config(uid: str = Depends(get_current_user_uid)):
    """Get user's calendar configuration."""
    config = get_user_calendar_config(uid)
    return config.dict()


@router.put("/config")
async def update_calendar_config(
    config: CalendarConfig,
    uid: str = Depends(get_current_user_uid)
):
    """Update user's calendar configuration."""
    try:
        if save_user_calendar_config(uid, config):
            return {"message": "Calendar configuration updated successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to update calendar configuration")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating config: {str(e)}")


@router.delete("/disconnect")
async def disconnect_calendar(uid: str = Depends(get_current_user_uid)):
    """Disconnect user's calendar integration."""
    try:
        if delete_user_calendar_integration(uid):
            return {"message": "Calendar integration disconnected successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to disconnect calendar integration")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error disconnecting: {str(e)}")


@router.post("/events")
async def create_calendar_event(
    event: CalendarEventCreate,
    uid: str = Depends(get_current_user_uid)
):
    """Create a calendar event."""
    try:
        created_event = calendar_service.create_event(uid, event)
        
        if created_event:
            return {
                "message": "Event created successfully",
                "event": created_event.dict()
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to create calendar event")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating event: {str(e)}")


@router.get("/events")
async def get_calendar_events(
    days_ahead: int = Query(30, ge=1, le=365),
    uid: str = Depends(get_current_user_uid)
):
    """Get upcoming calendar events."""
    try:
        events = calendar_service.get_events(uid, days_ahead)
        return {"events": events}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting events: {str(e)}")


@router.get("/events/history")
async def get_calendar_events_history(
    limit: int = Query(50, ge=1, le=100),
    uid: str = Depends(get_current_user_uid)
):
    """Get user's calendar events history."""
    try:
        events = get_user_calendar_events(uid, limit)
        return {"events": [event.dict() for event in events]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting events history: {str(e)}")


@router.post("/memories/{memory_id}/create-event")
async def create_event_from_memory(
    memory_id: str,
    uid: str = Depends(get_current_user_uid)
):
    """Create a calendar event from a memory/conversation."""
    try:
        # This would need to be implemented to fetch memory data
        # For now, we'll return a placeholder
        return {"message": "Memory event creation not yet implemented"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating memory event: {str(e)}")


# Webhook endpoint for automatic event creation
@router.post("/webhook/memory-created")
async def handle_memory_created_webhook(memory_data: Dict[str, Any]):
    """Handle memory creation webhook to automatically create calendar events."""
    try:
        uid = memory_data.get('uid')
        if not uid:
            raise HTTPException(status_code=400, detail="Missing user ID")
        
        # Check if user has calendar integration enabled
        integration = get_user_calendar_integration(uid)
        if not integration:
            return {"message": "User has no calendar integration"}
        
        # Create calendar event from memory
        event = calendar_service.create_memory_event(uid, memory_data)
        
        if event:
            return {
                "message": "Calendar event created successfully",
                "event_id": event.id
            }
        else:
            return {"message": "Calendar event creation skipped or failed"}
            
    except Exception as e:
        print(f"Error in memory webhook: {e}")
        raise HTTPException(status_code=500, detail=f"Webhook error: {str(e)}")


@router.get("/test")
async def test_calendar_integration(uid: str = Depends(get_current_user_uid)):
    """Test endpoint to verify calendar integration."""
    try:
        integration = get_user_calendar_integration(uid)
        if not integration:
            return {"status": "not_connected", "message": "No calendar integration found"}
        
        # Try to get credentials
        credentials = calendar_service.get_credentials(uid)
        if not credentials:
            return {"status": "invalid_credentials", "message": "Invalid or expired credentials"}
        
        # Try to fetch a few events
        events = calendar_service.get_events(uid, days_ahead=7)
        
        return {
            "status": "connected",
            "calendar_name": integration.calendar_name,
            "timezone": integration.timezone,
            "events_count": len(events),
            "sample_events": events[:3]  # Return first 3 events as sample
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}