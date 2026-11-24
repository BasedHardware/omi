"""Finish the owner-visible v3 window after its source leaves the in-progress lookup."""

from datetime import datetime, timezone

from config.conversations_v3 import conversations_v3_enabled, finish_no_pointer_enabled
from database import conversations_v3_live
from models.conversation import CreateConversationResponse
from models.conversation_enums import ConversationStatus
from utils.conversations.factory import deserialize_conversation
from utils.conversations.v3 import live, metrics, triggers


def finish_live_window(uid: str) -> CreateConversationResponse | None:
    if not finish_no_pointer_enabled() or not conversations_v3_enabled(uid):
        return None

    now = datetime.now(timezone.utc)
    window = conversations_v3_live.live_window(uid, now=now, max_idle=live.MAX_IDLE, pick=live.active)
    if window is None:
        metrics.FINISH_NO_POINTER.labels('no_live_window').inc()
        return None

    conversation = deserialize_conversation(window)
    outcome, recording_id = conversations_v3_live.request_finish(uid, conversation.id, now=now)
    metrics.FINISH_NO_POINTER.labels(outcome).inc()
    if not recording_id:
        return None
    if outcome == 'cut':
        triggers.enqueue_pending(uid, manual_end_id=recording_id)
    conversation.status = ConversationStatus.processing
    conversation.tile_state = 'transcribing' if outcome in {'requested', 'already_requested'} else 'writing'
    return CreateConversationResponse(conversation=conversation, messages=[])
