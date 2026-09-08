from datetime import datetime
from typing import List, Optional

from database import conversations as conversations_db
from utils.sync.lanes import capture_times_within_window

_CAPTURE_PROVENANCE_SLOP_SECONDS = 30 * 60


def capture_matches_server_conversation(
    uid: str,
    conversation_id: Optional[str],
    filenames: List[str],
    client_device_id: Optional[str],
) -> bool:
    """Bind fresh classification to a server-created conversation time window."""
    if not conversation_id or not client_device_id:
        return False
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation or conversation.get('client_device_id') != client_device_id:
        return False
    started_at = conversation.get('started_at')
    finished_at = conversation.get('finished_at') or started_at
    if not isinstance(started_at, datetime) or not isinstance(finished_at, datetime):
        return False
    lower = started_at.timestamp() - _CAPTURE_PROVENANCE_SLOP_SECONDS
    upper = finished_at.timestamp() + _CAPTURE_PROVENANCE_SLOP_SECONDS
    return capture_times_within_window(filenames, lower, upper)
