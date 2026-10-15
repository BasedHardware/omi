"""Final transactional fence for Dream effects, including late executor completions."""

from contextvars import ContextVar

ACTIVE_RUN: ContextVar[tuple[str, str] | None] = ContextVar('dream_active_run', default=None)


def assert_active(uid, transaction):
    active = ACTIVE_RUN.get()
    if active is None:
        return
    from config.dream_agent import enabled
    from database import review_store, dream_store

    if active[0] != uid or not enabled():
        raise review_store.ReviewConflict('dream_disabled')
    row = dream_store.state_ref(review_store.client(), uid).get(transaction=transaction).to_dict() or {}
    if (row.get('lease') or {}).get('run_id') != active[1]:
        raise review_store.ReviewConflict('dream_lease_lost')
