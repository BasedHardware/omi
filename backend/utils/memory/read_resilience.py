"""Bounded retries for synchronous, read-only MemoryService operations.

The one-second budget limits retry admission (including backoff), not an
in-flight SDK RPC. List reads retain their original wall/document RPC budget;
we never spawn abandoned threads or reset that budget. Writes are excluded.
"""

import json
import logging
import random
import threading
import time
from functools import wraps
from typing import Any, Callable

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


class MemoryReadResilience:
    """One thread-safe process-local circuit per fixed read operation.

    Three exhausted transient requests open for five seconds. After cooldown,
    one caller probes while peers fail fast. Permanent errors never open it.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.clock = clock
        self.sleep = sleep
        self.jitter = jitter
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
        # Share admission deadline across cursor->offset fallback for this request.
        deadline = started + 1.0
        if budget is not None:
            deadline = getattr(budget, '_memory_retry_deadline', deadline)
            budget._memory_retry_deadline = deadline
        attempts = 0
        transient = False
        try:
            while True:
                attempts += 1
                try:
                    result = fn()
                except Exception as exc:
                    transient = transient_store_error(exc)
                    delay = self.jitter(0.025, 0.075)
                    remaining = deadline - self.clock()
                    if budget is not None:
                        remaining = min(remaining, budget.remaining_seconds)
                        if budget.truncated or budget.remaining_documents <= 0:
                            remaining = 0
                    # Two attempts maximum, no retry on the half-open probe.
                    if transient and attempts < 2 and not probing and remaining > delay + 0.05:
                        self.sleep(delay)
                        if self.clock() < deadline and (budget is None or budget.remaining_seconds > 0.05):
                            continue
                    if transient or (isinstance(exc, HTTPException) and exc.status_code == 503):
                        self._log(operation, 'exhausted' if transient else 'permanent', attempts, started, exc)
                    raise
                else:
                    transient = False
                    if attempts > 1:
                        self._log(operation, 'recovered', attempts, started, None)
                    return result
        finally:
            with self._lock:
                # Completions from before an opening cannot close its circuit.
                if generation == self._generation:
                    if probing:
                        self._probe = False
                    if transient:
                        self._failures += 1
                        if probing or self._failures >= 3:
                            self._open_until = self.clock() + 5.0
                            self._generation += 1
                    elif probing or self._open_until == 0:
                        self._failures = 0
                        self._open_until = 0.0

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
