"""Stop an enrichment reprocess run before its LLM work once a newer sync revision owns the conversation.

The enrichment consumer marks its delivery (``ACTIVE``); ``process_conversation`` builds the checkpoint from
the conversation it was handed, so the frozen legacy sync callback and every other caller are unchanged.
A run is fenced only while its row is live: a deleted or redirected row continues so the existing redirect
handling (``before_notes`` -> ``ConversationAbsorbed`` -> custody transfer) keeps the outbox obligation.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, Callable

from utils.enrichment.admission import SyncConversationPersistenceFenced

logger = logging.getLogger(__name__)

ACTIVE: ContextVar[bool] = ContextVar('enrichment_early_abort_active', default=False)
_FIELDS = ['sync_content_revision', 'deleted', 'sync_merged_into']


def checkpoint_for(uid: str, conversation: Any) -> Callable[[str], None] | None:
    """A revision checkpoint for this enrichment delivery, or None when none applies."""
    if not ACTIVE.get():
        return None
    from config.sync_reprocess import early_abort_enabled

    snapshot = getattr(conversation, 'sync_content_revision', None)
    target = getattr(conversation, 'id', None)
    if not isinstance(snapshot, int) or not isinstance(target, str) or not early_abort_enabled():
        return None
    from database import conversations as conversations_db
    from utils.metrics import OMI_ENRICHMENT_EARLY_ABORT_TOTAL

    def check(stage: str) -> None:
        try:
            current = conversations_db.get_conversation_raw_snapshot(uid, target, field_paths=_FIELDS)
        except Exception as error:
            OMI_ENRICHMENT_EARLY_ABORT_TOTAL.labels(stage=stage, outcome='check_failed').inc()
            logger.warning(
                'event=enrichment_early_abort outcome=check_failed stage=%s exception_type=%s',
                stage,
                type(error).__name__,
            )
            return
        # Missing, deleted or redirected rows keep today's path: the redirect transfer or the persist fence decides.
        if not current or current.get('deleted') or current.get('sync_merged_into'):
            return
        if current.get('sync_content_revision') == snapshot:
            return
        OMI_ENRICHMENT_EARLY_ABORT_TOTAL.labels(stage=stage, outcome='superseded').inc()
        logger.info('event=enrichment_early_abort outcome=superseded stage=%s', stage)
        raise SyncConversationPersistenceFenced('sync conversation revision moved before %s' % stage)

    return check
