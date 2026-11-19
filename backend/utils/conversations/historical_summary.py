"""Summary-on-open for historical-tier (T1+) rows: ``POST /v1/conversations/{id}/summary/open``.

A historical row (``config/historical_tier.py``) carries a transcript and a
deterministic title. Its one summary is generated when the owner opens it,
summary-only: no memories, tasks, apps, folders, webhooks or notifications
(``process_conversation``'s historical seam). Refusals answer before any model
work, in this order: 404 gone; 409 locked, discarded or not historical; 200
``existing`` (idempotent, no model); 503 switch off; 429 per-user hourly,
per-user daily or global daily cap; 409 BYOK without keys; 402 budget; 429 the
row's daily attempts; 409 another writer. Then 200 ``generated``, 502 empty
output, or a typed retryable 503.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import HTTPException
from prometheus_client import Counter, Histogram

from config import historical_tier
from database import conversations as conversations_db
from database import processing_attention as attention_db
from database import redis_db
from database import users as users_db
from database.firestore_read_metrics import FirestoreReadSite
from utils.conversations import transcribing_hold
from utils.conversations.factory import deserialize_conversation
from utils.conversations.process_conversation import process_conversation, save_structured_vector
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.summary_delivery import present
from utils.executors import postprocess_executor, submit_with_context
from utils.generated_compute import require_generated_compute, validated_llm_byok
from utils.llm.usage_tracker import Features, track_usage
from utils.observability.fallback import record_fallback
from utils.observability.reasons import HistoricalSummaryOpenOutcome, ReasonFamily, reason_label
from utils.rate_limit_config import RATE_LIMIT_SHADOW, get_effective_limit

logger = logging.getLogger(__name__)

OUTCOME_HEADER = 'X-Omi-Summary-Outcome'
HOURLY_POLICY = 'conversations:historical_summary_open'
DAILY_POLICY = 'conversations:historical_summary_open_daily'
GLOBAL_POLICY = 'historical_summary_global'
ATTEMPTS_POLICY = 'historical_summary_attempts'
COMPUTE_FEATURE = 'historical_summary_open'
MAX_ATTEMPTS_PER_ROW_PER_DAY = 3
DAY_SECONDS = 86400
TRANSIENT_RETRY_AFTER_SECONDS = 30


Outcome = HistoricalSummaryOpenOutcome


OPEN_TOTAL = Counter('omi_historical_summary_open_total', 'Historical summary-on-open requests by outcome', ['outcome'])
LATENCY = Histogram(
    'omi_historical_summary_latency_seconds',
    'Historical summary-on-open generation latency',
    buckets=(1, 2, 5, 10, 20, 30, 60, 120),
)


def _count(outcome: Outcome) -> None:
    OPEN_TOTAL.labels(
        outcome=reason_label(ReasonFamily.HISTORICAL_SUMMARY_OPEN, outcome, HistoricalSummaryOpenOutcome)
    ).inc()


def after_summary(uid: str, conversation: Any) -> None:
    """The one follow-up a landed historical summary takes: its search vector."""
    if historical_tier.vector_enabled() and present(getattr(conversation, 'structured', None)):
        submit_with_context(postprocess_executor, save_structured_vector, uid, conversation)


def _refuse(outcome: Outcome, status: int, code: str, message: str, headers: dict | None = None) -> HTTPException:
    _count(outcome)
    logger.info('event=historical_summary_open outcome=%s status=%s', outcome.value, status)
    return HTTPException(status_code=status, detail={'code': code, 'message': message}, headers=headers)


def _reserve(key: str, policy: str, limit: int, window: int = DAY_SECONDS) -> tuple[bool, int, bool]:
    """(allowed, reset_seconds, reserved). Redis outages fail open (David, 2026-11-18)."""
    try:
        allowed, _, reset = redis_db.reserve_rate_limit(key, policy, limit, window)
        return allowed, reset, allowed
    except Exception:
        record_fallback(
            component='redis_ratelimit',
            from_mode=policy,
            to_mode='unlimited',
            reason='gate_unavailable',
            outcome='degraded',
        )
        return True, 0, False


def _release(key: str, policy: str) -> None:
    try:
        redis_db.release_rate_limit(key, policy)
    except Exception:
        logger.warning('event=historical_summary_open release_failed policy=%s', policy)


def release(slots: list[tuple[str, str]]) -> None:
    """Return reserved slots after a refusal; an admitted generation keeps them."""
    for key, policy in slots:
        _release(key, policy)


def _llm_key_funded(uid: str) -> bool:
    # A BYOK account's summaries run on its own LLM key, which only the request carries.
    return not users_db.is_byok_active(uid) or validated_llm_byok(uid)


def _retry(error: BaseException | None = None, outcome: Outcome = Outcome.TRANSIENT) -> HTTPException:
    if error is not None:
        logger.warning('event=historical_summary_open outcome=transient exception_type=%s', type(error).__name__)
    return _refuse(
        outcome,
        503,
        'historical_summary_retry',
        'The summary could not be written; try again',
        {'Retry-After': str(TRANSIENT_RETRY_AFTER_SECONDS)},
    )


def _take(slots: list, key: str, policy: str, limit: int, window: int, outcome: Outcome, code: str, message: str):
    allowed, reset, held = _reserve(key, policy, limit, window)
    if not allowed:
        if outcome is Outcome.RATE_LIMITED and RATE_LIMIT_SHADOW:
            logger.warning('event=historical_summary_open shadow_rate_limit policy=%s', policy)
            return
        raise _refuse(outcome, 429, code, message, {'Retry-After': str(max(reset, 1))})
    if held:
        slots.append((key, policy))


def admit(uid: str, conversation_id: str) -> list[tuple[str, str]]:
    """Every gate an owner-triggered historical generation takes (open and ``/reprocess``).

    Free refusals (switch, BYOK, budget) answer before any slot is taken. Then the
    owner's hourly and daily slots, the fleet slot and the row's attempt slot are
    reserved; any later refusal or store error returns them all.
    """
    if not historical_tier.open_enabled():
        raise _refuse(Outcome.DISABLED, 503, 'historical_summary_disabled', 'Summary on open is turned off')
    slots: list[tuple[str, str]] = []
    try:
        if not _llm_key_funded(uid):
            raise _refuse(Outcome.BYOK_REQUIRED, 409, 'byok_keys_required', 'Summarize this on a device with your keys')
        try:
            require_generated_compute(uid, COMPUTE_FEATURE)
        except HTTPException:
            _count(Outcome.BUDGET)
            raise
        for policy in (HOURLY_POLICY, DAILY_POLICY):
            limit, window = get_effective_limit(policy)
            _take(
                slots, uid, policy, limit, window, Outcome.RATE_LIMITED, 'rate_limited', 'Too many summaries; try later'
            )
        limit = historical_tier.global_daily_limit()
        if limit:
            _take(
                slots,
                'global',
                GLOBAL_POLICY,
                limit,
                DAY_SECONDS,
                Outcome.GLOBAL_LIMITED,
                'historical_summary_global_limit',
                'Summaries are busy today; try again later',
            )
        _take(
            slots,
            f'{uid}:{conversation_id}',
            ATTEMPTS_POLICY,
            MAX_ATTEMPTS_PER_ROW_PER_DAY,
            DAY_SECONDS,
            Outcome.ATTEMPTS_EXHAUSTED,
            'historical_summary_attempts_exhausted',
            'This summary was retried too often today',
        )
        return slots
    except HTTPException:
        release(slots)
        raise
    except Exception as error:
        release(slots)
        raise _retry(error) from error


def _claim(uid: str, conversation_id: str, row: dict[str, Any], slots: list) -> dict:
    try:
        try:
            operation, owned = attention_db.claim(
                uid, conversation_id, expected_generation=attention_db.generation(row), restart_succeeded=True
            )
        except attention_db.ClaimRejected as error:
            raise _refuse(Outcome.NOT_FOUND, 404, 'not_found', 'Conversation not found') from error
        if not owned or not attention_db.owns_live_claim(uid, operation):
            raise _refuse(
                Outcome.BUSY, 409, 'conversation_processing_in_progress', 'Conversation is already being processed'
            )
        return operation
    except HTTPException:
        release(slots)
        raise
    except Exception as error:
        release(slots)
        raise _retry(error) from error


def _generate(uid: str, row: dict[str, Any]) -> tuple[Any, bool]:
    conversation = deserialize_conversation(row)
    persisted: list[bool] = []
    with track_usage(uid, Features.HISTORICAL_SUMMARY):
        processed = process_conversation(
            uid,
            conversation.language or 'en',
            conversation,
            trigger=ProcessingTrigger.HISTORICAL_OPEN,
            first_party_only=True,
            persistence_observer=persisted.append,
        )
    # A fenced write (a newer append won the revision) landed nothing: it is not a summary.
    return processed, all(persisted)


def _reread(uid: str, conversation_id: str, operation: dict, slots: list) -> dict[str, Any]:
    try:
        current = conversations_db.get_conversation(
            uid, conversation_id, read_site=FirestoreReadSite.CONVERSATIONS_VALID_BY_ID
        )
    except Exception as error:
        attention_db.finish(uid, operation, 'failed')
        release(slots)
        raise _retry(error) from error
    if current is None or conversations_db.is_soft_deleted(current):
        attention_db.finish(uid, operation, 'failed')
        release(slots)
        raise _refuse(Outcome.NOT_FOUND, 404, 'not_found', 'Conversation not found')
    if present(current.get('structured')):
        attention_db.finish(uid, operation, 'succeeded')
        release(slots)
    return current


def open_summary(uid: str, conversation_id: str) -> tuple[Any, str]:
    """Return ``(wire body, outcome)`` or raise the typed refusal."""
    row = conversations_db.get_conversation(uid, conversation_id, read_site=FirestoreReadSite.CONVERSATIONS_VALID_BY_ID)
    if row is None or conversations_db.is_soft_deleted(row) or row.get('recording'):
        raise _refuse(Outcome.NOT_FOUND, 404, 'not_found', 'Conversation not found')
    if row.get('is_locked'):
        raise _refuse(Outcome.LOCKED, 409, 'conversation_locked', 'A paid plan is required to open this conversation')
    if row.get('discarded'):
        raise _refuse(Outcome.DISCARDED, 409, 'conversation_discarded', 'Restore this conversation first')
    if not historical_tier.is_historical(row):
        raise _refuse(Outcome.NOT_HISTORICAL, 409, 'not_historical', 'Use reprocess for this conversation')
    if present(row.get('structured')):
        _count(Outcome.EXISTING)
        return transcribing_hold.project(row), Outcome.EXISTING.value
    slots = admit(uid, conversation_id)
    operation = _claim(uid, conversation_id, row, slots)
    current = _reread(uid, conversation_id, operation, slots)
    if present(current.get('structured')):
        # Another open landed the summary between our read and our claim.
        _count(Outcome.EXISTING)
        return transcribing_hold.project(current), Outcome.EXISTING.value
    started = time.monotonic()
    try:
        processed, persisted = _generate(uid, current)
    except HTTPException:
        attention_db.finish(uid, operation, 'failed')
        _count(Outcome.TRANSIENT)
        raise
    except Exception as error:
        attention_db.finish(uid, operation, 'failed')
        raise _retry(error) from error
    if not persisted:
        attention_db.finish(uid, operation, 'failed')
        raise _retry(outcome=Outcome.FENCED)
    if not present(getattr(processed, 'structured', None)):
        attention_db.finish(uid, operation, 'failed')
        raise _refuse(Outcome.EMPTY, 502, 'summary_unavailable', 'No summary could be written for this conversation')
    attention_db.finish(uid, operation, 'succeeded')
    after_summary(uid, processed)
    LATENCY.observe(time.monotonic() - started)
    _count(Outcome.GENERATED)
    logger.info('event=historical_summary_open outcome=generated')
    return processed, Outcome.GENERATED.value
