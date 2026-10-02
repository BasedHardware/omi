```python
from typing import Optional
from datetime import datetime, timezone
from ..utils.firestore import run_with_transaction_contention_retry
from ..utils.validation import _clean_id, _clean_str

def create_meeting(meeting_data: dict) -> str:
    """Creates a new meeting in the calendar Meetings collection."""
    uid = _clean_id(meeting_data.get('uid'))
    meeting_id = _clean_id(meeting_data.get('meeting_id'))

    calendar_source = _clean_str(meeting_data.get('calendar_source', '')) or 'default_calendar'
    calendar_event_id = _clean_str(meeting_data.get('calendar_event_id', ''))

    data = {
        'uid': uid,
        'meeting_id': meeting_id,
        'calendar_source': calendar_source,
        'calendar_event_id': calendar_event_id,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }

    return run_with_transaction_contention_retry(
        lambda: _upsert_meeting_transaction(data)
    )

def get_meeting(meeting_id: str) -> dict:
    """Retrieve a meeting by its ID."""
    cleaned_id = _clean_id(meeting_id)
    return _get_meeting(cleaned_id)

def update_meeting(meeting_id: str, updates: dict) -> bool:
    """Update a meeting by ID with the provided fields."""
    cleaned_id = _clean_id(meeting_id)
    try:
        _update_meeting(cleaned_id, updates)
        return True
    except Exception as e:
        if isinstance(e, ValueError) and str(e) == 'Not Found':
            raise
        raise

def delete_meeting(meeting_id: str) -> bool:
    """Delete a meeting by ID."""
    cleaned_id = _clean_id(meeting_id)
    try:
        _delete_meeting(cleaned_id)
        return True
    except Exception as e:
        if isinstance(e, ValueError) and str(e) == 'Not Found':
            raise
        raise

def list_meetings(limit: int = 500) -> dict:
    """List meetings with optional limit."""
    if limit < 1 or limit > 500:
        limit = 500
    return _list_meetings(limit)
```

```python
from typing import Optional
from datetime import datetime, timezone
from ..utils.firestore import run_with_transaction_contention_retry
from ..utils.validation import _clean_id, _clean_str

def _clean_id(value: str) -> str:
    """Sanitizes and validates an identifier."""
    if not isinstance(value, str):
        value = str(value)
    return value.strip().replace('/', '')

def _clean_str(value: str, default: Optional[str] = None) -> str:
    """Sanitizes a string, returning default if empty."""
    if value:
        return str(value).strip()
    return default if default is not None else ''

def _upsert_meeting_transaction(data: dict) -> str:
    """Upserts a meeting in the calendar Meetings collection."""
    return Firestore().collection('calendar_meetings').document(data['meeting_id']).set(data, merge=True)

def _get_meeting(meeting_id: str) -> dict:
    """Retrieve a meeting by its ID."""
    return Firestore().collection('calendar_meetings').document(meeting_id).get().to_dict() or {}

def _update_meeting(meeting_id: str, updates: dict) -> None:
    """Update a meeting by ID with the provided fields."""
    Firestore().collection('calendar_meetings').document(meeting_id).update(updates)

def _delete_meeting(meeting_id: str) -> None:
    """Delete a meeting by ID."""
    Firestore().collection('calendar_meetings').document(meeting_id).delete()

def _list_meetings(limit: int) -> dict:
    """List meetings with optional limit."""
    return Firestore().collection('calendar_meetings').limit(limit).get().to_dict() or {}
```