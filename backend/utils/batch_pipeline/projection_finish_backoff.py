"""Finish-page selection gated by a shared, versioned backfill marker.

Before maintenance completes, use the legacy page without stamp transactions.
Once complete, every process (including a newly scaled replica) filters at once.
Clock writes on state transitions are unconditional, so rollback/re-enable does
not invalidate the pass. Negative marker reads are throttled to once a minute.
"""

import time

from config.batch_pipeline import projection_finish_backoff_enabled, projection_finish_async_skip_enabled
from database.batch_pipeline_store import PROJECTION_FINISH_STATES
from database.batch_pipeline_projection_finish import PROJECTION_FINISH_ASYNC_CLOCK, PROJECTION_FINISH_DUE_FIELD


class FinishBackoff:
    def __init__(self, projector):
        self.projector = projector
        self.complete = False
        self.check_after = 0.0
        self.monotonic = time.monotonic

    def page(self, size: int) -> list[str]:
        discovery = self.projector.finish_discovery
        backoff = projection_finish_backoff_enabled()
        skip_async = projection_finish_async_skip_enabled()
        if not backoff and not skip_async:
            return discovery.next(limit=size)
        if not self.complete and self.monotonic() >= self.check_after:
            self.check_after = self.monotonic() + 60.0
            self.complete = discovery.store.projection_finish_backfill_complete()
        if not self.complete:
            return discovery.next(limit=size)
        if skip_async:
            # Independent of due clocks and of this cursor. Even a page of only
            # excluded async receipts must keep the durable outbox scheduled.
            rows, _ = discovery.store.projection_page(limit=1, states=PROJECTION_FINISH_STATES)
            self.projector.has_async_followups |= bool(rows)
        ceiling = self.projector.clock() if backoff else float('inf')
        return discovery.next(limit=size, due_before=ceiling, exclude_async=skip_async)

    def observed_async(self, segment_id: str, entry: dict) -> None:
        self.projector.has_async_followups = True
        if (
            projection_finish_async_skip_enabled()
            and entry.get(PROJECTION_FINISH_DUE_FIELD) != PROJECTION_FINISH_ASYNC_CLOCK
        ):
            self.projector.store.retire_async_finish(segment_id)

    def settled(self, segment_id: str, entry: dict | None, result) -> None:
        """Defer only after a no-change walk using the clock-filtered page.

        A failed deferral leaves the existing clock due, so discovery retries it.
        The store fences on current state before changing the clock.
        """
        if not projection_finish_backoff_enabled() or not self.complete or result is not None:
            return
        state = entry.get('projection_state') if entry else None
        self.projector.store.defer_finish(segment_id, state, self.projector.clock())
