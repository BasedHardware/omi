"""Independent bounded discovery cursors for assignment and durable follow-ups."""

from config.batch_pipeline import projection_pagination_enabled


class ProjectionDiscovery:
    def __init__(self, store, *, states: tuple[str, ...] | None = None):
        self.store = store
        self.after = None
        # None keeps the store's default drain states and its exact legacy call.
        self.states = states

    def next(self, limit: int = 100) -> list[str]:
        scope = {} if self.states is None else {'states': self.states}
        if not projection_pagination_enabled():
            self.after = None
            if scope:
                return self.store.projection_page(limit=limit, after=None, **scope)[0]
            return self.store.projection_pending(limit=limit)
        segments, after = self.store.projection_page(limit=limit, after=self.after, **scope)
        # Commit the hint only after a successful query. Errors retry this page.
        self.after = after
        return segments
