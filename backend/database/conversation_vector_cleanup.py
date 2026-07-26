"""Projected conversation identity reads and source fences for vector cleanup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Collection
from uuid import uuid4

from google.cloud import firestore

from database import vector_db
from database._client import delete_collection_recursive, get_firestore_client
from database.conversation_finalization_effects import (
    FINALIZATION_INCARNATION_FIELD,
    FINALIZATION_VECTOR_GENERATION_FIELD,
    TRANSCRIPT_VECTOR_COUNT_FIELD,
    VECTOR_CLEANUP_PENDING_FIELD,
    finalization_incarnation_id,
    finalization_vector_generation_id,
    transcript_vector_count,
)
from database.conversation_finalization_jobs import get_stale_processing_orphan_after

CONVERSATIONS_COLLECTION = 'conversations'
FINALIZATION_JOBS_COLLECTION = 'conversation_finalization_jobs'
VECTOR_CLEANUP_OWNER_FIELD = 'vector_cleanup_owner_token'
VECTOR_CLEANUP_LEASE_EXPIRES_FIELD = 'vector_cleanup_lease_expires_at'
VECTOR_CLEANUP_LEASE_DURATION = timedelta(hours=1)
_EXPECTED_INCARNATION_UNSET = object()


class ConversationVectorCleanupConflict(RuntimeError):
    """The requested row incarnation no longer owns the conversation ID."""


class ConversationVectorCleanupBusy(RuntimeError):
    """A finalization worker can still mutate vectors for this source."""


@dataclass(frozen=True)
class ConversationVectorCleanupDescriptor:
    conversation_id: str
    finalization_incarnation_id: str | None
    finalization_vector_generation_id: str | None
    transcript_vector_count: int | None
    cleanup_owner_token: str


def _descriptor(
    conversation_id: str,
    data: dict[str, Any] | None,
    cleanup_owner_token: str,
) -> ConversationVectorCleanupDescriptor:
    return ConversationVectorCleanupDescriptor(
        conversation_id=conversation_id,
        finalization_incarnation_id=finalization_incarnation_id(data),
        finalization_vector_generation_id=finalization_vector_generation_id(data),
        transcript_vector_count=transcript_vector_count(data),
        cleanup_owner_token=cleanup_owner_token,
    )


def _conversation_ref(client: Any, uid: str, conversation_id: str) -> Any:
    return client.collection('users').document(uid).collection(CONVERSATIONS_COLLECTION).document(conversation_id)


def _cleanup_projection_fields() -> list[str]:
    return [
        'status',
        'discarded',
        'processing_admitted_at',
        'finalization_job_id',
        FINALIZATION_INCARNATION_FIELD,
        FINALIZATION_VECTOR_GENERATION_FIELD,
        TRANSCRIPT_VECTOR_COUNT_FIELD,
        VECTOR_CLEANUP_PENDING_FIELD,
        VECTOR_CLEANUP_OWNER_FIELD,
        VECTOR_CLEANUP_LEASE_EXPIRES_FIELD,
    ]


def _processing_admission_is_active(data: dict[str, Any], now: datetime) -> bool:
    """Recognize a live synchronous processor before it creates a finalization job."""
    if data.get('status') != 'processing' or data.get('discarded'):
        return False
    admitted_at = data.get('processing_admitted_at')
    if not isinstance(admitted_at, datetime):
        return False
    if admitted_at.tzinfo is None:
        admitted_at = admitted_at.replace(tzinfo=timezone.utc)
    return admitted_at + get_stale_processing_orphan_after() > now


def _claim_conversation_vector_cleanup_txn(
    transaction: Any,
    conversation_ref: Any,
    expected_finalization_incarnation_id: object,
    finalization_job_ref_for_id: Callable[[str], Any],
    cleanup_owner_token: str,
    now: datetime,
) -> tuple[ConversationVectorCleanupDescriptor | None, str | None]:
    snapshot = conversation_ref.get(
        transaction=transaction,
        field_paths=_cleanup_projection_fields(),
    )
    if not getattr(snapshot, 'exists', False):
        return None, None
    data = snapshot.to_dict() or {}
    if (
        expected_finalization_incarnation_id is not _EXPECTED_INCARNATION_UNSET
        and finalization_incarnation_id(data) != expected_finalization_incarnation_id
    ):
        raise ConversationVectorCleanupConflict('conversation_vector_cleanup_incarnation_changed')
    descriptor = _descriptor(conversation_ref.id, data, cleanup_owner_token)
    finalization_job_id = data.get('finalization_job_id')
    active_fanout_reason = (
        'conversation_vector_cleanup_processing_active' if _processing_admission_is_active(data, now) else None
    )
    if isinstance(finalization_job_id, str) and finalization_job_id:
        job_snapshot = finalization_job_ref_for_id(finalization_job_id).get(
            transaction=transaction,
            field_paths=['status', 'fanout_status', 'fanout_plan_version', 'lease_expires_at'],
        )
        job = job_snapshot.to_dict() if getattr(job_snapshot, 'exists', False) else None
        if isinstance(job, dict) and (
            job.get('fanout_status') == 'leased'
            or job.get('status') == 'leased'
            or (
                job.get('status') == 'dead_letter_cleanup'
                and isinstance(job.get('lease_expires_at'), datetime)
                and job['lease_expires_at'] > now
            )
        ):
            # A leased fanout can still own non-vector derived mutations even
            # after its job lease timestamp expires. Keep deletion fenced until
            # that worker durably closes the fanout claim.
            active_fanout_reason = 'conversation_vector_cleanup_fanout_active'
    existing_owner = data.get(VECTOR_CLEANUP_OWNER_FIELD)
    if (
        data.get(VECTOR_CLEANUP_PENDING_FIELD)
        and isinstance(existing_owner, str)
        and existing_owner != cleanup_owner_token
    ):
        # Expiry is an operator eligibility signal, not automatic takeover
        # authority. The old process may still return from a delayed provider
        # delete and target shared legacy IDs after a same-ID recreation.
        raise ConversationVectorCleanupBusy('conversation_vector_cleanup_already_claimed')
    cleanup_update: dict[str, Any] = {VECTOR_CLEANUP_PENDING_FIELD: True}
    if active_fanout_reason is None:
        cleanup_update.update(
            {
                VECTOR_CLEANUP_OWNER_FIELD: cleanup_owner_token,
                VECTOR_CLEANUP_LEASE_EXPIRES_FIELD: now + VECTOR_CLEANUP_LEASE_DURATION,
            }
        )
    transaction.update(conversation_ref, cleanup_update)
    return descriptor, active_fanout_reason


def claim_conversation_vector_cleanup_descriptor(
    uid: str,
    conversation_id: str,
    *,
    expected_finalization_incarnation_id: str | None | object = _EXPECTED_INCARNATION_UNSET,
    firestore_client: Any | None = None,
) -> ConversationVectorCleanupDescriptor | None:
    """Fence finalization and capture one row incarnation and vector generation."""
    client = firestore_client or get_firestore_client()
    cleanup_owner_token = uuid4().hex
    transactional = firestore.transactional(_claim_conversation_vector_cleanup_txn)
    descriptor, busy_reason = transactional(
        client.transaction(),
        _conversation_ref(client, uid, conversation_id),
        expected_finalization_incarnation_id,
        lambda job_id: client.collection(FINALIZATION_JOBS_COLLECTION).document(job_id),
        cleanup_owner_token,
        datetime.now(timezone.utc),
    )
    if busy_reason is not None:
        raise ConversationVectorCleanupBusy(busy_reason)
    return descriptor


def _release_conversation_vector_cleanup_txn(
    transaction: Any,
    conversation_ref: Any,
    descriptor: ConversationVectorCleanupDescriptor,
) -> bool:
    snapshot = conversation_ref.get(
        transaction=transaction,
        field_paths=[
            FINALIZATION_INCARNATION_FIELD,
            VECTOR_CLEANUP_PENDING_FIELD,
            VECTOR_CLEANUP_OWNER_FIELD,
        ],
    )
    if not getattr(snapshot, 'exists', False):
        return False
    conversation = snapshot.to_dict() or {}
    if (
        conversation.get(FINALIZATION_INCARNATION_FIELD) != descriptor.finalization_incarnation_id
        or not conversation.get(VECTOR_CLEANUP_PENDING_FIELD)
        or conversation.get(VECTOR_CLEANUP_OWNER_FIELD) != descriptor.cleanup_owner_token
    ):
        return False
    transaction.update(
        conversation_ref,
        {
            VECTOR_CLEANUP_OWNER_FIELD: firestore.DELETE_FIELD,
            VECTOR_CLEANUP_LEASE_EXPIRES_FIELD: firestore.DELETE_FIELD,
        },
    )
    return True


def release_conversation_vector_cleanup_descriptor(
    uid: str,
    descriptor: ConversationVectorCleanupDescriptor,
    *,
    firestore_client: Any | None = None,
) -> bool:
    """Release one failed cleanup attempt while retaining its finalization fence."""
    client = firestore_client or get_firestore_client()
    transactional = firestore.transactional(_release_conversation_vector_cleanup_txn)
    return transactional(
        client.transaction(),
        _conversation_ref(client, uid, descriptor.conversation_id),
        descriptor,
    )


def _force_release_expired_conversation_vector_cleanup_txn(
    transaction: Any,
    conversation_ref: Any,
    expected_finalization_incarnation_id: str | None,
    expected_cleanup_owner_token: str,
    now: datetime,
) -> bool:
    snapshot = conversation_ref.get(
        transaction=transaction,
        field_paths=[
            FINALIZATION_INCARNATION_FIELD,
            VECTOR_CLEANUP_PENDING_FIELD,
            VECTOR_CLEANUP_OWNER_FIELD,
            VECTOR_CLEANUP_LEASE_EXPIRES_FIELD,
        ],
    )
    if not getattr(snapshot, 'exists', False):
        return False
    conversation = snapshot.to_dict() or {}
    if conversation.get(FINALIZATION_INCARNATION_FIELD) != expected_finalization_incarnation_id:
        raise ConversationVectorCleanupConflict('conversation_vector_cleanup_incarnation_changed')
    if (
        not conversation.get(VECTOR_CLEANUP_PENDING_FIELD)
        or conversation.get(VECTOR_CLEANUP_OWNER_FIELD) != expected_cleanup_owner_token
    ):
        return False
    lease_expires_at = conversation.get(VECTOR_CLEANUP_LEASE_EXPIRES_FIELD)
    if not isinstance(lease_expires_at, datetime) or lease_expires_at > now:
        raise ConversationVectorCleanupBusy('conversation_vector_cleanup_owner_still_active')
    transaction.update(
        conversation_ref,
        {
            VECTOR_CLEANUP_OWNER_FIELD: firestore.DELETE_FIELD,
            VECTOR_CLEANUP_LEASE_EXPIRES_FIELD: firestore.DELETE_FIELD,
        },
    )
    return True


def force_release_expired_conversation_vector_cleanup_after_confirmed_termination(
    uid: str,
    conversation_id: str,
    *,
    expected_finalization_incarnation_id: str | None,
    expected_cleanup_owner_token: str,
    confirmed_worker_terminated: bool,
    firestore_client: Any | None = None,
) -> bool:
    """Release an expired cleanup owner only after its process cannot issue provider writes."""
    if not confirmed_worker_terminated:
        raise ValueError('confirmed_worker_terminated must be true')
    client = firestore_client or get_firestore_client()
    transactional = firestore.transactional(_force_release_expired_conversation_vector_cleanup_txn)
    return transactional(
        client.transaction(),
        _conversation_ref(client, uid, conversation_id),
        expected_finalization_incarnation_id,
        expected_cleanup_owner_token,
        datetime.now(timezone.utc),
    )


def claim_conversation_vector_cleanup_descriptors(
    uid: str,
    *,
    exclude_conversation_ids: Collection[str] | None = None,
    firestore_client: Any | None = None,
) -> list[ConversationVectorCleanupDescriptor]:
    """Fence and project all row incarnations and vector generations before a wipe."""
    client = firestore_client or get_firestore_client()
    collection = client.collection('users').document(uid).collection(CONVERSATIONS_COLLECTION)
    snapshots = list(collection.select(_cleanup_projection_fields()).stream())
    excluded_ids = frozenset(exclude_conversation_ids or ())
    descriptors: list[ConversationVectorCleanupDescriptor] = []
    try:
        for snapshot in snapshots:
            if snapshot.id in excluded_ids:
                continue
            descriptor = claim_conversation_vector_cleanup_descriptor(
                uid,
                snapshot.id,
                firestore_client=client,
            )
            if descriptor is not None:
                descriptors.append(descriptor)
    except Exception:
        for descriptor in descriptors:
            release_conversation_vector_cleanup_descriptor(uid, descriptor, firestore_client=client)
        raise
    return descriptors


def _delete_claimed_conversation_parent_txn(
    transaction: Any,
    conversation_ref: Any,
    expected_finalization_incarnation_id: str | None,
    cleanup_owner_token: str,
    delete_source: bool = True,
) -> bool:
    snapshot = conversation_ref.get(
        transaction=transaction,
        field_paths=[
            FINALIZATION_INCARNATION_FIELD,
            VECTOR_CLEANUP_PENDING_FIELD,
            VECTOR_CLEANUP_OWNER_FIELD,
        ],
    )
    if not getattr(snapshot, 'exists', False):
        return False
    conversation = snapshot.to_dict() or {}
    if conversation.get(FINALIZATION_INCARNATION_FIELD) != expected_finalization_incarnation_id:
        raise ConversationVectorCleanupConflict('conversation_delete_incarnation_changed')
    if not conversation.get(VECTOR_CLEANUP_PENDING_FIELD):
        raise ConversationVectorCleanupConflict('conversation_delete_cleanup_not_claimed')
    if conversation.get(VECTOR_CLEANUP_OWNER_FIELD) != cleanup_owner_token:
        raise ConversationVectorCleanupConflict('conversation_delete_cleanup_owner_changed')
    if delete_source:
        transaction.delete(conversation_ref)
    return True


def _validate_claimed_conversation_source(
    uid: str,
    descriptor: ConversationVectorCleanupDescriptor,
    *,
    firestore_client: Any | None = None,
) -> bool:
    client = firestore_client or get_firestore_client()
    transactional = firestore.transactional(_delete_claimed_conversation_parent_txn)
    return transactional(
        client.transaction(),
        _conversation_ref(client, uid, descriptor.conversation_id),
        descriptor.finalization_incarnation_id,
        descriptor.cleanup_owner_token,
        False,
    )


def _delete_claimed_conversation_document(
    uid: str,
    descriptor: ConversationVectorCleanupDescriptor,
    *,
    firestore_client: Any | None = None,
) -> bool:
    client = firestore_client or get_firestore_client()
    conversation_ref = _conversation_ref(client, uid, descriptor.conversation_id)
    if not _validate_claimed_conversation_source(uid, descriptor, firestore_client=client):
        return False
    for subcollection in conversation_ref.collections():
        delete_collection_recursive(subcollection, client=client)
    transactional = firestore.transactional(_delete_claimed_conversation_parent_txn)
    return transactional(
        client.transaction(),
        conversation_ref,
        descriptor.finalization_incarnation_id,
        descriptor.cleanup_owner_token,
    )


def delete_claimed_conversation_source(
    uid: str,
    descriptor: ConversationVectorCleanupDescriptor,
    *,
    delete_source_artifacts: Callable[[str, str], None],
    firestore_client: Any | None = None,
) -> bool:
    """Purge captured vector identities, then conditionally remove their source."""
    try:
        if not _validate_claimed_conversation_source(uid, descriptor, firestore_client=firestore_client):
            return False
        conversation_id = descriptor.conversation_id
        generation_id = descriptor.finalization_vector_generation_id
        vector_db.delete_vector(
            uid,
            conversation_id,
            generation_id,
            require_index=generation_id is not None,
        )
        if not _validate_claimed_conversation_source(uid, descriptor, firestore_client=firestore_client):
            return False
        vector_db.delete_transcript_chunk_vectors(
            uid,
            conversation_id,
            finalization_vector_generation_id=generation_id,
            transcript_vector_count=descriptor.transcript_vector_count,
            raise_on_failure=True,
            require_index=generation_id is not None,
        )
        if not _validate_claimed_conversation_source(uid, descriptor, firestore_client=firestore_client):
            return False
        delete_source_artifacts(uid, conversation_id)
        if not _validate_claimed_conversation_source(uid, descriptor, firestore_client=firestore_client):
            return False
        return _delete_claimed_conversation_document(uid, descriptor, firestore_client=firestore_client)
    except Exception:
        release_conversation_vector_cleanup_descriptor(uid, descriptor, firestore_client=firestore_client)
        raise


def delete_conversation_with_vector_cleanup(
    uid: str,
    conversation_id: str,
    *,
    delete_source_artifacts: Callable[[str, str], None],
    expected_finalization_incarnation_id: str | None | object = _EXPECTED_INCARNATION_UNSET,
    firestore_client: Any | None = None,
) -> bool:
    """Claim an unowned source deletion, then purge vectors and the source."""
    descriptor = claim_conversation_vector_cleanup_descriptor(
        uid,
        conversation_id,
        expected_finalization_incarnation_id=expected_finalization_incarnation_id,
        firestore_client=firestore_client,
    )
    if descriptor is None:
        return False
    return delete_claimed_conversation_source(
        uid,
        descriptor,
        delete_source_artifacts=delete_source_artifacts,
        firestore_client=firestore_client,
    )
