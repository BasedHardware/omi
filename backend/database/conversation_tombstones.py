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
# Durable marker on the tombstone: the conversation's batch-pipeline rows still
# need their per-conversation purge. Cleared only after the purge completes.
BATCH_PURGE_PENDING_FIELD = 'batch_purge_pending'

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
    """Collect this owner's batch purges instead of running them inside ``record_deletion``.

    The per-conversation purge scans every batch-pipeline row the owner has, so
    its cost grows with account history (minutes for heavy owners). Inside this
    scope ``record_deletion`` persists a pending marker on the tombstone and
    appends the id; the caller must hand every collected id to a durable runner.
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
    try:
        user.collection(COLLECTION).document(conversation_id).create(
            {
                'conversation_id': conversation_id,
                'deleted_at': datetime.now(timezone.utc),
                'client_session_id': external.get('from_segments_client_session_id'),
                'created_at': row.get('created_at'),
            }
        )
    except AlreadyExists:
        # A retried delete after hard cleanup must preserve the original binding.
        pass
    # Staged chunks are siblings, including when no conversation was ever created.
    # The tombstone transaction fence prevents a racing upload from restaging them.
    from database.from_segments_chunks import purge_chunks

    purge_chunks(uid, conversation_id, firestore_client=db)
    deferred = _DEFERRED_BATCH_PURGES.get()
    if deferred is not None and deferred[0] == uid:
        # Intent first: the marker survives a lost dispatch so a re-drive can find it.
        user.collection(COLLECTION).document(conversation_id).set(
            {BATCH_PURGE_PENDING_FIELD: True, 'batch_purge_requested_at': datetime.now(timezone.utc)}, merge=True
        )
        if conversation_id not in deferred[1]:
            deferred[1].append(conversation_id)
        return
    # Intent remains durable if storage cleanup fails, and retry runs the purge
    # again even when the original tombstone already exists.
    from database.batch_pipeline_purge import purge_batch_owner

    purge_batch_owner(uid, conversation_id=conversation_id)


def run_batch_purge(uid: str, conversation_id: str) -> str:
    """Run one deferred per-conversation batch purge; returns a bounded outcome.

    Idempotent and safe to retry. Refuses under an active legal hold (the
    marker stays pending for a later re-drive) and never runs without the
    tombstone that fences new batch writes for this conversation.
    """
    from database.batch_pipeline_purge import purge_batch_owner
    from database.legal_holds import assert_account_deletion_permitted

    tombstone_ref = db.collection('users').document(uid).collection(COLLECTION).document(conversation_id)
    snapshot = tombstone_ref.get()
    if not snapshot.exists:
        return 'no_tombstone'
    if not (snapshot.to_dict() or {}).get(BATCH_PURGE_PENDING_FIELD):
        return 'already_completed'
    # Raises LegalHoldActive / LegalHoldAuthorityUnavailable for the caller to map.
    assert_account_deletion_permitted(uid)
    purge_batch_owner(uid, conversation_id=conversation_id)
    tombstone_ref.update({BATCH_PURGE_PENDING_FIELD: False, 'batch_purge_completed_at': datetime.now(timezone.utc)})
    return 'purged'
