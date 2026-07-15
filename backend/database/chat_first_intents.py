"""Durable Chat-first proactive intent state, separate from the chat journal."""

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from google.cloud import firestore

from database._client import get_firestore_client
from database.read_boundary import MalformedDocError, parse_snapshot_strict
from models.chat_first import (
    ChatFirstBlockSpec,
    ChatFirstSubject,
    ColdStartSequenceTerminalState,
    DeferralReceipt,
    ProactiveBudgetState,
    ProactiveDeferral,
    ProactiveIntent,
    ProactiveIntentSource,
    QuestionCardSpec,
)
from models.proactive_budget import account_materialization, budget_allows, normalized_budget_state, reserve_budget
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode

INTENTS_COLLECTION = 'chat_first_proactive_intents'
DEFERRALS_COLLECTION = 'chat_first_deferrals'
STATE_COLLECTION = 'chat_first_proactive_state'
BUDGET_DOCUMENT = 'budget'
_DEFERRAL_DUE_AFTER = timedelta(hours=24)


class ChatFirstIntentStoreError(RuntimeError):
    """Base class for closed intent-store failures."""


class ChatFirstIntentGenerationMismatch(ChatFirstIntentStoreError):
    pass


class ChatFirstIntentConflictError(ChatFirstIntentStoreError):
    pass


class ProactiveBudgetExhausted(ChatFirstIntentStoreError):
    pass


class ProactiveIntentNotReady(ChatFirstIntentStoreError):
    pass


@dataclass(frozen=True)
class AgentJudgmentAdmission:
    """The one durable admission result that may precede a judge call.

    A newly acquired reservation is the cost gate for a single judge call. An
    already-pending reservation deliberately is *not* another admission: two
    concurrent post-commit wakes for the same continuity key must not spend two
    model calls while racing to create one intent.
    """

    existing_intent: ProactiveIntent | None
    newly_reserved: bool


def _db(firestore_client: Any = None) -> Any:
    return firestore_client or get_firestore_client()


def _user_ref(uid: str, *, firestore_client: Any = None):
    return _db(firestore_client).collection('users').document(uid)


def _control_ref(uid: str, *, firestore_client: Any = None):
    return _user_ref(uid, firestore_client=firestore_client).collection('task_intelligence_control').document('state')


def _intent_ref(uid: str, intent_id: str, *, firestore_client: Any = None):
    return _user_ref(uid, firestore_client=firestore_client).collection(INTENTS_COLLECTION).document(intent_id)


def _deferral_ref(uid: str, deferral_id: str, *, firestore_client: Any = None):
    return _user_ref(uid, firestore_client=firestore_client).collection(DEFERRALS_COLLECTION).document(deferral_id)


def _budget_ref(uid: str, *, firestore_client: Any = None):
    return _user_ref(uid, firestore_client=firestore_client).collection(STATE_COLLECTION).document(BUDGET_DOCUMENT)


def _stable_id(prefix: str, *parts: object) -> str:
    raw = '\x1f'.join(str(part) for part in parts).encode('utf-8')
    return f'{prefix}_{hashlib.sha256(raw).hexdigest()[:32]}'


def _require_control(snapshot: Any, account_generation: int) -> None:
    control = TaskWorkflowControl()
    if snapshot.exists:
        try:
            control = parse_snapshot_strict(TaskWorkflowControl, snapshot)
        except MalformedDocError as error:
            raise ChatFirstIntentGenerationMismatch('chat-first capability state is malformed') from error
    if (
        control.workflow_mode != TaskWorkflowMode.read
        or control.account_generation != account_generation
        or not control.chat_first_ui_enabled
    ):
        raise ChatFirstIntentGenerationMismatch('chat-first capability changed')


def _budget_from_snapshot(snapshot: Any, *, account_generation: int, now: datetime) -> ProactiveBudgetState:
    if not snapshot.exists:
        return ProactiveBudgetState(account_generation=account_generation)
    try:
        state = parse_snapshot_strict(ProactiveBudgetState, snapshot)
    except MalformedDocError as error:
        raise ChatFirstIntentGenerationMismatch('chat-first proactive budget state is malformed') from error
    if state.account_generation != account_generation:
        return ProactiveBudgetState(account_generation=account_generation)
    return normalized_budget_state(state, now=now)


def _intent_from_snapshot(snapshot: Any) -> ProactiveIntent:
    """Load correctness-critical proactive state without treating corruption as absent."""

    try:
        return parse_snapshot_strict(ProactiveIntent, snapshot)
    except MalformedDocError as error:
        raise ChatFirstIntentGenerationMismatch('chat-first proactive intent is malformed') from error


def _deferral_from_snapshot(snapshot: Any) -> ProactiveDeferral:
    """Load correctness-critical deferred-question state without a fallback."""

    try:
        return parse_snapshot_strict(ProactiveDeferral, snapshot)
    except MalformedDocError as error:
        raise ChatFirstIntentGenerationMismatch('chat-first deferral is malformed') from error


def _require_current_control(uid: str, *, account_generation: int, firestore_client: Any) -> None:
    """Fence read-only entry points before they inspect feature-specific rows."""

    _require_control(_control_ref(uid, firestore_client=firestore_client).get(), account_generation)


def _intent_payload(intent: ProactiveIntent) -> dict[str, Any]:
    return intent.model_dump(mode='python')


def get_budget_state(
    uid: str,
    *,
    account_generation: int,
    now: datetime,
    firestore_client: Any = None,
) -> ProactiveBudgetState:
    """Read bounded accounting only after the caller passed cohort eligibility."""

    client = _db(firestore_client)
    _require_current_control(uid, account_generation=account_generation, firestore_client=client)
    snapshot = _budget_ref(uid, firestore_client=client).get()
    return _budget_from_snapshot(snapshot, account_generation=account_generation, now=now)


def admit_agent_judgment(
    uid: str,
    *,
    continuity_key: str,
    subject: ChatFirstSubject,
    account_generation: int,
    now: datetime,
    firestore_client: Any = None,
) -> AgentJudgmentAdmission:
    """Atomically reserve one agent-tier evaluation before any provider call.

    This is intentionally separate from ``create_intent``. It makes the
    budget a genuine model-cost gate under concurrent wakes while allowing a
    declined or failed judgment to release its reservation without consuming a
    materialized turn.
    """

    client = _db(firestore_client)
    intent_id = _stable_id('cfi', uid, account_generation, 'agent_judgment', continuity_key)
    intent_ref = _intent_ref(uid, intent_id, firestore_client=client)
    budget_ref = _budget_ref(uid, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> AgentJudgmentAdmission:
        control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
        _require_control(control_snapshot, account_generation)
        existing_snapshot = intent_ref.get(transaction=write_transaction)
        if existing_snapshot.exists:
            existing = _intent_from_snapshot(existing_snapshot)
            if (
                existing.account_generation != account_generation
                or existing.source != 'agent_judgment'
                or existing.continuity_key != continuity_key
                or existing.subject != subject
            ):
                raise ChatFirstIntentConflictError('agent judgment continuity key was reused')
            return AgentJudgmentAdmission(existing_intent=existing, newly_reserved=False)

        budget_snapshot = budget_ref.get(transaction=write_transaction)
        budget = _budget_from_snapshot(budget_snapshot, account_generation=account_generation, now=now)
        if any(reservation.intent_id == intent_id for reservation in budget.reservations):
            return AgentJudgmentAdmission(existing_intent=None, newly_reserved=False)
        try:
            reserved = reserve_budget(budget, intent_id=intent_id, now=now)
        except ValueError as exc:
            raise ProactiveBudgetExhausted('proactive turn budget exhausted') from exc
        write_transaction.set(budget_ref, reserved.model_dump(mode='python'))
        return AgentJudgmentAdmission(existing_intent=None, newly_reserved=True)

    return apply(transaction)


def release_agent_judgment_admission(
    uid: str,
    *,
    continuity_key: str,
    account_generation: int,
    now: datetime,
    firestore_client: Any = None,
) -> None:
    """Release an unused pre-judge reservation without touching an intent.

    An existing intent owns its reservation until the local kernel receipt. A
    retry after a provider failure or empty selection therefore remains safe
    and idempotent.
    """

    client = _db(firestore_client)
    intent_id = _stable_id('cfi', uid, account_generation, 'agent_judgment', continuity_key)
    intent_ref = _intent_ref(uid, intent_id, firestore_client=client)
    budget_ref = _budget_ref(uid, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> None:
        control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
        _require_control(control_snapshot, account_generation)
        intent_snapshot = intent_ref.get(transaction=write_transaction)
        budget_snapshot = budget_ref.get(transaction=write_transaction)
        if intent_snapshot.exists:
            return
        budget = _budget_from_snapshot(budget_snapshot, account_generation=account_generation, now=now)
        reservations = [reservation for reservation in budget.reservations if reservation.intent_id != intent_id]
        if len(reservations) == len(budget.reservations):
            return
        write_transaction.set(
            budget_ref, budget.model_copy(update={'reservations': reservations}).model_dump(mode='python')
        )

    apply(transaction)


def create_intent(
    uid: str,
    *,
    source: ProactiveIntentSource,
    continuity_key: str,
    subject: ChatFirstSubject | None,
    blocks: list[ChatFirstBlockSpec],
    account_generation: int,
    now: datetime,
    firestore_client: Any = None,
) -> tuple[ProactiveIntent, bool]:
    """Idempotently persist an intent and atomically reserve agent-turn budget."""

    client = _db(firestore_client)
    intent_id = _stable_id('cfi', uid, account_generation, source, continuity_key)
    intent = ProactiveIntent(
        intent_id=intent_id,
        continuity_key=continuity_key,
        account_generation=account_generation,
        source=source,
        subject=subject,
        blocks=blocks,
        created_at=now,
    )
    intent_ref = _intent_ref(uid, intent_id, firestore_client=client)
    budget_ref = _budget_ref(uid, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> tuple[ProactiveIntent, bool]:
        control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
        _require_control(control_snapshot, account_generation)
        existing_snapshot = intent_ref.get(transaction=write_transaction)
        budget_snapshot = (
            budget_ref.get(transaction=write_transaction)
            if intent.consumes_turn_budget and not existing_snapshot.exists
            else None
        )
        if existing_snapshot.exists:
            existing = _intent_from_snapshot(existing_snapshot)
            if (
                existing.account_generation != account_generation
                or existing.source != source
                or existing.continuity_key != continuity_key
                or existing.subject != subject
                or existing.blocks != blocks
            ):
                raise ChatFirstIntentConflictError('intent continuity key was reused with different content')
            return existing, False

        reserved: ProactiveBudgetState | None = None
        if intent.consumes_turn_budget:
            assert budget_snapshot is not None
            budget = _budget_from_snapshot(budget_snapshot, account_generation=account_generation, now=now)
            try:
                reserved = reserve_budget(budget, intent_id=intent_id, now=now)
            except ValueError as exc:
                raise ProactiveBudgetExhausted('proactive turn budget exhausted') from exc
        write_transaction.set(intent_ref, _intent_payload(intent))
        if reserved is not None:
            write_transaction.set(budget_ref, reserved.model_dump(mode='python'))
        return intent, True

    return apply(transaction)


def get_or_create_cold_start_intent(
    uid: str,
    *,
    source: ProactiveIntentSource,
    continuity_key: str,
    subject: ChatFirstSubject | None,
    blocks: list[ChatFirstBlockSpec],
    account_generation: int,
    now: datetime,
    firestore_client: Any = None,
) -> tuple[ProactiveIntent, bool]:
    """Persist exactly one generation-bound cold-start intent.

    Cold-start richness is sampled only for the first writer. The stable ID is
    deliberately independent of the selected rich/sparse source so a retry
    after canonical data changes returns the original ready intent rather than
    producing a second first-run experience.
    """

    if source not in {'cold_start_rich', 'cold_start_sparse'}:
        raise ValueError('cold-start intents require a cold-start source')
    client = _db(firestore_client)
    intent_id = _stable_id('cfi', uid, account_generation, 'cold_start', continuity_key)
    intent = ProactiveIntent(
        intent_id=intent_id,
        continuity_key=continuity_key,
        account_generation=account_generation,
        source=source,
        subject=subject,
        blocks=blocks,
        delivery_state='pending_kernel_receipt',
        created_at=now,
    )
    intent_ref = _intent_ref(uid, intent_id, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> tuple[ProactiveIntent, bool]:
        control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
        _require_control(control_snapshot, account_generation)
        existing_snapshot = intent_ref.get(transaction=write_transaction)
        if existing_snapshot.exists:
            existing = _intent_from_snapshot(existing_snapshot)
            if (
                existing.account_generation != account_generation
                or existing.continuity_key != continuity_key
                or existing.source not in {'cold_start_rich', 'cold_start_sparse'}
            ):
                raise ChatFirstIntentConflictError('cold-start continuity key was reused')
            return existing, False
        write_transaction.set(intent_ref, _intent_payload(intent))
        return intent, True

    return apply(transaction)


def has_cold_start_intent_created_on(
    uid: str,
    *,
    account_generation: int,
    date_value: date,
    firestore_client: Any = None,
) -> bool:
    """Whether this generation already used today's deterministic opener slot."""

    client = _db(firestore_client)
    _require_current_control(uid, account_generation=account_generation, firestore_client=client)
    collection = _user_ref(uid, firestore_client=client).collection(INTENTS_COLLECTION)
    for snapshot in collection.stream():
        intent = _intent_from_snapshot(snapshot)
        if intent.account_generation != account_generation:
            continue
        if intent.source not in {'cold_start_rich', 'cold_start_sparse'}:
            continue
        if intent.created_at.date() == date_value:
            return True
    return False


def acknowledge_sparse_cold_start_sequence_terminal(
    uid: str,
    *,
    sequence_id: str,
    receipt_id: str,
    terminal_state: ColdStartSequenceTerminalState,
    account_generation: int,
    now: datetime,
    firestore_client: Any = None,
) -> ProactiveIntent:
    """Accept one local-journal terminal receipt for the sparse sequence.

    The receipt is attached to the original cold-start intent so it cannot
    become a client/operator completion flag. A sparse sequence remains active
    through the crash window before its initial materialization receipt reaches
    the server, then releases agent-tier judgment only after this terminal
    journal fact is durably acknowledged.
    """

    expected_sequence_id = f'cold-start:{account_generation}'
    if sequence_id != expected_sequence_id:
        raise ChatFirstIntentConflictError('cold-start terminal sequence does not match generation')
    client = _db(firestore_client)
    intent_id = _stable_id('cfi', uid, account_generation, 'cold_start', sequence_id)
    intent_ref = _intent_ref(uid, intent_id, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> ProactiveIntent:
        control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
        _require_control(control_snapshot, account_generation)
        snapshot = intent_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            raise ProactiveIntentNotReady('cold-start intent is not ready')
        intent = _intent_from_snapshot(snapshot)
        if (
            intent.account_generation != account_generation
            or intent.source != 'cold_start_sparse'
            or intent.subject != ChatFirstSubject(kind='cold_start', id=sequence_id)
            or intent.delivery_state != 'delivered'
            or intent.materialization_receipt_id is None
        ):
            raise ProactiveIntentNotReady('cold-start sequence is not ready for terminal acknowledgement')
        if intent.cold_start_sequence_terminal_receipt_id is not None:
            if (
                intent.cold_start_sequence_terminal_receipt_id != receipt_id
                or intent.cold_start_sequence_terminal_state != terminal_state
            ):
                raise ChatFirstIntentConflictError('cold-start sequence was already terminalized differently')
            return intent
        terminalized = intent.model_copy(
            update={
                'cold_start_sequence_terminal_state': terminal_state,
                'cold_start_sequence_terminal_receipt_id': receipt_id,
            }
        )
        write_transaction.set(intent_ref, _intent_payload(terminalized))
        return terminalized

    return apply(transaction)


def has_active_sparse_cold_start_sequence(
    uid: str,
    *,
    account_generation: int,
    firestore_client: Any = None,
) -> bool:
    """Whether a sparse local-journal sequence can still own the Chat tail."""

    client = _db(firestore_client)
    _require_current_control(uid, account_generation=account_generation, firestore_client=client)
    collection = _user_ref(uid, firestore_client=client).collection(INTENTS_COLLECTION)
    for snapshot in collection.stream():
        intent = _intent_from_snapshot(snapshot)
        if intent.account_generation != account_generation or intent.source != 'cold_start_sparse':
            continue
        if intent.cold_start_sequence_terminal_receipt_id is None:
            return True
    return False


def fetch_ready_intents(
    uid: str,
    *,
    account_generation: int,
    limit: int = 8,
    firestore_client: Any = None,
) -> list[ProactiveIntent]:
    """Return ready intents only; this never changes delivery or writes Chat."""

    client = _db(firestore_client)
    _require_current_control(uid, account_generation=account_generation, firestore_client=client)
    collection = _user_ref(uid, firestore_client=client).collection(INTENTS_COLLECTION)
    ready: list[ProactiveIntent] = []
    for snapshot in collection.stream():
        intent = _intent_from_snapshot(snapshot)
        if intent.account_generation != account_generation or intent.delivery_state not in {
            'ready',
            'pending_kernel_receipt',
        }:
            continue
        ready.append(intent)
    ready.sort(key=lambda intent: (intent.created_at, intent.intent_id))
    return ready[:limit]


def acknowledge_materialization(
    uid: str,
    *,
    intent_id: str,
    receipt_id: str,
    account_generation: int,
    now: datetime,
    firestore_client: Any = None,
) -> ProactiveIntent:
    """Accept a local-kernel receipt and atomically account for an agent turn."""

    client = _db(firestore_client)
    intent_ref = _intent_ref(uid, intent_id, firestore_client=client)
    budget_ref = _budget_ref(uid, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> ProactiveIntent:
        control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
        _require_control(control_snapshot, account_generation)
        intent_snapshot = intent_ref.get(transaction=write_transaction)
        if not intent_snapshot.exists:
            raise ProactiveIntentNotReady('proactive intent is not ready')
        intent = _intent_from_snapshot(intent_snapshot)
        budget_snapshot = budget_ref.get(transaction=write_transaction) if intent.consumes_turn_budget else None
        if intent.account_generation != account_generation:
            raise ChatFirstIntentGenerationMismatch('intent account generation changed')
        if intent.delivery_state == 'delivered':
            if intent.materialization_receipt_id != receipt_id:
                raise ChatFirstIntentConflictError('intent was already acknowledged by a different receipt')
            return intent
        if intent.delivery_state not in {'ready', 'pending_kernel_receipt'}:
            raise ProactiveIntentNotReady('proactive intent is not ready')

        delivered = intent.model_copy(
            update={
                'delivery_state': 'delivered',
                'delivered_at': now,
                'materialization_receipt_id': receipt_id,
            }
        )
        if intent.consumes_turn_budget:
            assert budget_snapshot is not None
            budget = _budget_from_snapshot(budget_snapshot, account_generation=account_generation, now=now)
            accounted = account_materialization(budget, intent_id=intent_id, now=now)
            write_transaction.set(budget_ref, accounted.model_dump(mode='python'))
        write_transaction.set(intent_ref, _intent_payload(delivered))
        return delivered

    return apply(transaction)


def record_deferral(
    uid: str,
    *,
    continuity_key: str,
    subject: ChatFirstSubject,
    question: QuestionCardSpec,
    account_generation: int,
    now: datetime,
    firestore_client: Any = None,
) -> tuple[DeferralReceipt, bool]:
    """Accept the kernel's idempotent deferral outbox record."""

    client = _db(firestore_client)
    deferral_id = _stable_id('cfd', uid, account_generation, continuity_key)
    deferral = ProactiveDeferral(
        deferral_id=deferral_id,
        continuity_key=continuity_key,
        account_generation=account_generation,
        subject=subject,
        question=question,
        created_at=now,
        due_at=now + _DEFERRAL_DUE_AFTER,
    )
    ref = _deferral_ref(uid, deferral_id, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> tuple[DeferralReceipt, bool]:
        control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
        _require_control(control_snapshot, account_generation)
        existing_snapshot = ref.get(transaction=write_transaction)
        if existing_snapshot.exists:
            existing = _deferral_from_snapshot(existing_snapshot)
            if (
                existing.account_generation != account_generation
                or existing.continuity_key != continuity_key
                or existing.subject != subject
                or existing.question != question
            ):
                raise ChatFirstIntentConflictError('deferral continuity key was reused with different content')
            return (
                DeferralReceipt(deferral_id=existing.deferral_id, due_at=existing.due_at, state=existing.state),
                False,
            )
        write_transaction.set(ref, deferral.model_dump(mode='python'))
        return DeferralReceipt(deferral_id=deferral_id, due_at=deferral.due_at, state='pending'), True

    return apply(transaction)


def release_due_deferrals(
    uid: str,
    *,
    account_generation: int,
    now: datetime,
    subject: ChatFirstSubject | None = None,
    firestore_client: Any = None,
) -> list[ProactiveIntent]:
    """Release due or meaningful-subject-change deferrals exactly once, verbatim."""

    client = _db(firestore_client)
    _require_current_control(uid, account_generation=account_generation, firestore_client=client)
    collection = _user_ref(uid, firestore_client=client).collection(DEFERRALS_COLLECTION)
    candidates: list[ProactiveDeferral] = []
    for snapshot in collection.stream():
        deferred = _deferral_from_snapshot(snapshot)
        if deferred.account_generation != account_generation or deferred.state != 'pending':
            continue
        if subject is not None:
            if deferred.subject != subject:
                continue
        elif deferred.due_at > now:
            continue
        candidates.append(deferred)

    released: list[ProactiveIntent] = []
    for deferred in candidates[:32]:
        intent = _release_deferral_transaction(
            uid,
            deferred,
            account_generation=account_generation,
            now=now,
            firestore_client=client,
        )
        if intent is not None:
            released.append(intent)
    return released


def _release_deferral_transaction(
    uid: str,
    deferred: ProactiveDeferral,
    *,
    account_generation: int,
    now: datetime,
    firestore_client: Any,
) -> ProactiveIntent | None:
    intent_id = _stable_id('cfi', uid, account_generation, 'deferral_reraise', deferred.continuity_key)
    intent = ProactiveIntent(
        intent_id=intent_id,
        continuity_key=deferred.continuity_key,
        account_generation=account_generation,
        source='deferral_reraise',
        subject=deferred.subject,
        blocks=[deferred.question],
        created_at=now,
    )
    deferral_ref = _deferral_ref(uid, deferred.deferral_id, firestore_client=firestore_client)
    intent_ref = _intent_ref(uid, intent_id, firestore_client=firestore_client)
    transaction = firestore_client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> ProactiveIntent | None:
        control_snapshot = _control_ref(uid, firestore_client=firestore_client).get(transaction=write_transaction)
        _require_control(control_snapshot, account_generation)
        deferral_snapshot = deferral_ref.get(transaction=write_transaction)
        intent_snapshot = intent_ref.get(transaction=write_transaction)
        if not deferral_snapshot.exists:
            return None
        current = _deferral_from_snapshot(deferral_snapshot)
        if current.account_generation != account_generation or current.state != 'pending':
            return None
        if intent_snapshot.exists:
            existing = _intent_from_snapshot(intent_snapshot)
            if existing.source != 'deferral_reraise' or existing.continuity_key != current.continuity_key:
                raise ChatFirstIntentConflictError('deferral intent collision')
            released = current.model_copy(update={'state': 'released', 'released_intent_id': existing.intent_id})
            write_transaction.set(deferral_ref, released.model_dump(mode='python'))
            return existing
        released = current.model_copy(update={'state': 'released', 'released_intent_id': intent_id})
        write_transaction.set(intent_ref, _intent_payload(intent))
        write_transaction.set(deferral_ref, released.model_dump(mode='python'))
        return intent

    return apply(transaction)


def iter_ready_intent_ids(
    intents: Iterable[ProactiveIntent],
) -> list[str]:
    """Small content-free helper for shape-only call-site accounting."""

    return [intent.intent_id for intent in intents]


__all__ = [
    'AgentJudgmentAdmission',
    'BUDGET_DOCUMENT',
    'ChatFirstIntentConflictError',
    'ChatFirstIntentGenerationMismatch',
    'ChatFirstIntentStoreError',
    'DEFERRALS_COLLECTION',
    'INTENTS_COLLECTION',
    'ProactiveBudgetExhausted',
    'ProactiveIntentNotReady',
    'acknowledge_materialization',
    'admit_agent_judgment',
    'create_intent',
    'get_or_create_cold_start_intent',
    'has_cold_start_intent_created_on',
    'acknowledge_sparse_cold_start_sequence_terminal',
    'has_active_sparse_cold_start_sequence',
    'fetch_ready_intents',
    'get_budget_state',
    'iter_ready_intent_ids',
    'release_agent_judgment_admission',
    'record_deferral',
    'release_due_deferrals',
]
