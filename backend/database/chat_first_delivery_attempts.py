"""Derived delivery attempts and terminal records for Chat-first intents."""

import logging
from datetime import datetime, timedelta, timezone
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


def _clean_id(value: Any, name: str = 'id', max_length: int = 64) -> str:
    """Validate and sanitize an identifier, rejecting empty/whitespace, path traversal, null bytes, and length overruns."""
    if not isinstance(value, str):
        raise ValueError(f'{name} must be a string')
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f'{name} cannot be empty')
    if '\x00' in cleaned:
        raise ValueError(f'{name} cannot contain null bytes')
    if any(traversal in cleaned for traversal in ('..', '/', '\\')):
        raise ValueError(f'{name} contains invalid path traversal')
    if len(cleaned) > max_length:
        raise ValueError(f'{name} exceeds maximum length')
    return cleaned


def _ensure_utc(dt: Any) -> datetime:
    """Ensure a datetime is timezone-aware and converted to UTC."""
    if not isinstance(dt, datetime):
        raise ValueError('Timestamp must be a datetime instance')
    if dt.tzinfo is None:
        raise ValueError('Naive datetime not allowed')
    return dt.astimezone(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    """Safely align a datetime to UTC, converting naive to UTC if necessary."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
    clean_uid = _clean_id(uid, name='uid')
    return firestore_client.collection('users').document(clean_uid)


def intent_ref(uid: str, intent_id: str, *, firestore_client: Any):
    clean_intent_id = _clean_id(intent_id, name='intent_id')
    return user_ref(uid, firestore_client=firestore_client).collection(INTENTS_COLLECTION).document(clean_intent_id)


def delivery_attempt_ref(uid: str, intent_id: str, *, firestore_client: Any):
    clean_intent_id = _clean_id(intent_id, name='intent_id')
    return user_ref(uid, firestore_client=firestore_client).collection(DELIVERY_ATTEMPTS_COLLECTION).document(clean_intent_id)


def dead_letter_ref(uid: str, intent_id: str, *, firestore_client: Any):
    clean_intent_id = _clean_id(intent_id, name='intent_id')
    return user_ref(uid, firestore_client=firestore_client).collection(DEAD_LETTERS_COLLECTION).document(clean_intent_id)


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

    now_utc = _as_utc(now) or datetime.now(timezone.utc)
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
    reset: dict[str, Any] = {'fetch_count': preserved_fetch_count + 1, 'last_fetched_at': now_utc}
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

    terminal_at_utc = _as_utc(terminal_at) or datetime.now(timezone.utc)
    terminal = parse_payload_strict(
        DeadLetteredProactiveIntent,
        intent.model_dump(mode='python'),
        document_path='<derived-chat-first-dead-letter>',
    )
    payload = terminal.model_dump(mode='python')
    if payload.get('last_fetched_at') is None:
        payload['last_fetched_at'] = terminal_at_utc
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
    clean_uid = _clean_id(uid, name='uid')
    clean_intent_id = _clean_id(intent_id, name='intent_id')
    now_utc = _as_utc(now) or datetime.now(timezone.utc)

    dead_ref = dead_letter_ref(clean_uid, clean_intent_id, firestore_client=firestore_client)
    active_ref = intent_ref(clean_uid, clean_intent_id, firestore_client=firestore_client)
    attempt_ref = delivery_attempt_ref(clean_uid, clean_intent_id, firestore_client=firestore_client)
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
        raw_terminal_at = intent.last_rejection_at or intent.last_fetched_at
        if raw_terminal_at is None:
            return None
        terminal_at = _as_utc(raw_terminal_at)
        if terminal_at is None or now_utc - terminal_at < TRANSIENT_DEAD_LETTER_REPAIR_AGE:
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

    clean_uid = _clean_id(uid, name='uid')
    now_utc = _as_utc(now) or datetime.now(timezone.utc)
    try:
        safe_limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        safe_limit = 10

    try:
        collection = user_ref(clean_uid, firestore_client=firestore_client).collection(DEAD_LETTERS_COLLECTION)
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
            .limit(2 * safe_limit)
        )
        repaired = 0
        for snapshot in query.stream():
            if repaired >= safe_limit:
                break
            raw = snapshot.to_dict() or {}
            raw_terminal_at = raw.get('last_rejection_at') or raw.get('last_fetched_at')
            if not isinstance(raw_terminal_at, datetime):
                continue
            terminal_at = _as_utc(raw_terminal_at)
            if terminal_at is None or now_utc - terminal_at < TRANSIENT_DEAD_LETTER_REPAIR_AGE:
                continue
            try:
                if (
                    requeue(
                        clean_uid,
                        snapshot.id,
                        account_generation=account_generation,
                        now=now_utc,
                        firestore_client=firestore_client,
                    )
                    is not None
                ):
                    repaired += 1
            except ChatFirstMalformedDeliveryAttempt:
                continue
            except Exception:
                logger.exception('Failed to requeue transient dead letter snapshot %s', getattr(snapshot, 'id', None))
                continue
    except GoogleAPICallError:
        logger.exception('Chat-first transient dead-letter repair scan failed')
        return True
    except Exception:
        logger.exception('Chat-first transient dead-letter repair scan encountered unexpected error')
        return True
    return False
