"""Snapshot-fenced, reversible terminal "no speech" state for stale captures.

No decoder, content rewrite, deletion, provider or delivery call lives here.
The caller must have an approved private plan for the exact row revision and
strict-VAD evidence that the retained audio has less than ten seconds of
speech. The close keeps every byte of audio and every content field: it only
stamps the reviewed hidden terminal shape and records the prior values in a
marker so the operator undo can restore the row exactly.

The state is named ``no_speech`` in the marker. Its exit is
``restore_no_speech`` (operator undo), which restores the saved fields and
removes the marker. Nothing in this module deletes a row or an audio object.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client
from utils.conversations.recovery import TERMINAL_NO_DERIVED_EFFECTS_FIELD

MARKER = 'no_speech_terminal'
POLICY = 'batch_live_no_speech_v1'
STATE = 'no_speech'
COMMITTED_REVISION_UNKNOWN = 'committed_revision_unknown'
_FIELDS = ('status', 'discarded', TERMINAL_NO_DERIVED_EFFECTS_FIELD)
# A row that another owner already retired, locked, merged or admitted to
# finalization is never ours to close or restore.
_REFUSED_ROW_FIELDS = ('deleted', 'sync_merged_into', 'is_locked', 'finalization_job_id')


class NoSpeechConflict(RuntimeError):
    """Closed reason codes only; never include identities or content."""


def revision(snapshot: Any) -> str | None:
    value = getattr(snapshot, 'update_time', None)
    if value is None:
        return None
    return value.rfc3339() if hasattr(value, 'rfc3339') else value.isoformat()


def _prior(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {key: {'present': key in row, 'value': row.get(key)} for key in _FIELDS}


def _close_txn(
    transaction: Any,
    client: Any,
    uid: str,
    cid: str,
    expected_revision: str,
    run_id: str,
    speech_seconds: float,
    audio_seconds: float,
    now: datetime,
    expected_privacy_generation: int | None = None,
) -> None:
    user = client.collection('users').document(uid)
    ref = user.collection('conversations').document(cid)
    snapshot = ref.get(transaction=transaction)
    if not snapshot.exists or revision(snapshot) != expected_revision:
        raise NoSpeechConflict('revision_changed')
    row = snapshot.to_dict() or {}
    if row.get('record_lane_owner') != 'batch_live_v1':
        raise NoSpeechConflict('not_batch_live_owner')
    if row.get('status') != 'in_progress':
        raise NoSpeechConflict('not_in_progress')
    if any(row.get(key) for key in _REFUSED_ROW_FIELDS):
        raise NoSpeechConflict('row_retired_or_locked')
    if row.get('discarded'):
        raise NoSpeechConflict('already_discarded')
    if row.get(MARKER):
        raise NoSpeechConflict('already_marked')
    # Owner consent is re-read in the same transaction as the write. A missing
    # preference keeps the canonical enabled default.
    owner = user.get(transaction=transaction).to_dict() or {}
    if (
        row.get('uses_custom_stt')
        or not row.get('private_cloud_sync_enabled')
        or not owner.get('private_cloud_sync_enabled', True)
    ):
        raise NoSpeechConflict('privacy_changed')
    if expected_privacy_generation is not None:
        # Enroll the authority in this transaction's conflict set. Checking only
        # consent would miss a revoke/re-enable after the operator's reproof.
        # Keep this import off the secret-free restore path.
        from database.batch_pipeline_privacy import PRIVACY_COLLECTION, privacy_owner_key

        privacy = (
            client.collection(PRIVACY_COLLECTION)
            .document(privacy_owner_key(uid))
            .get(transaction=transaction)
            .to_dict()
            or {}
        )
        if int(privacy.get('generation', 0)) != expected_privacy_generation:
            raise NoSpeechConflict('privacy_changed')
    transaction.update(
        ref,
        {
            'status': 'completed',
            'discarded': True,
            TERMINAL_NO_DERIVED_EFFECTS_FIELD: True,
            MARKER: {
                'version': 1,
                'policy': POLICY,
                'state': STATE,
                'run_id': run_id,
                'closed_at': now,
                'speech_seconds': speech_seconds,
                'audio_seconds': audio_seconds,
                'prior': _prior(row),
            },
        },
    )


def close_no_speech(
    uid: str,
    cid: str,
    *,
    expected_revision: str,
    run_id: str,
    speech_seconds: float,
    audio_seconds: float,
    firestore_client: Any = None,
    expected_privacy_generation: int | None = None,
) -> str:
    """Hide one unchanged in-progress capture as the reversible no-speech terminal.

    Returns the committed revision, or COMMITTED_REVISION_UNKNOWN when the SDK
    omits it. The ledger can record either without raising after the hide.
    An approved privacy generation, when supplied, is fenced in the write
    transaction; None preserves the direct caller consent-only contract.
    """
    if not run_id or not 0 <= speech_seconds < 10 or not 0 <= audio_seconds <= 7200:
        raise NoSpeechConflict('unbound_plan')
    client = firestore_client or get_firestore_client()
    transaction = client.transaction()
    firestore.transactional(_close_txn)(
        transaction,
        client,
        uid,
        cid,
        expected_revision,
        run_id,
        speech_seconds,
        audio_seconds,
        datetime.now(timezone.utc),
        expected_privacy_generation,
    )
    # No post-commit IO: the existing quiet evaluator retires terminal owners
    # idempotently. Keeping its state intact also preserves a live undo.
    results = getattr(transaction, 'write_results', None) or ()
    return (revision(results[0]) if results else None) or COMMITTED_REVISION_UNKNOWN


def _restore_txn(
    transaction: Any,
    client: Any,
    uid: str,
    cid: str,
    expected_closed_revision: str,
    run_id: str,
) -> None:
    user = client.collection('users').document(uid)
    ref = user.collection('conversations').document(cid)
    snapshot = ref.get(transaction=transaction)
    if not snapshot.exists or revision(snapshot) != expected_closed_revision:
        raise NoSpeechConflict('revision_changed')
    row = snapshot.to_dict() or {}
    marker = row.get(MARKER) or {}
    if (
        marker.get('version') != 1
        or marker.get('policy') != POLICY
        or marker.get('state') != STATE
        or marker.get('run_id') != run_id
        or row.get('status') != 'completed'
        or row.get('discarded') is not True
        or row.get(TERMINAL_NO_DERIVED_EFFECTS_FIELD) is not True
    ):
        raise NoSpeechConflict('not_matching_close')
    if any(row.get(key) for key in _REFUSED_ROW_FIELDS):
        raise NoSpeechConflict('row_retired_or_locked')
    prior = marker.get('prior') or {}
    if set(prior) != set(_FIELDS):
        raise NoSpeechConflict('invalid_snapshot')
    transaction.update(
        ref,
        {
            **{key: saved['value'] if saved['present'] else firestore.DELETE_FIELD for key, saved in prior.items()},
            MARKER: firestore.DELETE_FIELD,
        },
    )


def restore_no_speech(
    uid: str,
    cid: str,
    *,
    expected_closed_revision: str,
    run_id: str,
    firestore_client: Any = None,
) -> None:
    """Restore only the unchanged generation this run closed; never a later edit.

    Undo restores the owner's existing row and performs no cloud admission or
    audio access. Do not reapply consent gates: opting out after close must not
    strand the owner's row hidden. Run, revision and closed-shape fences remain.
    """
    client = firestore_client or get_firestore_client()
    firestore.transactional(_restore_txn)(client.transaction(), client, uid, cid, expected_closed_revision, run_id)
