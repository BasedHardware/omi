"""Independent bounded discovery cursors for assignment and durable follow-ups."""

import time

from config.batch_pipeline import (
    PROJECTION_DISCOVERY_STRIPES,
    projection_discovery_stripe,
    projection_pagination_enabled,
    projection_recent_discovery_seconds,
    projection_striping_enabled,
)


class ProjectionDiscovery:
    def __init__(self, store, *, states: tuple[str, ...] | None = None, recent: bool = False):
        self.store = store
        self.after = None
        # Second cursor over the newest commits only (assignment discovery opts in). It
        # shares each page with the main cursor, so the sweep does no more work per tick.
        self.recent = recent
        self.recent_after = None
        self.recent_started = False
        # None keeps the store's default drain states and its exact legacy call.
        self.states = states
        self.stripe = projection_discovery_stripe()
        self.seeded = False
        # The finish page's dark backoff adds a range filter, which moves the
        # ordering (and therefore the cursor) to the row's next-attempt clock.
        self.due_mode = False

    def next(self, limit: int = 100, due_before: float | None = None) -> list[str]:
        due_mode = due_before is not None
        if due_mode != self.due_mode:
            # A cursor from one ordering is meaningless in the other.
            self.due_mode, self.after, self.seeded = due_mode, None, False
        scope: dict[str, object] = {} if self.states is None else {'states': self.states}
        if due_mode:
            scope['due_before'] = due_before
        if not projection_pagination_enabled():
            self.after = None
            self.seeded = True
            if scope:
                return self.store.projection_page(limit=limit, after=None, **scope)[0]
            return self.store.projection_pending(limit=limit)
        striped = projection_striping_enabled()
        after = self.after
        seeding = not self.seeded and after is None and striped
        if seeding:
            _, head = self.store.projection_page(limit=1, after=None, **scope)
            if head is not None:
                oldest = float(head[0])
                # A timestamp-only cursor includes every tie at the lower bound.
                ceiling = float(due_before) if due_mode else time.time()
                offset = oldest + max(0.0, ceiling - oldest) * self.stripe / PROJECTION_DISCOVERY_STRIPES
                after = (offset,) if due_mode else (offset, '')
        newest = self.recent_page(limit, scope) if self.recent and not due_mode else []
        if newest:
            limit = max(1, limit - len(newest))
        segments, after = self.store.projection_page(limit=limit, after=after, **scope)
        if not segments and seeding:
            # Sparse/short collections or clock skew: do not waste a sweep tick.
            segments, after = self.store.projection_page(limit=limit, after=None, **scope)
        # Commit the hint only after a successful query. Errors retry this page.
        self.after = after
        self.seeded = True
        if newest:
            seen = set(newest)
            return newest + [segment for segment in segments if segment not in seen]
        return segments

    def recent_page(self, limit: int, scope: dict) -> list[str]:
        """Up to half a page from the newest commits, oldest first inside the window.

        The cursor walks from the window's floor to the newest row, then starts again.
        A process's first pass starts at its stripe's point in the window, so replicas
        do not all read the same rows. A failed query costs only this half page."""
        window = projection_recent_discovery_seconds()
        if window <= 0 or limit < 2:
            return []
        floor = time.time() - window
        after = self.recent_after
        if after is None or float(after[0]) < floor:
            phase = 0.0 if self.recent_started else window * self.stripe / PROJECTION_DISCOVERY_STRIPES
            after = (floor + phase, '')
        try:
            segments, cursor = self.store.projection_page(limit=limit // 2, after=after, **scope)
        except Exception:
            return []
        self.recent_started = True
        # None: the newest row was reached; the next pass starts at the floor again.
        self.recent_after = cursor
        return segments
