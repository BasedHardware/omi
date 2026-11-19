"""Context-carried v3 writer fence checked inside the existing persist transaction."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from utils.conversations.v3 import policy

_UNSPECIFIED = object()
_NATIVE_REARMED = 'v3_native_manual_rearmed_revision'
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
    """Reject a stale native notes attempt and give its exact source back to the builder once.

    A caller that gets False after a source read must end the transaction without
    publishing notes. Rollback would discard the source rearm.
    """
    binding = derived.get(policy.NATIVE_MANUAL_BINDING)
    if binding is None:
        return True
    cid = binding.get('recording_id') if isinstance(binding, dict) else None
    if (
        not isinstance(cid, str)
        or not cid
        or '/' in cid
        or cid not in (derived.get('v3_recording_ids') or [])
        or derived.get('deleted')
        or derived.get('is_locked')
    ):
        return False
    source = client.collection('users').document(uid).collection('conversations').document(cid)
    row = source.get(transaction=transaction).to_dict() or {}
    if policy.native_manual_binding(row, recording_id=cid) == binding:
        return True
    revision = binding.get('upload_revision')
    if (
        type(revision) is int
        and revision > 0
        and row.get(policy.NATIVE_MANUAL_READY) == revision
        and row.get(_NATIVE_REARMED) != revision
        and policy.builder_eligible(row)
        and not (row.get('discarded') or row.get('is_locked'))
    ):
        transaction.update(
            source,
            {
                _NATIVE_REARMED: revision,
                'v3_pending': True,
                'v3_pending_since': row.get('v3_pending_since') or datetime.now(timezone.utc),
            },
        )
    return False


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
