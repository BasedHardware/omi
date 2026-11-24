"""Scoped operator re-wake of overdue, committed batch summary debt.

No transcription, conversation edit, task deletion or processing runs here.
The ordinary enrichment worker retains all publication and paid-work fences.
"""

from __future__ import annotations

import re
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from utils.enrichment import outbox
from utils.sync import processing_hold


def refusal(row: dict, conversation: dict, jobs: list[dict], *, now: float) -> str | None:
    if not row or row.get('dormant') or row.get('effects_only') or row.get('summary_seen'):
        return 'settled'
    if row.get('held_reason') or row.get('summary_blocked_reason') or conversation.get('summary_blocked_reason'):
        return 'blocked'
    if row.get('lease_until', 0) > now:
        return 'leased'
    if not isinstance(row.get('due_at'), (int, float)) or row['due_at'] > now:
        return 'not_due'
    if not outbox.valid_dispatch_binding(row.get('dispatch')):
        return 'unbound'
    if (
        conversation.get('status') != 'completed'
        or conversation.get('deleted')
        or conversation.get('discarded')
        or conversation.get('sync_merged_into')
    ):
        return 'lifecycle'
    if (conversation.get('structured') or {}).get('title') or conversation.get('summary_output_present'):
        return 'already_titled'
    hold = conversation.get(processing_hold.FIELD) or {}
    since = processing_hold.timestamp(hold.get('pending_since'))
    if not hold.get('held') or not since or now - since < processing_hold.MAX_HOLD_SECONDS:
        return 'hold_not_overdue'
    if not jobs or any(j.get('state') != 'committed' or j.get('owner_id') != row['uid'] for j in jobs):
        return 'batch_not_committed'
    return None


def prepare(client: Any, document_id: str, run_id: str, *, now: float, apply: bool) -> tuple[str, dict | None]:
    """Revalidate custody, current batch state and privacy in the write transaction.

    A stable run id retries a failed/lost enqueue ACK with the SAME repair name.
    It never rotates task_token or changes acceptance/deadline/content metadata.
    """
    if not re.fullmatch('[0-9a-f]{64}', document_id) or not re.fullmatch('[a-zA-Z0-9_-]{1,80}', run_id):
        raise ValueError('invalid redrive scope')
    ref = client.collection(outbox.COLLECTION).document(document_id)

    @firestore.transactional
    def commit(transaction):
        from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed

        old = ref.get(transaction=transaction).to_dict() or {}
        uid, cid = old.get('uid'), old.get('conversation_id')
        if (
            not uid
            or not cid
            or outbox.key(uid, cid) != document_id
            or old.get('document_id', document_id) != document_id
        ):
            return 'settled', None
        conversation_ref = client.collection('users').document(uid).collection('conversations').document(cid)
        conversation = (
            conversation_ref.get(
                transaction=transaction,
                field_paths=[
                    'status',
                    'deleted',
                    'discarded',
                    'sync_merged_into',
                    'structured.title',
                    'summary_output_present',
                    'summary_blocked_reason',
                    processing_hold.FIELD,
                ],
            ).to_dict()
            or {}
        )
        jobs = {}
        for field, op in (
            ('conversation_id', '=='),
            ('conversation_ids', 'array_contains'),
            ('projection_binding.target_conversation_id', '=='),
        ):
            query = (
                client.collection('batch_pipeline_prod_jobs')
                .where(filter=FieldFilter(field, op, cid))
                .select(['state', 'owner_id'])
                .limit(1001)
            )
            matches = list(query.stream(transaction=transaction))
            if len(matches) == 1001:
                return 'batch_scope_too_large', None
            jobs.update((snapshot.id, snapshot.to_dict()) for snapshot in matches)
        reason = refusal(old, conversation, list(jobs.values()), now=now)
        if reason:
            return reason, None
        if old.get('operator_redrive_id') not in (None, run_id):
            raise ValueError('redrive run id is already pinned; reuse the original id')
        try:
            assert_batch_write_allowed(client, transaction, uid, conversation_ids=[cid])
        except BatchPrivacyBlocked:
            return 'privacy', None
        if not apply:
            return 'eligible', None
        pending = dict(old)
        if old.get('operator_redrive_id') != run_id:
            pending.update(
                wake_generation=int(old.get('wake_generation') or 0) + 1,
                task_due_at=now,
                wake_check_after=0,
                operator_redrive_id=run_id,
            )
            transaction.set(ref, pending)
        return 'prepared', pending

    return commit(client.transaction())


def redrive(client: Any, document_id: str, run_id: str, *, now: float, apply: bool = False) -> str:
    status, pending = prepare(client, document_id, run_id, now=now, apply=apply)
    if pending is not None:
        outbox.wake_row(pending)  # Existing generation-aware named-task tooling, after the durable commit.
        return 'rewoken'
    return status
