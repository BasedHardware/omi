"""Content-free user deletion intent, independent of hard-delete/processing rollback."""

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Iterator, List, Optional, Tuple

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


@cache_writer('tombstone_negative_cache')
def record_deletion(uid: str, conversation_id: str) -> None:
    user = db.collection('users').document(uid)
    row = user.collection('conversations').document(conversation_id).get().to_dict() or {}
    # Store identity only, never transcript, structured data, or calendar identity.
    external = row.get('external_data') or {}
    tombstone_ref = user.collection(COLLECTION).document(conversation_id)
    tombstone = {
        'conversation_id': conversation_id,
        'deleted_at': datetime.now(timezone.utc),
        'client_session_id': external.get('from_segments_client_session_id'),
        'created_at': row.get('created_at'),
    }
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
