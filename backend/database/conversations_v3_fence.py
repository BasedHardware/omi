"""Context-carried v3 writer fence checked inside the existing persist transaction."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

_current: ContextVar[tuple[str, str, str] | None] = ContextVar('conversation_v3_writer', default=None)


def current():
    return _current.get()


@contextmanager
def writer(uid, cid, token):
    held = _current.set((uid, cid, token))
    try:
        yield
    finally:
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
