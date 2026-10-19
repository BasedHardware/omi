"""Independent bounded discovery cursors for assignment and durable follow-ups."""

from config.batch_pipeline import projection_pagination_enabled


class ProjectionDiscovery:
    def __init__(self, store):
        self.store = store
        self.after = None

    def next(self, limit: int = 100) -> list[str]:
        if not projection_pagination_enabled():
            self.after = None
            return self.store.projection_pending(limit=limit)
        segments, after = self.store.projection_page(limit=limit, after=self.after)
        # Commit the hint only after a successful query. Errors retry this page.
        self.after = after
        return segments
