"""Bounded held expiry and UTC-nightly re-drive on the serving maintenance leader.

Durable keyset cursors survive restarts. CAS transitions, not the advisory leader
lease, own correctness. No audio/storage, conversation or retention mutations.
"""

import logging
import math

from config.batch_pipeline import batch_held_dead_letter_enabled
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import (
    RecoveryStore,
    held_candidates,
    dead_held_candidates,
    held_expired_stock,
)

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

    def tick(self, now):
        # Off has no queries, cursor writes, deadline stamps or expirations.
        # The separate RecoveryStore.requeue_quarantined tool remains usable.
        if not batch_held_dead_letter_enabled():
            return {'expired': 0, 'requeued': 0}
        state = self.store.run(lambda tx: tx.get('leases', CURSOR_KEY))
        if state.get('next_at', 0) > now:
            return {'expired': 0, 'requeued': 0}
        counts = {'expired': 0, 'requeued': 0}
        page = held_candidates(self.store.client, self.store.namespace, PAGE_SIZE, after_id=state.get('held_after'))
        for sid, _ in page:
            try:
                outcome = self.recovery.expire_held(sid, now)
            except (BatchPrivacyBlocked, ProjectionBlocked):
                continue  # Revocation/content-owner loss never authorizes a transition.
            if outcome == 'expired':
                counts['expired'] += 1
                self._record('expired')
        updated = {**state, 'held_after': page[-1][0] if len(page) == PAGE_SIZE else None}
        day = int(now // 86400)
        # First tick after UTC midnight starts a pass. Full pages continue on
        # later maintenance ticks; a finished pass sleeps until the next day.
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
                if changed:
                    counts['requeued'] += 1
                    self._record('requeued')
            updated.update(
                redrive_day=day, redrive_done=len(dead) < PAGE_SIZE, dead_after=dead[-1][0] if dead else None
            )
        updated['next_at'] = now + INTERVAL_SECONDS

        def checkpoint(tx):
            if tx.get('leases', CURSOR_KEY) == state:
                tx.put('leases', CURSOR_KEY, updated)

        # Checkpoint after work: a crash replays an idempotent page. A competing
        # leader cannot overwrite a newer cursor with this older snapshot.
        self.store.run(checkpoint)
        if self.metrics is not None:
            stock = held_expired_stock(self.store.client, self.store.namespace)
            self.metrics.held_expired_stock.set(stock)
            self.metrics.held_expired_observed_at.set(now)
        logger.info('event=batch_held_dead_letter expired=%d requeued=%d', counts['expired'], counts['requeued'])
        return counts
