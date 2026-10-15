"""Refresh derived visibility only after a terminal transaction commits."""

from contextvars import ContextVar
from functools import wraps

from database import conversations as conversations_db
from utils.observability.fallback import record_fallback

_pending: ContextVar[set[tuple[str, str]] | None] = ContextVar('terminal_visibility_refresh', default=None)


def stage_terminal_visibility_refresh(uid: str, conversation_id: str) -> None:
    pending = _pending.get()
    if pending is not None:
        pending.add((uid, conversation_id))


def refresh_terminal_visibility_after_commit(operation):
    """Collect retry-attempt effects; publish them only after successful return.

    A fenced retry can cause a harmless extra refresh. Failed transactions
    never invalidate, and retries cannot publish a new generation before commit.
    """

    @wraps(operation)
    def commit_then_refresh(*args, **kwargs):
        pending: set[tuple[str, str]] = set()
        token = _pending.set(pending)
        try:
            result = operation(*args, **kwargs)
        finally:
            _pending.reset(token)
        for uid, conversation_id in pending:
            observers = (
                (conversations_db.invalidate_people_stats_cache, (uid,)),
                (conversations_db._sync_conversation_search_index, (uid, conversation_id)),
            )
            for observer, observer_args in observers:
                try:
                    observer(*observer_args)
                except Exception:
                    # Observers never turn committed customer state into a retry.
                    record_fallback(
                        component='conversation_relevance',
                        from_mode='cached',
                        to_mode='uncached',
                        reason='other',
                        outcome='degraded',
                    )
        return result

    return commit_then_refresh
