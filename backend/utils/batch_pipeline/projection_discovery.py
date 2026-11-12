"""Independent bounded discovery cursors for assignment and durable follow-ups."""

import time

from config.batch_pipeline import (
    PROJECTION_DISCOVERY_STRIPES,
    projection_discovery_stripe,
    projection_pagination_enabled,
    projection_striping_enabled,
)


class ProjectionDiscovery:
    def __init__(self, store, *, states: tuple[str, ...] | None = None):
        self.store = store
        self.after = None
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
        segments, after = self.store.projection_page(limit=limit, after=after, **scope)
        if not segments and seeding:
            # Sparse/short collections or clock skew: do not waste a sweep tick.
            segments, after = self.store.projection_page(limit=limit, after=None, **scope)
        # Commit the hint only after a successful query. Errors retry this page.
        self.after = after
        self.seeded = True
        return segments
