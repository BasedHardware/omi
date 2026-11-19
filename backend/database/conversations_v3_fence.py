"""Context-carried v3 writer fence checked inside the existing persist transaction."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from utils.conversations.v3 import policy

_UNSPECIFIED = object()
_current: ContextVar[tuple[str, str, str, Any] | None] = ContextVar('conversation_v3_writer', default=None)


def current():
    return _current.get()


@contextmanager
def writer(uid, cid, token, *, native_binding=_UNSPECIFIED):
    held = _current.set((uid, cid, token, native_binding))
    try:
        yield
    finally:
        _current.reset(held)


def permits_native_source(transaction, client, uid, derived):
    """Recheck a native summary's immutable input during its existing transaction."""
    binding = derived.get(policy.NATIVE_MANUAL_BINDING)
    if binding is None:
        return True
    cid = binding.get('recording_id') if isinstance(binding, dict) else None
    if not isinstance(cid, str) or not cid or '/' in cid or cid not in (derived.get('v3_recording_ids') or []):
        return False
    source = client.collection('users').document(uid).collection('conversations').document(cid)
    row = source.get(transaction=transaction).to_dict() or {}
    return policy.native_manual_binding(row, recording_id=cid) == binding


def permits(transaction, client, uid, cid, derived):
    fence = current()
    if fence is None:
        return permits_native_source(transaction, client, uid, derived)
    if fence[:2] != (uid, cid):
        return False
    expected = fence[3]
    if expected is not _UNSPECIFIED and derived.get(policy.NATIVE_MANUAL_BINDING) != expected:
        return False
    ref = client.collection('users').document(uid).collection('conversation_v3_leases').document('summary-' + cid)
    row = ref.get(transaction=transaction).to_dict() or {}
    return bool(
        row.get('token') == fence[2]
        and row.get('until')
        and row['until'] > datetime.now(timezone.utc)
        and permits_native_source(transaction, client, uid, derived)
    )
