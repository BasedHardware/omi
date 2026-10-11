"""Server authorization for the local desktop chat-first block tool.

The local kernel owns its journal. This route validates capability and
canonical references only; it never creates, updates, or syncs a chat row.
"""

from typing import Annotated, Any

from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import ValidationError

import database.action_items as action_items_db
import database._client as db_client_module
import database.conversations as conversations_db
import database.goals as goals_db
from database.firestore_read_metrics import FirestoreReadSite
import database.task_intelligence_control as task_control_db
from models.chat_first import (
    CaptureLinkSpec,
    ConversationLinkSpec,
    ChatFirstJournalBlockSpec,
    ChatFirstBlockValidationReceipt,
    ChatFirstBlockValidationRequest,
    DeferralCreateRequest,
    DeferralReceipt,
    GoalLinkSpec,
    LegacyMaterializePromptsResponse,
    LegacyProactiveIntent,
    MaterializePromptsRequest,
    MaterializePromptsResponse,
    MemoryLinkSpec,
    MemoryReviewCardSpec,
    TaskCardSpec,
    stable_block_id,
)
from utils.memory.memory_service import fetch_memory_dict
from utils.other import endpoints as auth
from utils.task_intelligence.chat_first_eligibility import (
    resolve_chat_first_eligibility,
    resolve_task_intelligence_for_user,
)

router = APIRouter()


def _eligibility(uid: str):
    """Resolve Chat-first authority through the shared fail-closed boundary.

    Providers are passed explicitly so this route keeps its narrow unit-test
    seams; other feature ingress uses the utility's production defaults.
    """

    return resolve_chat_first_eligibility(
        uid,
        load_control=task_control_db.get_task_workflow_control,
        resolve_rollout=resolve_task_intelligence_for_user,
    )


def _require_materialization_capability(uid: str, *, owner_fence: str, control_generation: int):
    """Reject stale or off desktop ingress before reading any proactive state."""

    if owner_fence != uid:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found')
    eligibility = _eligibility(uid)
    if not eligibility.enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Not found')
    if eligibility.account_generation != control_generation:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='account generation mismatch')
    return eligibility


def _entity_available(uid: str, block: ChatFirstJournalBlockSpec) -> bool:
    if isinstance(block, TaskCardSpec):
        task = action_items_db.get_action_item(uid, block.task_id)
        return bool(task and not task.get('is_locked', False))
    if isinstance(block, GoalLinkSpec):
        return goals_db.get_goal_by_id(uid, block.goal_id) is not None
    if isinstance(block, CaptureLinkSpec):
        capture = conversations_db.get_conversation(
            uid, block.conversation_id, read_site=FirestoreReadSite.CHAT_FIRST_BLOCK_VALIDATION
        )
        return bool(
            capture
            and capture.get('source') == 'omi'
            and not capture.get('discarded', False)
            and not capture.get('is_locked', False)
        )
    if isinstance(block, ConversationLinkSpec):
        conversation = conversations_db.get_conversation(
            uid, block.conversation_id, read_site=FirestoreReadSite.CHAT_FIRST_BLOCK_VALIDATION
        )
        return bool(
            conversation
            and conversation.get('source') == 'desktop'
            and (conversation.get('external_data') or {}).get('conversation_role') == 'meeting'
            and not conversation.get('discarded', False)
            and not conversation.get('is_locked', False)
            and conversation.get('status') == 'completed'
        )
    if isinstance(block, MemoryLinkSpec):
        try:
            return bool(fetch_memory_dict(uid, block.memory_id, db_client=getattr(db_client_module, 'db', None)))
        except HTTPException:
            return False
    if isinstance(block, MemoryReviewCardSpec):
        # Every row is a claim the owner can accept or correct in place, so the
        # card is only admissible if each one is a memory this account still owns.
        client = getattr(db_client_module, 'db', None)
        try:
            return all(bool(fetch_memory_dict(uid, item.memory_id, db_client=client)) for item in block.items)
        except HTTPException:
            return False
    subject = block.subject
    if subject.kind == 'cold_start':
        # Synthetic cold-start subjects are admitted only through the
        # deterministic materialization endpoint, never agent tool input.
        return False
    if subject.kind == 'task':
        task = action_items_db.get_action_item(uid, subject.id)
        return bool(task and not task.get('is_locked', False))
    if subject.kind == 'goal':
        return goals_db.get_goal_by_id(uid, subject.id) is not None
    capture = conversations_db.get_conversation(
        uid, subject.id, read_site=FirestoreReadSite.CHAT_FIRST_BLOCK_VALIDATION
    )
    return bool(
        capture
        and capture.get('source') == 'omi'
        and not capture.get('discarded', False)
        and not capture.get('is_locked', False)
    )


@router.post(
    '/v1/chat-first/blocks/validate',
    response_model=ChatFirstBlockValidationReceipt,
    tags=['chat-first'],
)
def validate_chat_first_blocks(
    payload: Annotated[Any, Body()],
    uid: str = Depends(auth.get_current_user_uid),
) -> ChatFirstBlockValidationReceipt:
    """Validate all requested blocks or return a typed no-mutation rejection."""

    try:
        request = ChatFirstBlockValidationRequest.model_validate(payload)
    except ValidationError:
        return ChatFirstBlockValidationReceipt(accepted=False, code='invalid_request')

    # The local runtime binds this fence to its signed-in owner before it can
    # append a receipt. Fail closed if a stale/cross-account command reaches
    # the backend with another user's authenticated token.
    if request.owner_fence != uid:
        return ChatFirstBlockValidationReceipt(accepted=False, code='capability_unavailable')

    eligibility = _eligibility(uid)
    if not eligibility.enabled:
        return ChatFirstBlockValidationReceipt(accepted=False, code='capability_unavailable')
    if eligibility.account_generation != request.control_generation:
        return ChatFirstBlockValidationReceipt(accepted=False, code='generation_mismatch')
    if not all(_entity_available(uid, block) for block in request.blocks):
        return ChatFirstBlockValidationReceipt(accepted=False, code='entity_unavailable')

    block_ids = [
        stable_block_id(uid=uid, generation=request.control_generation, block=block) for block in request.blocks
    ]
    if len(block_ids) != len(set(block_ids)):
        return ChatFirstBlockValidationReceipt(accepted=False, code='invalid_request')

    return ChatFirstBlockValidationReceipt(
        accepted=True,
        code='accepted',
        blocks=[
            {'id': block_id, **block.model_dump(exclude_none=True)}
            for block_id, block in zip(block_ids, request.blocks)
        ],
    )


@router.post(
    '/v1/chat/materialize-prompts',
    response_model=LegacyMaterializePromptsResponse,
    tags=['chat-first'],
    operation_id='materialize_prompts_v1_chat_materialize_prompts_post',
)
def materialize_prompts_v1(
    request: MaterializePromptsRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> LegacyMaterializePromptsResponse:
    """Preserve the released block union; new receipt types remain pending for v2 clients."""

    response = _materialize_prompts(request, uid, exclude_block_types={'conversationLink'})
    compatible = [
        LegacyProactiveIntent.model_validate(intent.model_dump())
        for intent in response.intents
        if all(block.type != 'conversationLink' for block in intent.blocks)
    ]
    return LegacyMaterializePromptsResponse(intents=compatible)


@router.post(
    '/v2/chat/materialize-prompts',
    response_model=MaterializePromptsResponse,
    tags=['chat-first'],
)
def materialize_prompts(
    request: MaterializePromptsRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> MaterializePromptsResponse:
    return _materialize_prompts(request, uid)


def _materialize_prompts(
    request: MaterializePromptsRequest,
    uid: str,
    *,
    exclude_block_types: set[str] | frozenset[str] | None = None,
) -> MaterializePromptsResponse:
    """Retired delivery boundary for released clients: Chat needs a user turn.

    Return no queued or historical intents, without reading or preparing the
    proactive store. Rich blocks still use the capability-scoped validate tool.
    """
    _require_materialization_capability(
        uid, owner_fence=request.owner_fence, control_generation=request.control_generation
    )
    return MaterializePromptsResponse()


@router.post(
    '/v1/chat/deferrals',
    response_model=DeferralReceipt,
    tags=['chat-first'],
)
def record_chat_deferral(
    request: DeferralCreateRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> DeferralReceipt:
    """Receive one idempotent kernel-outbox deferral without touching Chat state."""

    _require_materialization_capability(
        uid,
        owner_fence=request.owner_fence,
        control_generation=request.control_generation,
    )
    # Acknowledge retired outboxes without scheduling a future Chat entry.
    return DeferralReceipt(
        deferral_id=str(uuid5(NAMESPACE_URL, f'chat-deferral:{uid}:{request.continuity_key}')),
        due_at=datetime.now(timezone.utc),
        state='released',
    )
