"""Server authorization for the local desktop chat-first block tool.

The local kernel owns its journal. This route validates capability and
canonical references only; it never creates, updates, or syncs a chat row.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends
from pydantic import ValidationError

import database.action_items as action_items_db
import database.conversations as conversations_db
import database.goals as goals_db
import database.task_intelligence_control as task_control_db
from models.chat_first import (
    CaptureLinkSpec,
    ChatFirstBlockSpec,
    ChatFirstBlockValidationReceipt,
    ChatFirstBlockValidationRequest,
    GoalLinkSpec,
    QuestionCardSpec,
    TaskCardSpec,
    stable_block_id,
)
from utils.other import endpoints as auth
from utils.task_intelligence.rollout import resolve_chat_first_ui, resolve_task_intelligence_for_user

router = APIRouter()


def _entity_available(uid: str, block: ChatFirstBlockSpec) -> bool:
    if isinstance(block, TaskCardSpec):
        task = action_items_db.get_action_item(uid, block.task_id)
        return bool(task and not task.get('is_locked', False))
    if isinstance(block, GoalLinkSpec):
        return goals_db.get_goal_by_id(uid, block.goal_id) is not None
    if isinstance(block, CaptureLinkSpec):
        capture = conversations_db.get_conversation(uid, block.conversation_id)
        return bool(capture and capture.get('source') == 'omi' and not capture.get('discarded', False))
    if isinstance(block, QuestionCardSpec):
        subject = block.subject
        if subject.kind == 'task':
            task = action_items_db.get_action_item(uid, subject.id)
            return bool(task and not task.get('is_locked', False))
        if subject.kind == 'goal':
            return goals_db.get_goal_by_id(uid, subject.id) is not None
        capture = conversations_db.get_conversation(uid, subject.id)
        return bool(capture and capture.get('source') == 'omi' and not capture.get('discarded', False))
    return False


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

    try:
        control = task_control_db.get_task_workflow_control(uid)
        rollout = resolve_task_intelligence_for_user(
            uid=uid,
            workflow_mode=control.workflow_mode,
            account_generation=control.account_generation,
        )
        enabled = resolve_chat_first_ui(rollout, control.chat_first_ui_enabled)
    except Exception:
        return ChatFirstBlockValidationReceipt(accepted=False, code='capability_unavailable')

    if not enabled:
        return ChatFirstBlockValidationReceipt(accepted=False, code='capability_unavailable')
    if control.account_generation != request.control_generation:
        return ChatFirstBlockValidationReceipt(accepted=False, code='generation_mismatch')
    if not all(_entity_available(uid, block) for block in request.blocks):
        return ChatFirstBlockValidationReceipt(accepted=False, code='entity_unavailable')

    block_ids = [
        stable_block_id(uid=uid, generation=control.account_generation, block=block) for block in request.blocks
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
