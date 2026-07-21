"""Server authorization for the local desktop chat-first block tool.

The local kernel owns its journal. This route validates capability and
canonical references only; it never creates, updates, or syncs a chat row.
"""

from typing import Annotated, Any

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, status
from pydantic import ValidationError

import database.action_items as action_items_db
import database._client as db_client_module
import database.chat_first_intents as chat_first_intents_db
import database.conversations as conversations_db
import database.goals as goals_db
import database.task_intelligence_control as task_control_db
from models.chat_first import (
    CaptureLinkSpec,
    ChatFirstBlockSpec,
    ChatFirstBlockValidationReceipt,
    ChatFirstBlockValidationRequest,
    ChatFirstSubject,
    DeferralCreateRequest,
    DeferralReceipt,
    GoalLinkSpec,
    MaterializePromptsRequest,
    MaterializePromptsResponse,
    MemoryLinkSpec,
    TaskCardSpec,
    stable_block_id,
)
from utils.metrics import CHAT_FIRST_PROACTIVE_TOTAL
from utils.memory.memory_service import fetch_memory_dict
from utils.other import endpoints as auth
from utils.task_intelligence.chat_first_eligibility import resolve_chat_first_eligibility
from utils.task_intelligence.proactive_engine import (
    classify_cold_start_profile,
    persist_cold_start_intent,
    persist_daily_opener_intent,
)
from utils.task_intelligence.rollout import resolve_task_intelligence_for_user

router = APIRouter()
logger = logging.getLogger(__name__)


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


def _daily_opener_blocks(uid: str) -> tuple[list[ChatFirstBlockSpec], ChatFirstSubject | None]:
    """Build the closed deterministic opener from canonical task/goal facts."""

    focused_goal = goals_db.get_user_goal(uid)
    if not focused_goal:
        return [], None
    goal_id = focused_goal.get('id') or focused_goal.get('goal_id')
    if not isinstance(goal_id, str) or not goal_id:
        return [], None
    title = focused_goal.get('title')
    summary = title if isinstance(title, str) and title.strip() else 'Today’s focus'
    blocks: list[ChatFirstBlockSpec] = [GoalLinkSpec(type='goalLink', goal_id=goal_id, summary=summary[:200])]
    for task in action_items_db.get_action_items(uid, completed=False, limit=3):
        task_id = task.get('id')
        if isinstance(task_id, str) and task_id:
            blocks.append(TaskCardSpec(type='taskCard', task_id=task_id))
    return blocks, ChatFirstSubject(kind='goal', id=goal_id)


def _maybe_persist_daily_opener(uid: str, *, control_generation: int, now: datetime) -> None:
    """Best-effort lazy opener preparation; a failure never breaks Chat fetch."""

    try:
        if chat_first_intents_db.has_active_sparse_cold_start_sequence(
            uid,
            account_generation=control_generation,
        ):
            # A sparse sequence is itself the deterministic Chat tail. Keep a
            # later daily opener out of the server queue until that journaled
            # sequence ends, rather than letting it compete behind a question.
            return
        if chat_first_intents_db.has_cold_start_intent_created_on(
            uid,
            account_generation=control_generation,
            date_value=now.date(),
        ):
            # The cold-start turn is this UTC day's first opener. Do not make
            # a second card compete with the new Chat experience.
            return
        blocks, subject = _daily_opener_blocks(uid)
        if not blocks:
            return
        persist_daily_opener_intent(
            uid,
            blocks=blocks,
            subject=subject,
            expected_generation=control_generation,
            now=now,
            eligibility_resolver=_eligibility,
        )
    except Exception as exc:
        # No product content enters this log. A later foreground request may retry.
        logger.warning('chat_first_daily_opener_prepare_failed uid=%s error=%s', uid, type(exc).__name__)


def _maybe_persist_cold_start(uid: str, *, control_generation: int, now: datetime) -> None:
    """Persist the stable first-run intent only after capability admission."""

    try:
        # The documented decision table depends only on canonical existence,
        # not focus scoring or model inference. Fetch the richer opener shape
        # only when the deterministic counts admit it.
        canonical_goals = goals_db.get_user_goals(uid, limit=1)
        open_tasks = action_items_db.get_action_items(uid, completed=False, limit=1)
        profile = classify_cold_start_profile(
            canonical_goal_count=len(canonical_goals),
            open_task_count=len(open_tasks),
        )
        rich_blocks, rich_subject = _daily_opener_blocks(uid) if profile == 'rich' else ([], None)
        persist_cold_start_intent(
            uid,
            profile=profile,
            rich_blocks=rich_blocks,
            rich_subject=rich_subject,
            expected_generation=control_generation,
            now=now,
            eligibility_resolver=_eligibility,
        )
    except Exception as exc:
        # First-run preparation is retryable and must not turn an ordinary
        # foreground Chat fetch into an error or leak product content.
        logger.warning('chat_first_cold_start_prepare_failed uid=%s error=%s', uid, type(exc).__name__)


def _entity_available(uid: str, block: ChatFirstBlockSpec) -> bool:
    if isinstance(block, TaskCardSpec):
        task = action_items_db.get_action_item(uid, block.task_id)
        return bool(task and not task.get('is_locked', False))
    if isinstance(block, GoalLinkSpec):
        return goals_db.get_goal_by_id(uid, block.goal_id) is not None
    if isinstance(block, CaptureLinkSpec):
        capture = conversations_db.get_conversation(uid, block.conversation_id)
        return bool(capture and capture.get('source') == 'omi' and not capture.get('discarded', False))
    if isinstance(block, MemoryLinkSpec):
        try:
            return bool(fetch_memory_dict(uid, block.memory_id, db_client=getattr(db_client_module, 'db', None)))
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
    capture = conversations_db.get_conversation(uid, subject.id)
    return bool(capture and capture.get('source') == 'omi' and not capture.get('discarded', False))


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
    response_model=MaterializePromptsResponse,
    tags=['chat-first'],
)
def materialize_prompts(
    request: MaterializePromptsRequest,
    uid: str = Depends(auth.get_current_user_uid),
) -> MaterializePromptsResponse:
    """Fetch ready intents and accept kernel receipts; never writes a Chat row."""

    _require_materialization_capability(
        uid,
        owner_fence=request.owner_fence,
        control_generation=request.control_generation,
    )
    # A materialization request is meaningful only from the already-loaded
    # rich main-Chat transcript. This keeps cold start and all proactive
    # delivery inert for legacy, notch, and background callers.
    if not request.initial_page_loaded or not request.window_foreground:
        return MaterializePromptsResponse()
    now = datetime.now(timezone.utc)
    for receipt in request.receipts:
        try:
            chat_first_intents_db.acknowledge_materialization(
                uid,
                intent_id=receipt.intent_id,
                receipt_id=receipt.receipt_id,
                account_generation=request.control_generation,
                now=now,
            )
        except chat_first_intents_db.ChatFirstIntentGenerationMismatch as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='account generation mismatch') from exc
        except (
            chat_first_intents_db.ChatFirstIntentConflictError,
            chat_first_intents_db.ProactiveIntentNotReady,
        ) as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='invalid materialization receipt') from exc
        CHAT_FIRST_PROACTIVE_TOTAL.labels(event='kernel_receipt', source='materialization').inc()

    # The kernel can only emit this after it durably terminalizes the scripted
    # sequence in its canonical journal. This is an acknowledgement on the
    # existing sparse intent, not a client-controlled rollout/completion flag.
    for terminal_receipt in request.cold_start_sequence_terminal_receipts:
        try:
            chat_first_intents_db.acknowledge_sparse_cold_start_sequence_terminal(
                uid,
                sequence_id=terminal_receipt.sequence_id,
                receipt_id=terminal_receipt.receipt_id,
                terminal_state=terminal_receipt.terminal_state,
                account_generation=request.control_generation,
                now=now,
            )
        except chat_first_intents_db.ChatFirstIntentGenerationMismatch as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='account generation mismatch') from exc
        except (
            chat_first_intents_db.ChatFirstIntentConflictError,
            chat_first_intents_db.ProactiveIntentNotReady,
        ) as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail='invalid cold-start terminal receipt'
            ) from exc
        CHAT_FIRST_PROACTIVE_TOTAL.labels(event='cold_start_terminal_receipt', source='cold_start_sparse').inc()

    try:
        released = chat_first_intents_db.release_due_deferrals(
            uid,
            account_generation=request.control_generation,
            now=now,
        )
        for _intent in released:
            CHAT_FIRST_PROACTIVE_TOTAL.labels(event='deferral_released', source='deferral_reraise').inc()
        _maybe_persist_cold_start(uid, control_generation=request.control_generation, now=now)
        _maybe_persist_daily_opener(uid, control_generation=request.control_generation, now=now)
        intents = chat_first_intents_db.fetch_ready_intents(
            uid,
            account_generation=request.control_generation,
        )
    except chat_first_intents_db.ChatFirstIntentGenerationMismatch as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='account generation mismatch') from exc
    CHAT_FIRST_PROACTIVE_TOTAL.labels(event='fetch', source='materialization').inc()
    return MaterializePromptsResponse(intents=intents)


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
    try:
        receipt, created = chat_first_intents_db.record_deferral(
            uid,
            continuity_key=request.continuity_key,
            subject=request.subject,
            question=request.question,
            account_generation=request.control_generation,
            now=datetime.now(timezone.utc),
        )
    except chat_first_intents_db.ChatFirstIntentGenerationMismatch as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='account generation mismatch') from exc
    except chat_first_intents_db.ChatFirstIntentConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='deferral continuity conflict') from exc
    if created:
        CHAT_FIRST_PROACTIVE_TOTAL.labels(event='deferral_recorded', source='deferral_reraise').inc()
    return receipt
