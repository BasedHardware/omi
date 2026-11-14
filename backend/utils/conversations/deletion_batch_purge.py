"""Conversation deletes arm batch-purge obligations; the reconciler dispatches them.

That purge scans every batch-pipeline row the owner has (prod 2026-11-11: a
6k-row owner held the account gate 53 s, a 34k-row owner 366 s), so the delete
request only arms a durable obligation next to its tombstone. Producers never
enqueue: dispatch belongs to this reconciler, which first proves the serving
consumer has the route, then sends each due obligation as a new generation.

It also dispatches accepted-delete erasures (``conversation_erasure_jobs``). One
account's erasures run one at a time behind its gate, so at most
``MAX_ERASURES_PER_ACCOUNT`` of them go out per pass and the rest are spread
over later passes: a 53-delete burst neither fills the shared queue with gate
waiters nor starves other accounts.
"""

import logging
from contextlib import contextmanager
from typing import Iterator

from database import conversation_batch_purge_jobs as purge_jobs
from database import conversation_tombstones
from utils.observability.fallback import record_fallback
from utils.cloud_tasks import (
    conversation_batch_purge_consumer_ready,
    enqueue_conversation_batch_purge,
    is_conversation_batch_purge_dispatch_configured,
)

logger = logging.getLogger(__name__)

ENQUEUE_RETRY_SECONDS = 60
# Dispatches without progress (checkpoint hand-offs reset the count) log an error;
# the obligation is never dropped.
ALERT_AFTER_ATTEMPTS = 8
# The account-deletion queue runs 4 dispatches at once (prod) and a cascade takes ~5 s, so
# 6 per pass finish inside one erasure's 45 s gate wait without holding every slot all pass.
MAX_ERASURES_PER_ACCOUNT = 6
ERASURE_SPREAD_SECONDS = 60
# Scan wider than one pass dispatches, so one account's backlog cannot hide everyone else's.
ERASURE_SCAN_FACTOR = 4


def accepts_conversation_deletes() -> bool:
    """A busy account gate may accept a delete only where its erasure obligation is dispatched."""
    return is_conversation_batch_purge_dispatch_configured() is True


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
    erasures = purge_jobs.due_jobs(limit=limit * ERASURE_SCAN_FACTOR, collection=purge_jobs.ERASURE_COLLECTION)
    if not due and not erasures:
        return {}
    ready = conversation_batch_purge_consumer_ready()
    if ready is False:
        # Rollout or rollback: the serving consumer lacks the route. Obligations wait.
        held = len(due) + len(erasures)
        logger.warning('conversation batch purge consumer not serving the route; holding %d due', held)
        return {'due': held, 'held_for_consumer': held}
    if ready is None:
        # Fail-open: the probe could not answer, so dispatch is unverified. A task
        # that reaches an old consumer is lost only until the redrive.
        record_fallback(
            component='other',
            from_mode='verified_consumer_dispatch',
            to_mode='unverified_dispatch',
            reason='other',
            outcome='degraded',
            log=logger,
        )
    counts = {'due': len(due), 'dispatched': 0, 'skipped': 0, 'enqueue_failed': 0}
    for snapshot in due:
        _dispatch(snapshot.id, purge_jobs.COLLECTION, counts)
    if erasures:
        counts.update({'erasures_due': len(erasures), 'erasures_dispatched': 0, 'erasures_spread': 0})
        per_account: dict[str, int] = {}
        for snapshot in erasures:
            uid = str((snapshot.to_dict() or {}).get('uid'))
            queued = per_account.get(uid, 0)
            per_account[uid] = queued + 1
            if queued >= MAX_ERASURES_PER_ACCOUNT:
                purge_jobs.defer(
                    snapshot.id,
                    ERASURE_SPREAD_SECONDS * (queued // MAX_ERASURES_PER_ACCOUNT),
                    collection=purge_jobs.ERASURE_COLLECTION,
                )
                counts['erasures_spread'] += 1
                continue
            if counts['erasures_dispatched'] >= limit:
                break
            if _dispatch(snapshot.id, purge_jobs.ERASURE_COLLECTION, counts):
                counts['erasures_dispatched'] += 1
    return counts


def _dispatch(job: str, collection: str, counts: dict[str, int]) -> bool:
    erasure = collection == purge_jobs.ERASURE_COLLECTION
    claim = purge_jobs.claim_dispatch(job, collection=collection)
    if claim is None:
        counts['skipped'] += 1
        return False
    generation, attempts = claim
    if attempts > ALERT_AFTER_ATTEMPTS:
        logger.error(
            'conversation %s obligation still pending job=%s generation=%d attempts=%d',
            'erasure' if erasure else 'batch purge',
            job,
            generation,
            attempts,
        )
    try:
        enqueue_conversation_batch_purge(job, generation, erasure=erasure)
    except Exception as error:
        counts['enqueue_failed'] += 1
        logger.warning('conversation batch purge enqueue failed job=%s exception_type=%s', job, type(error).__name__)
        purge_jobs.defer(job, ENQUEUE_RETRY_SECONDS, collection=collection)
        return False
    counts['dispatched'] += 1
    return True
