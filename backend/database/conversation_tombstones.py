"""Content-free user deletion intent, independent of hard-delete/processing rollback."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Iterator, List, Optional, Tuple

from google.api_core.exceptions import AlreadyExists

from database._client import db
from database.fsr_read_cache import cache_writer
from database import privacy_check_metrics as metrics
from database.privacy_negative_cache import decide

COLLECTION = 'deleted_conversations'

_DEFERRED_BATCH_PURGES: ContextVar[Optional[Tuple[str, List[str]]]] = ContextVar(
    'deferred_conversation_batch_purges', default=None
)


def is_deleted(uid: str, conversation_id: str) -> bool:
    metrics.called('tombstone')

    def live():
        return not metrics.read_snapshot(
            'tombstone', db.collection('users').document(uid).collection(COLLECTION).document(conversation_id), uid=uid
        ).exists

    return not decide('tombstone', uid, db, conversation_id, live, 'tombstone_negative_cache')


@contextmanager
def defer_batch_purges(uid: str) -> Iterator[List[str]]:
    """Arm a durable purge obligation instead of running the purge inside ``record_deletion``.

    The per-conversation purge scans every batch-pipeline row the owner has, so
    its cost grows with account history (minutes for heavy owners). Inside this
    scope ``record_deletion`` writes the obligation in the same commit as the
    tombstone; the backend-sync reconciler owns dispatching it.
    """
    collected: List[str] = []
    token = _DEFERRED_BATCH_PURGES.set((uid, collected))
    try:
        yield collected
    finally:
        _DEFERRED_BATCH_PURGES.reset(token)


def _tombstone_payload(conversation_id: str, row: dict) -> dict:
    # Store identity only, never transcript, structured data, or calendar identity.
    external = row.get('external_data') or {}
    return {
        'conversation_id': conversation_id,
        'deleted_at': datetime.now(timezone.utc),
        'client_session_id': external.get('from_segments_client_session_id'),
        'created_at': row.get('created_at'),
    }


@cache_writer('tombstone_negative_cache')
def accept_deletion(uid: str, conversation_id: str, *, firestore_client: Any = None) -> None:
    """Accept a delete without the account gate: hide it now, owe its erasure durably.

    One transaction writes the tombstone (kept if a retry already wrote it), marks
    the row ``deleted`` so every product read drops it at once, and arms the
    erasure obligation; its runner performs the request's cascade under the gate,
    which also arms the batch purge. Nothing is erased here. An active legal hold
    rejects the request as before; a hold placed after this commit stops the
    erasure and the conversation stays hidden but retained.
    """
    from database._client import get_firestore_client
    from database.conversation_batch_purge_jobs import accept_fields, erasure_job_ref
    from database.legal_holds import assert_account_deletion_permitted

    assert_account_deletion_permitted(uid)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    user = client.collection('users').document(uid)
    conversation_ref = user.collection('conversations').document(conversation_id)
    tombstone_ref = user.collection(COLLECTION).document(conversation_id)
    obligation_ref = erasure_job_ref(client, uid, conversation_id)

    def body(transaction):
        row_snapshot = conversation_ref.get(
            field_paths=['external_data', 'created_at', 'deleted', 'sync_merged_from'], transaction=transaction
        )
        tombstone_exists = tombstone_ref.get(transaction=transaction).exists
        owed = obligation_ref.get(transaction=transaction)
        row = (row_snapshot.to_dict() or {}) if row_snapshot.exists else {}
        # Merge donors are read now, while the row exists: their canonical audio is erased with it.
        # A retry after the row is gone keeps the donors an earlier acceptance recorded.
        sources = list((owed.to_dict() or {}).get('audio_source_ids') or []) if owed.exists else []
        for source in row.get('sync_merged_from') or []:
            if source and source != conversation_id and str(source) not in sources:
                sources.append(str(source))
        if not tombstone_exists:
            transaction.create(tombstone_ref, _tombstone_payload(conversation_id, row))
        if row_snapshot.exists and not row.get('deleted'):
            transaction.update(conversation_ref, {'deleted': True})
        owed_fields = accept_fields(uid, conversation_id, audio_source_ids=sources)
        if owed.exists:
            transaction.update(obligation_ref, owed_fields)  # generation/attempts/lease survive a re-accept
        else:
            transaction.set(obligation_ref, owed_fields)

    _in_transaction(client, body)


def _in_transaction(client: Any, body: Any) -> Any:
    from google.cloud import firestore

    @firestore.transactional
    def run(transaction):
        return body(transaction)

    return run(client.transaction())


@cache_writer('tombstone_negative_cache')
def record_deletion(uid: str, conversation_id: str) -> None:
    user = db.collection('users').document(uid)
    row = user.collection('conversations').document(conversation_id).get().to_dict() or {}
    tombstone_ref = user.collection(COLLECTION).document(conversation_id)
    tombstone = _tombstone_payload(conversation_id, row)
    deferred = _DEFERRED_BATCH_PURGES.get()
    deferred = deferred if deferred is not None and deferred[0] == uid else None
    if deferred is not None:
        from database.conversation_batch_purge_jobs import arm_fields, job_ref

        # The obligation commits with the intent, before any fallible cleanup.
        obligation = (job_ref(db, uid, conversation_id), arm_fields(uid, conversation_id))
        try:
            batch = db.batch()
            batch.create(tombstone_ref, tombstone)
            batch.set(*obligation, merge=True)
            batch.commit()
        except AlreadyExists:
            # A retried delete keeps the original tombstone and re-arms the obligation.
            obligation[0].set(obligation[1], merge=True)
        if conversation_id not in deferred[1]:
            deferred[1].append(conversation_id)
    else:
        try:
            tombstone_ref.create(tombstone)
        except AlreadyExists:
            # A retried delete after hard cleanup must preserve the original binding.
            pass
    # Staged chunks are siblings, including when no conversation was ever created.
    # The tombstone transaction fence prevents a racing upload from restaging them.
    from database.from_segments_chunks import purge_chunks

    purge_chunks(uid, conversation_id, firestore_client=db)
    if deferred is not None:
        return
    # Intent remains durable if storage cleanup fails, and retry runs the purge
    # again even when the original tombstone already exists.
    from database.batch_pipeline_purge import purge_batch_owner

    purge_batch_owner(uid, conversation_id=conversation_id)
