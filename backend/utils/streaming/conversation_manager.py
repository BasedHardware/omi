import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import database.calendar_meetings as calendar_db
import database.conversations as conversations_db
from database import redis_db
from database.redis_db import get_cached_user_geolocation
from models.conversation import (
    Conversation,
    ConversationSource,
    ConversationStatus,
    Geolocation,
    Structured,
)
from models.message_event import ConversationEvent, MessageEvent
from utils.app_integrations import trigger_external_integrations
from utils.conversations.location import get_google_maps_location
from utils.conversations.process_conversation import process_conversation


async def create_in_progress_conversation(
    uid: str,
    language: str,
    source: ConversationSource,
    private_cloud_sync_enabled: bool,
    session_id: str = '',
    check_calendar: bool = False,
    conversation_id: Optional[str] = None,
) -> str:
    """Create a new in-progress conversation stub in DB and Redis. Returns conversation_id."""
    new_conversation_id = conversation_id or str(uuid_mod.uuid4())

    stub_conversation = Conversation(
        id=new_conversation_id,
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        structured=Structured(),
        language=language,
        transcript_segments=[],
        photos=[],
        status=ConversationStatus.in_progress,
        source=source,
        private_cloud_sync_enabled=private_cloud_sync_enabled,
    )
    conversations_db.upsert_conversation(uid, conversation_data=stub_conversation.dict())
    redis_db.set_in_progress_conversation_id(uid, new_conversation_id)

    # Auto-detect calendar meeting (desktop source)
    if check_calendar and source == ConversationSource.desktop:
        detected_meeting_id = _detect_calendar_meeting(uid, session_id)
        if detected_meeting_id:
            redis_db.set_conversation_meeting_id(new_conversation_id, detected_meeting_id)

    print(f"conversation_manager: created stub conversation {new_conversation_id}", uid, session_id)
    return new_conversation_id


def _detect_calendar_meeting(uid: str, session_id: str) -> Optional[str]:
    """Check for a calendar meeting within ±2 minutes of now."""
    now = datetime.now(timezone.utc)
    time_window = timedelta(minutes=2)
    start_range = now - time_window
    end_range = now + time_window

    meetings = calendar_db.get_meetings_in_time_range(uid, start_range, end_range)
    if not meetings:
        return None

    if len(meetings) == 1:
        return meetings[0]['id']

    # Multiple meetings — pick closest by start time
    closest_meeting = None
    smallest_diff = None
    for meeting in meetings:
        time_diff = abs((meeting['start_time'] - now).total_seconds())
        if smallest_diff is None or time_diff < smallest_diff:
            smallest_diff = time_diff
            closest_meeting = meeting

    if closest_meeting:
        print(
            f"conversation_manager: selected closest meeting: {closest_meeting.get('title', 'untitled')} (diff: {smallest_diff}s)",
            uid,
            session_id,
        )
        return closest_meeting['id']

    return None


async def process_completed_conversation(
    uid: str,
    conversation_id: str,
    language: str,
    send_message_event: Optional[Callable[[MessageEvent], None]] = None,
    pusher_handler=None,
    session_id: str = '',
) -> None:
    """Process a completed conversation, either via pusher or locally."""
    print(f"conversation_manager: processing conversation {conversation_id}", uid, session_id)

    conversation_data = conversations_db.get_conversation(uid, conversation_id)
    if not conversation_data:
        print(f"conversation_manager: conversation {conversation_id} not found", uid, session_id)
        return

    has_content = conversation_data.get('transcript_segments') or conversation_data.get('photos')
    if not has_content:
        print(f"conversation_manager: deleting empty conversation {conversation_id}", uid, session_id)
        conversations_db.delete_conversation(uid, conversation_id)
        return

    if pusher_handler is not None and pusher_handler.is_connected():
        # Notify client that processing started
        if send_message_event:
            conversation = Conversation(**conversation_data)
            send_message_event(ConversationEvent(event_type="memory_processing_started", memory=conversation))
        await pusher_handler.request_conversation_processing(conversation_id)
    else:
        # Local fallback
        await _process_conversation_locally(
            uid, conversation_id, conversation_data, language, send_message_event, session_id
        )


async def _process_conversation_locally(
    uid: str,
    conversation_id: str,
    conversation_data: dict,
    language: str,
    send_message_event: Optional[Callable[[MessageEvent], None]] = None,
    session_id: str = '',
) -> None:
    """Process conversation locally when pusher is not available."""
    conversation = Conversation(**conversation_data)

    if conversation.status != ConversationStatus.processing:
        if send_message_event:
            send_message_event(ConversationEvent(event_type="memory_processing_started", memory=conversation))
        conversations_db.update_conversation_status(uid, conversation.id, ConversationStatus.processing)
        conversation.status = ConversationStatus.processing

    try:
        geolocation = get_cached_user_geolocation(uid)
        if geolocation:
            geolocation = Geolocation(**geolocation)
            conversation.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)

        conversation = process_conversation(uid, language, conversation)
        messages = trigger_external_integrations(uid, conversation)
    except Exception as e:
        print(f"conversation_manager: error processing conversation: {e}", uid, session_id)
        conversations_db.set_conversation_as_discarded(uid, conversation.id)
        conversation.discarded = True
        messages = []

    if send_message_event:
        send_message_event(ConversationEvent(event_type="memory_created", memory=conversation, messages=messages))
