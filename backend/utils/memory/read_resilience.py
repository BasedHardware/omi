"""Bounded retries for synchronous, read-only MemoryService operations.

The one-second budget limits retry admission (including backoff), not an
in-flight SDK RPC. List reads retain their original wall/document RPC budget;
we never spawn abandoned threads or reset that budget. Writes are excluded.
"""

import json
import logging
import os
import random
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Literal

from fastapi import HTTPException
from google.api_core import exceptions as google_errors

from utils.other.list_budget import ListReadBudgetExhausted

logger = logging.getLogger(__name__)


def transient_store_error(exc: Exception) -> bool:
    """Inspect typed provider causes; never retry validation or scan exhaustion."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, ListReadBudgetExhausted):
            return False
        if isinstance(current, HTTPException) and current.status_code != 503:
            return False
        if isinstance(
            current,
            (
                google_errors.ServiceUnavailable,
                google_errors.DeadlineExceeded,
                google_errors.TooManyRequests,
                google_errors.InternalServerError,
                google_errors.Aborted,
            ),
        ):
            return True
        # Pinecone wraps HTTP errors in PineconeApiException (SDK versions use
        # different import paths). Only trust its typed status, never message text.
        if type(current).__module__.startswith('pinecone.') and getattr(current, 'status', None) in (
            429,
            500,
            502,
            503,
            504,
        ):
            return True
        current = current.__cause__
    return False


class MemoryReadCircuitOpen(HTTPException):
    def __init__(self) -> None:
        super().__init__(503, 'Memory backing store temporarily unavailable', headers={'Retry-After': '5'})


MemoryBackingStoreStream = Literal['canonical', 'historical', 'cursor', 'admission']


class MemoryBackingStoreUnavailable(HTTPException):
    """Recoverable backing-store failure for mixed-list reads.

    Subclasses ``HTTPException`` so existing callers keep the same 503 body.
    ``GET /v3/memories`` first-page fallback catches this type instead of
    matching ``detail`` strings — a renamed or newly added unavailable
    message must not escape to clients as a hard 503.
    """

    def __init__(self, detail: str, *, stream: MemoryBackingStoreStream) -> None:
        super().__init__(status_code=503, detail=detail)
        self.stream = stream


class MemoryReadAdmissionDenied(MemoryBackingStoreUnavailable):
    """No store call was admitted; offset fallback must use the same gate."""

    def __init__(self) -> None:
        super().__init__('Memory read admission exhausted', stream='admission')
        self.headers = {'Retry-After': '1'}


class RetryAllowance:
    """Process-wide whole-operation burst and in-flight cap; one token/sec refill, no waiting."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._tokens = 0.0
        self._in_flight = 0
        self._updated: float | None = None

    def take(self) -> bool:
        # Read mutable configuration at admission, not module import time.
        try:
            capacity = max(0, min(64, int(os.environ.get('OMI_MEMORY_READ_RETRY_BURST', '8'))))
        except ValueError:
            capacity = 8
        with self._lock:
            now = self._clock()
            if self._updated is None:
                self._tokens = float(capacity)
            else:
                self._tokens = min(float(capacity), self._tokens + max(0.0, now - self._updated))
            self._updated = now
            if self._tokens < 1 or self._in_flight >= capacity:
                return False
            self._tokens -= 1
            self._in_flight += 1
            return True

    def release(self) -> None:
        with self._lock:
            self._in_flight -= 1


# Shared across all three operation circuits; no user/operation-keyed bucket.
_retry_allowance = RetryAllowance()
_request_state_lock = threading.Lock()


class MemoryReadAttempts:
    """One request's two whole-operation attempts, including offset fallback."""

    def __init__(self, deadline: float) -> None:
        self.deadline = deadline
        self.used = 0
        self.error: Exception = MemoryReadAdmissionDenied()
        self._lock = threading.Lock()

    def claim(self) -> bool:
        with self._lock:
            if self.used >= 2:
                return False
            self.used += 1
            return True


@dataclass
class _StoreEvidence:
    succeeded: bool = False
    failed: bool = False


_store_evidence: ContextVar[_StoreEvidence | None] = ContextVar('memory_store_evidence', default=None)


def memory_store_read(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Record provider-read evidence even when the service heals/absorbs errors."""
    evidence = _store_evidence.get()
    try:
        result = fn(*args, **kwargs)
    except Exception:
        if evidence is not None:
            evidence.failed = True
        raise
    if evidence is not None:
        evidence.succeeded = True
    return result


class MemoryReadResilience:
    """Thread-safe operation circuit plus request and process whole-operation admission.

    Three exhausted transient requests open for five seconds. One caller probes
    after cooldown; only a successful backing read can close the circuit.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
        allowance: RetryAllowance | None = None,
    ) -> None:
        self.clock = clock
        self.sleep = sleep
        self.jitter = jitter
        self.allowance = allowance
        self._lock = threading.Lock()
        self._failures = 0
        self._open_until = 0.0
        self._probe = False
        self._generation = 0

    def call(self, operation: str, fn: Callable[[], Any], *, budget: Any = None) -> Any:
        started = self.clock()
        with self._lock:
            generation = self._generation
            probing = self._open_until != 0
            denied = probing and (started < self._open_until or self._probe)
            if probing and not denied:
                self._probe = True
        if denied:
            self._log(operation, 'circuit_open', 0, started, MemoryReadCircuitOpen())
            raise MemoryReadCircuitOpen()
        # Budget normally travels serially through the router; also preserve
        # one state if internal callers fan out with the same request budget.
        with _request_state_lock:
            state = getattr(budget, '_memory_read_attempts', None) if budget is not None else None
            if not isinstance(state, MemoryReadAttempts):
                state = MemoryReadAttempts(started + 1.0)
                if budget is not None:
                    budget._memory_read_attempts = state
        attempts = 0
        transient = False
        completed = False
        evidence = _StoreEvidence()
        token = _store_evidence.set(evidence)
        try:
            while True:
                # Every entry path (first attempt, retry, offset fallback) uses
                # the same process allowance before executing the operation.
                allowance = self.allowance or _retry_allowance
                with self._lock:
                    # First admission gates on TIME headroom only: an
                    # exhausted document budget is a normal truncated page
                    # (the charge path flags budget.truncated downstream),
                    # not an admission failure; the retry check below keeps
                    # the full budget-aware headroom.
                    time_headroom = state.deadline - self.clock() > 0.05
                    admitted = (
                        generation == self._generation
                        and (probing or self._open_until == 0)
                        and time_headroom
                        and state.used < 2
                        and allowance.take()
                    )
                    if admitted:
                        admitted = state.claim()
                        if not admitted:
                            allowance.release()
                if not admitted:
                    self._log(operation, 'admission_denied', attempts, started, state.error)
                    raise state.error
                attempts += 1
                evidence.succeeded = False
                evidence.failed = False
                try:
                    try:
                        result = fn()
                    finally:
                        allowance.release()
                except Exception as exc:
                    state.error = exc
                    transient = transient_store_error(exc)
                    delay = self.jitter(0.025, 0.075)
                    # A retry needs headroom, request attempts, a global token,
                    # and a still-closed circuit. Check again after backoff.
                    if transient and state.used < 2 and not probing and self._headroom(state, budget) > delay + 0.05:
                        self.sleep(delay)
                        continue
                    if transient or (isinstance(exc, HTTPException) and exc.status_code == 503):
                        self._log(operation, 'exhausted' if transient else 'permanent', attempts, started, exc)
                    raise
                else:
                    transient = False
                    completed = True
                    if attempts > 1:
                        self._log(operation, 'recovered', attempts, started, None)
                    return result
        finally:
            _store_evidence.reset(token)
            with self._lock:
                # Pre-opening completions cannot close a newer circuit.
                if generation == self._generation:
                    if probing:
                        self._probe = False
                    healthy = completed and evidence.succeeded and not evidence.failed
                    if transient or (probing and not healthy):
                        if transient:
                            self._failures += 1
                        if probing or self._failures >= 3:
                            self._open_until = self.clock() + 5.0
                            self._generation += 1
                    elif healthy:
                        self._failures = 0
                        self._open_until = 0.0

    def _headroom(self, state: MemoryReadAttempts, budget: Any) -> float:
        remaining = state.deadline - self.clock()
        if budget is not None:
            if budget.truncated or budget.remaining_documents <= 0:
                return 0.0
            remaining = min(remaining, budget.remaining_seconds)
        return remaining

    def _log(self, operation: str, outcome: str, attempts: int, started: float, exc: Exception | None) -> None:
        fields = {
            'event': 'memory_store_read',
            'operation': operation,
            'outcome': outcome,
            'attempts': attempts,
            'exception_class': type(exc).__name__ if exc is not None else 'none',
            'elapsed_ms': round((self.clock() - started) * 1000, 2),
        }
        # Bounded fields only; no provider message, uid, query or content.
        logger.log(
            logging.INFO if outcome == 'recovered' else logging.WARNING,
            'memory_store_read %s',
            json.dumps(fields, sort_keys=True),
            extra=fields,
        )


def resilient_memory_read(method: Callable[..., Any]) -> Callable[..., Any]:
    # Exactly three decorated methods; no uid-keyed/unbounded registry.
    policy = MemoryReadResilience()

    @wraps(method)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        return policy.call(
            method.__name__,
            lambda: method(*args, **kwargs),
            budget=kwargs.get('request_budget') or kwargs.get('budget'),
        )

    return wrapped
