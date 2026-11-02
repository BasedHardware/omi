"""Explicit processing satisfies an outstanding sync hold without another paid run."""

from typing import Any
import time

from database import conversations as conversations_db
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.summary_delivery import present, PROCESS_CONTEXT
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
    if trigger not in EXPLICIT or not processing_hold.owns_runtime():
        return
    revision = getattr(conversation, 'sync_content_revision', None)
    if revision is None or not (conversation.discarded or present(conversation.structured)):
        return
    if not processing_hold.enabled():
        # Rollback must still settle existing debt, including a budget-choice
        # completion whose automatic first-summary row is already dormant.
        stored = conversations_db.get_conversation(uid, conversation.id)
        if not stored or processing_hold.FIELD not in stored:
            return
    # A later append winning this fence still owes its automatic quiet window.
    # Manual runs change the baseline, never consume the automatic late budget.
    conversations_db.complete_sync_processing_hold(
        uid,
        conversation.id,
        revision,
        processing_hold.content_snapshot(conversation.model_dump()) if present(conversation.structured) else None,
        automatic=False,
    )


def defer_held_budget_denial() -> None:
    context = PROCESS_CONTEXT.get()
    if context and context.get('sync_hold'):
        if context.get('hold_outcome') == 'max_hold':
            # The one-hour cap is terminal even when the funded refresh cannot
            # run. The callback settles the hold and merge ledger without
            # re-arming another quiet window.
            context['hold_budget_denied_at_max'] = True
            return
        # A prior summary is not a receipt for this revision. Keep the outbox
        # wake through resets/upgrades, including a denial at a later dispatch.
        raise processing_hold.ProcessingDeferred('processing_budget', time.time() + processing_hold.QUIET_SECONDS)
