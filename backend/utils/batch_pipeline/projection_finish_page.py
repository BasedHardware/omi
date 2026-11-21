"""Finish-page discovery and classification for the async skip policy."""

import time
import threading

from config.batch_pipeline import (
    projection_finish_async_skip_enabled,
    projection_finish_classify_page_limit,
)
from database.batch_pipeline_store import PROJECTION_FINISH_STATES
from database.batch_pipeline_projection_finish import PROJECTION_FINISH_ASYNC_CLOCK, PROJECTION_FINISH_DUE_FIELD
from utils.batch_pipeline.metrics import PROJECTION_FINISH_CLASSIFIED, PROJECTION_FINISH_CLASSIFICATION_FAILURES

# No sleeps on the serving path. Repeated reconcile RPCs cannot refill the
# per-page migration budget until 20 seconds after its last attempt.
CLASSIFY_COOLDOWN_SECONDS = 20.0


class FinishPage:
    def __init__(self, projector):
        self.projector = projector
        self.complete = False
        self.check_after = 0.0
        self.monotonic = time.monotonic
        self.classify_lock = threading.Lock()
        self.classify_page = threading.local()
        self.classify_inflight = 0
        self.classify_remaining = 0
        self.classify_after = 0.0

    def page(self, size: int) -> list[str]:
        discovery = self.projector.finish_discovery
        # Sweeps may arrive on different executor threads. Keep each page cap
        # separate while sharing one process-wide migration budget.
        self.classify_page.limit = projection_finish_classify_page_limit()
        self.classify_page.remaining = self.classify_page.limit
        if not projection_finish_async_skip_enabled():
            return discovery.next(limit=size)
        if not self.complete and self.monotonic() >= self.check_after:
            self.check_after = self.monotonic() + 60.0
            self.complete = discovery.store.projection_finish_backfill_complete()
        if not self.complete:
            return discovery.next(limit=size)
        # Independent of the sync cursor. Only classified async receipts wake
        # discovery here; legacy async rows wake it when read below.
        rows, _ = discovery.store.projection_page(
            limit=1, states=PROJECTION_FINISH_STATES, due_before=PROJECTION_FINISH_ASYNC_CLOCK
        )
        self.projector.has_async_followups |= bool(rows)
        return discovery.next(limit=size, due_before=float('inf'), exclude_async=True)

    def observed_async(self, segment_id: str, entry: dict) -> None:
        self.projector.has_async_followups = True
        if (
            projection_finish_async_skip_enabled()
            and entry.get(PROJECTION_FINISH_DUE_FIELD) != PROJECTION_FINISH_ASYNC_CLOCK
        ):
            with self.classify_lock:
                if getattr(self.classify_page, 'remaining', 0) <= 0:
                    return
                now = self.monotonic()
                if now >= self.classify_after and self.classify_inflight == 0:
                    self.classify_remaining = self.classify_page.limit
                if self.classify_remaining <= 0:
                    return
                self.classify_remaining -= 1
                self.classify_page.remaining -= 1
                self.classify_inflight += 1
                self.classify_after = now + CLASSIFY_COOLDOWN_SECONDS
            try:
                classified = self.projector.store.retire_async_finish(segment_id)
            except Exception:
                # Classification is a read-saving hint, never a delivery step.
                # Leave its clock eligible; do not turn contention into a sweep
                # error or invoke the synchronous row's deferral path.
                PROJECTION_FINISH_CLASSIFICATION_FAILURES.inc()
                return
            finally:
                with self.classify_lock:
                    self.classify_inflight -= 1
                    self.classify_after = max(self.classify_after, self.monotonic() + CLASSIFY_COOLDOWN_SECONDS)
            if classified:
                PROJECTION_FINISH_CLASSIFIED.inc()
