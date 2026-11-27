"""Context-carried v3 writer fence checked inside the existing persist transaction."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from utils.conversations.v3 import policy

_UNSPECIFIED = object()
_NATIVE_REARMED = 'v3_native_manual_rearmed_revision'
_current: ContextVar[tuple[str, str, str, Any] | None] = ContextVar('conversation_v3_writer', default=None)


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
def writer(uid, cid, token, *, native_binding=_UNSPECIFIED):
    held = _current.set((uid, cid, token, native_binding))
    outcome = _outcome.set(None)
    try:
        yield
    finally:
        _outcome.reset(outcome)
        _current.reset(held)


def _settle_unavailable_native(transaction, client, uid, derived):
    cid = derived.get('id')
    if (
        not isinstance(cid, str)
        or not cid
        or '/' in cid
        or derived.get('v3_derived') is not True
        or not derived.get('v3_process_pending')
    ):
        return
    receipt = derived.get(policy.NATIVE_MANUAL_NOTES_VISIBILITY)
    written = bool(receipt or derived.get('v3_notes_written'))
    target = client.collection('users').document(uid).collection('conversations').document(cid)
    from database.conversations import claim_conversation_status_in_txn

    patch = claim_conversation_status_in_txn(
        derived,
        expected_status=derived.get('status'),
        claimed_status='completed',
        extra_updates={
            'tile_state': 'done' if written else 'failed',
            'v3_process_pending': False,
            'v3_process_failed': not written,
            'v3_process_failure_reason': None if written else 'native_source_unavailable',
            'summary_retryable': False,
            'manual_end': False,
            policy.NATIVE_MANUAL_BINDING: None,
            'sync_content_revision': int(derived.get('sync_content_revision') or 0) + 1,
            **(
                {'summary_covers_through': receipt['finished_at'], 'v3_notes_written': True}
                if receipt and receipt.get('finished_at')
                else {}
            ),
        },
    )
    if patch is not None:
        transaction.update(target, patch)


# A fence can register a wake while staging a transaction. The caller clears
# the scratch list on each retry and publishes only after a committed return.
def wake_repairs(uid, repairs):
    if not repairs:
        return
    from utils.conversations.v3.triggers import wake_native_manual_ready

    for repair in repairs:
        if repair is not None:
            cid, revision = repair
            wake_native_manual_ready(uid, cid, revision, rearm=True)


def permits_native_source(transaction, client, uid, derived, *, repairs=None):
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
    eligible = (
        row.get('recording') is True
        and policy.builder_eligible(row)
        and not (row.get('discarded') or row.get('is_locked'))
    )
    wake = None
    if not eligible:
        _settle_unavailable_native(transaction, client, uid, derived)
    elif type(revision) is int and revision > 0 and row.get(_NATIVE_REARMED) != revision:
        transaction.update(
            source,
            {
                _NATIVE_REARMED: revision,
                'v3_pending': True,
                'v3_pending_since': row.get('v3_pending_since') or datetime.now(timezone.utc),
            },
        )
        wake = (cid, revision)
    if repairs is not None:
        repairs.append(wake)
    return False


def permits(transaction, client, uid, cid, derived, *, repairs=None):
    fence = current()
    if fence is None:
        return permits_native_source(transaction, client, uid, derived, repairs=repairs)
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
        and permits_native_source(transaction, client, uid, derived, repairs=repairs)
    )
