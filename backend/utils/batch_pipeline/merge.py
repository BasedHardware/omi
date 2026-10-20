"""Ordered durable result log. Projection consumers must use stable segment IDs."""

import logging
import time

from google.api_core.exceptions import FailedPrecondition

from config.batch_pipeline import merge_catch_up_depth, merge_head_wait_seconds
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_store import Store
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.metrics import QueueMetrics

logger = logging.getLogger(__name__)

# A missing head-wait index falls back to strict order; retry the query after this.
HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS = 300
_HEAD_STATES = frozenset({'ready', 'leased', 'retry', 'record_pending', 'privacy_blocked'})
_FRESH_FIRST_HEAD_STATES = _HEAD_STATES | {'result_ready'}
_WAIT_BUCKETS = (60, 120, 300, 600, 1800)


class HeadWaitUnavailable(Exception):
    """The head-wait query has no serving index; the merge keeps strict order."""


def _wait_bucket(seconds: float) -> str:
    return next((f'lt{bound}' for bound in _WAIT_BUCKETS if seconds < bound), f'ge{_WAIT_BUCKETS[-1]}')


def _catch_up(job: dict) -> bool:
    # Only rows classified at admission; record-lane and older rows keep the plain order.
    return job.get('fresh_capture') is False


def _awaiting_projection(tx, owner: dict) -> int:
    """Committed rows not yet projected. A missing watermark row never holds a commit."""
    sequence = owner.get('log_sequence', 0)
    projected = owner.get('projection_watermark')
    if not projected:
        return sequence
    done = tx.get('results', projected).get('log_sequence')
    return sequence - done if done else 0


class OrderedMerge:
    def __init__(
        self,
        store: Store,
        *,
        metrics: QueueMetrics | None = None,
        commit_source: str = 'ordered_merge',
        head_wait_seconds: float | None = None,
        catch_up_depth: int | None = None,
    ):
        self.store = store
        self.metrics = metrics
        self.commit_source = commit_source
        # None reads BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS on every commit.
        self.head_wait_seconds = head_wait_seconds
        # None reads BATCH_PIPELINE_MERGE_CATCH_UP_DEPTH on every commit.
        self.catch_up_depth = catch_up_depth
        self._head_wait_retry_at = 0.0
        self._fresh_first_retry_at = 0.0
        # Owners whose last commit attempt held catch-up rows for projection
        # depth. Maintenance re-offers them by owner: a held backlog can fill
        # the global result_ready page and hide them from discovery.
        self.held_owners: set[str] = set()

    def _head_wait(self) -> float:
        if time.monotonic() < self._head_wait_retry_at:
            return 0.0
        return self.head_wait_seconds if self.head_wait_seconds is not None else merge_head_wait_seconds()

    def _catch_up_depth(self) -> int:
        if time.monotonic() < self._fresh_first_retry_at:
            return 0
        return self.catch_up_depth if self.catch_up_depth is not None else merge_catch_up_depth()

    def commit_next(self, owner_id: str, now: float) -> dict | None:
        key = owner_key(owner_id)
        wait = self._head_wait()
        depth = self._catch_up_depth()
        blocked: dict = {}
        bypass: dict = {}
        fresh_first: dict = {}
        held: dict = {}

        def commit(tx, waiter: dict | None = None, fresh: dict | None = None):
            blocked.clear()  # Firestore may retry this callback.
            bypass.clear()
            fresh_first.clear()
            held.clear()
            owner = tx.get('owners', key)
            # Terminal quarantine atomically removes merge_pending; it never
            # enters this success log or the projection predecessor chain.
            candidate = tx.first_pending(key)
            if fresh is not None:
                # Fresh-first (David's fresh bar, 2026-10-20): the probed fresh
                # row must still be pending and ready behind a catch-up head;
                # it commits ahead of that backlog, which appends later as
                # late_capture through the unchanged body below.
                current = tx.get('jobs', fresh['segment_id'])
                if not (
                    candidate
                    and _catch_up(candidate)
                    and current.get('merge_pending')
                    and current.get('state') == 'result_ready'
                    and current.get('fresh_capture') is True
                ):
                    return None
                fresh_first.update(head_state=candidate['state'])
                candidate = current
            elif candidate and candidate['state'] != 'result_ready':
                if waiter is None:
                    blocked.update(head_state=candidate['state'], catch_up=_catch_up(candidate))
                    return None
                # Bounded head wait (David, 2026-10-20): the probed waiter must
                # still be pending and ready; then release the owner's ready
                # rows in capture order. The bypassed head later appends as
                # late_capture through the unchanged body below.
                current = tx.get('jobs', waiter['segment_id'])
                if not (
                    current.get('merge_pending')
                    and current.get('state') == 'result_ready'
                    and current.get('ready_at') == waiter['ready_at']
                ):
                    return None
                bypass.update(head_state=candidate['state'], waited=now - waiter['ready_at'])
                try:
                    candidate = tx.first_ready_pending(key)
                except FailedPrecondition as error:
                    raise HeadWaitUnavailable from error
            if not candidate or candidate['state'] != 'result_ready':
                return None
            if depth and not fresh_first and _catch_up(candidate) and _awaiting_projection(tx, owner) >= depth:
                # Keep the owner's unprojected log short so a fresh row lands
                # near the projection head. Maintenance re-offers this owner.
                held['catch_up'] = True
                return None
            job = tx.get('jobs', candidate['segment_id'])
            existing = tx.get('results', job['segment_id'])
            if existing:
                raise RuntimeError('result log exists for pending job; reconciliation required')
            watermark = owner.get('watermark')
            position = {'capture_at': job['capture_at'], 'segment_id': job['segment_id']}
            late = bool(
                watermark
                and (position['capture_at'], position['segment_id'])
                <= (watermark['capture_at'], watermark['segment_id'])
            )
            tail = owner.get('log_tail', watermark['segment_id'] if watermark else None)
            entry = {
                **position,
                'protocol_version': job['protocol_version'],
                'owner_key': key,
                'owner_id': job['owner_id'],
                'conversation_id': job.get('conversation_id'),
                'privacy_generation': job.get('privacy_generation'),
                'previous_segment_id': tail,
                'late_capture': late,
                'log_sequence': owner.get('log_sequence', 0) + 1,
                'result': job['result'],
                'committed_at': now,
                'projection_state': 'pending',
            }
            if job.get('recovery_state') == 'recovered':
                entry['recovery_version'] = 1
            if bypass:
                entry['head_wait_bypass'] = True
            if fresh_first:
                entry['fresh_first'] = True
            tx.put('results', job['segment_id'], entry)
            job.update(state='committed', merge_pending=False)
            tx.put('jobs', job['segment_id'], job)
            owner.update(
                watermark=watermark if late else position,
                log_tail=job['segment_id'],
                log_sequence=entry['log_sequence'],
                revision=owner.get('revision', 0) + 1,
            )
            tx.put('owners', key, owner)
            return entry

        entry = self.store.run(commit)
        strict_blocked, strict_held = dict(blocked), bool(held)
        if entry is None and depth and (strict_held or strict_blocked.get('catch_up')):
            # A catch-up row heads the owner. Probe for a ready fresh row
            # outside the strict transaction (no transactional query lock);
            # only a ready one opens a second, re-verifying transaction.
            try:
                fresh = self.store.first_fresh_pending(key)
                if fresh and fresh.get('state') == 'result_ready':
                    entry = self.store.run(lambda tx: commit(tx, fresh=fresh))
            except BatchPrivacyBlocked:
                return None
            except FailedPrecondition:
                # Without the fresh query a catch-up hold would also hold fresh
                # rows: take the plain order now and retry the query later.
                self._fresh_first_retry_at = time.monotonic() + HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS
                logger.warning(
                    'event=batch_merge outcome=fresh_first_unavailable source=%s count=1', self.commit_source
                )
                from utils.observability.fallback import record_fallback

                record_fallback(
                    component='firestore_read',
                    from_mode='fresh_first',
                    to_mode='ordered_merge',
                    reason='unavailable',
                    outcome='degraded',
                    log=logger,
                )
                self.held_owners.discard(owner_id)
                return self.commit_next(owner_id, now)
        if entry is None and strict_blocked and wait > 0:
            # The strict transaction issues no head-wait query. Probe outside
            # it so a blocked owner takes no extra transactional query lock;
            # only an expired wait opens a second, re-verifying transaction.
            try:
                waiter = self.store.longest_ready_pending(key)
                if waiter and now - waiter['ready_at'] >= wait:
                    entry = self.store.run(lambda tx: commit(tx, waiter))
            except BatchPrivacyBlocked:
                # An owner-wide fence (often the reason the head is blocked)
                # also refuses the successor; strict order commits nothing here.
                return None
            except (FailedPrecondition, HeadWaitUnavailable):
                # The head is not ready, so strict order commits nothing either.
                self._head_wait_retry_at = time.monotonic() + HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS
                logger.warning('event=batch_merge outcome=head_wait_unavailable source=%s count=1', self.commit_source)
                from utils.observability.fallback import record_fallback

                record_fallback(
                    component='firestore_read',
                    from_mode='head_wait',
                    to_mode='strict_order',
                    reason='unavailable',
                    outcome='degraded',
                    log=logger,
                )
                return None
        if strict_held or held:
            self.held_owners.add(owner_id)
        else:
            self.held_owners.discard(owner_id)
        if entry:
            record_correctness('committed', source=self.commit_source)
            if self.metrics:
                self.metrics.record('committed')
            if fresh_first:
                head_state = (
                    fresh_first['head_state'] if fresh_first['head_state'] in _FRESH_FIRST_HEAD_STATES else 'other'
                )
                logger.info(
                    'event=batch_merge outcome=fresh_first source=%s head_state=%s count=1',
                    self.commit_source,
                    head_state,
                )
            if bypass:
                head_state = bypass['head_state'] if bypass['head_state'] in _HEAD_STATES else 'other'
                logger.info(
                    'event=batch_merge outcome=head_wait_bypass source=%s head_state=%s wait_bucket=%s count=1',
                    self.commit_source,
                    head_state,
                    _wait_bucket(bypass['waited']),
                )
        return entry

    def committed_result(self, segment_id: str) -> dict:
        """Idempotent re-read after a lost commit reply; no external side effects."""
        return self.store.run(lambda tx: tx.get('results', segment_id))
