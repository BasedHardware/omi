"""Revision-fenced administrative undo and replay receipts. No external effects."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping, Sequence

from google.cloud import firestore

from database import conversations as conversations_db
from database._client import get_firestore_client, run_transactional
from database.legal_holds import assert_no_destructive_operation_transaction
from database.smart_merge import conversation_collection, decode_merge_row, audit_ref, merge_audit


@dataclass(frozen=True)
class UnmergeResult:
    outcome: str
    reason: str
    survivor_id: str = ''
    donor_ids: tuple[str, ...] = ()
    removed_segments: int = 0
    revision: int = 0


def unmerge_transaction(
    uid: str,
    donor_id: str,
    *,
    expected_revision: int,
    expected_content_revision: Any,
    dry_run: bool,
    now: datetime,
    suffix: Callable[[Mapping[str, Any], str], list[str]],
    eligibility: Callable[[Mapping[str, Any], Sequence[Mapping[str, Any]]], str | None],
    payload: Callable[..., tuple[dict[str, Any], int]],
    audio_filenames: Mapping[str, Sequence[str]] | None = None,
    expected_donor_revisions: Mapping[str, Any] | None = None,
    firestore_client: Any = None,
) -> UnmergeResult:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = conversation_collection(client, uid)

    @firestore.transactional
    def undo(transaction) -> UnmergeResult:
        # The audit sibling this transaction writes is user-scoped data the
        # account-deletion wipe owns; never recreate it under a live wipe gate.
        assert_no_destructive_operation_transaction(transaction, client, uid=uid)
        requested = collection.document(donor_id).get(transaction=transaction).to_dict() or {}
        donor_state = requested.get('smart_merge') or {}
        survivor_id = str(donor_state.get('survivor_id') or '')
        if donor_state.get('role') == 'unmerged':
            return UnmergeResult('noop', 'already_unmerged', survivor_id)
        if donor_state.get('role') != 'donor' or not survivor_id:
            return UnmergeResult('ineligible', 'not_a_donor')
        survivor_ref = collection.document(survivor_id)
        raw = survivor_ref.get(transaction=transaction).to_dict() or {}
        if not raw or raw.get('deleted'):
            return UnmergeResult('ineligible', 'survivor_missing_or_deleted', survivor_id)
        state = raw.get('smart_merge') or {}
        if (
            int(state.get('revision') or 0) != expected_revision
            or raw.get('sync_content_revision') != expected_content_revision
        ):
            return UnmergeResult('ineligible', 'revision_conflict', survivor_id)
        survivor, segments = decode_merge_row(uid, dict(raw, id=survivor_id))
        donor_ids = suffix(survivor, donor_id)
        entries = state.get('fragments') or []
        if (
            len(entries) != len({entry.get('id') for entry in entries})
            or not entries
            or entries[0].get('id') != survivor_id
        ):
            return UnmergeResult('ineligible', 'invalid_ledger', survivor_id)
        donors = []
        audits = []
        for cid in donor_ids:
            row = collection.document(cid).get(transaction=transaction).to_dict() or {}
            donors.append(decode_merge_row(uid, dict(row, id=cid)))
            audits.append(audit_ref(client, uid, cid).get(transaction=transaction).to_dict())
        reason = eligibility(survivor, [row for row, _ in donors])
        if reason is not None:
            return UnmergeResult('ineligible', reason, survivor_id, tuple(donor_ids))
        if not dry_run and (
            expected_donor_revisions is None
            or set(expected_donor_revisions) != set(donor_ids)
            or any(
                expected_donor_revisions[cid] != row.get('sync_content_revision')
                for cid, (row, _) in zip(donor_ids, donors)
            )
            or audio_filenames is None
            or set(audio_filenames) != set(donor_ids)
        ):
            return UnmergeResult('ineligible', 'revision_conflict', survivor_id, tuple(donor_ids))
        update, removed = payload(survivor, segments, donors, now=now)
        if not dry_run:
            assert audio_filenames is not None
            update['smart_merge']['unmerge_pending']['audio_filenames'] = {
                cid: list(audio_filenames[cid]) for cid in donor_ids
            }
        result = UnmergeResult(
            'dry_run' if dry_run else 'ok',
            'eligible',
            survivor_id,
            tuple(donor_ids),
            removed,
            int(update['smart_merge']['revision']),
        )
        if dry_run:
            return result
        encoded = conversations_db.encode_conversation_for_write(
            uid, update, raw.get('data_protection_level') or 'enhanced'
        )
        conversations_db._invalidate_client_processing(encoded)  # pyright: ignore[reportPrivateUsage]
        donor_updates = []
        for (donor, _), existing_audit in zip(donors, audits):
            cid = str(donor['id'])
            state = dict(donor.get('smart_merge') or {})
            state.update(role='unmerged', unmerged_at=now, unmerge_actor='admin', unmerge_root=donor_id)
            state['unmerge_audio_filenames'] = list((audio_filenames or {}).get(cid, []))
            patch = {
                'deleted': False,
                'discarded': False,
                'sync_merged_into': firestore.DELETE_FIELD,
                'sync_content_revision': int(donor.get('sync_content_revision') or 0) + 1,
                'sync_live_target': True,
                'smart_merge': state,
            }
            # Older merges predate the sibling audit. Reconstruct only its closed
            # numeric/id projection, using the retained donor's original decision.
            audit = merge_audit(cid, survivor_id, donor, donor.get('source'))
            if existing_audit:
                audit.update({key: existing_audit[key] for key in audit if key in existing_audit})
            audit.update(unmerged_at=now, unmerge_actor='admin')
            donor_updates.append((cid, patch, audit))
        transaction.update(survivor_ref, encoded)
        for cid, patch, audit in donor_updates:
            transaction.update(collection.document(cid), patch)
            transaction.set(audit_ref(client, uid, cid), audit)
        return result

    return run_transactional(client, undo)


def checkpoint_unmerge(
    uid: str,
    survivor_id: str,
    *,
    owner: str,
    now: datetime,
    lease_seconds: int,
    completed_donor: str | None = None,
    complete: bool = False,
    firestore_client: Any = None,
) -> dict[str, Any] | None:
    """Claim/reclaim or checkpoint one pending undo; all checks are transactional."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = conversation_collection(client, uid).document(survivor_id)

    @firestore.transactional
    def checkpoint(transaction):
        row = ref.get(transaction=transaction).to_dict() or {}
        state = dict(row.get('smart_merge') or {})
        pending = dict(state.get('unmerge_pending') or {})
        if row.get('deleted') or not pending or int(state.get('revision') or 0) != pending.get('revision'):
            return None
        lease = pending.get('lease') or {}
        until = lease.get('until')
        if lease.get('owner') not in (None, owner) and isinstance(until, datetime) and until > now:
            return None
        if complete:
            if int(state.get('refreshed_revision') or 0) < pending['revision']:
                return None
            if set(pending.get('processed_ids') or []) | set(pending.get('deleted_ids') or []) != set(
                pending['donor_ids']
            ):
                return None
            state.pop('unmerge_pending')
        else:
            if completed_donor:
                if completed_donor not in pending['donor_ids']:
                    return None
                donor = (
                    conversation_collection(client, uid)
                    .document(completed_donor)
                    .get(transaction=transaction)
                    .to_dict()
                )
                field = 'deleted_ids' if not donor or donor.get('deleted') else 'processed_ids'
                pending[field] = sorted({*(pending.get(field) or []), completed_donor})
            pending['lease'] = {'owner': owner, 'until': now + timedelta(seconds=lease_seconds)}
            state['unmerge_pending'] = pending
        transaction.update(ref, {'smart_merge': state})
        return pending

    return run_transactional(client, checkpoint)


def release_unmerge(uid: str, survivor_id: str, *, owner: str, firestore_client: Any = None) -> None:
    """Release only this worker's lease on handled failure; crashes expire normally."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = conversation_collection(client, uid).document(survivor_id)

    @firestore.transactional
    def release(transaction):
        row = ref.get(transaction=transaction).to_dict() or {}
        state = dict(row.get('smart_merge') or {})
        pending = dict(state.get('unmerge_pending') or {})
        if (pending.get('lease') or {}).get('owner') != owner:
            return
        pending.pop('lease', None)
        if (state.get('refresh_lease') or {}).get('owner') == owner:
            state.pop('refresh_lease', None)
        state['unmerge_pending'] = pending
        transaction.update(ref, {'smart_merge': state})

    run_transactional(client, release)
