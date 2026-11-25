"""Context-carried v3 writer fence checked inside the existing persist transaction."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone

_current: ContextVar[tuple[str, str, str] | None] = ContextVar('conversation_v3_writer', default=None)


@dataclass(frozen=True)
class PersistenceDecline:
    reason: str
    update_time: datetime | None
    transient: bool = False


_declined: ContextVar[PersistenceDecline | None] = ContextVar('conversation_v3_persistence_declined', default=None)


def record_persistence_outcome(decline: PersistenceDecline | None) -> None:
    """Report a committed decline while keeping the public persistence result boolean."""
    _declined.set(decline)


def persistence_declined() -> PersistenceDecline | None:
    return _declined.get()


def current():
    return _current.get()


@contextmanager
def writer(uid, cid, token):
    held = _current.set((uid, cid, token))
    declined = _declined.set(None)
    try:
        yield
    finally:
        _declined.reset(declined)
        _current.reset(held)


def permits(transaction, client, uid, cid):
    fence = current()
    if fence is None:
        return True
    if fence[:2] != (uid, cid):
        return False
    ref = client.collection('users').document(uid).collection('conversation_v3_leases').document('summary-' + cid)
    row = ref.get(transaction=transaction).to_dict() or {}
    return row.get('token') == fence[2] and row.get('until') and row['until'] > datetime.now(timezone.utc)
