"""Derived delivery attempts and terminal records for Chat-first intents."""

import logging
from datetime import datetime, timedelta
from typing import Any

from google.api_core.exceptions import GoogleAPICallError
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from database.firestore_index_registry import CHAT_FIRST_TRANSIENT_DEAD_LETTER_REPAIR_QUERY
from database.read_boundary import MalformedDocError, parse_payload_strict, parse_snapshot_strict
from models.chat_first import DeadLetteredProactiveIntent, ProactiveIntent

INTENTS_COLLECTION = 'chat_first_proactive_intents'
DELIVERY_ATTEMPTS_COLLECTION = 'chat_first_delivery_attempts'
DEAD_LETTERS_COLLECTION = 'chat_first_dead_letters'
TRANSIENT_DEAD_LETTER_REPAIR_AGE = timedelta(hours=6)
UNACKNOWLEDGED_DEAD_LETTER_REASON = 'unacknowledged_after_fetch_budget'
KERNEL_FAILURE_DEAD_LETTER_REASON = 'permanent_rejection:kernel_materialization_failed'
TRANSIENT_DEAD_LETTER_REASONS = frozenset({UNACKNOWLEDGED_DEAD_LETTER_REASON, KERNEL_FAILURE_DEAD_LETTER_REASON})
UNACKNOWLEDGED_FETCH_BUDGET = 20

logger = logging.getLogger(__name__)


class ChatFirstMalformedDeliveryAttempt(RuntimeError):
    pass


class DeliveryAttemptState(BaseModel):
    """The bounded sibling schema; intent blocks never revalidate on a poll."""

    model_config = ConfigDict(extra='ignore', frozen=True)

    fetch_count: int = Field(default=0, ge=0)
    last_fetched_at: datetime | None = None
    requeue_count: int = Field(default=0, ge=0, le=1)
    materialization_attempts: int = Field(default=0, ge=0)
    last_rejection_code: str | None = Field(default=None, min_length=1, max_length=64, pattern=r'^[a-z0-9_]+$')
    last_rejection_at: datetime | None = None
    first_deferred_at: datetime | None = None
    last_deferral_at: datetime | None = None


def user_ref(uid: str, *, firestore_client: Any):
    return firestore_client.collection('users').document(uid)


def intent_ref(uid: str, intent_id: str, *, firestore_client: Any):
    return user_ref(uid, firestore_client=firestore_client).collection(INTENTS_COLLECTION).document(intent_id)


def delivery_attempt_ref(uid: str, intent_id: str, *, firestore_client: Any):
    return user_ref(uid, firestore_client=firestore_client).collection(DELIVERY_ATTEMPTS_COLLECTION).document(intent_id)


def dead_letter_ref(uid: str, intent_id: str, *, firestore_client: Any):
    return user_ref(uid, firestore_client=firestore_client).collection(DEAD_LETTERS_COLLECTION).document(intent_id)


def intent_with_delivery_attempt(intent: ProactiveIntent, snapshot: Any) -> ProactiveIntent:
    if not snapshot.exists:
        return intent
    try:
        attempt = parse_snapshot_strict(DeliveryAttemptState, snapshot)
    except MalformedDocError as error:
        raise ChatFirstMalformedDeliveryAttempt('chat-first delivery attempt state is malformed') from error
    return intent.model_copy(update=attempt.model_dump(mode='python'))


def valid_attempt_value(_intent: ProactiveIntent, field: str, value: Any) -> bool:
    try:
        DeliveryAttemptState.model_validate({field: value})
    except ValidationError:
        return False
    return True


def reset_malformed_delivery_attempt(intent: ProactiveIntent, raw: dict[str, Any], *, now: datetime) -> dict[str, Any]:
    """Preserve every independently valid field and spend the next fetch."""

    raw_requeue_count = raw.get('requeue_count', 0)
    preserved_requeue_count = (
        raw_requeue_count if valid_attempt_value(intent, 'requeue_count', raw_requeue_count) else 0
    )
    raw_fetch_count = raw.get('fetch_count', 0)
    preserved_fetch_count = (
        raw_fetch_count
        if valid_attempt_value(intent, 'fetch_count', raw_fetch_count)
        else (UNACKNOWLEDGED_FETCH_BUDGET - 1 if preserved_requeue_count > 0 else 0)
    )
    reset: dict[str, Any] = {'fetch_count': preserved_fetch_count + 1, 'last_fetched_at': now}
    defaults = {
        'requeue_count': preserved_requeue_count,
        'materialization_attempts': 0,
        'last_rejection_code': None,
        'last_rejection_at': None,
        'first_deferred_at': None,
        'last_deferral_at': None,
    }
    for field, default in defaults.items():
        value = raw.get(field, default)
        reset[field] = value if valid_attempt_value(intent, field, value) else default
    return reset


def dead_letter_payload(intent: ProactiveIntent, *, terminal_at: datetime) -> dict[str, Any]:
    """Keep the complete terminal record while ensuring repair ordering is non-null."""

    terminal = parse_payload_strict(
        DeadLetteredProactiveIntent,
        intent.model_dump(mode='python'),
        document_path='<derived-chat-first-dead-letter>',
    )
    payload = terminal.model_dump(mode='python')
    if payload.get('last_fetched_at') is None:
        payload['last_fetched_at'] = terminal_at
    return payload


def move_to_dead_letters(
    write_transaction: Any,
    *,
    intent_ref_value: Any,
    dead_letter_ref_value: Any,
    intent: ProactiveIntent,
    terminal_at: datetime,
) -> None:
    write_transaction.set(dead_letter_ref_value, dead_letter_payload(intent, terminal_at=terminal_at))
    write_transaction.delete(intent_ref_value)


def requeue_transient_dead_letter(
    uid: str,
    intent_id: str,
    *,
    account_generation: int,
    now: datetime,
    firestore_client: Any,
) -> ProactiveIntent | None:
    dead_ref = dead_letter_ref(uid, intent_id, firestore_client=firestore_client)
    active_ref = intent_ref(uid, intent_id, firestore_client=firestore_client)
    attempt_ref = delivery_attempt_ref(uid, intent_id, firestore_client=firestore_client)
    transaction = firestore_client.transaction()

    @firestore.transactional
    def apply(write_transaction: Any) -> ProactiveIntent | None:
        snapshot = dead_ref.get(transaction=write_transaction)
        if not snapshot.exists:
            return None
        try:
            intent = parse_snapshot_strict(DeadLetteredProactiveIntent, snapshot)
        except MalformedDocError as error:
            raise ChatFirstMalformedDeliveryAttempt('chat-first dead letter is malformed') from error
        attempt_snapshot = attempt_ref.get(transaction=write_transaction)
        intent = intent_with_delivery_attempt(intent, attempt_snapshot)
        if (
            intent.account_generation != account_generation
            or intent.delivery_state != 'dead_letter'
            or intent.dead_letter_reason not in TRANSIENT_DEAD_LETTER_REASONS
            or intent.requeue_count != 0
        ):
            return None
        terminal_at = intent.last_rejection_at or intent.last_fetched_at
        if terminal_at is None or now - terminal_at < TRANSIENT_DEAD_LETTER_REPAIR_AGE:
            return None
        requeued = intent.model_copy(
            update={
                'delivery_state': 'ready',
                'dead_letter_reason': None,
                'fetch_count': 0,
                'last_fetched_at': None,
                'materialization_attempts': 0,
                'last_rejection_code': None,
                'last_rejection_at': None,
                'requeue_count': 1,
            }
        )
        active_payload = requeued.model_dump(
            mode='python',
            exclude={
                'fetch_count',
                'last_fetched_at',
                'requeue_count',
                'materialization_attempts',
                'last_rejection_code',
                'last_rejection_at',
                'first_deferred_at',
                'last_deferral_at',
                'dead_letter_reason',
            },
        )
        write_transaction.set(active_ref, active_payload)
        write_transaction.set(
            attempt_ref,
            {
                'fetch_count': 0,
                'requeue_count': 1,
                'materialization_attempts': 0,
                'last_rejection_code': None,
                'last_rejection_at': None,
            },
            merge=True,
        )
        write_transaction.delete(dead_ref)
        return requeued

    return apply(transaction)


def repair_transient_dead_letters(
    uid: str,
    *,
    account_generation: int,
    limit: int,
    now: datetime,
    firestore_client: Any,
    requeue: Any = requeue_transient_dead_letter,
) -> bool:
    """Repair a bounded terminal window; return whether the serving query failed."""

    collection = user_ref(uid, firestore_client=firestore_client).collection(DEAD_LETTERS_COLLECTION)
    try:
        query = (
            CHAT_FIRST_TRANSIENT_DEAD_LETTER_REPAIR_QUERY.build(
                collection,
                {
                    'account_generation': account_generation,
                    'requeue_count': 0,
                    'dead_letter_reasons': list(TRANSIENT_DEAD_LETTER_REASONS),
                    'last_fetched_at': None,
                },
                field_filter_factory=FieldFilter,
            )
            .order_by('last_fetched_at')
            .limit(2 * limit)
        )
        repaired = 0
        for snapshot in query.stream():
            if repaired >= limit:
                break
            raw = snapshot.to_dict() or {}
            terminal_at = raw.get('last_rejection_at') or raw.get('last_fetched_at')
            if not isinstance(terminal_at, datetime) or now - terminal_at < TRANSIENT_DEAD_LETTER_REPAIR_AGE:
                continue
            try:
                if (
                    requeue(
                        uid,
                        snapshot.id,
                        account_generation=account_generation,
                        now=now,
                        firestore_client=firestore_client,
                    )
                    is not None
                ):
                    repaired += 1
            except ChatFirstMalformedDeliveryAttempt:
                continue
    except GoogleAPICallError:
        logger.exception('Chat-first transient dead-letter repair scan failed')
        return True
    return False
