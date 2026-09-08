"""Bounded, non-fatal persistence for gateway accounting events."""

from __future__ import annotations

import asyncio
import logging
import os

from database.llm_gateway_accounting import record_llm_gateway_attempt
from llm_gateway.gateway.accounting import AccountingContext, AttemptTrace, ProviderAttempt, build_accounting_event
from llm_gateway.gateway.metrics import observe_accounting_event
from utils.executors import db_executor, run_blocking

ACCOUNTING_ENABLED_ENV_VAR = 'LLM_GATEWAY_ACCOUNTING_ENABLED'
ACCOUNTING_WRITE_TIMEOUT_SECONDS_ENV_VAR = 'LLM_GATEWAY_ACCOUNTING_WRITE_TIMEOUT_SECONDS'
ACCOUNTING_MAX_PENDING_TRACES_ENV_VAR = 'LLM_GATEWAY_ACCOUNTING_MAX_PENDING_TRACES'
DEFAULT_ACCOUNTING_WRITE_TIMEOUT_SECONDS = 1.0
DEFAULT_ACCOUNTING_MAX_PENDING_TRACES = 1_000
_background_persistence_tasks: set[asyncio.Task[None]] = set()
logger = logging.getLogger(__name__)


def schedule_attempt_trace(context: AccountingContext, trace: AttemptTrace) -> None:
    """Best-effort persist an immutable copy after the response has completed.

    Accounting must not add Firestore latency to model responses or streaming
    tails. Pending work is explicitly bounded: overflow is not silently lost,
    but observed as a dropped accounting event for alerting and reconciliation.
    """
    if not accounting_enabled() or not trace.attempts:
        return
    if len(_background_persistence_tasks) >= accounting_max_pending_traces():
        _observe_dropped_trace(context, trace)
        return
    snapshot = AttemptTrace(attempts=list(trace.attempts))
    task = asyncio.create_task(
        persist_attempt_trace(context, snapshot),
        name='llm-gateway-accounting-persistence',
    )
    _background_persistence_tasks.add(task)
    task.add_done_callback(_background_persistence_tasks.discard)


async def drain_accounting_persistence_tasks() -> None:
    """Give scheduled writes one configured timeout during orderly shutdown."""
    pending = tuple(_background_persistence_tasks)
    if pending:
        await asyncio.wait(pending, timeout=accounting_write_timeout_seconds())


async def persist_attempt_trace(context: AccountingContext, trace: AttemptTrace) -> None:
    """Persist all attempts in a trace concurrently without affecting serving.

    A timeout or Firestore failure is reflected in the bounded delivery metric,
    never converted into a user-facing model failure.
    """
    if not accounting_enabled():
        return
    await asyncio.gather(*(_persist_attempt(context, attempt) for attempt in trace.attempts))


async def _persist_attempt(context: AccountingContext, attempt: ProviderAttempt) -> None:
    """Bound one write so retry/fallback attempts can flush concurrently."""
    event = None
    try:
        event = build_accounting_event(context, attempt)
        created = await asyncio.wait_for(
            run_blocking(db_executor, record_llm_gateway_attempt, event.as_dict()),
            timeout=accounting_write_timeout_seconds(),
        )
    except Exception:
        if event is not None:
            observe_accounting_event(event, delivery='failed')
        else:
            logger.warning(
                'llm_gateway_accounting_event_build_failed provider=%s model=%s',
                attempt.provider,
                attempt.configured_model,
            )
        return
    observe_accounting_event(event, delivery='written' if created else 'duplicate')


def _observe_dropped_trace(context: AccountingContext, trace: AttemptTrace) -> None:
    """Expose bounded-queue overflow without storing a partial event."""
    for attempt in trace.attempts:
        try:
            event = build_accounting_event(context, attempt)
        except Exception:
            logger.warning(
                'llm_gateway_accounting_drop_observation_failed provider=%s model=%s',
                attempt.provider,
                attempt.configured_model,
            )
            continue
        observe_accounting_event(event, delivery='dropped')


def accounting_enabled() -> bool:
    return os.getenv(ACCOUNTING_ENABLED_ENV_VAR, '').strip().lower() in {'1', 'true', 'yes'}


def accounting_write_timeout_seconds() -> float:
    raw = os.getenv(ACCOUNTING_WRITE_TIMEOUT_SECONDS_ENV_VAR, '').strip()
    if not raw:
        return DEFAULT_ACCOUNTING_WRITE_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_ACCOUNTING_WRITE_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_ACCOUNTING_WRITE_TIMEOUT_SECONDS


def accounting_max_pending_traces() -> int:
    raw = os.getenv(ACCOUNTING_MAX_PENDING_TRACES_ENV_VAR, '').strip()
    if not raw:
        return DEFAULT_ACCOUNTING_MAX_PENDING_TRACES
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_ACCOUNTING_MAX_PENDING_TRACES
    return value if value > 0 else DEFAULT_ACCOUNTING_MAX_PENDING_TRACES
