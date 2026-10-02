"""Transactional preservation of automatic-refresh tasks; never updates user fields.

Bounded IDs-only query plus full document reads includes soft deletions, unlike
list APIs. The conversation receipt serializes refreshes and retains identities
of subsequently hard-deleted rows. Source revision and account generation fence
stale work. Any error aborts; callers must not fall through to destructive replace.
"""

from __future__ import annotations

from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client, run_transactional
from database.action_items import typed_doc
from database.action_items import _prepare_action_item_for_write  # pyright: ignore[reportPrivateUsage]
from database.action_items_cache import bump_action_items_list_version
from database.action_item_refresh_policy import LIMIT, RECEIPT, plan


def task_refs(user: Any, conversation_id: str, transaction: Any) -> list[Any]:
    """Bounded complete conversation membership, including deleted rows; overflow fails closed."""
    query = user.collection('action_items').where(filter=FieldFilter('conversation_id', '==', conversation_id))
    snapshots = list(query.select([]).limit(LIMIT + 1).stream(transaction=transaction))
    if len(snapshots) > LIMIT:
        raise ValueError('refresh task budget exceeded')
    return [snapshot.reference for snapshot in snapshots]


def reconcile(
    uid: str,
    conversation_id: str,
    items: list[dict],
    *,
    expected_revision: int | None,
    donor_id: str | None = None,
    firestore_client: Any = None,
) -> dict | None:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)
    conversation_ref = user.collection('conversations').document(conversation_id)

    @firestore.transactional
    def write(transaction):
        conversation = typed_doc(conversation_ref.get(transaction=transaction))
        if not conversation or conversation.get('deleted'):
            raise ValueError('refresh conversation unavailable')
        if donor_id is None and conversation.get('sync_content_revision') != expected_revision:
            raise ValueError('refresh conversation revision changed')
        control = typed_doc(user.collection('task_intelligence_control').document('state').get(transaction=transaction))
        generation = int(control.get('account_generation', 0))
        if conversation.get(RECEIPT) and conversation[RECEIPT].get('generation') != generation:
            raise ValueError('refresh receipt generation changed')
        refs = task_refs(user, conversation_id, transaction)
        rows = {ref.id: typed_doc(ref.get(transaction=transaction)) for ref in refs}
        donor_rows, donor_receipt = None, None
        if donor_id is not None:
            donor = typed_doc(user.collection('conversations').document(donor_id).get(transaction=transaction))
            smart_target = (donor.get('smart_merge') or {}).get('survivor_id')
            sync_target = donor.get('sync_merged_into')
            # Sync ancestry is persisted atomically with the redirect. It also
            # owns transitive sources whose immediate redirect is an older donor.
            owns_source = smart_target == conversation_id or (
                sync_target and donor_id in conversation.get('sync_merged_from', [])
            )
            if not donor.get('deleted') or not owns_source:
                raise ValueError('refresh donor is not an absorbed source')
            donor_refs = task_refs(user, donor_id, transaction)
            donor_rows = {ref.id: typed_doc(ref.get(transaction=transaction)) for ref in donor_refs}
            donor_receipt = donor.get(RECEIPT) or {}
            if donor_receipt and donor_receipt.get('generation') != generation:
                raise ValueError('refresh donor generation changed')
        elif not rows and not conversation.get(RECEIPT):
            return None  # First processing: original writer and delivery order, unchanged.
        all_rows = {**rows, **(donor_rows or {})}
        if not all_rows and not conversation.get(RECEIPT) and not donor_receipt:
            return None  # Empty donor cleanup must not change first-processing behavior.
        if any(row.get('account_generation', 0) != generation for row in all_rows.values()):
            raise ValueError('refresh account generation changed')
        receipt, creates, updates, counts = plan(
            conversation_id,
            rows,
            items,
            conversation.get(RECEIPT) or {},
            generation,
            donor_rows=donor_rows,
            donor_receipt=donor_receipt,
        )
        # Deterministic IDs must never overwrite an occupied document (including a tombstone).
        for task_id in creates:
            if user.collection('action_items').document(task_id).get(transaction=transaction).exists:
                raise ValueError('refresh task identity collision')
        for task_id, item in creates.items():
            transaction.create(user.collection('action_items').document(task_id), _prepare_action_item_for_write(item))
        for task_id, patch in updates.items():
            transaction.update(user.collection('action_items').document(task_id), patch)
        transaction.update(conversation_ref, {RECEIPT: receipt})
        pending = [task_id for task_id, row in rows.items() if row.get('refresh_delivery') == 'pending']
        return {'counts': counts, 'pending': [*pending, *creates]}

    result = run_transactional(client, write)
    if result is not None:
        bump_action_items_list_version(uid)
    return result


def claim_delivery(uid: str, conversation_id: str, task_ids: list[str], *, firestore_client: Any = None) -> list[dict]:
    """At most one submission per new ID; ambiguous external delivery is never blindly retried.

    A crash after claim can leave an undelivered task. Exactly-once provider creation
    requires provider idempotency/reconciliation, outside this preservation change.
    """
    if not task_ids:
        return []
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)

    @firestore.transactional
    def claim(transaction):
        conversation = typed_doc(
            user.collection('conversations').document(conversation_id).get(transaction=transaction)
        )
        control = typed_doc(user.collection('task_intelligence_control').document('state').get(transaction=transaction))
        refs = [user.collection('action_items').document(task_id) for task_id in dict.fromkeys(task_ids)]
        rows = [(ref, typed_doc(ref.get(transaction=transaction))) for ref in refs]
        result = []
        if not conversation or conversation.get('deleted'):
            return result
        for ref, row in rows:
            if (
                row.get('conversation_id') != conversation_id
                or row.get('refresh_delivery') != 'pending'
                or row.get('account_generation', 0) != control.get('account_generation', 0)
            ):
                continue
            transaction.update(ref, {'refresh_delivery': 'claimed'})
            if (
                row.get('deleted')
                or row.get('completed')
                or row.get('exported')
                or row.get('apple_reminder_id')
                or row.get('sync_requested')
            ):
                continue
            result.append(dict(row, id=ref.id))
        return result

    return run_transactional(client, claim)


def pending_rows(uid: str, conversation_id: str, task_ids: list[str], *, firestore_client: Any = None) -> list[dict]:
    """Current payloads for derived vectors; delivery subsequently rechecks authoritative rows."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    collection = client.collection('users').document(uid).collection('action_items')
    rows = []
    for task_id in task_ids:
        row = typed_doc(collection.document(task_id).get())
        if row.get('conversation_id') == conversation_id and not row.get('deleted'):
            rows.append(dict(row, id=task_id))
    return rows
