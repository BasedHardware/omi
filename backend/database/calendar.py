from datetime import datetime
from typing import Optional, Dict, Any
from database._client import db
from models.calendar import CalendarIntegration, CalendarEvent, CalendarConfig


def get_user_calendar_integration(uid: str) -> Optional[CalendarIntegration]:
    """Get user's calendar integration configuration."""
    try:
        doc = db.collection('calendar_integrations').document(uid).get()
        if doc.exists:
            data = doc.to_dict()
            return CalendarIntegration(**data)
        return None
    except Exception as e:
        print(f"Error getting calendar integration for user {uid}: {e}")
        return None


def save_user_calendar_integration(uid: str, integration: CalendarIntegration) -> bool:
    """Save or update user's calendar integration configuration."""
    try:
        integration_data = integration.dict()
        integration_data['updated_at'] = datetime.utcnow()
        
        db.collection('calendar_integrations').document(uid).set(integration_data)
        return True
    except Exception as e:
        print(f"Error saving calendar integration for user {uid}: {e}")
        return False


def delete_user_calendar_integration(uid: str) -> bool:
    """Delete user's calendar integration configuration."""
    try:
        db.collection('calendar_integrations').document(uid).delete()
        return True
    except Exception as e:
        print(f"Error deleting calendar integration for user {uid}: {e}")
        return False


def get_user_calendar_config(uid: str) -> Optional[CalendarConfig]:
    """Get user's calendar configuration."""
    try:
        doc = db.collection('calendar_configs').document(uid).get()
        if doc.exists:
            data = doc.to_dict()
            return CalendarConfig(**data)
        return CalendarConfig()  # Return default config if none exists
    except Exception as e:
        print(f"Error getting calendar config for user {uid}: {e}")
        return CalendarConfig()


def save_user_calendar_config(uid: str, config: CalendarConfig) -> bool:
    """Save user's calendar configuration."""
    try:
        config_data = config.dict()
        db.collection('calendar_configs').document(uid).set(config_data)
        return True
    except Exception as e:
        print(f"Error saving calendar config for user {uid}: {e}")
        return False


def save_calendar_event(uid: str, event: CalendarEvent) -> bool:
    """Save a calendar event record."""
    try:
        event_data = event.dict()
        event_data['uid'] = uid
        
        # Use a composite key for the document ID
        doc_id = f"{uid}_{event.calendar_id}_{event.event_id}"
        
        db.collection('calendar_events').document(doc_id).set(event_data)
        return True
    except Exception as e:
        print(f"Error saving calendar event for user {uid}: {e}")
        return False


def get_user_calendar_events(uid: str, limit: int = 50) -> list:
    """Get user's calendar events."""
    try:
        query = db.collection('calendar_events').where('uid', '==', uid).order_by('start_time', direction='DESCENDING').limit(limit)
        docs = query.stream()
        
        events = []
        for doc in docs:
            event_data = doc.to_dict()
            events.append(CalendarEvent(**event_data))
        
        return events
    except Exception as e:
        print(f"Error getting calendar events for user {uid}: {e}")
        return []


def delete_calendar_event(uid: str, calendar_id: str, event_id: str) -> bool:
    """Delete a calendar event record."""
    try:
        doc_id = f"{uid}_{calendar_id}_{event_id}"
        db.collection('calendar_events').document(doc_id).delete()
        return True
    except Exception as e:
        print(f"Error deleting calendar event for user {uid}: {e}")
        return False