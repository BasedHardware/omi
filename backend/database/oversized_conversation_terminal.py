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

from database._client import get_firestore_client
from database.conversation_terminal_title import (
    TERMINAL_SIZE_HEADROOM_BYTES,
    kept_row_terminal_update,
    user_time_zone,
)
from utils.firestore_document_size import FIRESTORE_MAX_DOCUMENT_BYTES, estimate_firestore_document_bytes

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
    return transactional(
        client.transaction(),
        conversation_ref,
        datetime.now(timezone.utc) - quiet_for,
        uid,
        lambda zone_uid: user_time_zone(client, zone_uid),
    )
