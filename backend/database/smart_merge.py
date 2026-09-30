"""Storage for folding a finished conversation into its predecessor.

The only writer of ``smart_merge`` (survivor ledger/revision, donor marker) and
``smart_merge_decision``. The absorb transaction reuses the sync bridge's
redirect contract (``deleted`` + ``discarded`` + ``sync_merged_into`` on the
donor, ``sync_merged_from`` on the survivor), so every existing redirect reader
(owner detail reads, manual speaker assignment, deletion purge, list/count
filters) treats both kinds of donor alike.

Transcripts are decoded strictly and re-encoded with the conversation codec:
an unreadable blob aborts the transaction instead of becoming an empty list.
The deterministic policy is injected by the caller (``plan``), so this module
stays storage-only and every precondition is evaluated on rows read inside the
transaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping, Optional, Sequence

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database import conversations as conversations_db
from database._client import get_firestore_client, run_transactional
from database.firestore_index_registry import CONVERSATIONS_SMART_MERGE_PRECEDING_QUERY

logger = logging.getLogger(__name__)

SMART_MERGE_FIELD = 'smart_merge'
DECISION_FIELD = 'smart_merge_decision'
AUDIT_COLLECTION = 'smart_merge_audit'
_CONVERSATIONS = 'conversations'
_ALL_STATUSES = ('in_progress', 'processing', 'merging', 'completed', 'failed')
# Metadata only: the predecessor's transcript is read separately, and only for
# the one row that can become the survivor.
_PRECEDING_FIELDS = (
    'id',
    'created_at',
    'started_at',
    'finished_at',
    'source',
    'client_device_id',
    'status',
    'discarded',
    'deleted',
    'is_locked',
    'structured.title',
    'structured.overview',
    'user_title',
    'starred',
    'folder_user_set',
    'sync_relevance_user_kept',
    'visibility',
    'has_photos',
    'capture_group',
    'uses_custom_stt',
    'external_data.duplicate_capture_of',
    'relevance_decision.trigger',
    SMART_MERGE_FIELD,
)

Plan = Callable[
    [Mapping[str, Any], Sequence[Mapping[str, Any]], Mapping[str, Any], Sequence[Mapping[str, Any]]],
    tuple[Optional[str], Optional[dict], Optional[dict]],
]


@dataclass(frozen=True)
class AbsorbResult:
    outcome: str  # 'absorbed' | 'already_absorbed' | 'rejected'
    reason: str


def conversation_collection(client: Any, uid: str) -> Any:
    return client.collection('users').document(uid).collection(_CONVERSATIONS)


def audit_ref(client: Any, uid: str, donor_id: str) -> Any:
    # Sibling of conversations, deliberately outside every conversation cascade.
    return client.collection('users').document(uid).collection(AUDIT_COLLECTION).document(donor_id)


def merge_audit(donor_id: str, survivor_id: str, donor_update: Mapping[str, Any], source: Any) -> dict[str, Any]:
    """Closed content-free projection; never copy arbitrary decision fields."""
    decision = donor_update.get(DECISION_FIELD) or {}
    merged_at = donor_update[SMART_MERGE_FIELD]['merged_at']
    return {
        'donor_id': donor_id,
        'survivor_id': survivor_id,
        'p_same': decision.get('p_same'),
        'threshold': decision.get('threshold'),
        'question_version': decision.get('question_version'),
        'served_model': decision.get('served_model'),
        'gap_seconds': decision.get('gap_seconds'),
        'merged_at': merged_at,
        'mode': decision.get('mode'),
        'source': source,
        'expire_at': merged_at + timedelta(days=60),
    }


def find_preceding_conversations(
    uid: str,
    *,
    source: str,
    created_before: datetime,
    limit: int,
    firestore_client: Any = None,
) -> list[dict[str, Any]]:
    """Newest-first visible rows of one source created before ``created_before``.

    Every status is requested so a busy immediate predecessor is seen (and
    blocks the pair) instead of being skipped for an older row. Served by the
    existing ``conversations_discarded_source_status_created`` index.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = CONVERSATIONS_SMART_MERGE_PRECEDING_QUERY.build(
        conversation_collection(client, uid),
        {
            'discarded': False,
            'source': source,
            'statuses': list(_ALL_STATUSES),
            'created_before': created_before,
        },
        field_filter_factory=FieldFilter,
    )
    query = query.order_by('created_at', direction=firestore.Query.DESCENDING).select(list(_PRECEDING_FIELDS))
    rows = []
    for snapshot in query.limit(limit).stream():
        data = snapshot.to_dict() or {}
        data['id'] = snapshot.id
        rows.append(data)
    return rows


def decode_merge_row(uid: str, raw: Mapping[str, Any]) -> tuple[dict[str, Any], list[Any]]:
    row = dict(raw)
    # The adapter's strict codec: an unreadable blob raises instead of becoming [].
    segments = conversations_db._decode_transcript_segments_strict(  # pyright: ignore[reportPrivateUsage]
        uid, raw.get('transcript_segments', []), bool(raw.get('transcript_segments_compressed'))
    )
    row.pop('transcript_segments', None)
    return row, list(segments)


def record_decision(uid: str, conversation_id: str, record: Mapping[str, Any], *, firestore_client: Any = None) -> bool:
    """Store the server-only decision record on a live (non-deleted) conversation."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = conversation_collection(client, uid).document(conversation_id)

    @firestore.transactional
    def write(transaction) -> bool:
        row = ref.get(transaction=transaction).to_dict()
        if not row or row.get('deleted'):
            return False
        transaction.update(ref, {DECISION_FIELD: dict(record)})
        return True

    return run_transactional(client, write)


def absorb_conversation(
    uid: str,
    survivor_id: str,
    donor_id: str,
    *,
    expected_revision: int,
    plan: Plan,
    firestore_client: Any = None,
) -> AbsorbResult:
    """Atomically append the donor to the survivor and leave a redirect tombstone.

    ``plan`` re-applies the deterministic policy to the rows read here and
    returns ``(reason, survivor_update, donor_update)``; a reason rejects.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = conversation_collection(client, uid)
    survivor_ref = collection.document(survivor_id)
    donor_ref = collection.document(donor_id)

    @firestore.transactional
    def absorb(transaction) -> AbsorbResult:
        survivor_raw = survivor_ref.get(transaction=transaction).to_dict()
        donor_raw = donor_ref.get(transaction=transaction).to_dict()
        if not donor_raw:
            return AbsorbResult('rejected', 'conversation_not_eligible')
        donor_state = donor_raw.get(SMART_MERGE_FIELD) or {}
        if donor_raw.get('deleted'):
            if donor_state.get('role') == 'donor' and donor_state.get('survivor_id') == survivor_id:
                return AbsorbResult('already_absorbed', 'absorbed')
            return AbsorbResult('rejected', 'conversation_not_eligible')
        if not survivor_raw or survivor_raw.get('deleted'):
            return AbsorbResult('rejected', 'survivor_changed')
        if int((survivor_raw.get(SMART_MERGE_FIELD) or {}).get('revision') or 0) != expected_revision:
            return AbsorbResult('rejected', 'survivor_changed')
        survivor, survivor_segments = decode_merge_row(uid, dict(survivor_raw, id=survivor_id))
        donor, donor_segments = decode_merge_row(uid, dict(donor_raw, id=donor_id))
        reason, survivor_update, donor_update = plan(survivor, survivor_segments, donor, donor_segments)
        if reason is not None or survivor_update is None or donor_update is None:
            return AbsorbResult('rejected', reason or 'survivor_changed')
        level = survivor_update.get('data_protection_level') or 'enhanced'
        payload = conversations_db.encode_conversation_for_write(uid, survivor_update, level)
        # The survivor transcript changed: a stored client projection described the old one.
        conversations_db._invalidate_client_processing(payload)  # pyright: ignore[reportPrivateUsage]
        transaction.update(survivor_ref, payload)
        transaction.update(donor_ref, donor_update)
        transaction.set(
            audit_ref(client, uid, donor_id), merge_audit(donor_id, survivor_id, donor_update, donor.get('source'))
        )
        return AbsorbResult('absorbed', 'absorbed')

    result = run_transactional(client, absorb)
    if result.outcome == 'absorbed':
        # The same fail-open search-index hooks the conversation adapter runs after its writes.
        conversations_db._sync_conversation_search_index(uid, survivor_id)  # pyright: ignore[reportPrivateUsage]
        conversations_db._delete_conversation_search_index(uid, donor_id)  # pyright: ignore[reportPrivateUsage]
    return result


def claim_survivor_refresh(
    uid: str,
    survivor_id: str,
    *,
    owner: str,
    now: datetime,
    lease_seconds: int,
    firestore_client: Any = None,
) -> Optional[int]:
    """Take the refresh lease for an owed survivor refresh; the revision to refresh, or ``None``."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = conversation_collection(client, uid).document(survivor_id)

    @firestore.transactional
    def claim(transaction) -> Optional[int]:
        row = ref.get(transaction=transaction).to_dict()
        if not row or row.get('deleted'):
            return None
        state = dict(row.get(SMART_MERGE_FIELD) or {})
        revision = int(state.get('revision') or 0)
        if int(state.get('refreshed_revision') or 0) >= revision:
            return None
        lease = state.get('refresh_lease') or {}
        until = lease.get('until')
        if lease.get('owner') not in (None, owner) and isinstance(until, datetime) and until > now:
            return None
        state['refresh_lease'] = {'owner': owner, 'until': now + timedelta(seconds=lease_seconds)}
        transaction.update(ref, {SMART_MERGE_FIELD: state})
        return revision

    return run_transactional(client, claim)


def complete_survivor_refresh(
    uid: str, survivor_id: str, *, owner: str, revision: int, firestore_client: Any = None
) -> bool:
    """Record a persisted refresh of ``revision``; only the current lease owner may."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = conversation_collection(client, uid).document(survivor_id)

    @firestore.transactional
    def complete(transaction) -> bool:
        row = ref.get(transaction=transaction).to_dict()
        if not row or row.get('deleted'):
            return False
        state = dict(row.get(SMART_MERGE_FIELD) or {})
        if int(state.get('revision') or 0) != revision or (state.get('refresh_lease') or {}).get('owner') != owner:
            return False
        state['refreshed_revision'] = revision
        state.pop('refresh_lease', None)
        transaction.update(ref, {SMART_MERGE_FIELD: state})
        return True

    return run_transactional(client, complete)
