"""Ordered durable result log. Projection consumers must use stable segment IDs."""

import logging
import time

from google.api_core.exceptions import FailedPrecondition, GoogleAPICallError

from config.batch_pipeline import merge_head_wait_seconds
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_store import Store
from utils.batch_pipeline.correctness_metrics import record as record_correctness
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.metrics import QueueMetrics
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

# A missing head-wait index falls back to strict order; retry the query after this.
HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS = 300
_HEAD_STATES = frozenset({'ready', 'leased', 'retry', 'record_pending', 'privacy_blocked'})
_WAIT_BUCKETS = (60, 120, 300, 600, 1800)


class HeadWaitUnavailable(Exception):
    """The head-wait query has no serving index; the merge keeps strict order."""


def _wait_bucket(seconds: float) -> str:
    return next((f'lt{bound}' for bound in _WAIT_BUCKETS if seconds < bound), f'ge{_WAIT_BUCKETS[-1]}')


class OrderedMerge:
    def __init__(
        self,
        store: Store,
        *,
        metrics: QueueMetrics | None = None,
        commit_source: str = 'ordered_merge',
        head_wait_seconds: float | None = None,
    ):
        self.store = store
        self.metrics = metrics
        self.commit_source = commit_source
        # None reads BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS on every commit.
        self.head_wait_seconds = head_wait_seconds
        self._head_wait_retry_at = 0.0

    def _head_wait(self) -> float:
        if time.monotonic() < self._head_wait_retry_at:
            return 0.0
        return self.head_wait_seconds if self.head_wait_seconds is not None else merge_head_wait_seconds()

    def _head_wait_unavailable(self) -> None:
        self._head_wait_retry_at = time.monotonic() + HEAD_WAIT_UNAVAILABLE_RETRY_SECONDS
        logger.warning('event=batch_merge outcome=head_wait_unavailable source=%s count=1', self.commit_source)
        record_fallback(
            component='firestore_read',
            from_mode='head_wait',
            to_mode='strict_order',
            reason='unavailable',
            outcome='degraded',
            log=logger,
        )
        return None

    def commit_next(self, owner_id: str, now: float) -> dict | None:
        key = owner_key(owner_id)
        wait = self._head_wait()
        blocked: dict = {}
        bypass: dict = {}

        def commit(tx, waiter: dict | None = None):
            blocked.clear()  # Firestore may retry this callback.
            bypass.clear()
            owner = tx.get('owners', key)
            # Terminal quarantine atomically removes merge_pending; it never
            # enters this success log or the projection predecessor chain.
            candidate = tx.first_pending(key)
            if candidate and candidate['state'] != 'result_ready':
                if waiter is None:
                    blocked['head_state'] = candidate['state']
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
        if entry is None and blocked and wait > 0:
            # The strict transaction issues no head-wait query. Probe outside
            # it so a blocked owner takes no extra transactional query lock;
            # only an expired wait opens a second, re-verifying transaction.
            # Every early return below is strict order's result: the head is not ready.
            try:
                waiter = self.store.longest_ready_pending(key)
            except FailedPrecondition:
                return self._head_wait_unavailable()
            except GoogleAPICallError as error:
                # A transient probe read must not fail a drain strict order would finish.
                logger.warning(
                    'event=batch_merge outcome=head_wait_probe_retry source=%s exception_type=%s count=1',
                    self.commit_source,
                    type(error).__name__,
                )
                return None
            if not waiter or now - waiter['ready_at'] < wait:
                return None
            try:
                entry = self.store.run(lambda tx: commit(tx, waiter))
            except BatchPrivacyBlocked:
                # An owner-wide fence (often the reason the head is blocked)
                # also refuses the successor; strict order commits nothing here.
                return None
            except HeadWaitUnavailable:
                return self._head_wait_unavailable()
        if entry:
            record_correctness('committed', source=self.commit_source)
            if self.metrics:
                self.metrics.record('committed')
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
