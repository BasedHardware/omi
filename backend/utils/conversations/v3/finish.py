"""Finish the owner-visible v3 window after its source leaves the in-progress lookup."""

import logging
from datetime import datetime, timezone

from config.conversations_v3 import conversations_v3_enabled, finish_no_pointer_enabled
from database import conversations_v3_live
from models.conversation import CreateConversationResponse
from models.conversation_enums import ConversationStatus
from utils.conversations.factory import deserialize_conversation
from utils.conversations.v3 import live, metrics, triggers
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def finish_live_window(
    uid: str, window_id: str | None = None, *, allow_recording_fallback: bool = False, named_only: bool = False
) -> CreateConversationResponse | None:
    """``named_only``: finish only the window (or just-sealed capture) ``window_id`` names; None otherwise.

    The route uses it while a legacy row is in progress, so a named v3 Finish never falls back to another
    window or recording, and a miss leaves the legacy Finish to run unchanged.
    """
    if not finish_no_pointer_enabled():
        if not named_only:
            metrics.FINISH_NO_POINTER.labels('disabled').inc()
        return None
    if named_only and not window_id:
        return None
    if not conversations_v3_enabled(uid):
        if not named_only:
            metrics.FINISH_NO_POINTER.labels('owner_not_enabled').inc()
        return None

    now = datetime.now(timezone.utc)
    if window_id:
        window = conversations_v3_live.live_window_by_id(uid, window_id, now=now)
        if window is not None:
            outcome, recording_id = conversations_v3_live.request_finish(uid, window['id'], now=now)
            if outcome != 'no_live_window':
                return _acknowledge(uid, window, outcome, recording_id)
        if named_only:
            named_outcome, named, recording_id = conversations_v3_live.request_named_finish(uid, window_id, now=now)
            if not named:
                return None
            _recovered('named_window')
            return _acknowledge(uid, named, named_outcome, recording_id)
    window = conversations_v3_live.live_window(uid, now=now, max_idle=live.MAX_IDLE, pick=live.active)
    if window is None:
        named_outcome = None
        if window_id:
            # The named window left the live set (a pendant capture seals at a speech pause): finish the
            # capture it names, if that capture just sealed.
            named_outcome, named, recording_id = conversations_v3_live.request_named_finish(uid, window_id, now=now)
            if named:
                _recovered('named_window')
                return _acknowledge(uid, named, named_outcome, recording_id)
        if not allow_recording_fallback:
            metrics.FINISH_NO_POINTER.labels(named_outcome or 'no_live_window').inc()
            return None
        outcome, recording = conversations_v3_live.request_recording_finish(uid, now=now)
        if recording:
            _recovered('none')
        elif named_outcome:
            # Nothing to finish: the name is why this Finish was attempted, so its outcome is the answer.
            logger.info('v3 named Finish found nothing; single-capture fallback outcome=%s', outcome)
            outcome = named_outcome
        return _acknowledge(uid, recording, outcome, recording['id'] if recording else '')
    outcome, recording_id = conversations_v3_live.request_finish(uid, window['id'], now=now)
    return _acknowledge(uid, window, outcome, recording_id)


def _recovered(from_mode):
    record_fallback(
        component='conversation_finalization',
        from_mode=from_mode,
        to_mode='recording',
        reason='other',
        outcome='recovered',
    )


def _acknowledge(uid, window, outcome, recording_id):
    metrics.FINISH_NO_POINTER.labels(outcome).inc()
    if not recording_id:
        return None
    if outcome in {'cut', 'consumed', 'recording_cut', 'named_recording_cut'}:
        triggers.enqueue_pending(uid, manual_end_id=recording_id)
    conversation = deserialize_conversation(window)
    if outcome in {'resolved_empty', 'already_empty', 'already_visible'}:
        # A silent tail can resolve empty while an earlier member still has speech. An already visible
        # window is a completed Home card; Finish answers with it and changes nothing.
        conversation.discarded = outcome != 'already_visible' and not live.has_finish_content({}, window, recording_id)
        conversation.status = ConversationStatus.completed
        conversation.tile_state = 'done'
    else:
        conversation.status = ConversationStatus.processing
        conversation.tile_state = (
            'transcribing'
            if outcome in {'requested', 'already_requested', 'recording_requested', 'named_recording_requested'}
            else 'writing'
        )
    return CreateConversationResponse(conversation=conversation, messages=[])
