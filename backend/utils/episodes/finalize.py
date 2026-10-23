"""Episode hooks around a conversation's finalize, shared by every finalize path.

- ``close_now``: the finalize is starting. The conversation's live episode closes
  before its processing runs (``service.close_on_finalize``), so the app's next read
  shows no live episode and the next words open a new one. The durable finalizer
  calls it when a job starts; client-finalize routes call it with the request.
- ``schedule_after_finalization``: the durable finalizer's post-processing hook
  (``service.on_conversation_finalized``: tail notes, item reconciliation) for
  the synchronous ``POST /v1/conversations`` route, run off the request path.

Both are fail-open and cheap for users outside the episodes cohort. The episode
service is imported at the call, so importing a router never loads it.
"""

from __future__ import annotations

import logging
from typing import Any

from config.episodes import episodes_enabled_for
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.episodes import client_gate
from utils.executors import lifecycle_executor, submit_with_context

logger = logging.getLogger(__name__)


def close_now(uid: str, conversation_id: str, trigger: ProcessingTrigger, source: Any = None) -> str:
    """Close the conversation's live episode now. Blocking; never raises."""
    if not episodes_enabled_for(uid):
        return 'disabled'
    try:
        if not client_gate.client_seen_cached(uid):
            # No app of this user shows episodes: nothing to close, and the service is never loaded.
            return 'skipped_no_client'
        from utils.episodes.service import close_on_finalize

        return close_on_finalize(uid, conversation_id, trigger=trigger.value, source=source)
    except Exception as error:
        logger.warning('event=episode_finalize_close outcome=error exception_type=%s', type(error).__name__)
        return 'error'


def schedule_after_finalization(uid: str, conversation_id: str, trigger: ProcessingTrigger) -> None:
    """Run the post-processing episode hook on the episode pool; the caller never waits."""
    if not episodes_enabled_for(uid):
        return
    try:
        submit_with_context(lifecycle_executor(uid, episode=True), _after_finalization, uid, conversation_id, trigger)
    except Exception as error:
        logger.warning('event=episode_finalize outcome=error exception_type=%s', type(error).__name__)


def _after_finalization(uid: str, conversation_id: str, trigger: ProcessingTrigger) -> None:
    from database import conversations as conversations_db
    from utils.episodes.service import on_conversation_finalized

    row = conversations_db.get_conversation(uid, conversation_id)
    if row:
        on_conversation_finalized(uid, conversation_id, row, trigger=trigger.value)
