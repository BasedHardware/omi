"""Post-commit, fail-closed Chat-first proactive-intent orchestration."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal, Protocol

import database.chat_first_intents as intent_db
from models.chat_first import (
    CaptureLinkSpec,
    ConversationLinkSpec,
    ConversationLinkActionItemSpec,
    ChatFirstBlockSpec,
    ChatFirstSubject,
    ColdStartSequence,
    ProactiveIntent,
    QuestionCardSpec,
    QuestionOption,
)
from utils.conversations.meeting_treatment import is_meeting_treatment_eligible
from utils.log_sanitizer import sanitize_pii
from utils.metrics import CHAT_FIRST_PROACTIVE_TOTAL
from utils.task_intelligence.chat_first_eligibility import ChatFirstEligibility, resolve_chat_first_eligibility

logger = logging.getLogger(__name__)

WakeTriggerKind = Literal['task_changed', 'goal_changed', 'capture_finalized', 'deferral_due']
ColdStartProfile = Literal['rich', 'sparse']


def classify_cold_start_profile(*, canonical_goal_count: int, open_task_count: int) -> ColdStartProfile:
    """Return ``rich`` only when canonical goals and open tasks both exist.

    This intentionally is the entire first-run decision table: it has no
    model call, ranking heuristic, or dependency on legacy onboarding state.
    """

    return 'rich' if canonical_goal_count >= 1 and open_task_count >= 1 else 'sparse'


def cold_start_sparse_question(*, sequence_id: str) -> QuestionCardSpec:
    """Return sparse cold-start script step one as a typed server intent."""

    return QuestionCardSpec(
        type='questionCard',
        question_id=f'{sequence_id}:step:1',
        text="What's the main outcome you're working toward right now? You can choose one or tell me in your own words.",
        subject=ChatFirstSubject(kind='cold_start', id=sequence_id),
        cold_start_sequence=ColdStartSequence(sequence_id=sequence_id, step=1),
        options=[
            QuestionOption(
                option_id=f'{sequence_id}:outcome:progress',
                label='Make progress',
                prepared_answer='I want to make progress on something important.',
            ),
            QuestionOption(
                option_id=f'{sequence_id}:outcome:organize',
                label='Get organized',
                prepared_answer='I want to get organized and make a clear plan.',
            ),
            QuestionOption(
                option_id=f'{sequence_id}:outcome:decide',
                label='Decide what matters',
                prepared_answer='I want help deciding what to focus on next.',
            ),
        ],
    )


@dataclass(frozen=True)
class ProactiveWakeTrigger:
    """Content-free post-commit trigger. It cannot be a Chat transcript event."""

    kind: WakeTriggerKind
    subject: ChatFirstSubject
    continuity_key: str


@dataclass(frozen=True)
class ProactiveCandidate:
    """Deterministic shortlist member passed to an injectable judgment seam."""

    subject: ChatFirstSubject
    trigger_kind: WakeTriggerKind
    continuity_key: str


@dataclass(frozen=True)
class ProactiveSelection:
    """A structured judgment result. Empty remains the default action."""

    blocks: list[ChatFirstBlockSpec]


class ProactiveJudge(Protocol):
    model_version: str

    def judge(self, candidates: list[ProactiveCandidate]) -> ProactiveSelection | None: ...


class EmptyProactiveJudge:
    """Safe default until a production structured judge is intentionally bound."""

    model_version = 'empty-default.v1'

    def judge(self, candidates: list[ProactiveCandidate]) -> ProactiveSelection | None:
        return None


@dataclass(frozen=True)
class ProactiveWakeResult:
    outcome: Literal[
        'disabled',
        'stale',
        'budget_exhausted',
        'already_pending',
        'declined',
        'created',
        'no_candidate',
        'suppressed_by_cold_start',
    ]
    intent: ProactiveIntent | None = None


def wake_after_commit(
    uid: str,
    trigger: ProactiveWakeTrigger,
    *,
    expected_generation: int | None = None,
    judge: ProactiveJudge | None = None,
    now: datetime | None = None,
    eligibility_resolver: Callable[[str], ChatFirstEligibility] = resolve_chat_first_eligibility,
) -> ProactiveWakeResult:
    """Create an optional agent-tier intent without affecting the source mutation.

    This is synchronous by design so the caller can choose the owning background
    executor. It never mutates the source task, goal, capture, or any chat row.
    The wrapper below isolates all failures after the source transaction commits.
    """

    resolved_now = now or datetime.now(timezone.utc)
    eligibility = eligibility_resolver(uid)
    if not eligibility.enabled:
        return ProactiveWakeResult(outcome='disabled')
    if expected_generation is not None and eligibility.account_generation != expected_generation:
        return ProactiveWakeResult(outcome='stale')
    assert eligibility.account_generation is not None
    generation = eligibility.account_generation
    _meter('wake', trigger.kind)

    # A due deferral is deterministic. Release it before agent judgment, but
    # never recurse into this wake path from the release/receipt operation.
    released = intent_db.release_due_deferrals(
        uid,
        account_generation=generation,
        now=resolved_now,
        subject=trigger.subject,
    )
    for _intent in released:
        _meter('deferral_released', 'deferral_reraise')

    if trigger.kind not in {'task_changed', 'goal_changed'}:
        return ProactiveWakeResult(outcome='no_candidate')

    # Sparse cold start is an ordered local-journal interaction. Its terminal
    # receipt lives on the original intent, so agent judgment is quiet only
    # while that sequence is active—not for the entire account generation.
    if intent_db.has_active_sparse_cold_start_sequence(uid, account_generation=generation):
        return ProactiveWakeResult(outcome='suppressed_by_cold_start')

    try:
        admission = intent_db.admit_agent_judgment(
            uid,
            continuity_key=trigger.continuity_key,
            subject=trigger.subject,
            account_generation=generation,
            now=resolved_now,
        )
    except intent_db.ProactiveBudgetExhausted:
        # The admission transaction is intentionally before the provider call.
        _meter('budget_short_circuit', 'agent_judgment')
        return ProactiveWakeResult(outcome='budget_exhausted')
    if admission.existing_intent is not None:
        return ProactiveWakeResult(outcome='created', intent=admission.existing_intent)
    if not admission.newly_reserved:
        return ProactiveWakeResult(outcome='already_pending')

    admission_resolved = False
    try:
        candidates = _deterministic_shortlist(trigger)
        if not candidates:
            return ProactiveWakeResult(outcome='no_candidate')

        resolved_judge = judge or EmptyProactiveJudge()
        _meter('judgment_called', 'agent_judgment')
        selection = resolved_judge.judge(candidates)
        if (
            selection is None
            or not selection.blocks
            or not any(block.type == 'questionCard' for block in selection.blocks)
            # Meeting receipts are server-finalized capture facts. Agent/tool
            # output must not be able to mint a conversationLink for an
            # ambient or otherwise unrelated conversation.
            or any(block.type == 'conversationLink' for block in selection.blocks)
        ):
            _meter('judgment_declined', 'agent_judgment')
            return ProactiveWakeResult(outcome='declined')

        intent, created = intent_db.create_intent(
            uid,
            source='agent_judgment',
            continuity_key=trigger.continuity_key,
            subject=trigger.subject,
            blocks=selection.blocks,
            account_generation=generation,
            now=resolved_now,
        )
        admission_resolved = True
        if created:
            _meter('intent_created', 'agent_judgment')
        return ProactiveWakeResult(outcome='created', intent=intent)
    finally:
        if not admission_resolved:
            try:
                intent_db.release_agent_judgment_admission(
                    uid,
                    continuity_key=trigger.continuity_key,
                    account_generation=generation,
                    now=resolved_now,
                )
            except Exception as exc:
                # The source mutation has already committed. Preserve its result;
                # control-generation rollover also makes the old reservation inert.
                logger.warning(
                    'chat_first_proactive_admission_release_failed uid=%s error=%s',
                    sanitize_pii(uid),
                    type(exc).__name__,
                )


def run_post_commit_wake(
    uid: str,
    trigger: ProactiveWakeTrigger,
    **kwargs,
) -> ProactiveWakeResult:
    """Failure-isolated convenience seam for background mutation owners."""

    try:
        return wake_after_commit(uid, trigger, **kwargs)
    except Exception as exc:
        logger.warning('chat_first_proactive_wake_failed uid=%s error=%s', sanitize_pii(uid), type(exc).__name__)
        _meter('wake_failed', trigger.kind)
        return ProactiveWakeResult(outcome='declined')


def run_task_changed_wake(uid: str, *, task_id: str, mutation_key: object) -> ProactiveWakeResult:
    """Wake the proactive engine after an authoritative task commit."""

    return run_post_commit_wake(
        uid,
        ProactiveWakeTrigger(
            kind='task_changed',
            subject=ChatFirstSubject(kind='task', id=task_id),
            continuity_key=f'task:{task_id}:{mutation_key}',
        ),
    )


def run_goal_changed_wake(uid: str, *, goal_id: str, mutation_key: object) -> ProactiveWakeResult:
    """Wake the proactive engine after an authoritative goal commit."""

    return run_post_commit_wake(
        uid,
        ProactiveWakeTrigger(
            kind='goal_changed',
            subject=ChatFirstSubject(kind='goal', id=goal_id),
            continuity_key=f'goal:{goal_id}:{mutation_key}',
        ),
    )


def recommended_meeting_action_items(structured: object) -> list[ConversationLinkActionItemSpec]:
    """Project the user's open meeting commitments into the durable Chat receipt."""

    action_items = (
        structured.get('action_items', []) if isinstance(structured, dict) else getattr(structured, 'action_items', [])
    )
    recommendations: list[ConversationLinkActionItemSpec] = []
    for item in action_items or []:
        if isinstance(item, dict):
            value = item
        elif hasattr(item, '__dict__'):
            value = vars(item)
        else:
            continue
        if value.get('capture_owner') != 'user' or value.get('completed', False) or value.get('deleted', False):
            continue
        description = str(value.get('description') or '').strip()
        if not description:
            continue
        task_id = value.get('target_task_id')
        recommendations.append(
            ConversationLinkActionItemSpec(
                description=description[:300],
                task_id=task_id if isinstance(task_id, str) and task_id else None,
            )
        )
        if len(recommendations) == 8:
            break
    return recommendations


def persist_capture_arrival_intent(
    uid: str,
    *,
    conversation_id: str,
    summary: str,
    expected_generation: int | None = None,
    now: datetime | None = None,
    eligibility_resolver: Callable[[str], ChatFirstEligibility] = resolve_chat_first_eligibility,
    is_desktop_meeting: bool = False,
    recommended_action_items: list[ConversationLinkActionItemSpec] | None = None,
) -> ProactiveIntent | None:
    """Persist the deterministic capture receipt without calling an LLM.

    Capture finalization has already committed by the time this hook runs. A
    malformed title or unavailable intent store therefore must not turn a
    successful capture into a failed source operation.
    """

    resolved_now = now or datetime.now(timezone.utc)
    try:
        eligibility = eligibility_resolver(uid)
        if not eligibility.enabled or (
            expected_generation is not None and eligibility.account_generation != expected_generation
        ):
            return None
        assert eligibility.account_generation is not None
        bounded_summary = summary.strip()[:200]
        if not bounded_summary:
            if not is_desktop_meeting:
                return None
            bounded_summary = 'Your meeting notes are ready.'
        block: ChatFirstBlockSpec
        if is_desktop_meeting:
            block = ConversationLinkSpec(
                type='conversationLink',
                conversation_id=conversation_id,
                summary=bounded_summary,
                recommended_action_items=recommended_action_items or [],
            )
        else:
            block = CaptureLinkSpec(type='captureLink', conversation_id=conversation_id, summary=bounded_summary)
        intent, created = intent_db.create_intent(
            uid,
            source='capture_arrival',
            continuity_key=f'capture:{conversation_id}',
            subject=ChatFirstSubject(kind='capture', id=conversation_id),
            blocks=[block],
            account_generation=eligibility.account_generation,
            now=resolved_now,
        )
        if created:
            _meter('intent_created', 'capture_arrival')
        return intent
    except Exception as exc:
        logger.warning(
            'chat_first_capture_arrival_intent_failed uid=%s error=%s',
            sanitize_pii(uid),
            type(exc).__name__,
        )
        return None


def persist_desktop_meeting_arrival(uid: str, conversation) -> None:
    """Repair-safe adapter from a completed desktop conversation to its exact Chat receipt."""

    status = conversation.get('status') if isinstance(conversation, dict) else conversation.status
    status = getattr(status, 'value', status)
    if status != 'completed' or not is_meeting_treatment_eligible(conversation):
        return
    conversation_id = conversation['id'] if isinstance(conversation, dict) else conversation.id
    structured = (conversation.get('structured') if isinstance(conversation, dict) else conversation.structured) or {}
    title = structured.get('title') if isinstance(structured, dict) else structured.title
    overview = structured.get('overview') if isinstance(structured, dict) else structured.overview
    persist_capture_arrival_intent(
        uid,
        conversation_id=conversation_id,
        summary=title or overview or '',
        is_desktop_meeting=True,
        recommended_action_items=recommended_meeting_action_items(structured),
    )


def persist_desktop_meeting_arrival_best_effort(uid: str, conversation) -> None:
    """Failure-isolate the repair adapter from conversation creation/retry."""
    try:
        persist_desktop_meeting_arrival(uid, conversation)
    except Exception as exc:
        logger.warning(
            'desktop_meeting_arrival_adapter_failed uid=%s error=%s',
            sanitize_pii(uid),
            type(exc).__name__,
        )


def persist_daily_opener_intent(
    uid: str,
    *,
    blocks: list[ChatFirstBlockSpec],
    subject: ChatFirstSubject | None,
    expected_generation: int | None = None,
    now: datetime | None = None,
    eligibility_resolver: Callable[[str], ChatFirstEligibility] = resolve_chat_first_eligibility,
) -> ProactiveIntent | None:
    """Persist the once-per-UTC-day deterministic opener supplied by the caller."""

    resolved_now = now or datetime.now(timezone.utc)
    eligibility = eligibility_resolver(uid)
    if not eligibility.enabled or (
        expected_generation is not None and eligibility.account_generation != expected_generation
    ):
        return None
    assert eligibility.account_generation is not None
    intent, created = intent_db.create_intent(
        uid,
        source='daily_opener',
        continuity_key=f'daily:{resolved_now.date().isoformat()}',
        subject=subject,
        blocks=blocks,
        account_generation=eligibility.account_generation,
        now=resolved_now,
    )
    if created:
        _meter('intent_created', 'daily_opener')
    return intent


def persist_cold_start_intent(
    uid: str,
    *,
    profile: ColdStartProfile,
    rich_blocks: list[ChatFirstBlockSpec],
    rich_subject: ChatFirstSubject | None,
    expected_generation: int | None = None,
    now: datetime | None = None,
    eligibility_resolver: Callable[[str], ChatFirstEligibility] = resolve_chat_first_eligibility,
) -> ProactiveIntent | None:
    """Create the one deterministic, generation-bound first-run intent.

    The intent store picks the first winning rich/sparse payload under its
    transaction and returns it verbatim thereafter. This function never
    writes a visible Chat row; only the desktop kernel can do that.
    """

    resolved_now = now or datetime.now(timezone.utc)
    eligibility = eligibility_resolver(uid)
    if not eligibility.enabled or (
        expected_generation is not None and eligibility.account_generation != expected_generation
    ):
        return None
    assert eligibility.account_generation is not None
    generation = eligibility.account_generation
    sequence_id = f'cold-start:{generation}'
    if profile == 'rich':
        if not rich_blocks or rich_subject is None:
            return None
        source: Literal['cold_start_rich', 'cold_start_sparse'] = 'cold_start_rich'
        blocks = rich_blocks
        subject = rich_subject
    else:
        source = 'cold_start_sparse'
        blocks: list[ChatFirstBlockSpec] = [cold_start_sparse_question(sequence_id=sequence_id)]
        subject = ChatFirstSubject(kind='cold_start', id=sequence_id)
    intent, created = intent_db.get_or_create_cold_start_intent(
        uid,
        source=source,
        continuity_key=sequence_id,
        subject=subject,
        blocks=blocks,
        account_generation=generation,
        now=resolved_now,
    )
    if created:
        _meter('intent_created', source)
    return intent


def _deterministic_shortlist(trigger: ProactiveWakeTrigger) -> list[ProactiveCandidate]:
    return [
        ProactiveCandidate(
            subject=trigger.subject,
            trigger_kind=trigger.kind,
            continuity_key=trigger.continuity_key,
        )
    ]


def _meter(event: str, source: str) -> None:
    """Emit only bounded shape labels; never content, prompts, or subject IDs."""

    CHAT_FIRST_PROACTIVE_TOTAL.labels(event=event, source=source).inc()


__all__ = [
    'EmptyProactiveJudge',
    'ColdStartProfile',
    'ProactiveCandidate',
    'ProactiveJudge',
    'ProactiveSelection',
    'ProactiveWakeResult',
    'ProactiveWakeTrigger',
    'persist_capture_arrival_intent',
    'classify_cold_start_profile',
    'cold_start_sparse_question',
    'persist_cold_start_intent',
    'persist_daily_opener_intent',
    'run_goal_changed_wake',
    'run_post_commit_wake',
    'run_task_changed_wake',
    'wake_after_commit',
]
