"""Bounded, rotating reconnect recovery; cursor state never changes user content."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore
from config.refactor_modes import serving_for, shadow_or_serve
from utils.conversations.lifecycle_metrics import observe

from database.account_deletion_marker import account_deletion_document, account_deletion_firestore_client
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status
from database.firestore_index_registry import STALE_RECOVERY_PAGE_QUERY

PAGE_SIZE = 10
PAGE_BACKOFF = timedelta(minutes=1)
HEAD_CLAIM_INTERVAL = 3


def _claim_page_txn(transaction, state_ref, revision, next_cursor, now, *, deletion_ref):
    """CAS prevents concurrent reconnects from spending the same page budget."""
    # A live socket's executor can outlast auth/teardown cancellation. Fence
    # the new metadata write with the erasure authority in this transaction,
    # so a wipe cannot walk this subcollection and then have us recreate it.
    marker = deletion_ref.get(transaction=transaction)
    status = normalize_account_deletion_status(
        marker_exists=marker.exists, raw_status=(marker.to_dict() or {}).get('wipe_status')
    )
    if account_deletion_blocks_access(status):
        return False
    current = state_ref.get(transaction=transaction).to_dict() or {}
    if int(current.get('revision') or 0) != revision:
        return False
    not_before = current.get('not_before')
    if isinstance(not_before, datetime) and not_before > now:
        return False
    transaction.set(
        state_ref,
        {'revision': revision + 1, 'cursor': next_cursor, 'not_before': now + PAGE_BACKOFF},
    )
    return True


def get_stale_recovery_page(
    uid: str, *, cutoff: datetime, now: datetime | None = None, firestore_client: Any = None
) -> list[dict[str, Any]]:
    """Claim at most ten rows, newest eligible first, resuming past prior attempts.

    Read at most three bounded pages in shadow (tail, wrap and head probe),
    plus cursor state and the deletion marker. A transaction CAS
    advances the cursor *before* processing, so refusals, errors, cancellations,
    or a worker dying cannot pin the head. A short/empty tail wraps on the next
    claim. No snapshot lookup is needed for the cursor: deleted rows still make
    valid value cursors. One minute between claims bounds reconnect storms.
    The cursor and erasure marker use the same authoritative customer data
    plane. Finalization's normal idempotency/privacy fences remain authoritative.
    """
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    now = now or datetime.now(timezone.utc)
    user_ref = client.collection('users').document(uid)
    state_ref = user_ref.collection('conversation_recovery_state').document('stale_in_progress')
    state = state_ref.get().to_dict() or {}
    not_before = state.get('not_before')
    if isinstance(not_before, datetime) and not_before > now:
        return []
    conversations = user_ref.collection('conversations')
    query = (
        STALE_RECOVERY_PAGE_QUERY.build(
            conversations, {'status': 'in_progress', 'cutoff': cutoff}, field_filter_factory=firestore.FieldFilter
        )
        .order_by('finished_at', direction=firestore.Query.DESCENDING)
        .order_by('__name__', direction=firestore.Query.DESCENDING)
        .select(['finished_at'])
        .limit(PAGE_SIZE)
    )
    cursor = state.get('cursor')
    if (
        isinstance(cursor, dict)
        and isinstance(cursor.get('finished_at'), datetime)
        and isinstance(cursor.get('id'), str)
        and cursor['id']
        and '/' not in cursor['id']
    ):
        page = list(
            query.start_after(
                {'finished_at': cursor['finished_at'], '__name__': conversations.document(cursor['id'])}
            ).stream()
        )
        if not page:
            page = list(query.stream())
    else:
        page = list(query.stream())
    head_claim = bool(cursor) and (int(state.get('revision') or 0) + 1) % HEAD_CLAIM_INTERVAL == 0
    if head_claim and shadow_or_serve('LIFECYCLE_V2_MODE'):
        head = list(query.stream())
        observe('recovery_head', [s.id for s in page] == [s.id for s in head])
        if serving_for('LIFECYCLE_V2_MODE', uid):
            page = head
    next_cursor = None
    if len(page) == PAGE_SIZE:
        next_cursor = {'finished_at': page[-1].to_dict()['finished_at'], 'id': page[-1].id}
    if head_claim and serving_for('LIFECYCLE_V2_MODE', uid):
        # A head probe must not reset the tail's progress through old refusals.
        next_cursor = cursor
    claimed = firestore.transactional(_claim_page_txn)(
        client.transaction(),
        state_ref,
        int(state.get('revision') or 0),
        next_cursor,
        now,
        deletion_ref=account_deletion_document(uid, firestore_client=client),
    )
    return [{'id': snapshot.id} for snapshot in page] if claimed else []
