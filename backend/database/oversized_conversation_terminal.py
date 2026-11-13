"""Terminal for a live-capture conversation stuck at Firestore's 1 MiB document ceiling.

Finalization starts by binding a durable job onto the conversation, which grows
the document; at the ceiling Firestore rejects that write on every attempt, so
the row stays ``in_progress`` (invisible to the user) and every later listen
session retries it. ``in_progress`` -> ``completed`` is two bytes shorter, so it
is the one lifecycle write such a document still accepts. This is the
``in_progress`` sibling of ``complete_unstampable_orphan_conversation``
(FC-permanent-write-rejection-retried-forever). Only the lifecycle owner
(``utils.conversations.lifecycle``) calls it.

The transactional entry here used to hand its body to the Firestore SDK's
bare transaction path; it now rides the shared bounded engine
(``database.bounded_lane_transaction.run_bounded_lane_transaction``) — five
fresh single-commit transactions, equal-jitter rungs, replayed aborts and
expiries, and a typed, labeled ``FirestoreContentionExhausted`` — instead of
the bare SDK transaction mint whose read-time ``Aborted`` faults escaped
unclassified and whose same-id commit replay could not survive a retired
transaction id. An aborted or expired chain wrote nothing and the body
re-reads every fence inside its transaction, so the replay is safe.

Failure-Class: FC-bare-sync-backfill-and-conversation-job-transactions-fail-on-first-contention
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Literal

from google.cloud import firestore

from database.quiet_check_retirement import stop_quiet_check_for_conversation
from database._client import get_firestore_client
from database.bounded_lane_transaction import run_bounded_lane_transaction
from database.conversation_terminal_title import (
    TERMINAL_SIZE_HEADROOM_BYTES,
    kept_row_terminal_update,
    user_time_zone,
)
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes

logger = logging.getLogger(__name__)

# Static per-entry operation label: the lane's exhaustion marker names the
# flow on the calling module's logger (database.bounded_lane_transaction).
OVERSIZED_IN_PROGRESS_TERMINAL_LABEL = 'oversized_in_progress_terminal'

# A bounded log token.
OversizedInProgressOutcome = Literal['closed', 'missing', 'not_in_progress', 'owned', 'recent_write', 'below_ceiling']


def _complete_oversized_in_progress_conversation_txn(
    transaction: Any,
    conversation_ref: Any,
    quiet_before: datetime,
    uid: str,
    time_zone_for_uid: Callable[[str], str | None] | None = None,
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
    """
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return 'missing'
    data = snapshot.to_dict() or {}
    if data.get('status') != 'in_progress':
        return 'not_in_progress'
    if data.get('discarded') or data.get('deleted') or data.get('deferred') or data.get('finalization_job_id'):
        return 'owned'
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
    uid: str, conversation_id: str, *, quiet_for: timedelta, firestore_client: Any = None
) -> OversizedInProgressOutcome:
    """Terminalize an in_progress conversation too large to accept its finalization binding."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    conversation_ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
    transactional = firestore.transactional(_complete_oversized_in_progress_conversation_txn)

    def apply(transaction: Any) -> OversizedInProgressOutcome:
        return transactional(
            transaction,
            conversation_ref,
            datetime.now(timezone.utc) - quiet_for,
            uid,
            lambda zone_uid: user_time_zone(client, zone_uid),
        )

    outcome = run_bounded_lane_transaction(
        client, apply, operation_name=OVERSIZED_IN_PROGRESS_TERMINAL_LABEL, logger=logger
    )
    if outcome == 'closed':
        stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=client)
    return outcome
