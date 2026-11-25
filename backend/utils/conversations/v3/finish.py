"""Finish the owner-visible v3 window after its source leaves the in-progress lookup."""

from datetime import datetime, timezone

from config.conversations_v3 import conversations_v3_enabled, finish_no_pointer_enabled
from database import conversations_v3_live
from models.conversation import CreateConversationResponse
from models.conversation_enums import ConversationStatus
from utils.conversations.factory import deserialize_conversation
from utils.conversations.v3 import live, metrics, triggers
from utils.observability.fallback import record_fallback


def finish_live_window(uid: str, window_id: str | None = None) -> CreateConversationResponse | None:
    if not finish_no_pointer_enabled():
        metrics.FINISH_NO_POINTER.labels('disabled').inc()
        return None
    if not conversations_v3_enabled(uid):
        metrics.FINISH_NO_POINTER.labels('owner_not_enabled').inc()
        return None

    now = datetime.now(timezone.utc)
    if window_id:
        window = conversations_v3_live.live_window_by_id(uid, window_id, now=now)
        if window is not None:
            outcome, recording_id = conversations_v3_live.request_finish(uid, window['id'], now=now)
            if outcome != 'no_live_window':
                return _acknowledge(uid, window, outcome, recording_id)
    window = conversations_v3_live.live_window(uid, now=now, max_idle=live.MAX_IDLE, pick=live.active)
    if window is None:
        if window_id:
            metrics.FINISH_NO_POINTER.labels('no_live_window').inc()
            return None
        outcome, recording = conversations_v3_live.request_recording_finish(uid, now=now)
        if recording:
            record_fallback(
                component='conversation_finalization',
                from_mode='none',
                to_mode='recording',
                reason='other',
                outcome='recovered',
            )
        return _acknowledge(uid, recording, outcome, recording['id'] if recording else '')
    outcome, recording_id = conversations_v3_live.request_finish(uid, window['id'], now=now)
    return _acknowledge(uid, window, outcome, recording_id)


def _acknowledge(uid, window, outcome, recording_id):
    metrics.FINISH_NO_POINTER.labels(outcome).inc()
    if not recording_id:
        return None
    if outcome in {'cut', 'consumed', 'recording_cut'}:
        triggers.enqueue_pending(uid, manual_end_id=recording_id)
    conversation = deserialize_conversation(window)
    if outcome in {'resolved_empty', 'already_empty'}:
        conversation.status = ConversationStatus.completed
        conversation.tile_state = 'done'
    else:
        conversation.status = ConversationStatus.processing
        conversation.tile_state = (
            'transcribing' if outcome in {'requested', 'already_requested', 'recording_requested'} else 'writing'
        )
    return CreateConversationResponse(conversation=conversation, messages=[])
