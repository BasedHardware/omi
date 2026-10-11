"""Per-attempt v2 admission at the gateway's actual provider boundary."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from config.proactivity_v2 import AttemptEnvelope, ProactivityDenied, producer_for
from llm_gateway.gateway.accounting import (
    AccountingContext,
    AttemptTrace,
    UsageStatus,
    build_accounting_event,
    rate_card_for,
)
from llm_gateway.gateway.errors import GatewayInvalidRequestError, PROACTIVITY_ADMISSION_REASONS
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProactivityAttemptContext:
    uid: str
    item_id: str
    producer: str
    call_id: str
    step: str
    accounting: AccountingContext


_current: ContextVar[ProactivityAttemptContext | None] = ContextVar('proactivity_v2_attempt', default=None)


def current_attempt() -> ProactivityAttemptContext | None:
    return _current.get()


@contextmanager
def attempt_scope(value: ProactivityAttemptContext | None):
    token = _current.set(value)
    try:
        yield
    finally:
        _current.reset(token)


def context_from_request(request: Any, caller: Any, accounting: AccountingContext) -> ProactivityAttemptContext | None:
    values = [request.headers.get(f'x-omi-proactivity-{field}') for field in ('item', 'producer', 'call', 'step')]
    feature_is_v2 = (caller.usage_feature or '').startswith('proactivity_v2_')
    if not any(values) and not feature_is_v2:
        return None
    item, producer, call, step = values
    if not all(values) or caller.name != 'backend' or not caller.user_uid or accounting.payer != 'omi':
        raise GatewayInvalidRequestError('invalid proactivity identity', rejection_reason='proactivity_identity')
    if len(item) != 32 or any(c not in '0123456789abcdef' for c in item):
        raise GatewayInvalidRequestError('invalid proactivity item', rejection_reason='proactivity_item')
    try:
        producer_for(producer)
        if str(UUID(call)) != call:
            raise ValueError('noncanonical call id')
    except (ValueError, ProactivityDenied) as exc:
        raise GatewayInvalidRequestError(
            'invalid proactivity identity', rejection_reason='proactivity_identity'
        ) from exc
    if (
        step not in {'gate', 'generate', 'critic', 'prefilter', 'dedupe', 'usefulness', 'phrase'}
        or accounting.request_id != call
        or accounting.feature != f'proactivity_v2_{producer}'
    ):
        raise GatewayInvalidRequestError('invalid proactivity attribution', rejection_reason='proactivity_attribution')
    if producer == 'commitment_followup' and step != 'phrase':
        raise GatewayInvalidRequestError('invalid proactivity step', rejection_reason='proactivity_step')
    return ProactivityAttemptContext(caller.user_uid, item, producer, call, step, accounting)


def envelope_for(
    context: ProactivityAttemptContext, provider: str, model: str, request: dict[str, Any]
) -> AttemptEnvelope:
    row = producer_for(context.producer)
    jev = provider == 'openrouter' and model == 'typesafe/jev-1.13'
    if not jev and (provider, model) != ('openai', 'gpt-6-luna'):
        raise ProactivityDenied('unsupported_model')
    if jev != (context.step in {'prefilter', 'dedupe', 'usefulness'}):
        raise ProactivityDenied('invalid_lane')
    payload = dict(request, model=model)
    if jev:
        if set(payload) - {'model', 'state', 'questions'} or not isinstance(payload.get('state'), str):
            raise ProactivityDenied('invalid_request')
        output_tokens = 0
    else:
        allowed = {
            'model',
            'messages',
            'stream',
            'response_format',
            'max_completion_tokens',
            'reasoning_effort',
            'temperature',
            'top_p',
        }
        if set(payload) - allowed or payload.get('stream') is True:
            raise ProactivityDenied('invalid_request')
        messages = payload.get('messages')
        if not isinstance(messages, list) or not messages or len(messages) > 32:
            raise ProactivityDenied('invalid_request')
        if any(
            not isinstance(m, dict) or not isinstance(m.get('content'), str) or set(m) - {'role', 'content'}
            for m in messages
        ):
            raise ProactivityDenied('invalid_request')
        output_tokens = payload.get('max_completion_tokens')
        if type(output_tokens) is not int or not 1 <= output_tokens <= row.max_output_tokens:
            raise ProactivityDenied('invalid_output_bound')
    serialized = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode()
    if len(serialized) > row.max_request_bytes:
        raise ProactivityDenied('input_bound')
    # Text tokenizers cannot produce more tokens than UTF-8 bytes. Include schema,
    # question names/options and wire punctuation, plus 4096 tokens for fixed model
    # framing (<=32 chat messages). Only these two pinned text models are supported.
    input_bound = len(serialized) + 4096
    card = rate_card_for(provider, model)
    if card is None:
        raise ProactivityDenied('unpriced')
    rates = card.effective_rates(input_bound)
    numerator = input_bound * rates.input_micro_usd_per_million + output_tokens * rates.output_micro_usd_per_million
    return AttemptEnvelope(
        provider,
        model,
        card.rate_card_id,
        (numerator + 999999) // 1000000,
        hashlib.sha256(serialized).hexdigest(),
        context.step,
    )


async def execute_budgeted_provider(
    *,
    request: dict[str, Any],
    provider_ref: Any,
    route: Any,
    credentials: Any,
    provider_call: Any,
    timeout_ms: int,
    attempt_trace: AttemptTrace,
) -> Any:
    context = current_attempt()
    if context is None:
        raise GatewayInvalidRequestError(
            'missing proactivity authority', rejection_reason='proactivity_authority_missing'
        )
    try:
        if os.getenv('LLM_GATEWAY_ACCOUNTING_ENABLED', '').lower() not in {'true', '1', 'yes'}:
            raise ProactivityDenied('accounting_disabled')
        # Backend admission dependencies are needed only for v2 attempts, never
        # for gateway startup or ordinary gateway traffic.
        from database.proactivity_budget import BudgetAuthority
        from utils.proactivity import ensure_admitted

        await ensure_admitted(context.uid, context.producer)
        envelope = envelope_for(context, provider_ref.provider, provider_ref.model, request)
        authority = BudgetAuthority()
        reservation = await run_blocking(
            db_executor,
            authority.reserve,
            uid=context.uid,
            item_id=context.item_id,
            producer=context.producer,
            call_id=context.call_id,
            envelope=envelope,
        )
    except Exception as exc:
        reason = exc.reason if isinstance(exc, ProactivityDenied) else 'unavailable'
        reason = reason if reason in PROACTIVITY_ADMISSION_REASONS else 'unknown'
        logger.info('proactivity_v2_admission producer=%s result=denied reason=%s', context.producer, reason)
        raise GatewayInvalidRequestError(
            f'proactivity admission denied: {reason}',
            param='proactivity_admission',
            rejection_reason=f'proactivity_admission.{reason}',
        ) from exc
    if timeout_ms <= 0:
        await run_blocking(db_executor, authority.release_unsent, reservation=reservation)
        raise GatewayInvalidRequestError('proactivity deadline elapsed', rejection_reason='proactivity_deadline')
    try:
        response = await asyncio.wait_for(
            provider_call(request, provider_ref=provider_ref, credentials=credentials, timeout_ms=timeout_ms),
            timeout=timeout_ms / 1000,
        )
    except BaseException as exc:
        attempt = attempt_trace.record(
            provider=provider_ref.provider,
            configured_model=provider_ref.model,
            route_artifact_id=route.route_artifact_id,
            fallback_reason=None,
            retry_ordinal=1,
            outcome='error',
            error_class='provider_failed',
            usage_status=UsageStatus.INDETERMINATE,
        )
        event = build_accounting_event(context.accounting, attempt)
        try:
            await run_blocking(db_executor, authority.settle, reservation=reservation, event=event)
        except Exception:
            logger.warning('proactivity_v2_budget_settled producer=%s result=held', context.producer)
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise GatewayInvalidRequestError(
            'proactivity provider failed; reservation retained', rejection_reason='proactivity_provider_failed'
        ) from exc
    attempt = attempt_trace.record(
        provider=provider_ref.provider,
        configured_model=provider_ref.model,
        route_artifact_id=route.route_artifact_id,
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=response.accounting,
        usage_status=(
            UsageStatus.CONFIRMED
            if response.accounting.usage is not None and response.accounting.billable_usage_complete
            else UsageStatus.INDETERMINATE
        ),
    )
    event = build_accounting_event(context.accounting, attempt)
    try:
        settled = await run_blocking(db_executor, authority.settle, reservation=reservation, event=event)
    except Exception as exc:
        raise GatewayInvalidRequestError(
            'proactivity settlement unavailable', rejection_reason='proactivity_settlement_unavailable'
        ) from exc
    if not settled:
        logger.error(
            'proactivity_v2_budget_invariant_failed producer=%s result=held_or_over_reserved', context.producer
        )
        raise GatewayInvalidRequestError(
            'proactivity settlement rejected', rejection_reason='proactivity_settlement_rejected'
        )
    return response
