import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import database.calendar_meetings as calendar_db
import database.conversations as conversations_db
from database import redis_db
from models.conversation import Conversation
from models.conversation_enums import ConversationSource, ConversationStatus
from models.structured import Structured
from models.transcript_segment import TranscriptSegment
from utils.conversations.factory import deserialize_conversation
from utils.conversations.process_conversation import process_conversation

logger = logging.getLogger(__name__)


class DesktopBackgroundConversationError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def create_in_progress_desktop_conversation(
    uid: str,
    language: str,
    source: ConversationSource = ConversationSource.desktop,
    private_cloud_sync_enabled: bool = False,
    call_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> str:
    """Create a desktop/listen in-progress conversation and Redis pointer."""
    new_conversation_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    stub_conversation = Conversation(
        id=new_conversation_id,
        created_at=now,
        started_at=now,
        finished_at=now,
        structured=Structured(),
        language=language,
        transcript_segments=[],
        photos=[],
        status=ConversationStatus.in_progress,
        source=source,
        private_cloud_sync_enabled=private_cloud_sync_enabled,
        call_id=call_id,
    )
    conversations_db.upsert_conversation(uid, conversation_data=stub_conversation.dict())
    redis_db.set_in_progress_conversation_id(uid, new_conversation_id)

    detected_meeting_id = _detect_current_desktop_meeting(uid) if source == ConversationSource.desktop else None
    if detected_meeting_id:
        redis_db.set_conversation_meeting_id(new_conversation_id, detected_meeting_id)

    logger.info(
        "Created new in-progress conversation: %s uid=%s session=%s source=%s",
        new_conversation_id,
        uid,
        session_id,
        source.value,
    )
    return new_conversation_id


def append_segments_to_in_progress_conversation(
    uid: str,
    conversation_id: str,
    segments: List[TranscriptSegment],
    finished_at: datetime,
) -> List[TranscriptSegment]:
    """Append transcript segments to the in-progress conversation and bump finished_at."""
    conversation_data = conversations_db.get_conversation(uid, conversation_id)
    if not conversation_data:
        raise ValueError("conversation not found")

    conversation = deserialize_conversation(conversation_data)
    if conversation.status != ConversationStatus.in_progress:
        raise ValueError("conversation is not in_progress")

    if not segments:
        conversations_db.update_conversation_finished_at(uid, conversation_id, finished_at)
        return []

    conversation.transcript_segments, updated_segments, _removed_ids = TranscriptSegment.combine_segments(
        conversation.transcript_segments,
        segments,
    )
    conversations_db.update_conversation_segments(
        uid,
        conversation.id,
        [segment.dict() for segment in conversation.transcript_segments],
        finished_at=finished_at,
    )
    return updated_segments


def finish_desktop_background_conversation(uid: str, conversation_id: str) -> Conversation:
    """Finalize one explicit desktop background conversation by ID."""
    conversation_data = conversations_db.get_conversation(uid, conversation_id)
    if not conversation_data:
        raise DesktopBackgroundConversationError("conversation_id not found", status_code=404)

    conversation = deserialize_conversation(conversation_data)
    if conversation.status == ConversationStatus.completed:
        return conversation
    if conversation.status != ConversationStatus.in_progress:
        raise DesktopBackgroundConversationError("conversation is not in_progress", status_code=409)

    conversations_db.update_conversation_status(uid, conversation.id, ConversationStatus.processing)
    processed_conversation = process_conversation(uid, conversation.language, conversation, force_process=True)

    if redis_db.get_in_progress_conversation_id(uid) == conversation.id:
        redis_db.remove_in_progress_conversation_id(uid)

    logger.info(
        "Finished desktop background conversation: %s uid=%s segments=%s",
        conversation.id,
        uid,
        len(processed_conversation.transcript_segments),
    )
    return processed_conversation


def _detect_current_desktop_meeting(uid: str) -> Optional[str]:
    now = datetime.now(timezone.utc)
    time_window = timedelta(minutes=2)
    meetings = calendar_db.get_meetings_in_time_range(uid, now - time_window, now + time_window)

    if len(meetings) == 1:
        return meetings[0]['id']
    if len(meetings) <= 1:
        return None

    closest_meeting = min(meetings, key=lambda meeting: abs((meeting['start_time'] - now).total_seconds()))
    return closest_meeting['id']
