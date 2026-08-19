"""Persistence and identity fence for one conversation processing generation."""

from typing import Any, Callable, cast

from models.conversation import Conversation, CreateConversation, ExternalIntegrationCreateConversation
from models.conversation_enums import ConversationStatus
from utils.sync.conversation_artifact_protocol import FinalizationIdentity, conversation_finalization_identity

ConversationInput = Conversation | CreateConversation | ExternalIntegrationCreateConversation


def persist_generation(
    uid: str,
    language_code: str,
    conversation: ConversationInput,
    *,
    force_process: bool,
    people: list[Any],
    defer_derived_effects: bool,
    replay_derived_effects: bool,
    expected_identity: FinalizationIdentity | None,
    get_structured: Callable[..., tuple[Any, bool]],
    get_conversation_obj: Callable[..., Conversation],
    authorities: tuple[Any, Any],
) -> tuple[Conversation, bool, FinalizationIdentity | None, bool]:
    storage, lifecycle = authorities
    if replay_derived_effects:
        if not isinstance(conversation, Conversation):
            raise ValueError('derived-effect replay requires a persisted conversation')
        return conversation, conversation.discarded, expected_identity, True

    is_initial = isinstance(conversation, (CreateConversation, ExternalIntegrationCreateConversation))
    if not is_initial and expected_identity is None:
        current = storage.get_conversation(uid, conversation.id)
        if current is None:
            return conversation, False, None, False
        expected_identity = cast(
            FinalizationIdentity,
            tuple(
                current.get(field)
                for field in ('finalization_incarnation_id', 'finalization_job_id', 'finalization_revision')
            ),
        )
    structured, discarded = get_structured(uid, language_code, conversation, force_process, people=people)
    result = get_conversation_obj(uid, structured, conversation)
    result.status = ConversationStatus.completed if defer_derived_effects else ConversationStatus.processing
    if is_initial:
        create = (
            lifecycle.create_completed_conversation
            if defer_derived_effects
            else lifecycle.create_processing_conversation
        )
        persisted = create(uid, result.dict(), idempotent=True)
    else:
        persisted = lifecycle.persist_processed_conversation(
            uid, result.dict(), expected_finalization_identity=expected_identity
        )
    return result, discarded, expected_identity, persisted


def require_artifact_identity(
    uid: str,
    conversation_id: str,
    expected_identity: FinalizationIdentity | None,
    storage: Any,
) -> FinalizationIdentity:
    identity = expected_identity or conversation_finalization_identity(storage.get_conversation(uid, conversation_id))
    if identity is None:
        raise RuntimeError('conversation_artifact_identity_missing')
    return identity
