"""Independent bounded discovery cursors for assignment and durable follow-ups."""

from config.batch_pipeline import projection_pagination_enabled


def owner_page(store, segments):
    """Group cheap job hints before attempting any row; fences remain authoritative.

    Pages carry only ids. One job read per row avoids the full projection read
    and predecessor transactions for every non-head. Missing/failed hints stay
    independent so the normal attempt can report or recover the malformed row.
    """
    groups = {}
    for sid in segments:
        try:
            job = store.ref('jobs', sid).get().to_dict() or {}
        except Exception:
            job = {}
        binding = job.get('projection_binding')
        owner = binding.get('owner_id') if isinstance(binding, dict) else None
        owner = owner if isinstance(owner, str) and owner else None
        groups.setdefault((owner, None if owner else sid), []).append((sid, job))
    return [(owner, rows) for (owner, _), rows in groups.items()]


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
