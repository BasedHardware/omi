"""Bounded held expiry and UTC-nightly re-drive on the serving maintenance leader.

Durable keyset cursors survive restarts. CAS transitions, not the advisory leader
lease, own correctness. No audio/storage, conversation or retention mutations.
"""

import logging
import math
import time

from config.batch_pipeline import batch_held_dead_letter_enabled
from config.refactor_modes import batch_input_expiring_enabled
from database.batch_pipeline_record_dead_letter import record_dead_letter_stock
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import (
    RecoveryStore,
    held_candidates,
    dead_held_candidates,
    held_expired_stock,
    input_expiring_candidates,
)
from database.batch_pipeline_projection import ProjectionStore
from database.batch_pipeline_projection_release import ProjectionReleaseStore, expired_page_ids
from utils.batch_pipeline.input_retention import held_input_leg, invalid_staged_clock

PAGE_SIZE = 32
INTERVAL_SECONDS = 300
CURSOR_KEY = 'held_dead_letter'
logger = logging.getLogger(__name__)


class HeldDeadLetter:
    def __init__(self, store, *, metrics=None):
        self.store = store
        self.recovery = RecoveryStore(store)
        self.metrics = metrics

    def _record(self, event):
        if self.metrics is not None:
            if event == 'expired':
                self.metrics.held_expired.inc()
            elif event == 'requeued':
                self.metrics.record('requeued')

    def _observe_clock(self, job):
        # Name pages also see absent clock fields, excluded by ordered queries.
        if self.metrics is not None and held_input_leg(job) and invalid_staged_clock(job):
            self.metrics.staged_input_clock_invalid.inc()

    def tick(self, now):
        # Off has no queries, cursor writes, deadline stamps or expirations.
        # The separate RecoveryStore.requeue_quarantined tool remains usable.
        if not batch_held_dead_letter_enabled():
            return {'expired': 0, 'requeued': 0}
        state = self.store.run(lambda tx: tx.get('leases', CURSOR_KEY))
        counts = {'expired': 0, 'requeued': 0}
        updated = dict(state)
        input_enabled = batch_input_expiring_enabled()
        urgency_after = state.get('input_after')
        urgent = []
        if input_enabled:
            urgent, urgency_after = input_expiring_candidates(
                self.store.client, self.store.namespace, now, after=urgency_after
            )
            updated['input_after'] = urgency_after
        # Urgency runs on EVERY maintenance tick, before the next_at sleep.
        # At 128 rows/stream, 22,583 rows need 177 pages plus one tick of wait:
        # serving_tick_seconds() defaults to 20s (59m20s), capped at 60s (2h58m).
        # These cadence bounds exclude RPC/work latency. A conservative 300s
        # completed-tick budget gives 178 * 300 = 53,400s (14h50m), not 14h45m.
        # Urgency discovery is independent of held_after. Its
        # age cursors advance over refusals; the transaction still owns every
        # current-object, privacy, content and active-intent check.
        for sid, job in urgent:
            try:
                self._observe_clock(job)
                if self.recovery.expire_held(sid, now) == 'expired':
                    counts['expired'] += 1
                    self._record('expired')
            except (BatchPrivacyBlocked, ProjectionBlocked):
                continue
            except Exception as error:
                logger.warning(
                    'event=batch_held_dead_letter action=input_expire outcome=retry exception_type=%s',
                    type(error).__name__,
                )

        def checkpoint(tx):
            if tx.get('leases', CURSOR_KEY) == state:
                tx.put('leases', CURSOR_KEY, updated)

        # Only the ordinary name page and nightly redrive honor next_at.
        # Persist urgency progress alone, preserving every ordinary-pass field.
        # With the input kill off this sleeping path has no queries or writes.
        if state.get('next_at', 0) > now:
            if input_enabled:
                self.store.run(checkpoint)
                logger.info(
                    'event=batch_held_dead_letter expired=%d requeued=%d', counts['expired'], counts['requeued']
                )
            return counts
        page = held_candidates(self.store.client, self.store.namespace, PAGE_SIZE, after_id=state.get('held_after'))
        for sid, job in page:
            try:
                self._observe_clock(job)
                outcome = self.recovery.expire_held(sid, now)
            except (BatchPrivacyBlocked, ProjectionBlocked):
                continue  # Revocation/content-owner loss never authorizes a transition.
            except Exception as error:
                logger.warning(
                    'event=batch_held_dead_letter action=expire outcome=retry exception_type=%s', type(error).__name__
                )
                continue  # One malformed/unreadable row cannot pin the page forever.
            if outcome == 'expired':
                counts['expired'] += 1
                self._record('expired')
        updated['held_after'] = page[-1][0] if len(page) == PAGE_SIZE else None
        day = int(now // 86400)
        # First tick after UTC midnight starts a pass. Full pages continue on
        # later ordinary passes; only a finished redrive waits for the next day.
        if state.get('redrive_day') != day or not state.get('redrive_done'):
            after = state.get('dead_after') if state.get('redrive_day') == day else None
            dead = dead_held_candidates(self.store.client, self.store.namespace, PAGE_SIZE, after_id=after)
            for sid, job in dead:
                # A row expired today gets until the next night; stale snapshots
                # are rechecked by the sanctioned content/privacy/lease CAS.
                expired_at = job.get('held_expired_at')
                if (
                    isinstance(expired_at, bool)
                    or not isinstance(expired_at, (int, float))
                    or not math.isfinite(expired_at)
                    or expired_at >= day * 86400
                ):
                    continue
                try:
                    changed = self.recovery.requeue_quarantined(sid, now, dead_before=day * 86400)
                except (BatchPrivacyBlocked, ProjectionBlocked):
                    continue
                except Exception as error:
                    logger.warning(
                        'event=batch_held_dead_letter action=requeue outcome=retry exception_type=%s',
                        type(error).__name__,
                    )
                    continue
                if changed:
                    counts['requeued'] += 1
                    self._record('requeued')
            updated.update(
                redrive_day=day, redrive_done=len(dead) < PAGE_SIZE, dead_after=dead[-1][0] if dead else None
            )
        updated['next_at'] = now + INTERVAL_SECONDS

        # Checkpoint after work: a crash replays an idempotent page. A competing
        # leader cannot overwrite a newer cursor with this older snapshot.
        self.store.run(checkpoint)
        if self.metrics is not None:
            stock = held_expired_stock(self.store.client, self.store.namespace)
            self.metrics.held_expired_stock.set(stock)
            self.metrics.held_expired_observed_at.set(now)
        logger.info('event=batch_held_dead_letter expired=%d requeued=%d', counts['expired'], counts['requeued'])
        return counts


class ProjectionHeldDeadLetter:
    """Nightly retained-receipt re-drive, including while new expiry is killed.

    This is the flag-off recovery path for rows already written as held_expired.
    It uses the same leader, cadence, bounded pages and checkpoint CAS as 4a.
    """

    CURSOR = 'projection_held_dead_letter'

    def __init__(self, store, *, metrics=None):
        self.store, self.metrics = store, metrics

    def tick(self, now):
        state = self.store.run(lambda tx: tx.get('leases', self.CURSOR))
        if state.get('next_at', 0) > now:
            return 0
        day = int(now // 86400)
        released = 0
        updated = {**state, 'next_at': now + INTERVAL_SECONDS}
        if state.get('redrive_day') != day or not state.get('redrive_done'):
            # Large unrestorable prefixes must not starve the tail when a
            # bounded pass takes more than a day. Only completed passes restart.
            after = state.get('after_id') if not state.get('redrive_done', True) else None
            page = expired_page_ids(self.store.client, self.store.namespace, PAGE_SIZE, after)
            projection = ProjectionReleaseStore(ProjectionStore(self.store))
            deadline = time.monotonic() + 5.0
            processed = 0
            for sid in page:
                if time.monotonic() >= deadline:
                    break
                processed += 1
                try:
                    if projection.release(sid, now, dead_before=day * 86400):
                        released += 1
                except Exception as error:
                    logger.warning(
                        'event=batch_projection action=redrive_expired outcome=retry exception_type=%s',
                        type(error).__name__,
                    )
            updated.update(
                redrive_day=day,
                redrive_done=processed == len(page) and len(page) < PAGE_SIZE,
                after_id=page[processed - 1] if processed else after,
            )

        def checkpoint(tx):
            if tx.get('leases', self.CURSOR) == state:
                tx.put('leases', self.CURSOR, updated)

        self.store.run(checkpoint)
        if self.metrics is not None:
            stock = held_expired_stock(self.store.client, self.store.namespace)
            self.metrics.held_expired_stock.set(stock)
            self.metrics.held_expired_observed_at.set(now)
            if batch_held_dead_letter_enabled():
                stock = record_dead_letter_stock(self.store.client, self.store.namespace)
                self.metrics.record_dead_letter_stock.set(stock)
                self.metrics.record_dead_letter_observed_at.set(now)
        return released
