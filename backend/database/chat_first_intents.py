"""Durable Chat-first proactive intent state, separate from the chat journal."""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.firestore_index_registry import CHAT_FIRST_DEFERRALS_DUE_QUERY, CHAT_FIRST_DEFERRALS_SUBJECT_QUERY
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
from models.proactive_budget import account_materialization, normalized_budget_state, reserve_budget
from models.task_intelligence import TaskWorkflowControl

INTENTS_COLLECTION = 'chat_first_proactive_intents'
DEFERRALS_COLLECTION = 'chat_first_deferrals'
STATE_COLLECTION = 'chat_first_proactive_state'
BUDGET_DOCUMENT = 'budget'
_DEFERRAL_DUE_AFTER = timedelta(hours=24)
CONTINUOUS_DEFERRAL_BUDGET = timedelta(days=7)
FETCH_CANDIDATE_SCAN_MULTIPLIER = 2

# A ready intent must reach a terminal state under bounded identical retries:
# typed kernel failures park it after three reports, while fetch-only clients
# cannot keep any head item live beyond twenty unacknowledged deliveries.
MATERIALIZATION_REJECTION_BUDGET = 3
UNACKNOWLEDGED_FETCH_BUDGET = 20
STALLED_READY_AGE = timedelta(hours=24)
PERMANENT_REJECTION_CODES = frozenset({'invalid_intent', 'identity_conflict'})


@dataclass(frozen=True)
class IntentLifecycleEvent:
    event: str
    source: ProactiveIntentSource
    reason: str


@dataclass(frozen=True)
class ReadyIntentBatch:
    intents: list[ProactiveIntent]
    lifecycle_events: tuple[IntentLifecycleEvent, ...]
    stalled_source: ProactiveIntentSource | None


@dataclass(frozen=True)
class DeferralReleaseBatch:
    intents: list[ProactiveIntent]
    malformed_count: int


class ChatFirstIntentStoreError(RuntimeError):
    """Base class for closed intent-store failures."""


class ChatFirstIntentGenerationMismatch(ChatFirstIntentStoreError):
    pass


class ChatFirstIntentDocumentGenerationMismatch(ChatFirstIntentStoreError):
    pass


class ChatFirstMalformedDocument(ChatFirstIntentStoreError):
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


def proactive_intent_id(
    uid: str,
    *,
    account_generation: int,
    source_key: str,
    continuity_key: str,
) -> str:
    """Return the canonical durable ID for one proactive intent identity."""

    return _stable_id('cfi', uid, account_generation, source_key, continuity_key)


def proactive_deferral_id(uid: str, *, account_generation: int, continuity_key: str) -> str:
    """Return the canonical durable ID for one deferred question identity."""

    return _stable_id('cfd', uid, account_generation, continuity_key)


def _require_control(snapshot: Any, *, uid: str, account_generation: int) -> None:
    control = TaskWorkflowControl()
    if snapshot.exists:
        try:
            control = parse_snapshot_strict(TaskWorkflowControl, snapshot)
        except MalformedDocError as error:
            raise ChatFirstIntentGenerationMismatch('chat-first capability state is malformed') from error
    if control.account_generation != account_generation:
        raise ChatFirstIntentGenerationMismatch('chat-first capability changed')


def _budget_from_snapshot(snapshot: Any, *, account_generation: int, now: datetime) -> ProactiveBudgetState:
    if not snapshot.exists:
        return ProactiveBudgetState(account_generation=account_generation)
    try:
        state = parse_snapshot_strict(ProactiveBudgetState, snapshot)
    except MalformedDocError as error:
        raise ChatFirstMalformedDocument('chat-first proactive budget state is malformed') from error
    if state.account_generation != account_generation:
        return ProactiveBudgetState(account_generation=account_generation)
    return normalized_budget_state(state, now=now)


def _intent_from_snapshot(snapshot: Any) -> ProactiveIntent:
    """Load correctness-critical proactive state without treating corruption as absent."""

    try:
        return parse_snapshot_strict(ProactiveIntent, snapshot)
    except MalformedDocError as error:
        raise ChatFirstMalformedDocument('chat-first proactive intent is malformed') from error


def _deferral_from_snapshot(snapshot: Any) -> ProactiveDeferral:
    """Load correctness-critical deferred-question state without a fallback."""

    try:
        return parse_snapshot_strict(ProactiveDeferral, snapshot)
    except MalformedDocError as error:
        raise ChatFirstMalformedDocument('chat-first deferral is malformed') from error


def _require_current_control(uid: str, *, account_generation: int, firestore_client: Any) -> None:
    """Fence read-only entry points before they inspect feature-specific rows."""

    _require_control(
        _control_ref(uid, firestore_client=firestore_client).get(),
        uid=uid,
        account_generation=account_generation,
    )


def _intent_payload(intent: ProactiveIntent) -> dict[str, Any]:
    return intent.model_dump(mode='python')


def get_budget_state(
    uid: str,
    *,
    account_generation: int,
    now: datetime,
    firestore_client: Any = None,
) -> ProactiveBudgetState:
    """Read bounded accounting after the caller passed generation validation."""

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
    intent_id = proactive_intent_id(
        uid,
        account_generation=account_generation,
        source_key='agent_judgment',
        continuity_key=continuity_key,
    )
    intent_ref = _intent_ref(uid, intent_id, firestore_client=client)
    budget_ref = _budget_ref(uid, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> AgentJudgmentAdmission:
        control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
        _require_control(control_snapshot, uid=uid, account_generation=account_generation)
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
    intent_id = proactive_intent_id(
        uid,
        account_generation=account_generation,
        source_key='agent_judgment',
        continuity_key=continuity_key,
    )
    intent_ref = _intent_ref(uid, intent_id, firestore_client=client)
    budget_ref = _budget_ref(uid, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> None:
        control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
        _require_control(control_snapshot, uid=uid, account_generation=account_generation)
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
    intent_id = proactive_intent_id(
        uid,
        account_generation=account_generation,
        source_key=source,
        continuity_key=continuity_key,
    )
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
        _require_control(control_snapshot, uid=uid, account_generation=account_generation)
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
    intent_id = proactive_intent_id(
        uid,
        account_generation=account_generation,
        source_key='cold_start',
        continuity_key=continuity_key,
    )
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
        _require_control(control_snapshot, uid=uid, account_generation=account_generation)
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
    intent_id = proactive_intent_id(
        uid,
        account_generation=account_generation,
        source_key='cold_start',
        continuity_key=sequence_id,
    )
    intent_ref = _intent_ref(uid, intent_id, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> ProactiveIntent:
        control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
        _require_control(control_snapshot, uid=uid, account_generation=account_generation)
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


def _stable_chat_first_turn_id(intent_id: str) -> str:
    return f'turn_cfi_{hashlib.sha256(intent_id.encode()).hexdigest()[:24]}'


def _synthetic_reconciliation_receipt_id(intent_id: str) -> str:
    return f'cfi_reconciled_{hashlib.sha256(intent_id.encode()).hexdigest()[:24]}'


def _message_has_intent_identity(uid: str, intent_id: str, *, firestore_client: Any) -> bool:
    """Point-read the stable chat row and verify its embedded intent identity."""

    snapshot = (
        _user_ref(uid, firestore_client=firestore_client)
        .collection('messages')
        .document(_stable_chat_first_turn_id(intent_id))
        .get()
    )
    if not snapshot.exists:
        return False
    metadata = (snapshot.to_dict() or {}).get('metadata')
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            return False
    return isinstance(metadata, dict) and metadata.get('chatFirstIntentId') == intent_id


def _fetch_priority(intent: ProactiveIntent) -> int:
    if intent.source == 'daily_opener' or any(block.type == 'conversationLink' for block in intent.blocks):
        return 0
    if intent.source == 'capture_arrival' and all(block.type == 'captureLink' for block in intent.blocks):
        return 2
    return 1


def _advance_fetched_intent(
    uid: str,
    intent_id: str,
    *,
    account_generation: int,
    now: datetime,
    reconcile: bool,
    firestore_client: Any,
) -> tuple[ProactiveIntent | None, IntentLifecycleEvent | None]:
    intent_ref = _intent_ref(uid, intent_id, firestore_client=firestore_client)
    transaction = firestore_client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> tuple[ProactiveIntent | None, IntentLifecycleEvent | None]:
        snapshot = intent_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            return None, None
        intent = _intent_from_snapshot(snapshot)
        if intent.account_generation != account_generation or intent.delivery_state not in {
            'ready',
            'pending_kernel_receipt',
        }:
            return None, None

        fetch_count = intent.fetch_count + 1
        common = {'fetch_count': fetch_count, 'last_fetched_at': now}
        if reconcile:
            budget_ref = _budget_ref(uid, firestore_client=firestore_client)
            budget_snapshot = budget_ref.get(transaction=write_transaction) if intent.consumes_turn_budget else None
            delivered = intent.model_copy(
                update={
                    **common,
                    'delivery_state': 'delivered',
                    'delivered_at': now,
                    'materialization_receipt_id': _synthetic_reconciliation_receipt_id(intent.intent_id),
                }
            )
            if intent.consumes_turn_budget:
                assert budget_snapshot is not None
                budget = _budget_from_snapshot(budget_snapshot, account_generation=account_generation, now=now)
                write_transaction.set(
                    budget_ref, account_materialization(budget, intent_id=intent_id, now=now).model_dump(mode='python')
                )
            write_transaction.set(intent_ref, _intent_payload(delivered))
            return None, IntentLifecycleEvent('reconciled', intent.source, 'existing_chat_row')
        if fetch_count > UNACKNOWLEDGED_FETCH_BUDGET:
            dead_lettered = intent.model_copy(
                update={
                    **common,
                    'delivery_state': 'dead_letter',
                    'dead_letter_reason': 'unacknowledged_after_fetch_budget',
                }
            )
            write_transaction.set(intent_ref, _intent_payload(dead_lettered))
            return None, IntentLifecycleEvent('dead_letter', intent.source, 'unacknowledged_after_fetch_budget')
        fetched = intent.model_copy(update=common)
        write_transaction.set(intent_ref, common, merge=True)
        return fetched, None

    return apply(transaction)


def _dead_letter_malformed_intent(
    uid: str,
    intent_id: str,
    *,
    account_generation: int,
    firestore_client: Any,
) -> None:
    """Terminalize one still-active malformed row without racing a newer writer."""

    intent_ref = _intent_ref(uid, intent_id, firestore_client=firestore_client)
    transaction = firestore_client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> None:
        snapshot = intent_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            return
        raw = snapshot.to_dict() or {}
        if raw.get('account_generation') != account_generation or raw.get('delivery_state') not in {
            'ready',
            'pending_kernel_receipt',
        }:
            return
        try:
            _intent_from_snapshot(snapshot)
        except ChatFirstMalformedDocument:
            write_transaction.set(
                intent_ref,
                {**raw, 'delivery_state': 'dead_letter', 'dead_letter_reason': 'malformed_document'},
            )

    apply(transaction)


def fetch_ready_intent_batch(
    uid: str,
    *,
    account_generation: int,
    limit: int = 8,
    exclude_block_types: set[str] | frozenset[str] | None = None,
    deferred_intent_ids: set[str] | frozenset[str] | None = None,
    now: datetime | None = None,
    firestore_client: Any = None,
) -> ReadyIntentBatch:
    """Fetch a priority batch while bounding poison retries and reconciling stable rows."""

    client = _db(firestore_client)
    fetched_at = now or datetime.now(timezone.utc)
    _require_current_control(uid, account_generation=account_generation, firestore_client=client)
    collection = _user_ref(uid, firestore_client=client).collection(INTENTS_COLLECTION)
    # Push the delivery-state filter to Firestore so delivered historical rows
    # are never transferred for a foreground materialization.  The caller only
    # ever needs ready or pending-receipt intents, which are bounded; the full
    # collection otherwise grows with account age.
    query = collection.where(filter=FieldFilter('delivery_state', 'in', ['ready', 'pending_kernel_receipt']))
    candidates: list[ProactiveIntent] = []
    malformed_intent_ids: list[str] = []
    for snapshot in query.stream():
        try:
            intent = _intent_from_snapshot(snapshot)
        except ChatFirstMalformedDocument:
            raw = snapshot.to_dict() or {}
            malformed_intent_ids.append(getattr(snapshot, 'id', raw.get('intent_id', 'malformed')))
            continue
        if intent.account_generation != account_generation:
            continue
        # Apply compatibility filtering before the delivery window is bounded.
        # Legacy clients cannot acknowledge newer block types, so letting those
        # rows consume the first ``limit`` results would permanently starve the
        # legacy-compatible intents behind them.
        if exclude_block_types and any(block.type in exclude_block_types for block in intent.blocks):
            continue
        candidates.append(intent)
    candidates.sort(key=lambda intent: (_fetch_priority(intent), intent.created_at, intent.intent_id))
    oldest_candidate = min(candidates, key=lambda intent: (intent.created_at, intent.intent_id), default=None)

    ready: list[ProactiveIntent] = []
    lifecycle_events: list[IntentLifecycleEvent] = []
    candidate_scan_limit = FETCH_CANDIDATE_SCAN_MULTIPLIER * limit
    malformed_scan_count = min(len(malformed_intent_ids), candidate_scan_limit)
    for intent_id in malformed_intent_ids[:malformed_scan_count]:
        try:
            _dead_letter_malformed_intent(
                uid,
                intent_id,
                account_generation=account_generation,
                firestore_client=client,
            )
        except Exception:
            # A concurrently deleted or repaired malformed row is isolated from
            # every independent ready intent in this fetch.
            continue
    # Process beyond the response limit when earlier candidates terminalize,
    # but never let a poison backlog amplify point reads and transactions
    # without bound on every device poll.
    remaining_scan_limit = candidate_scan_limit - malformed_scan_count
    for intent in candidates[:remaining_scan_limit]:
        if deferred_intent_ids and intent.intent_id in deferred_intent_ids:
            if len(ready) < limit:
                ready.append(intent)
            if len(ready) >= limit:
                break
            continue
        reconcile = intent.fetch_count >= 2 and _message_has_intent_identity(
            uid, intent.intent_id, firestore_client=client
        )
        try:
            advanced, event = _advance_fetched_intent(
                uid,
                intent.intent_id,
                account_generation=account_generation,
                now=fetched_at,
                reconcile=reconcile,
                firestore_client=client,
            )
        except Exception:
            # One concurrently malformed or otherwise unadvanceable row is
            # never allowed to block independent ready intents.
            continue
        if event is not None:
            lifecycle_events.append(event)
        if advanced is not None and len(ready) < limit:
            ready.append(advanced)
        if len(ready) >= limit:
            break

    stalled_source = (
        oldest_candidate.source
        if oldest_candidate is not None and fetched_at - oldest_candidate.created_at > STALLED_READY_AGE
        else None
    )
    return ReadyIntentBatch(ready, tuple(lifecycle_events), stalled_source)


def fetch_ready_intents(
    uid: str,
    *,
    account_generation: int,
    limit: int = 8,
    exclude_block_types: set[str] | frozenset[str] | None = None,
    now: datetime | None = None,
    firestore_client: Any = None,
) -> list[ProactiveIntent]:
    """Compatibility wrapper for callers that only consume the live intents."""

    return fetch_ready_intent_batch(
        uid,
        account_generation=account_generation,
        limit=limit,
        exclude_block_types=exclude_block_types,
        now=now,
        firestore_client=firestore_client,
    ).intents


def record_materialization_rejection(
    uid: str,
    *,
    intent_id: str,
    code: str,
    account_generation: int,
    now: datetime,
    firestore_client: Any = None,
) -> tuple[ProactiveIntent | None, str | None]:
    """Record a typed kernel rejection and park deterministic poison within budget."""

    client = _db(firestore_client)
    intent_ref = _intent_ref(uid, intent_id, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> tuple[ProactiveIntent | None, str | None]:
        control_snapshot = _control_ref(uid, firestore_client=client).get(transaction=write_transaction)
        _require_control(control_snapshot, uid=uid, account_generation=account_generation)
        snapshot = intent_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            return None, None
        intent = _intent_from_snapshot(snapshot)
        if intent.account_generation != account_generation:
            raise ChatFirstIntentDocumentGenerationMismatch('intent account generation changed')
        if intent.delivery_state in {'dead_letter', 'delivered'}:
            return intent, None
        if intent.delivery_state not in {'ready', 'pending_kernel_receipt'}:
            raise ProactiveIntentNotReady('proactive intent is not ready')

        attempts = intent.materialization_attempts + 1
        reason: str | None = None
        if code in PERMANENT_REJECTION_CODES:
            reason = f'permanent_rejection:{code}'
        elif attempts >= MATERIALIZATION_REJECTION_BUDGET:
            reason = 'rejection_budget_exhausted'
        rejected = intent.model_copy(
            update={
                'materialization_attempts': attempts,
                'last_rejection_code': code,
                'last_rejection_at': now,
                **({'delivery_state': 'dead_letter', 'dead_letter_reason': reason} if reason else {}),
            }
        )
        write_transaction.set(intent_ref, _intent_payload(rejected))
        return rejected, reason

    return apply(transaction)


def record_materialization_deferral(
    uid: str,
    *,
    intent_id: str,
    account_generation: int,
    now: datetime,
    firestore_client: Any = None,
) -> ProactiveIntent | None:
    """Record one explicit suppression without refunding an earlier fetch."""

    client = _db(firestore_client)
    intent_ref = _intent_ref(uid, intent_id, firestore_client=client)
    transaction = client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> ProactiveIntent | None:
        snapshot = intent_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            return None
        intent = _intent_from_snapshot(snapshot)
        if intent.account_generation != account_generation:
            raise ChatFirstIntentDocumentGenerationMismatch('intent account generation changed')
        if intent.delivery_state not in {'ready', 'pending_kernel_receipt'}:
            return intent
        first_deferred_at = intent.first_deferred_at or now
        if now - first_deferred_at >= CONTINUOUS_DEFERRAL_BUDGET:
            dead_lettered = intent.model_copy(
                update={
                    'first_deferred_at': first_deferred_at,
                    'last_deferral_at': now,
                    'delivery_state': 'dead_letter',
                    'dead_letter_reason': 'deferred_beyond_budget',
                }
            )
            write_transaction.set(intent_ref, _intent_payload(dead_lettered))
            return dead_lettered
        write_transaction.set(
            intent_ref,
            {'first_deferred_at': first_deferred_at, 'last_deferral_at': now},
            merge=True,
        )
        return intent.model_copy(update={'first_deferred_at': first_deferred_at, 'last_deferral_at': now})

    return apply(transaction)


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
        _require_control(control_snapshot, uid=uid, account_generation=account_generation)
        intent_snapshot = intent_ref.get(transaction=write_transaction)
        if not intent_snapshot.exists:
            raise ProactiveIntentNotReady('proactive intent is not ready')
        intent = _intent_from_snapshot(intent_snapshot)
        budget_snapshot = budget_ref.get(transaction=write_transaction) if intent.consumes_turn_budget else None
        if intent.account_generation != account_generation:
            raise ChatFirstIntentDocumentGenerationMismatch('intent account generation changed')
        if intent.delivery_state == 'delivered':
            if intent.materialization_receipt_id != receipt_id:
                raise ChatFirstIntentConflictError('intent was delivered with a different receipt')
            return intent
        if intent.delivery_state == 'dead_letter':
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
    deferral_id = proactive_deferral_id(
        uid,
        account_generation=account_generation,
        continuity_key=continuity_key,
    )
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
        _require_control(control_snapshot, uid=uid, account_generation=account_generation)
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
) -> DeferralReleaseBatch:
    """Release due or meaningful-subject-change deferrals exactly once.

    Keep the pending/state and releaseability predicates in Firestore. A user's
    deferral collection is unbounded, and streaming released or future rows on
    every foreground wake turns old history into the hot path.
    """

    client = _db(firestore_client)
    _require_current_control(uid, account_generation=account_generation, firestore_client=client)
    collection = _user_ref(uid, firestore_client=client).collection(DEFERRALS_COLLECTION)
    if subject is None:
        query = CHAT_FIRST_DEFERRALS_DUE_QUERY.build(
            collection,
            {'account_generation': account_generation, 'state': 'pending', 'due_at': now},
            field_filter_factory=FieldFilter,
        )
    else:
        query = CHAT_FIRST_DEFERRALS_SUBJECT_QUERY.build(
            collection,
            {
                'account_generation': account_generation,
                'state': 'pending',
                'subject_kind': subject.kind,
                'subject_id': subject.id,
            },
            field_filter_factory=FieldFilter,
        )
    query = query.limit(32)
    candidates: list[ProactiveDeferral] = []
    malformed_count = 0
    for snapshot in query.stream():
        try:
            deferred = _deferral_from_snapshot(snapshot)
        except ChatFirstMalformedDocument:
            malformed_count += 1
            continue
        # Keep strict model validation and an exact subject check as the final
        # fence for old/malformed rows and for fake clients that do not fully
        # emulate Firestore's nested-field filtering.
        if deferred.account_generation != account_generation or deferred.state != 'pending':
            continue
        if subject is not None and deferred.subject != subject:
            continue
        if subject is None and deferred.due_at > now:
            continue
        candidates.append(deferred)

    released: list[ProactiveIntent] = []
    for deferred in candidates:
        try:
            intent = _release_deferral_transaction(
                uid,
                deferred,
                account_generation=account_generation,
                now=now,
                firestore_client=client,
            )
        except ChatFirstIntentGenerationMismatch:
            raise
        except ChatFirstMalformedDocument:
            malformed_count += 1
            continue
        except Exception:
            # One concurrently deleted, conflicting, or otherwise broken row
            # cannot roll back independent due deferrals in this batch.
            continue
        if intent is not None:
            released.append(intent)
    return DeferralReleaseBatch(released, malformed_count)


def _release_deferral_transaction(
    uid: str,
    deferred: ProactiveDeferral,
    *,
    account_generation: int,
    now: datetime,
    firestore_client: Any,
) -> ProactiveIntent | None:
    intent_id = proactive_intent_id(
        uid,
        account_generation=account_generation,
        source_key='deferral_reraise',
        continuity_key=deferred.continuity_key,
    )
    released_question = deferred.question.model_copy(
        update={'question_id': _stable_id('qri', deferred.question.question_id, deferred.deferral_id)}
    )
    intent = ProactiveIntent(
        intent_id=intent_id,
        continuity_key=deferred.continuity_key,
        account_generation=account_generation,
        source='deferral_reraise',
        subject=deferred.subject,
        blocks=[released_question],
        created_at=now,
    )
    deferral_ref = _deferral_ref(uid, deferred.deferral_id, firestore_client=firestore_client)
    intent_ref = _intent_ref(uid, intent_id, firestore_client=firestore_client)
    transaction = firestore_client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> ProactiveIntent | None:
        control_snapshot = _control_ref(uid, firestore_client=firestore_client).get(transaction=write_transaction)
        _require_control(control_snapshot, uid=uid, account_generation=account_generation)
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
    'ChatFirstIntentDocumentGenerationMismatch',
    'ChatFirstIntentGenerationMismatch',
    'ChatFirstMalformedDocument',
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
    'fetch_ready_intent_batch',
    'get_budget_state',
    'iter_ready_intent_ids',
    'proactive_deferral_id',
    'proactive_intent_id',
    'release_agent_judgment_admission',
    'record_deferral',
    'release_due_deferrals',
    'record_materialization_rejection',
]
