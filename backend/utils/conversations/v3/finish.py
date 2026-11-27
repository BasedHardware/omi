"""Finish the owner-visible v3 window after its source leaves the in-progress lookup."""

import logging
from datetime import datetime, timezone
from typing import Callable

from config.conversations_v3 import (
    conversations_v3_enabled,
    finish_newer_capture_enabled,
    finish_no_pointer_enabled,
)
from database import conversations_v3_live
from models.conversation import CreateConversationResponse
from models.conversation_enums import ConversationStatus
from utils.conversations.factory import deserialize_conversation
from utils.conversations.v3 import live, metrics, triggers
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def finish_live_window(
    uid: str,
    window_id: str | None = None,
    *,
    allow_recording_fallback: bool = False,
    named_only: bool = False,
    observe_recording: Callable[[str], None] | None = None,
) -> CreateConversationResponse | None:
    """``named_only``: finish only the window (or just-sealed capture) ``window_id`` names, never a newer
    capture that superseded it (``strict``); None otherwise.

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
    # A holdout named_only Finish answers for the named window alone, so it never redirects to a newer capture.
    newer_capture = finish_newer_capture_enabled() and not named_only
    if window_id:
        window = conversations_v3_live.live_window_by_id(uid, window_id, now=now)
        if window is not None:
            outcome, recording_id, capture = conversations_v3_live.request_finish(
                uid, window['id'], now=now, newer_capture=newer_capture
            )
            if outcome != 'no_live_window':
                return _acknowledge(uid, capture or window, outcome, recording_id, observe_recording)
        if named_only:
            named_outcome, named, recording_id = conversations_v3_live.request_named_finish(
                uid, window_id, now=now, strict=True
            )
            if not named:
                metrics.FINISH_NO_POINTER.labels(named_outcome or 'no_live_window').inc()
                return None
            _recovered('named_window')
            return _acknowledge(uid, named, named_outcome, recording_id, observe_recording)
    window = conversations_v3_live.live_window(uid, now=now, max_idle=live.MAX_IDLE, pick=live.active)
    if window is None:
        named_outcome = None
        if window_id:
            # The named window left the live set (a pendant capture seals at a speech pause): finish the
            # capture it names, if that capture just sealed.
            named_outcome, named, recording_id = conversations_v3_live.request_named_finish(uid, window_id, now=now)
            if named:
                _recovered('named_window')
                return _acknowledge(uid, named, named_outcome, recording_id, observe_recording)
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
        return _acknowledge(uid, recording, outcome, recording['id'] if recording else '', observe_recording)
    # A capture that sealed after the window's last speech takes the cut, and the answer names it.
    outcome, recording_id, capture = conversations_v3_live.request_finish(
        uid, window['id'], now=now, newer_capture=newer_capture
    )
    return _acknowledge(uid, capture or window, outcome, recording_id, observe_recording)


def _recovered(from_mode):
    record_fallback(
        component='conversation_finalization',
        from_mode=from_mode,
        to_mode='recording',
        reason='other',
        outcome='recovered',
    )


# Finish outcomes that cut or request a recording on this deliberate Finish (or found it already cut or
# requested). Prefixed variants (``named_*`` from a Finish that named a window which left the live set, and
# ``newer_*``/``newer_dual_*`` from a Finish that moved to a newer capture) are the same act on another
# path, so the deliberate-Finish SLI strips the prefix before matching.
DELIBERATE_FINISH_OUTCOMES = frozenset(
    {
        'already_cut',
        'already_requested',
        'consumed',
        'cut',
        'recording_cut',
        'recording_requested',
        'requested',
    }
)


def deliberate_finish(outcome: str) -> bool:
    base = outcome.removeprefix('named_').removeprefix('newer_').removeprefix('dual_')
    return base in DELIBERATE_FINISH_OUTCOMES


def _acknowledge(uid, window, outcome, recording_id, observe_recording=None):
    metrics.FINISH_NO_POINTER.labels(outcome).inc()
    if not recording_id:
        return None
    # The SLI binds the recording the answer names, the same response target that carries the
    # v3_finish_requested stamp: the newer capture on ``newer_*``, the window tail on ``newer_dual_*`` (the
    # capture's request rides along unstamped and unbound) and on ``tail`` or a declined newer capture.
    if observe_recording is not None and deliberate_finish(outcome):
        observe_recording(recording_id)
    # A Finish that found a newer capture is counted apart (``newer_*``; ``newer_dual_*`` when the window tail
    # was cut and the capture requested too) and answered like the path that stored it.
    outcome = outcome.removeprefix('newer_').removeprefix('dual_')
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
