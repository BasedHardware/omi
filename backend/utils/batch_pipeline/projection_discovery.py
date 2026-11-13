"""Independent bounded discovery cursors for assignment and durable follow-ups."""

import random
import time

from config.batch_pipeline import (
    PROJECTION_DISCOVERY_STRIPES,
    projection_discovery_stripe,
    projection_pagination_enabled,
    projection_recent_discovery_seconds,
    projection_striping_enabled,
)

# A main cursor that has not wrapped for this long starts again at a new random point.
MAIN_PASS_SECONDS = 1800.0
RECENT_OFFERED_PRUNE = 4096


class ProjectionDiscovery:
    def __init__(self, store, *, states: tuple[str, ...] | None = None, recent: bool = False):
        self.store = store
        self.after = None
        # Assignment discovery opts in to a second, stateless read of the newest commits.
        # It shares each page with the main cursor, so the page holds no more rows.
        self.recent = recent
        # segment -> time offered by the recent read; one offer per row per process.
        self.offered: dict[str, float] = {}
        self.random = random.random
        self.pass_started = time.time()
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
        recent_on = self.recent and not due_mode and projection_recent_discovery_seconds() > 0
        if recent_on and striped and self.seeded and time.time() - self.pass_started > MAIN_PASS_SECONDS:
            # The main cursor has not reached the newest row for a whole pass period: rows
            # arrive as fast as it reads. Rows before every process's start point would
            # then wait for a wrap that never comes, so start again at a new random point.
            # A continuous point, not one of the 4096 buckets: every row can be the start.
            self.stripe = self.random() * PROJECTION_DISCOVERY_STRIPES
            self.after, self.seeded, self.pass_started = None, False, time.time()
            return self.next(limit, due_before)
        newest, read = self.recent_page(limit, scope) if recent_on else ([], 0)
        if read:
            limit = max(1, limit - read)
        segments, after = self.store.projection_page(limit=limit, after=after, **scope)
        if not segments and seeding:
            # Sparse/short collections or clock skew: do not waste a sweep tick.
            segments, after = self.store.projection_page(limit=limit, after=None, **scope)
        # Commit the hint only after a successful query. Errors retry this page.
        self.after = after
        self.seeded = True
        if after is None or seeding:
            self.pass_started = time.time()
        if newest:
            now = time.time()
            for segment in newest:
                self.offered[segment] = now
            seen = set(newest)
            return newest + [segment for segment in segments if segment not in seen]
        return segments

    def recent_page(self, limit: int, scope: dict) -> tuple[list[str], int]:
        """Rows from the newest commits this process has not offered yet, and rows read.

        Each tick reads up to half a page, oldest first, from a random point in the last
        `projection_recent_discovery_seconds`. There is no cursor: replicas land on
        different points, a restart changes nothing, and a row is offered here at most
        once per process (it has left the window before its entry expires). The main
        cursor still reaches every row. A failed query costs only this half page."""
        window = projection_recent_discovery_seconds()
        if limit < 2:
            return [], 0
        now = time.time()
        if len(self.offered) > RECENT_OFFERED_PRUNE:
            self.offered = {name: at for name, at in self.offered.items() if now - at <= window}
        try:
            start = now - window + window * self.random()
            segments, _ = self.store.projection_page(limit=limit // 2, after=(start, ''), **scope)
        except Exception:
            return [], 0
        return [name for name in segments if now - self.offered.get(name, -window - 1.0) > window], len(segments)
