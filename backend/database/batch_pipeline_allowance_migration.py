"""Resumable CAS migration of current allowance decisions; no content reads."""

from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, wait
from contextvars import copy_context
import math
import threading
import time

from google.cloud import firestore

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_allowance_hold import OWNERS, STATE, enabled, park
from utils.executors import db_executor

KEY = 'allowance_parking_v1'


class MigrationOwnerChanged(RuntimeError):
    """A row's owner moved after discovery. Nothing is parked for that row; replaying the page is safe."""


class _Stopped(Exception):
    """Another worker failed; leave this page uncheckpointed."""


class RowRateLimiter:
    """One shared monotonic token bucket, including transaction retries.

    Capacity one deliberately smooths starts instead of allowing a page-sized
    burst. Keep this instance across pages; never reset its credit per page.
    """

    def __init__(self, rate: float | None = None, *, clock=time.monotonic):
        if rate is not None and (not math.isfinite(rate) or rate <= 0):
            raise ValueError('max-rows-per-second must be finite and positive')
        self.rate = rate
        self.clock = clock
        self.lock = threading.Lock()
        self.tokens = 1.0
        self.updated = clock()

    def acquire(self, stopped: threading.Event) -> None:
        while not stopped.is_set():
            if self.rate is None:
                return
            with self.lock:
                now = self.clock()
                self.tokens = min(1.0, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                delay = (1.0 - self.tokens) / self.rate
            # Never sleep with the bucket lock held. An error wakes all waiters.
            stopped.wait(delay)
        raise _Stopped()


def _prefetch_row(tx, segment_id, owner):
    """Migration-only BatchGet into this attempt's FirestoreTransaction cache.

    Enroll both documents in the same conflict set as individual get() calls.
    BatchGet order is unspecified; match reference paths, including absent holds.
    This changes no shared store or privacy behavior outside this operator tool.
    """
    references = {}
    for address in [('jobs', segment_id), (OWNERS, owner)]:
        reference = tx._ref(*address)
        references[reference.path] = (reference, address)
    seen = set()
    for snapshot in tx.client.get_all([reference for reference, _ in references.values()], transaction=tx.transaction):
        address = references[snapshot.reference.path][1]
        tx.exists[address] = snapshot.exists
        tx.cache[address] = (snapshot.to_dict() or {}) if snapshot.exists else {}
        seen.add(snapshot.reference.path)
    if seen != references.keys():
        raise RuntimeError('incomplete migration transactional prefetch')


def _apply_rows(store, rows, now, concurrency, limiter):
    stopped = threading.Event()

    def process(group, owner=None):
        parked, fenced = 0, 0
        for snapshot in group:
            if stopped.is_set():
                break

            def migrate(tx):
                if owner is not None:
                    # Discovery is only a scheduling hint. Both documents must
                    # be read again in this transaction, including every retry.
                    _prefetch_row(tx, snapshot.id, owner)
                job = tx.get('jobs', snapshot.id)
                if job and owner is not None and job.get('owner_key') != owner:
                    raise MigrationOwnerChanged('migration owner changed; retry the page')
                return park(tx, job, now)

            try:
                parked += store.run(migrate, before_attempt=lambda: limiter.acquire(stopped))
            except BatchPrivacyBlocked:
                fenced += 1  # Erasure owns the row; never bypass its authority.
            except _Stopped:
                break
            except Exception:
                stopped.set()
                raise
        return parked, fenced

    if concurrency == 1:
        return process(rows)

    # One leaf task per owner holds that owner's slot until all of its commits
    # finish. No two transactions in this process write the same hold document.
    groups = defaultdict(list)
    for snapshot in rows:
        owner = (snapshot.to_dict() or {}).get('owner_key')
        if not isinstance(owner, str) or not owner:
            raise RuntimeError('migration candidate has no owner key')
        groups[owner].append(snapshot)
    remaining = iter(groups.items())
    pending = set()
    parked, fenced = 0, 0

    def submit_next():
        entry = next(remaining, None)
        if entry is not None:
            owner, group = entry
            # These futures are observed synchronously. Keep context propagation
            # without the fire-and-forget helper's unrelated BYOK error handling.
            pending.add(db_executor.submit(copy_context().run, process, group, owner))

    failure = None
    try:
        for _ in range(min(concurrency, len(groups))):
            submit_next()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                pending.remove(future)
                parked_count, fenced_count = future.result()
                parked += parked_count
                fenced += fenced_count
            if not stopped.is_set():
                for _ in done:
                    submit_next()
    except BaseException as error:
        failure = error
        raise
    finally:
        stopped.set()
        # Committing work cannot be cancelled safely. Drain it before returning
        # an error, and never checkpoint a partially successful page.
        if pending:
            wait(pending)
            if failure is not None:
                # Only the first failure propagates. Keep the others so the
                # operator's stop classification sees every owner group's error.
                siblings = (future.exception() for future in pending if not future.cancelled())
                setattr(failure, 'migration_sibling_errors', tuple(error for error in siblings if error))
    return parked, fenced


def candidates(store):
    return (
        store.client.collection(f'{store.namespace}_jobs')
        .where('state', '==', 'retry')
        .where('compute_decision.outcome', '==', 'held')
        .where('compute_decision.reason', '==', 'allowance_exhausted')
    )


def counts(store) -> dict:
    """COUNT aggregations only: a dry run never reads or prints a user row."""
    jobs = store.client.collection(f'{store.namespace}_jobs')
    return {
        'retry': int(jobs.where('state', '==', 'retry').count().get()[0][0].value),
        'allowance_retry': int(candidates(store).count().get()[0][0].value),
        'policy_held': int(jobs.where('state', '==', STATE).count().get()[0][0].value),
    }


def apply_page(
    store, now: float, *, size: int = 100, concurrency: int = 1, rate_limiter: RowRateLimiter | None = None
) -> dict:
    if not enabled():
        raise ValueError('parking switch is off')
    if not 1 <= concurrency <= 32:
        raise ValueError('concurrency must be 1..32')
    size = max(1, min(size, 100))
    progress = store.client.collection(f'{store.namespace}_migrations').document(KEY)
    checkpoint = progress.get().to_dict() or {}
    query = candidates(store).order_by('__name__')
    if checkpoint.get('after'):
        ref = store.client.collection(f'{store.namespace}_jobs').document(checkpoint['after'])
        query = query.start_after({'__name__': ref})
    # Same candidate filters, ordering, cursor and bound; the concurrent path
    # projects only owner metadata, at the same one discovery read per row.
    rows = list(query.limit(size).select(['owner_key'] if concurrency > 1 else []).stream())
    parked, fenced = _apply_rows(store, rows, now, concurrency, rate_limiter or RowRateLimiter())
    # A crash before this write replays only this bounded page. park's state
    # predicate makes that replay idempotent. A failure never advances it.
    complete = len(rows) < size

    @firestore.transactional
    def checkpoint_page(transaction):
        current = progress.get(transaction=transaction).to_dict() or {}
        if current != checkpoint:
            raise RuntimeError('migration checkpoint changed; resume durable progress')
        transaction.set(progress, {'after': None if complete else rows[-1].id, 'complete': complete, 'updated_at': now})

    checkpoint_page(store.client.transaction())
    return {'examined': len(rows), 'parked': parked, 'fenced': fenced, 'complete': complete}
