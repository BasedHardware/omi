"""Explicit processing satisfies an outstanding sync hold without another paid run."""

from typing import Any

from database import conversations as conversations_db
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.summary_delivery import present
from utils.sync import processing_hold

EXPLICIT = frozenset(
    {
        ProcessingTrigger.CLIENT_FINALIZE,
        ProcessingTrigger.BACKLOG_CHOICE,
        ProcessingTrigger.FIRST_OPEN,
        ProcessingTrigger.USER_REPROCESS,
        ProcessingTrigger.MERGE,
    }
)


def complete_explicit(uid: str, conversation: Any, trigger: ProcessingTrigger) -> None:
    if trigger not in EXPLICIT or not processing_hold.scheduling_enabled():
        return
    revision = getattr(conversation, 'sync_content_revision', None)
    if revision is None or not (conversation.discarded or present(conversation.structured)):
        return
    # A later append winning this fence still owes its automatic quiet window.
    # Manual runs change the baseline, never consume the automatic late budget.
    conversations_db.complete_sync_processing_hold(
        uid,
        conversation.id,
        revision,
        processing_hold.content_snapshot(conversation.model_dump()),
        automatic=False,
    )
