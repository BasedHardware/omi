"""Terminal for a live-capture conversation stuck at Firestore's 1 MiB document ceiling.

Finalization starts by binding a durable job onto the conversation, which grows
the document; at the ceiling Firestore rejects that write on every attempt, so
the row stays ``in_progress`` (invisible to the user) and every later listen
session retries it. ``in_progress`` -> ``completed`` is two bytes shorter, so it
is the one lifecycle write such a document still accepts. This is the
``in_progress`` sibling of ``complete_unstampable_orphan_conversation``
(FC-permanent-write-rejection-retried-forever). Only the lifecycle owner
(``utils.conversations.lifecycle``) calls it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal

from google.cloud import firestore

from database.quiet_check_retirement import stop_quiet_check_for_conversation
from database._client import get_firestore_client
from database import conversation_finalization_jobs as jobs_db
from database import recording_sessions as recording_sessions_db
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.conversation_terminal_title import (
    TERMINAL_SIZE_HEADROOM_BYTES,
    kept_row_terminal_update,
    user_time_zone,
)
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes

# A bounded log token.
OversizedInProgressOutcome = Literal[
    'closed',
    'missing',
    'not_in_progress',
    'owned',
    'recent_write',
    'below_ceiling',
    'recording_active',
    'account_deleting',
]


def _complete_oversized_in_progress_conversation_txn(
    transaction: Any,
    conversation_ref: Any,
    quiet_before: datetime,
    uid: str,
    time_zone_for_uid: Callable[[str], str | None] | None = None,
    *,
    conversation_id: str | None = None,
    recording_sessions_collection: Any | None = None,
    account_deletion_ref: Any | None = None,
    now: datetime | None = None,
) -> OversizedInProgressOutcome:
    """Close an ``in_progress`` row whose document is at the ceiling, keeping its content.

    Fences, all read inside this transaction: the row is still ``in_progress``,
    not discarded, deleted or deferred, has no durable finalization owner, no
    writer has touched it since ``quiet_before`` (the server-owned
    ``update_time``, the stand-in for an ownership fence the processing sweep
    also uses), and its estimated size is genuinely within the terminal
    headroom of the ceiling, so a row that has since shrunk keeps normal
    finalization instead. The transcript and every other field stay as stored;
    only optional growth (the deterministic title) is added, and only if it fits.

    The recovery variants of this terminal (quiet finalization) additionally
    re-assert the admission fences that guarded the failed finalization: a
    recording session whose lease is still live, or an account-deletion marker
    that blocks access, refuses the close, because a reconnect that renews only
    its lease document or a deletion started after that admission read must not
    have its row terminalized underneath it. An absent session document is not
    evidence of an active recorder — it can never become known again — so only
    a live lease refuses; both refusals resolve without operator action (the
    lease expires or the deletion finishes), leaving the row exactly as it was.
    """
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return 'missing'
    data = snapshot.to_dict() or {}
    if data.get('status') != 'in_progress':
        return 'not_in_progress'
    if data.get('discarded') or data.get('deleted') or data.get('deferred') or data.get('finalization_job_id'):
        return 'owned'
    if recording_sessions_collection is not None and conversation_id is not None:
        effective_now = now or datetime.now(timezone.utc)
        lease_expiry = jobs_db.recording_session_lease_expiry(
            transaction,
            recording_sessions_collection,
            uid,
            conversation_id,
            data,
            effective_now,
        )
        if lease_expiry is not None and lease_expiry > effective_now:
            return 'recording_active'
    if account_deletion_ref is not None:
        marker = account_deletion_ref.get(transaction=transaction)
        deletion_status = normalize_account_deletion_status(
            marker_exists=bool(marker.exists),
            raw_status=(marker.to_dict() or {}).get('wipe_status'),
        )
        if account_deletion_blocks_access(deletion_status):
            return 'account_deleting'
    last_written = getattr(snapshot, 'update_time', None)
    if not isinstance(last_written, datetime) or last_written > quiet_before:
        return 'recent_write'
    path = getattr(conversation_ref, 'path', None)
    estimated = estimate_firestore_document_bytes(data, path if isinstance(path, str) else None)
    if estimated + TERMINAL_SIZE_HEADROOM_BYTES < FIRESTORE_MAX_DOCUMENT_BYTES:
        return 'below_ceiling'
    terminal = kept_row_terminal_update(uid, data, conversation_ref, {'status': 'completed'}, time_zone_for_uid)
    transaction.update(conversation_ref, terminal)
    return 'closed'


def complete_oversized_in_progress_conversation(
    uid: str,
    conversation_id: str,
    *,
    quiet_for: timedelta | None = None,
    firestore_client: Any = None,
    recovery_fences: bool = False,
    recovery_cutoff: datetime | None = None,
) -> OversizedInProgressOutcome:
    """Terminalize an in_progress conversation too large to accept its finalization binding.

    ``recovery_fences`` re-asserts the SERVER_RECOVERY admission fences (expired
    recording lease, no blocking account-deletion marker) inside the close
    transaction; the live-listen sweep keeps relying on its quiet window alone.
    ``recovery_cutoff`` pins that quiet window to the check's own absolute
    cutoff rather than reconstructing it from ``quiet_for`` at a later ``now``:
    admission latency must not shift the fence forward. Exactly one of
    ``quiet_for`` / ``recovery_cutoff`` is required.
    """
    if (quiet_for is None) == (recovery_cutoff is None):
        raise ValueError('exactly one of quiet_for or recovery_cutoff is required')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    conversation_ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
    user_ref = client.collection('users').document(uid)
    now = datetime.now(timezone.utc)
    quiet_before = (
        recovery_cutoff if recovery_cutoff is not None else now - (quiet_for if quiet_for is not None else timedelta(0))
    )
    if quiet_before.tzinfo is None:
        quiet_before = quiet_before.replace(tzinfo=timezone.utc)
    transactional = firestore.transactional(_complete_oversized_in_progress_conversation_txn)
    outcome = transactional(
        client.transaction(),
        conversation_ref,
        quiet_before,
        uid,
        lambda zone_uid: user_time_zone(client, zone_uid),
        conversation_id=conversation_id if recovery_fences else None,
        recording_sessions_collection=(
            user_ref.collection(recording_sessions_db.RECORDING_SESSIONS_COLLECTION) if recovery_fences else None
        ),
        account_deletion_ref=(client.collection('account_deletions').document(uid) if recovery_fences else None),
        now=now,
    )
    if outcome == 'closed':
        stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=client)
    return outcome
