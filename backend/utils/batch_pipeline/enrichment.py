"""Task adapter for the existing coalesced sync enrichment outbox."""

import re
from typing import Callable

from google.cloud import firestore
from database._client import get_firestore_client
from database.batch_pipeline_privacy import BatchPrivacyBlocked, assert_batch_write_allowed
from utils.sync import reprocess


def discard_blocked(document_id: str) -> bool:
    """A deletion/protection fence retires derived work without recreating it."""
    client = get_firestore_client()
    ref = client.collection(reprocess.COLLECTION).document(document_id)

    @firestore.transactional
    def discard(transaction):
        row = ref.get(transaction=transaction).to_dict() or {}
        if not row:
            return False
        try:
            assert_batch_write_allowed(client, transaction, row['uid'], conversation_ids=[row['conversation_id']])
        except BatchPrivacyBlocked:
            transaction.delete(ref)
            return True
        return False

    return discard(client.transaction())


def run_enrichment(
    document_id: str,
    task_token: str,
    *,
    now: float | None = None,
    process: Callable | None = None,
) -> str:
    if not re.fullmatch('[0-9a-f]{64}', document_id) or not re.fullmatch('[0-9a-f]{32}', task_token):
        raise ValueError('invalid sync enrichment task binding')
    if not reprocess.owns_runtime():
        raise RuntimeError('sync enrichment requires production or a Firestore emulator')
    if discard_blocked(document_id):
        return 'superseded'

    def enrich(uid: str, conversation_id: str, language: str):
        if discard_blocked(document_id):
            return
        callback = process
        if callback is None:
            from utils.sync.pipeline import _reprocess_conversation_after_update  # type: ignore[reportPrivateUsage]

            callback = _reprocess_conversation_after_update
        callback(uid, conversation_id, language)

    return reprocess.run(document_id, task_token, enrich, now=now)
