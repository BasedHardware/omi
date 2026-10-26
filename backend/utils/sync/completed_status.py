"""Read-only legacy job reconciliation against durable content receipts.

The requested job remains the client handle even when a redrive completed the
same content under a new handle. A valid cap hold (``stt_cap_hold_v1``/``held``)
is answered like its completion: the dark fence (contract h) ACKs held content
with the ledger's job id and writes no Redis job, so its poll must reach a
terminal answer after the job TTL (M1 review L10-2). Unknown/failed work is
never ACKed.

A completed receipt whose result names a conversation the user deleted is the
one privacy denial answered terminally: the content was already processed, and
the user's deletion is the final word on it. The answer is ``completed`` with
an empty result and ``reason_code='conversation_deleted'``, so the phone ACKs
its WAL instead of confirming a 404 and re-uploading the deleted audio. No
deleted (or surviving) conversation ID is ever echoed.
"""

import logging
import os
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from database._client import get_firestore_client
from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed
from database.sync_ledger import (
    is_valid_completed_sync_content_result,
    is_valid_held_sync_content_result,
    sync_content_reference,
)
from utils.sync.stage import collection_name
from utils.observability.fallback import record_fallback
from utils.sync.deleted_conversation import (
    CONVERSATION_DELETED_REASON_CODE,
    confirm_only_user_deletions,
    deleted_conversation_result,
    is_conversation_deleted,
)

logger = logging.getLogger(__name__)


def get_completed_legacy_status(job_id: str, uid: str, job: dict[str, Any] | None) -> dict[str, Any] | None:
    # No Firestore client or lookup on the dark path, including TTL misses.
    if os.getenv('SYNC_DURABLE_STATUS_RECONCILIATION', 'false').strip().lower() != 'true':
        return None
    if not job_id or len(job_id) > 128 or '/' in job_id or job_id.startswith('bp_'):
        return None
    if job is not None and (job.get('uid') != uid or job.get('job_id') != job_id):
        return None
    if job is not None and job.get('status') == 'completed':
        return None
    client = get_firestore_client()

    @firestore.transactional
    def read(transaction: Any) -> dict[str, Any] | None:
        content_id = (job or {}).get('content_id')
        exact_handle = False
        if not content_id:
            # A retained old request is an immutable job -> content alias even
            # after an operator redrive changes the ledger's current job id.
            custody = (
                client.collection(collection_name('sync_redrive_required'))
                .document(job_id)
                .get(transaction=transaction)
                .to_dict()
                or {}
            )
            if custody:
                if custody.get('uid') != uid or custody.get('job_id') != job_id:
                    return None
                content_id = (custody.get('payload') or {}).get('content_id')
        if content_id:
            if not isinstance(content_id, str) or len(content_id) > 256 or '/' in content_id:
                return None
            reference = sync_content_reference(client, uid, content_id)
        else:
            # Old completions predate custody aliases. Equality is scoped to
            # this owner and bounded; re-read the candidate in this transaction.
            candidates = list(
                client.collection('users')
                .document(uid)
                .collection(collection_name('sync_content_ledger'))
                .where(filter=FieldFilter('job_id', '==', job_id))
                .select(())
                .limit(2)
                .stream(transaction=transaction)
            )
            if len(candidates) != 1:
                return None
            reference = candidates[0].reference
            exact_handle = True
        ledger = reference.get(transaction=transaction).to_dict() or {}
        result = ledger.get('result')
        if exact_handle and ledger.get('job_id') != job_id:
            return None
        completed = ledger.get('status') == 'completed' and is_valid_completed_sync_content_result(result)
        held = (
            ledger.get('dispatch_protocol') == 'stt_cap_hold_v1'
            and ledger.get('status') == 'held'
            and is_valid_held_sync_content_result(result)
        )
        if not isinstance(result, dict) or not (completed or held):
            return None
        # Preserve the batch status route's privacy boundary, including empty
        # completions, deleted accounts and redirected/deleted result targets.
        ids = []
        for key in ('new_memories', 'updated_memories'):
            values = result.get(key, [])
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                return None
            ids.extend(values)
        total = result['total_segments']
        lane = (job or {}).get('lane', 'fresh')
        status = {
            'job_id': job_id,
            'status': 'completed',
            'lane': lane if lane in {'fresh', 'backfill'} else 'fresh',
            'total_segments': total,
            'processed_segments': total,
            'successful_segments': total,
            'failed_segments': 0,
            'result': result,
        }
        try:
            assert_batch_write_allowed(client, transaction, uid, conversation_ids=ids)
        except BatchPrivacyBlocked as error:
            if not is_conversation_deleted(error):
                raise
            # Account, protection and generation fences all passed before the
            # conversation walk. Every other denied ID must also be a deletion.
            confirm_only_user_deletions(
                lambda one: assert_batch_write_allowed(client, transaction, uid, conversation_ids=one), ids
            )
            logger.info('event=sync_status_reconciliation outcome=conversation_deleted_terminal')
            return {
                **status,
                'result': deleted_conversation_result(total),
                'reason_code': CONVERSATION_DELETED_REASON_CODE,
            }
        return status

    try:
        return read(client.transaction())
    except BatchPrivacyBlocked as error:
        # A denied proof is not a failed read. Decline durable completion and
        # let the route resume its pre-reconciliation status/cleanup rules.
        # Never turn a privacy denial into a synthetic ACK.
        logger.warning('event=sync_status_reconciliation outcome=privacy_blocked fence_reason=%s', error.reason.value)
        record_fallback(
            component='sync_dispatch',
            from_mode='durable_completion',
            to_mode='redis_status',
            reason='policy',
            outcome='degraded',
        )
        return None
