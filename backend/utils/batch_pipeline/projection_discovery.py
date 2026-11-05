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

    def next(self, limit: int = 100) -> list[str]:
        scope = {} if self.states is None else {'states': self.states}
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
                after = (oldest + max(0.0, time.time() - oldest) * self.stripe / PROJECTION_DISCOVERY_STRIPES, '')
        segments, after = self.store.projection_page(limit=limit, after=after, **scope)
        if not segments and seeding:
            # Sparse/short collections or clock skew: do not waste a sweep tick.
            segments, after = self.store.projection_page(limit=limit, after=None, **scope)
        # Commit the hint only after a successful query. Errors retry this page.
        self.after = after
        self.seeded = True
        return segments
