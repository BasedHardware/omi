"""Opt into durable follow-up discovery only after the writer/backfill rollout."""

from copy import deepcopy
import logging
import math
import time

from database.batch_pipeline_projection_followup_clock import MAX_DELAY_SECONDS, defer_unchanged
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


class FollowupClock:
    def __init__(self, projector):
        self.projector = projector
        self.complete = False
        self.active = False
        self.check_after = 0.0
        self.monotonic = time.monotonic
        # At most one snapshot per running follow-up slot, removed on every exit.
        self.entries: dict[str, dict] = {}

    def before(self, enabled: bool) -> float | None:
        self.active = False
        if not enabled:
            return None
        if not self.complete and self.monotonic() >= self.check_after:
            self.check_after = self.monotonic() + 60.0
            try:
                self.complete = self.projector.store.store.projection_followup_backfill_complete() is True
            except Exception:
                # No readiness evidence: keep the unfiltered, durable legacy path.
                record_fallback(
                    component='firestore_read',
                    from_mode='followup_due',
                    to_mode='legacy_discovery',
                    reason='unavailable',
                    outcome='degraded',
                    log=logger,
                )
                return None
        if not self.complete:
            return None
        now = float(self.projector.clock())
        self.active = math.isfinite(now) and now >= 0
        return now if self.active else None

    def observe(self, segment: str, entry: dict):
        if self.active:
            self.entries[segment] = deepcopy(entry)

    def settle(self, segment: str, outcome: str, ceiling: float) -> bool:
        entry = self.entries.pop(segment, None)
        if not self.active or entry is None or outcome != 'incomplete' or ceiling <= 0:
            return False
        try:
            return defer_unchanged(
                self.projector.store, segment, entry, float(self.projector.clock()), min(ceiling, MAX_DELAY_SECONDS)
            )
        except Exception:
            # A scheduling optimization failure must leave the obligation due.
            record_fallback(
                component='firestore_read',
                from_mode='followup_deferred',
                to_mode='due_discovery',
                reason='unavailable',
                outcome='degraded',
                log=logger,
            )
            return False
