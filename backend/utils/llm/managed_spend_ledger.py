"""Ledger rows for managed model spend that bypasses the LLM gateway.

The gateway writes one immutable row per provider attempt to the Firestore
collection ``llm_gateway_attempts`` (``database.llm_gateway_accounting``). Two
backend surfaces call providers directly and were invisible to that ledger:

* ``routers/desktop_proxy.py`` — direct Vertex / AI Studio Gemini calls that do
  not hop the gateway (BYOK, batch embeddings, ``FEATURE_MODE=off``).
* ``routers/omni_relay.py`` — the legacy realtime WebSocket relay.

This module lets those surfaces record the same event shape into the same
collection, so "managed spend for uid X grouped by feature" is one query
regardless of which door the call went through. It builds the event with the
gateway's own ``build_accounting_event`` and persists it with the gateway's own
DB helper; there is no second ledger.

Rules, matching ``llm_gateway.gateway.accounting_sink``:

* Gated by ``LLM_GATEWAY_ACCOUNTING_ENABLED`` on the serving identity, read at
  call time. Off means no write and no error.
* Best-effort and bounded: a write never delays or fails the model call, is
  given one timeout, and pending writes are capped so a Firestore outage cannot
  grow the process without bound.
* Bounded metadata only: no prompts, provider payloads, headers, or keys.
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from threading import RLock
from typing import Any
from uuid import uuid4

from database.llm_gateway_accounting import record_llm_gateway_attempt
from llm_gateway.gateway.accounting import (
    AccountingContext,
    AccountingEvent,
    PricedUsage,
    ProviderAttempt,
    ProviderResponseMetadata,
    UsageStatus,
    build_accounting_event,
)

logger = logging.getLogger(__name__)

# Same switch and knobs as the gateway sink; one identity, one contract. The
# names are duplicated rather than imported because the sink module pulls the
# gateway's Prometheus registry into whichever process imports it.
ACCOUNTING_ENABLED_ENV_VAR = 'LLM_GATEWAY_ACCOUNTING_ENABLED'
ACCOUNTING_WRITE_TIMEOUT_SECONDS_ENV_VAR = 'LLM_GATEWAY_ACCOUNTING_WRITE_TIMEOUT_SECONDS'
ACCOUNTING_MAX_PENDING_TRACES_ENV_VAR = 'LLM_GATEWAY_ACCOUNTING_MAX_PENDING_TRACES'
DEFAULT_ACCOUNTING_WRITE_TIMEOUT_SECONDS = 1.0
DEFAULT_ACCOUNTING_MAX_PENDING_TRACES = 1_000

# ``caller`` values: which door the attempt went through.
DESKTOP_PROXY_CALLER = 'desktop_proxy'
OMNI_RELAY_CALLER = 'omni_relay'
# ``feature`` for realtime voice on every route (relay today, direct hub via
# ``/v2/realtime/usage`` later). Deliberately the same word as the
# ``llm_usage`` account those turns already debit, so both ledgers agree.
DESKTOP_REALTIME_FEATURE = 'desktop_chat_realtime'

# Ledger writes get their own two threads. The cap below counts the underlying
# Firestore calls until they actually return, so a hung Firestore can occupy at
# most this pool plus the capped queue and never a shared executor that gates
# quota or auth reads.
_LEDGER_WORKERS = 2
_ledger_executor: ThreadPoolExecutor | None = None
_ledger_state_lock = RLock()
_pending_writes: set[Future[bool]] = set()
_ledger_shutdown_in_progress = False


def _get_ledger_executor() -> ThreadPoolExecutor:
    global _ledger_executor
    with _ledger_state_lock:
        if _ledger_executor is None:
            _ledger_executor = ThreadPoolExecutor(max_workers=_LEDGER_WORKERS, thread_name_prefix='spend-ledger')
        return _ledger_executor


def _discard_pending_write(future: Future[bool]) -> None:
    with _ledger_state_lock:
        _pending_writes.discard(future)


@dataclass(frozen=True)
class ManagedAttempt:
    """One provider attempt made outside the gateway, in ledger terms."""

    request_id: str
    caller: str
    user_uid: str | None
    feature: str
    api_surface: str
    payer: str
    provider: str
    configured_model: str
    outcome: str
    app_platform: str | None = 'desktop'
    route_artifact_id: str | None = None
    error_class: str = 'none'
    retry_ordinal: int = 1
    fallback_reason: str | None = None
    metadata: ProviderResponseMetadata | None = None
    usage_status: UsageStatus | None = None
    priced: PricedUsage | None = None
    # One invocation per session with an increasing ordinal groups a realtime
    # session's turns; a plain request leaves both at their defaults.
    invocation_id: str | None = None
    ordinal: int = 1


def build_managed_attempt_event(attempt: ManagedAttempt) -> AccountingEvent:
    """The exact ledger event the gateway would write for this attempt."""
    metadata = attempt.metadata or ProviderResponseMetadata()
    usage_status = attempt.usage_status or (
        UsageStatus.CONFIRMED if metadata.usage is not None else UsageStatus.NOT_REPORTED
    )
    context = AccountingContext(
        invocation_id=attempt.invocation_id or str(uuid4()),
        request_id=attempt.request_id,
        caller=attempt.caller,
        user_uid=attempt.user_uid,
        feature=attempt.feature,
        api_surface=attempt.api_surface,
        payer=attempt.payer,
        app_platform=attempt.app_platform,
    )
    provider_attempt = ProviderAttempt(
        ordinal=max(attempt.ordinal, 1),
        provider=attempt.provider,
        configured_model=attempt.configured_model,
        route_artifact_id=attempt.route_artifact_id,
        fallback_reason=attempt.fallback_reason,
        retry_ordinal=max(attempt.retry_ordinal, 1),
        outcome=attempt.outcome,
        error_class=attempt.error_class,
        usage=metadata.usage,
        usage_status=usage_status,
        provider_response_id=metadata.provider_response_id,
        actual_model_version=metadata.actual_model_version,
        traffic_type=metadata.traffic_type,
    )
    return build_accounting_event(context, provider_attempt, priced=attempt.priced)


def record_managed_attempt(attempt: ManagedAttempt, *, firestore_client: Any | None = None) -> bool:
    """Synchronously persist one attempt. Raises on failure; callers decide the policy.

    The customer data plane is the target: the ledger snapshots the user's
    subscription tier from ``users/{uid}``, and on desktop-backend that document
    lives in the customer project, not the compute project.
    """
    if firestore_client is None:
        from database._client import get_customer_firestore_client

        firestore_client = get_customer_firestore_client()
    event = build_managed_attempt_event(attempt)
    return record_llm_gateway_attempt(event.as_dict(), firestore_client=firestore_client)


def schedule_managed_attempt(attempt: ManagedAttempt) -> bool:
    """Best-effort background persist. Returns whether a write was scheduled.

    Never raises and never blocks the caller. Returns ``False`` when accounting
    is disabled, when the pending-write cap is reached, or when there is no
    running event loop to own the write. The cap counts Firestore calls that
    have not returned yet, not asyncio wrappers, so it bounds real work.
    """
    if not accounting_enabled():
        return False
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning(
            'managed_spend_ledger_dropped caller=%s feature=%s reason=no_event_loop', attempt.caller, attempt.feature
        )
        return False
    # No request context is copied into the write: the attempt already holds
    # every field the row needs, and a request's context vars can carry
    # validated BYOK credentials that a stalled write must not keep alive.
    with _ledger_state_lock:
        if _ledger_shutdown_in_progress:
            logger.warning(
                'managed_spend_ledger_dropped caller=%s feature=%s reason=shutdown', attempt.caller, attempt.feature
            )
            return False
        if len(_pending_writes) >= accounting_max_pending_traces():
            logger.warning(
                'managed_spend_ledger_dropped caller=%s feature=%s reason=pending_cap', attempt.caller, attempt.feature
            )
            return False
        try:
            future = _get_ledger_executor().submit(record_managed_attempt, attempt)
        except RuntimeError:
            # Interpreter shutdown: the executor no longer accepts work.
            return False
        _pending_writes.add(future)
        future.add_done_callback(_discard_pending_write)
    loop.create_task(_observe(attempt, asyncio.wrap_future(future, loop=loop)), name='managed-spend-ledger-persistence')
    return True


async def _observe(attempt: ManagedAttempt, future: 'asyncio.Future[bool]') -> None:
    """Log a slow or failed write. The write itself is neither cancelled nor awaited on the request path."""
    try:
        await asyncio.wait_for(asyncio.shield(future), timeout=accounting_write_timeout_seconds())
    except asyncio.TimeoutError:
        logger.warning(
            'managed_spend_ledger_write_slow caller=%s feature=%s provider=%s',
            attempt.caller,
            attempt.feature,
            attempt.provider,
        )
    except Exception:
        # The attempt already happened and the response is already on its way;
        # the only thing left to protect is the process. UIDs stay out of logs.
        logger.warning(
            'managed_spend_ledger_write_failed caller=%s feature=%s provider=%s',
            attempt.caller,
            attempt.feature,
            attempt.provider,
        )


async def drain_pending_writes() -> None:
    """Give scheduled writes one configured timeout during orderly shutdown (and tests)."""
    loop = asyncio.get_running_loop()
    with _ledger_state_lock:
        pending = [asyncio.wrap_future(future, loop=loop) for future in tuple(_pending_writes)]
    if pending:
        await asyncio.wait(pending, timeout=accounting_write_timeout_seconds())


async def shutdown_managed_spend_ledger() -> None:
    """Drain accepted writes and close the private executor for app shutdown.

    The executor is detached before shutdown so a later in-process app/test
    lifespan can lazily create a fresh pool. Already-running writes are not
    cancelled after the bounded drain; they retain the best-effort ledger
    contract while no new work is accepted by the retired pool.
    """
    global _ledger_executor, _ledger_shutdown_in_progress
    with _ledger_state_lock:
        if _ledger_shutdown_in_progress:
            return
        _ledger_shutdown_in_progress = True
    try:
        await drain_pending_writes()
    finally:
        with _ledger_state_lock:
            executor = _ledger_executor
            _ledger_executor = None
            _ledger_shutdown_in_progress = False
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)


def accounting_enabled() -> bool:
    return os.getenv(ACCOUNTING_ENABLED_ENV_VAR, '').strip().lower() in {'1', 'true', 'yes'}


def accounting_write_timeout_seconds() -> float:
    raw = os.getenv(ACCOUNTING_WRITE_TIMEOUT_SECONDS_ENV_VAR, '').strip()
    try:
        value = float(raw) if raw else DEFAULT_ACCOUNTING_WRITE_TIMEOUT_SECONDS
    except ValueError:
        return DEFAULT_ACCOUNTING_WRITE_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_ACCOUNTING_WRITE_TIMEOUT_SECONDS


def accounting_max_pending_traces() -> int:
    raw = os.getenv(ACCOUNTING_MAX_PENDING_TRACES_ENV_VAR, '').strip()
    try:
        value = int(raw) if raw else DEFAULT_ACCOUNTING_MAX_PENDING_TRACES
    except ValueError:
        return DEFAULT_ACCOUNTING_MAX_PENDING_TRACES
    return value if value > 0 else DEFAULT_ACCOUNTING_MAX_PENDING_TRACES
