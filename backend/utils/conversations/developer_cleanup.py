"""Private cleanup helpers shared by developer conversation routes."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, cast
import uuid

from google.cloud import firestore

from database._client import get_firestore_client
from database.conversation_finalization_effects import FINALIZATION_INCARNATION_FIELD
from database.conversation_vector_cleanup import (
    ConversationVectorCleanupBusy,
    ConversationVectorCleanupConflict,
    claim_conversation_vector_cleanup_descriptor,
    delete_claimed_conversation_source,
    delete_conversation_with_vector_cleanup,
)
from models.conversation_enums import ConversationStatus
from utils.conversations import lifecycle as lifecycle_service
from utils.other.conversation_playback_storage import delete_conversation_playback_artifacts

FROM_SEGMENTS_CLAIM_STALE_AFTER = timedelta(minutes=15)
_FROM_SEGMENTS_CONVERSATION_NAMESPACE = uuid.UUID('fb2f1f36-3c84-47a4-9c62-b3f6fdb3fd13')


class ConversationCleanupUnavailable(RuntimeError):
    """A conversation cleanup cannot safely proceed yet."""


def from_segments_conversation_id(uid: str, client_session_id: str) -> str:
    return str(uuid.uuid5(_FROM_SEGMENTS_CONVERSATION_NAMESPACE, f'{uid}\0{client_session_id}'))


def is_stale_from_segments_claim(conversation: dict[str, Any], client_session_id: str, now: datetime) -> bool:
    external_data = cast(dict[str, Any], conversation.get('external_data') or {})
    if external_data.get('from_segments_client_session_id') != client_session_id:
        return False
    if conversation.get('status') != ConversationStatus.processing.value:
        return False
    claimed_at = external_data.get('from_segments_claimed_at')
    if not isinstance(claimed_at, datetime):
        return False
    if claimed_at.tzinfo is None:
        claimed_at = claimed_at.replace(tzinfo=timezone.utc)
    return now - claimed_at > FROM_SEGMENTS_CLAIM_STALE_AFTER


def cleanup_conversation(uid: str, conversation_id: str, expected_incarnation_id: str | None) -> bool:
    """Remove one known row incarnation or report a retryable cleanup conflict."""
    try:
        return delete_conversation_with_vector_cleanup(
            uid,
            conversation_id,
            delete_source_artifacts=delete_conversation_playback_artifacts,
            expected_finalization_incarnation_id=expected_incarnation_id,
        )
    except (ConversationVectorCleanupBusy, ConversationVectorCleanupConflict) as error:
        raise ConversationCleanupUnavailable from error


def cleanup_conversation_for_endpoint(uid: str, conversation_id: str, expected_incarnation_id: str | None) -> bool:
    """Claim and remove one row incarnation for the developer DELETE route."""
    try:
        descriptor = claim_conversation_vector_cleanup_descriptor(
            uid,
            conversation_id,
            expected_finalization_incarnation_id=expected_incarnation_id,
        )
    except (ConversationVectorCleanupBusy, ConversationVectorCleanupConflict) as error:
        raise ConversationCleanupUnavailable from error
    if descriptor is None:
        return False
    try:
        return delete_claimed_conversation_source(
            uid,
            descriptor,
            delete_source_artifacts=delete_conversation_playback_artifacts,
        )
    except (ConversationVectorCleanupBusy, ConversationVectorCleanupConflict) as error:
        raise ConversationCleanupUnavailable from error


def _renew_from_segments_processing_lease_txn(
    transaction: Any,
    conversation_ref: Any,
    expected_incarnation_id: str | None,
    now: datetime,
) -> bool:
    snapshot = conversation_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return False
    conversation = snapshot.to_dict() or {}
    if (
        conversation.get('status') != ConversationStatus.processing.value
        or conversation.get('discarded')
        or conversation.get(FINALIZATION_INCARNATION_FIELD) != expected_incarnation_id
    ):
        return False
    transaction.update(conversation_ref, {'processing_admitted_at': now})
    return True


def renew_from_segments_processing_lease(
    uid: str,
    conversation_id: str,
    expected_incarnation_id: str | None,
) -> bool:
    client = get_firestore_client()
    conversation_ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
    transactional = firestore.transactional(_renew_from_segments_processing_lease_txn)
    return transactional(
        client.transaction(),
        conversation_ref,
        expected_incarnation_id,
        datetime.now(timezone.utc),
    )


@contextmanager
def from_segments_processing_guard(uid: str, conversation_id: str, expected_incarnation_id: str | None):
    if not renew_from_segments_processing_lease(uid, conversation_id, expected_incarnation_id):
        raise ConversationCleanupUnavailable('from_segments_processing_ownership_changed')

    def renew(renew_uid: str, renew_conversation_id: str) -> bool:
        return renew_from_segments_processing_lease(renew_uid, renew_conversation_id, expected_incarnation_id)

    with lifecycle_service.processing_admission_guard(
        uid,
        conversation_id,
        rollback_on_failure=False,
        renew=renew,
    ):
        yield
