"""Conversation deletes arm batch-purge obligations; the reconciler dispatches them.

That purge scans every batch-pipeline row the owner has (prod 2026-11-11: a
6k-row owner held the account gate 53 s, a 34k-row owner 366 s), so the delete
request only arms a durable obligation next to its tombstone. Producers never
enqueue: dispatch belongs to this reconciler, which first proves the serving
consumer has the route, then sends each due obligation as a new generation.
"""

import logging
from contextlib import contextmanager
from typing import Iterator

from database import conversation_batch_purge_jobs as purge_jobs
from database import conversation_tombstones
from utils.cloud_tasks import (
    conversation_batch_purge_consumer_ready,
    enqueue_conversation_batch_purge,
    is_conversation_batch_purge_dispatch_configured,
)

logger = logging.getLogger(__name__)

ENQUEUE_RETRY_SECONDS = 60
# Repeated generations without completion page someone; the obligation is never dropped.
ALERT_AFTER_GENERATIONS = 8


@contextmanager
def deferred_batch_purges(uid: str) -> Iterator[None]:
    """Inside this scope ``record_deletion`` arms an obligation instead of purging inline.

    Without task dispatch configured (dev, local, tests) the purge stays inline.
    """
    if not is_conversation_batch_purge_dispatch_configured():
        yield
        return
    with conversation_tombstones.defer_batch_purges(uid):
        yield


def reconcile_conversation_batch_purges(limit: int = 50) -> dict[str, int]:
    """Dispatch due obligations: new deletes, lost tasks, exhausted retries, released holds."""
    if not is_conversation_batch_purge_dispatch_configured():
        return {}
    due = purge_jobs.due_jobs(limit=limit)
    if not due:
        return {}
    ready = conversation_batch_purge_consumer_ready()
    if ready is False:
        # Rollout or rollback: the serving consumer lacks the route. Obligations wait.
        logger.warning('conversation batch purge consumer not serving the route; holding %d due', len(due))
        return {'due': len(due), 'held_for_consumer': len(due)}
    counts = {'due': len(due), 'dispatched': 0, 'skipped': 0, 'enqueue_failed': 0}
    for snapshot in due:
        generation = purge_jobs.claim_dispatch(snapshot.id)
        if generation is None:
            counts['skipped'] += 1
            continue
        if generation > ALERT_AFTER_GENERATIONS:
            logger.error(
                'conversation batch purge obligation still pending job=%s generation=%d', snapshot.id, generation
            )
        try:
            enqueue_conversation_batch_purge(snapshot.id, generation)
            counts['dispatched'] += 1
        except Exception as error:
            counts['enqueue_failed'] += 1
            logger.warning(
                'conversation batch purge enqueue failed job=%s exception_type=%s', snapshot.id, type(error).__name__
            )
            purge_jobs.defer(snapshot.id, ENQUEUE_RETRY_SECONDS)
    return counts
