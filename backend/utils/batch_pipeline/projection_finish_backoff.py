"""Finish-page selection gated by a shared, versioned backfill marker.

Before maintenance completes, use the legacy page without stamp transactions.
Once complete, every process (including a newly scaled replica) filters at once.
Clock writes on state transitions are unconditional, so rollback/re-enable does
not invalidate the pass. Negative marker reads are throttled to once a minute.
"""

import time

from config.batch_pipeline import projection_finish_backoff_enabled


class FinishBackoff:
    def __init__(self, projector):
        self.projector = projector
        self.complete = False
        self.check_after = 0.0
        self.monotonic = time.monotonic

    def page(self, size: int) -> list[str]:
        discovery = self.projector.finish_discovery
        if not projection_finish_backoff_enabled():
            return discovery.next(limit=size)
        if not self.complete and self.monotonic() >= self.check_after:
            self.check_after = self.monotonic() + 60.0
            self.complete = discovery.store.projection_finish_backfill_complete()
        return discovery.next(limit=size, due_before=self.projector.clock() if self.complete else None)

    def settled(self, segment_id: str, entry: dict | None, result) -> None:
        """Defer only after a no-change walk using the clock-filtered page.

        A failed deferral leaves the existing clock due, so discovery retries it.
        The store fences on current state before changing the clock.
        """
        if not projection_finish_backoff_enabled() or not self.complete or result is not None:
            return
        state = entry.get('projection_state') if entry else None
        self.projector.store.defer_finish(segment_id, state, self.projector.clock())
