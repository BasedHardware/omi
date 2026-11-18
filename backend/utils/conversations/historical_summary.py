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
from enum import StrEnum
from typing import Any, Mapping

from fastapi import HTTPException
from prometheus_client import Counter, Histogram

from config import historical_tier
from database import conversations as conversations_db
from database import processing_attention as attention_db
from database import redis_db
from database import users as users_db
from database.firestore_read_metrics import FirestoreReadSite
from utils import byok
from utils.conversations import transcribing_hold
from utils.conversations.factory import deserialize_conversation
from utils.conversations.process_conversation import process_conversation, save_structured_vector
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.summary_delivery import present
from utils.executors import postprocess_executor, submit_with_context
from utils.generated_compute import require_generated_compute
from utils.llm.usage_tracker import Features, track_usage
from utils.observability.fallback import record_fallback
from utils.other.endpoints import check_rate_limit_inline

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


class Outcome(StrEnum):
    EXISTING = 'existing'
    GENERATED = 'generated'
    NOT_FOUND = 'not_found'
    LOCKED = 'locked'
    DISCARDED = 'discarded'
    NOT_HISTORICAL = 'not_historical'
    DISABLED = 'disabled'
    RATE_LIMITED = 'rate_limited'
    GLOBAL_LIMITED = 'global_limited'
    BYOK_REQUIRED = 'byok_keys_required'
    BUDGET = 'budget'
    ATTEMPTS_EXHAUSTED = 'attempts_exhausted'
    BUSY = 'busy'
    EMPTY = 'empty'
    TRANSIENT = 'transient'


OPEN_TOTAL = Counter('omi_historical_summary_open_total', 'Historical summary-on-open requests by outcome', ['outcome'])
LATENCY = Histogram(
    'omi_historical_summary_latency_seconds',
    'Historical summary-on-open generation latency',
    buckets=(1, 2, 5, 10, 20, 30, 60, 120),
)


def summary_on_open(row: Mapping[str, Any]) -> bool:
    return bool(
        historical_tier.is_historical(dict(row))
        and not present(row.get('structured'))
        and not row.get('is_locked')
        and not row.get('discarded')
        and historical_tier.open_enabled()
    )


def project(row: dict[str, Any]) -> dict[str, Any]:
    """Wire copy advertising ``summary_on_open``; nothing is stored."""
    return {**row, 'summary_on_open': True} if summary_on_open(row) else row


def after_summary(uid: str, conversation: Any) -> None:
    """The one follow-up a landed historical summary takes: its search vector."""
    if historical_tier.vector_enabled() and present(getattr(conversation, 'structured', None)):
        submit_with_context(postprocess_executor, save_structured_vector, uid, conversation)


def _refuse(outcome: Outcome, status: int, code: str, message: str, headers: dict | None = None) -> HTTPException:
    OPEN_TOTAL.labels(outcome=outcome.value).inc()
    logger.info('event=historical_summary_open outcome=%s status=%s', outcome.value, status)
    return HTTPException(status_code=status, detail={'code': code, 'message': message}, headers=headers)


def _reserve(key: str, policy: str, limit: int) -> tuple[bool, int, bool]:
    """(allowed, reset_seconds, reserved). Redis outages fail open (David, 2026-11-18)."""
    try:
        allowed, _, reset = redis_db.reserve_rate_limit(key, policy, limit, DAY_SECONDS)
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


def _admit(uid: str, conversation_id: str, row: dict[str, Any]) -> tuple[dict, list[tuple[str, str]]]:
    """Every gate after the idempotent read; returns the attention claim and slots to release on refusal."""
    if not historical_tier.open_enabled():
        raise _refuse(Outcome.DISABLED, 503, 'historical_summary_disabled', 'Summary on open is turned off')
    for policy in (HOURLY_POLICY, DAILY_POLICY):
        try:
            check_rate_limit_inline(uid, policy)
        except HTTPException as error:
            OPEN_TOTAL.labels(outcome=Outcome.RATE_LIMITED.value).inc()
            raise error
    reserved: list[tuple[str, str]] = []
    try:
        limit = historical_tier.global_daily_limit()
        if limit:
            allowed, reset, held = _reserve('global', GLOBAL_POLICY, limit)
            if not allowed:
                raise _refuse(
                    Outcome.GLOBAL_LIMITED,
                    429,
                    'historical_summary_global_limit',
                    'Summaries are busy today; try again later',
                    {'Retry-After': str(max(reset, 1))},
                )
            if held:
                reserved.append(('global', GLOBAL_POLICY))
        # A BYOK account's summaries run on its own keys, which only the request carries.
        if users_db.is_byok_active(uid) and not byok.has_validated_byok_keys():
            raise _refuse(Outcome.BYOK_REQUIRED, 409, 'byok_keys_required', 'Summarize this on a device with your keys')
        try:
            require_generated_compute(uid, COMPUTE_FEATURE)
        except HTTPException:
            OPEN_TOTAL.labels(outcome=Outcome.BUDGET.value).inc()
            raise
        attempt_key = f'{uid}:{conversation_id}'
        allowed, reset, held = _reserve(attempt_key, ATTEMPTS_POLICY, MAX_ATTEMPTS_PER_ROW_PER_DAY)
        if not allowed:
            raise _refuse(
                Outcome.ATTEMPTS_EXHAUSTED,
                429,
                'historical_summary_attempts_exhausted',
                'This summary was retried too often today',
                {'Retry-After': str(max(reset, 1))},
            )
        if held:
            reserved.append((attempt_key, ATTEMPTS_POLICY))
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
        return operation, reserved
    except HTTPException:
        for key, policy in reserved:
            _release(key, policy)
        raise


def _generate(uid: str, row: dict[str, Any]) -> Any:
    conversation = deserialize_conversation(row)
    with track_usage(uid, Features.HISTORICAL_SUMMARY):
        return process_conversation(
            uid,
            conversation.language or 'en',
            conversation,
            trigger=ProcessingTrigger.HISTORICAL_OPEN,
            first_party_only=True,
        )


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
        OPEN_TOTAL.labels(outcome=Outcome.EXISTING.value).inc()
        return transcribing_hold.project(row), Outcome.EXISTING.value
    operation, _reserved = _admit(uid, conversation_id, row)
    started = time.monotonic()
    try:
        processed = _generate(uid, row)
    except HTTPException:
        attention_db.finish(uid, operation, 'failed')
        OPEN_TOTAL.labels(outcome=Outcome.TRANSIENT.value).inc()
        raise
    except Exception as error:
        attention_db.finish(uid, operation, 'failed')
        logger.warning('event=historical_summary_open outcome=transient exception_type=%s', type(error).__name__)
        raise _refuse(
            Outcome.TRANSIENT,
            503,
            'historical_summary_retry',
            'The summary could not be written; try again',
            {'Retry-After': str(TRANSIENT_RETRY_AFTER_SECONDS)},
        ) from error
    if not present(getattr(processed, 'structured', None)):
        attention_db.finish(uid, operation, 'failed')
        raise _refuse(Outcome.EMPTY, 502, 'summary_unavailable', 'No summary could be written for this conversation')
    attention_db.finish(uid, operation, 'succeeded')
    after_summary(uid, processed)
    LATENCY.observe(time.monotonic() - started)
    OPEN_TOTAL.labels(outcome=Outcome.GENERATED.value).inc()
    logger.info('event=historical_summary_open outcome=generated')
    return processed, Outcome.GENERATED.value
