"""Context-carried v3 writer fence checked inside the existing persist transaction."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone

_current: ContextVar[tuple[str, str, str] | None] = ContextVar('conversation_v3_writer', default=None)


class ProcessingPersistenceFenced(RuntimeError):
    """The processing write declined a stale or no-longer-authorized result."""


@dataclass(frozen=True)
class PersistenceDecline:
    reason: str
    update_time: datetime | None
    transient: bool = False


@dataclass(frozen=True)
class _PersistenceOutcome:
    decline: PersistenceDecline | None


_outcome: ContextVar[_PersistenceOutcome | None] = ContextVar('conversation_v3_persistence_outcome', default=None)


def record_persistence_outcome(uid: str, cid: str, decline: PersistenceDecline | None) -> None:
    """Keep the first result for the leased row, including a successful persist."""
    held = current()
    if held is not None and held[:2] == (uid, cid) and _outcome.get() is None:
        _outcome.set(_PersistenceOutcome(decline))


def persistence_declined() -> PersistenceDecline | None:
    outcome = _outcome.get()
    return outcome.decline if outcome is not None else None


def current():
    return _current.get()


@contextmanager
def writer(uid, cid, token):
    held = _current.set((uid, cid, token))
    outcome = _outcome.set(None)
    try:
        yield
    finally:
        _outcome.reset(outcome)
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
