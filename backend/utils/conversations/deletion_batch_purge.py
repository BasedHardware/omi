"""Hand a conversation delete's per-conversation batch purge to its durable task.

That purge scans every batch-pipeline row the owner has (prod 2026-11-11: a
6k-row owner held the account gate 53 s, a 34k-row owner 366 s). The tombstone
keeps fencing new batch writes; the purge itself runs on backend-sync.
"""

import logging
from contextlib import contextmanager
from typing import Iterable, Iterator

from fastapi import HTTPException

from database import conversation_tombstones
from utils.cloud_tasks import enqueue_conversation_batch_purge, is_conversation_batch_purge_dispatch_configured
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


@contextmanager
def batch_purges_dispatched_after(uid: str) -> Iterator[None]:
    """Defer ``record_deletion``'s batch purges in this scope, then dispatch them.

    Dispatch runs on success and on failure: every collected id already carries
    a durable pending marker. Without task dispatch configured the purge stays
    inline in ``record_deletion``, unchanged.
    """
    if not is_conversation_batch_purge_dispatch_configured():
        yield
        return
    with conversation_tombstones.defer_batch_purges(uid) as deferred:
        try:
            yield
        except BaseException:
            dispatch_deferred_batch_purges(uid, deferred, raise_on_failure=False)
            raise
        dispatch_deferred_batch_purges(uid, deferred, raise_on_failure=True)


def dispatch_deferred_batch_purges(uid: str, conversation_ids: Iterable[str], *, raise_on_failure: bool) -> None:
    """Enqueue each collected purge; an enqueue failure falls back to the inline purge."""
    stranded = 0
    for conversation_id in conversation_ids:
        try:
            enqueue_conversation_batch_purge(uid, conversation_id)
            continue
        except Exception as error:
            record_fallback(
                component='other',
                from_mode='cloud_tasks',
                to_mode='inline_batch_purge',
                reason='other',
                outcome='degraded',
                log=logger,
            )
            logger.warning(
                'event=conversation_delete action=batch_purge_enqueue outcome=error exception_type=%s',
                type(error).__name__,
            )
        try:
            conversation_tombstones.run_batch_purge(uid, conversation_id)
        except Exception as error:
            # The pending marker on the tombstone survives for a re-drive.
            stranded += 1
            logger.error(
                'event=conversation_delete action=batch_purge_inline outcome=error exception_type=%s',
                type(error).__name__,
            )
    if stranded and raise_on_failure:
        # A retried delete re-records the marker and enqueues again.
        raise HTTPException(503, 'Conversation storage deletion is busy, please retry')
