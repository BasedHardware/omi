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
import database.conversation_finalization_jobs as finalization_jobs_db
import database.conversations as conversations_db
import database.goals as goals_db
from database.firestore_read_metrics import FirestoreReadSite
import database.task_intelligence_control as task_control_db
from models.chat_first import (
    CaptureLinkSpec,
    ConversationLinkSpec,
    ChatFirstBlockSpec,
    ChatFirstJournalBlockSpec,
    ChatFirstBlockValidationReceipt,
    ChatFirstBlockValidationRequest,
    ChatFirstSubject,
    DeferralCreateRequest,
    DeferralReceipt,
    GoalLinkSpec,
    LegacyMaterializePromptsResponse,
    LegacyProactiveIntent,
    MaterializableProactiveIntent,
    MaterializePromptsRequest,
    MaterializePromptsResponse,
    ProactiveMaterializationRejection,
    ProactiveMaterializationRejectionOutcome,
    ProactiveMaterializationReceiptOutcome,
    MemoryLinkSpec,
    MemoryReviewCardSpec,
    TaskCardSpec,
    stable_block_id,
)
from utils.metrics import CHAT_FIRST_PROACTIVE_TOTAL
from utils.chat_first_materialize_queue import drain_materialize_rejections, record_all_hard_reject_batch
from utils.durable_queue_policy import ProcessOutcome
from utils.log_sanitizer import sanitize_pii
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

_METRIC_REJECTION_CODES = frozenset({'invalid_intent', 'identity_conflict', 'kernel_materialization_failed'})


def _bounded_rejection_reason(code: str) -> str:
    return code if code in _METRIC_REJECTION_CODES else 'unknown'


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
        logger.warning('chat_first_daily_opener_prepare_failed uid=%s error=%s', sanitize_pii(uid), type(exc).__name__)


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
        logger.warning('chat_first_cold_start_prepare_failed uid=%s error=%s', sanitize_pii(uid), type(exc).__name__)


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
    """Fetch ready intents and accept kernel receipts; never writes a Chat row.

    Materialization acknowledgements retire an intent account-wide after one
    client consumes it. Canonical server-side Chat-row creation is separate
    follow-up work; until then the consuming client's kernel sync is the writer.
    """

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
    receipt_outcomes: list[ProactiveMaterializationReceiptOutcome] = []
    rejection_outcomes: list[ProactiveMaterializationRejectionOutcome] = []
    deferred_intent_ids: set[str] = set()

    def process_rejection(rejection: ProactiveMaterializationRejection) -> ProcessOutcome:
        try:
            rejected_intent, dead_letter_reason = chat_first_intents_db.record_materialization_rejection(
                uid,
                intent_id=rejection.intent_id,
                code=rejection.code,
                account_generation=request.control_generation,
                now=now,
            )
        except chat_first_intents_db.ChatFirstIntentGenerationMismatch as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='account generation mismatch') from exc
        except chat_first_intents_db.ChatFirstIntentDocumentGenerationMismatch:
            rejection_outcomes.append(
                ProactiveMaterializationRejectionOutcome(intent_id=rejection.intent_id, outcome='generation_mismatch')
            )
            return ProcessOutcome.reject('generation_mismatch', reason='generation_mismatch')
        except chat_first_intents_db.ChatFirstMalformedDocument:
            rejection_outcomes.append(
                ProactiveMaterializationRejectionOutcome(intent_id=rejection.intent_id, outcome='malformed')
            )
            return ProcessOutcome.reject('malformed', reason='malformed')
        except chat_first_intents_db.ProactiveIntentNotReady:
            rejection_outcomes.append(
                ProactiveMaterializationRejectionOutcome(intent_id=rejection.intent_id, outcome='absorbed')
            )
            return ProcessOutcome.ack()
        except Exception:
            logger.exception('materialization rejection processing failed')
            rejection_outcomes.append(
                ProactiveMaterializationRejectionOutcome(intent_id=rejection.intent_id, outcome='malformed')
            )
            return ProcessOutcome.reject('malformed', reason='malformed')
        if rejected_intent is None:
            rejection_outcomes.append(
                ProactiveMaterializationRejectionOutcome(intent_id=rejection.intent_id, outcome='missing')
            )
            return ProcessOutcome.ack()
        outcome = (
            'absorbed'
            if rejected_intent.delivery_state in {'delivered', 'dead_letter'} and dead_letter_reason is None
            else 'recorded'
        )
        rejection_outcomes.append(
            ProactiveMaterializationRejectionOutcome(intent_id=rejection.intent_id, outcome=outcome)
        )
        metric_code = _bounded_rejection_reason(rejection.code)
        CHAT_FIRST_PROACTIVE_TOTAL.labels(event='rejected', source=rejected_intent.source, reason=metric_code).inc()
        if dead_letter_reason is not None:
            CHAT_FIRST_PROACTIVE_TOTAL.labels(
                event='dead_letter',
                source=rejected_intent.source,
                reason=(
                    f'permanent_rejection:{metric_code}'
                    if dead_letter_reason.startswith('permanent_rejection:')
                    else dead_letter_reason
                ),
            ).inc()
        if outcome == 'recorded':
            return ProcessOutcome.reject(outcome, reason='hard_reject')
        return ProcessOutcome.ack()

    drain_materialize_rejections(request.rejections, process_rejection)
    record_all_hard_reject_batch(rejection_outcomes)

    for deferral in request.deferrals:
        try:
            deferred_intent = chat_first_intents_db.record_materialization_deferral(
                uid,
                intent_id=deferral.intent_id,
                account_generation=request.control_generation,
                now=now,
            )
            deferred_intent_ids.add(deferral.intent_id)
            if deferred_intent is not None and deferred_intent.dead_letter_reason == 'deferred_beyond_budget':
                CHAT_FIRST_PROACTIVE_TOTAL.labels(
                    event='dead_letter', source=deferred_intent.source, reason='deferred_beyond_budget'
                ).inc()
        except (
            chat_first_intents_db.ChatFirstIntentDocumentGenerationMismatch,
            chat_first_intents_db.ChatFirstMalformedDocument,
            chat_first_intents_db.ProactiveIntentNotReady,
        ):
            # A stale device's explicit deferral must not poison the next batch.
            continue
        except Exception:
            logger.exception('materialization deferral processing failed')
            continue

    for receipt in request.receipts:
        try:
            delivered_intent = chat_first_intents_db.acknowledge_materialization(
                uid,
                intent_id=receipt.intent_id,
                receipt_id=receipt.receipt_id,
                account_generation=request.control_generation,
                now=now,
            )
            for block in delivered_intent.blocks:
                if isinstance(block, ConversationLinkSpec):
                    try:
                        finalization_jobs_db.mark_meeting_receipt_materialized(
                            uid,
                            block.conversation_id,
                            delivered_intent.intent_id,
                            materialized_at=now,
                        )
                    except Exception:
                        logger.exception('meeting receipt materialization projection failed')
            outcome = 'acknowledged' if delivered_intent.delivery_state == 'delivered' else 'already_terminal'
        except (
            chat_first_intents_db.ChatFirstIntentGenerationMismatch,
            chat_first_intents_db.ChatFirstIntentDocumentGenerationMismatch,
        ):
            outcome = 'generation_mismatch'
        except chat_first_intents_db.ChatFirstIntentConflictError:
            outcome = 'conflict'
        except chat_first_intents_db.ProactiveIntentNotReady:
            outcome = 'missing'
        except Exception:
            logger.exception('materialization receipt processing failed')
            outcome = 'conflict'
        receipt_outcomes.append(ProactiveMaterializationReceiptOutcome(intent_id=receipt.intent_id, outcome=outcome))
        CHAT_FIRST_PROACTIVE_TOTAL.labels(event='kernel_receipt', source='materialization', reason=outcome).inc()
        if outcome in {'conflict', 'generation_mismatch'}:
            logger.warning(
                'materialization receipt outcome=%s intent_id=%s receipt_id=%s',
                outcome,
                receipt.intent_id,
                receipt.receipt_id,
            )

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
            outcome = 'acknowledged'
        except chat_first_intents_db.ChatFirstIntentGenerationMismatch:
            outcome = 'generation_mismatch'
        except chat_first_intents_db.ChatFirstIntentConflictError:
            outcome = 'conflict'
        except chat_first_intents_db.ProactiveIntentNotReady:
            outcome = 'missing'
        except Exception:
            logger.exception('cold-start terminal receipt processing failed')
            outcome = 'conflict'
        receipt_outcomes.append(
            ProactiveMaterializationReceiptOutcome(intent_id=terminal_receipt.sequence_id, outcome=outcome)
        )
        CHAT_FIRST_PROACTIVE_TOTAL.labels(
            event='cold_start_terminal_receipt', source='cold_start_sparse', reason='none'
        ).inc()

    try:
        release_batch = chat_first_intents_db.release_due_deferrals(
            uid,
            account_generation=request.control_generation,
            now=now,
        )
        for _intent in release_batch.intents:
            CHAT_FIRST_PROACTIVE_TOTAL.labels(event='deferral_released', source='deferral_reraise', reason='none').inc()
        for _ in range(release_batch.malformed_count):
            CHAT_FIRST_PROACTIVE_TOTAL.labels(
                event='deferral_malformed', source='deferral_reraise', reason='malformed_document'
            ).inc()
        _maybe_persist_cold_start(uid, control_generation=request.control_generation, now=now)
        _maybe_persist_daily_opener(uid, control_generation=request.control_generation, now=now)
        batch = chat_first_intents_db.fetch_ready_intent_batch(
            uid,
            account_generation=request.control_generation,
            exclude_block_types=exclude_block_types,
            deferred_intent_ids=deferred_intent_ids,
            now=now,
        )
    except chat_first_intents_db.ChatFirstIntentGenerationMismatch as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail='account generation mismatch') from exc
    for lifecycle_event in batch.lifecycle_events:
        CHAT_FIRST_PROACTIVE_TOTAL.labels(
            event=lifecycle_event.event,
            source=lifecycle_event.source,
            reason=lifecycle_event.reason,
        ).inc()
    if batch.stalled_source is not None:
        CHAT_FIRST_PROACTIVE_TOTAL.labels(
            event='stalled', source=batch.stalled_source, reason='ready_older_than_24h'
        ).inc()
    CHAT_FIRST_PROACTIVE_TOTAL.labels(event='fetch', source='materialization', reason='none').inc()
    return MaterializePromptsResponse(
        intents=[
            MaterializableProactiveIntent.model_validate(
                intent.model_dump(exclude={'first_deferred_at', 'last_deferral_at', 'requeue_count'})
            )
            for intent in batch.intents
        ],
        receipt_outcomes=receipt_outcomes,
        rejection_outcomes=rejection_outcomes,
    )


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
        CHAT_FIRST_PROACTIVE_TOTAL.labels(event='deferral_recorded', source='deferral_reraise', reason='none').inc()
    return receipt
