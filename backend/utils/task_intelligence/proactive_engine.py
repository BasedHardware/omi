"""Post-commit, fail-closed Chat-first proactive-intent orchestration."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Literal, Protocol

import database.chat_first_intents as intent_db
from models.chat_first import CaptureLinkSpec, ChatFirstBlockSpec, ChatFirstSubject, ProactiveIntent
from utils.metrics import CHAT_FIRST_PROACTIVE_TOTAL
from utils.task_intelligence.chat_first_eligibility import ChatFirstEligibility, resolve_chat_first_eligibility

logger = logging.getLogger(__name__)

WakeTriggerKind = Literal['task_changed', 'goal_changed', 'capture_finalized', 'deferral_due']


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
    outcome: Literal['disabled', 'stale', 'budget_exhausted', 'already_pending', 'declined', 'created', 'no_candidate']
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
                logger.warning('chat_first_proactive_admission_release_failed uid=%s error=%s', uid, type(exc).__name__)


def run_post_commit_wake(
    uid: str,
    trigger: ProactiveWakeTrigger,
    **kwargs,
) -> ProactiveWakeResult:
    """Failure-isolated convenience seam for background mutation owners."""

    try:
        return wake_after_commit(uid, trigger, **kwargs)
    except Exception as exc:
        logger.warning('chat_first_proactive_wake_failed uid=%s error=%s', uid, type(exc).__name__)
        _meter('wake_failed', trigger.kind)
        return ProactiveWakeResult(outcome='declined')


def persist_capture_arrival_intent(
    uid: str,
    *,
    conversation_id: str,
    summary: str,
    expected_generation: int | None = None,
    now: datetime | None = None,
    eligibility_resolver: Callable[[str], ChatFirstEligibility] = resolve_chat_first_eligibility,
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
            return None
        intent, created = intent_db.create_intent(
            uid,
            source='capture_arrival',
            continuity_key=f'capture:{conversation_id}',
            subject=ChatFirstSubject(kind='capture', id=conversation_id),
            blocks=[CaptureLinkSpec(type='captureLink', conversation_id=conversation_id, summary=bounded_summary)],
            account_generation=eligibility.account_generation,
            now=resolved_now,
        )
        if created:
            _meter('intent_created', 'capture_arrival')
        return intent
    except Exception as exc:
        logger.warning('chat_first_capture_arrival_intent_failed uid=%s error=%s', uid, type(exc).__name__)
        return None


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
    'ProactiveCandidate',
    'ProactiveJudge',
    'ProactiveSelection',
    'ProactiveWakeResult',
    'ProactiveWakeTrigger',
    'persist_capture_arrival_intent',
    'persist_daily_opener_intent',
    'run_post_commit_wake',
    'wake_after_commit',
]
