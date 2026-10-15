"""Bounded outer retries for Firestore transaction contention.

The Firestore SDK retries ``Aborted`` errors raised by commit, but not errors
raised while the decorated transaction body performs reads.  A fresh outer
transaction is therefore required for read-time contention.  Keep this helper
narrow: ambiguous commit outcomes and unrelated provider failures must not be
replayed.
"""

import logging
import random
import time
from typing import Any, Callable, TypeVar

try:
    # The fallback class below rebinds this name in lightweight stub environments.
    from google.api_core.exceptions import Aborted as FirestoreAborted  # type: ignore[reportAssignmentType]
except Exception:  # pragma: no cover - lightweight tests may stub only google.cloud

    class FirestoreAborted(Exception):
        """Stub-safe fallback for test environments without google-api-core."""


logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_MAX_ATTEMPTS = 5
_INITIAL_MAX_DELAY_SECONDS = 0.2
_MAX_DELAY_SECONDS = 1.0


class FirestoreContentionExhausted(RuntimeError):
    """Raised after every bounded transaction-contention attempt is used."""


# Attribute names a wrapped (non-google.api_core) error may expose to signal a
# retryable contention/aborted status. ``grpc_status_code`` 10 is gRPC ABORTED.
_CONTENSION_HTTP_CODES = frozenset({409})
_CONTENSION_GRPC_CODES = frozenset({10})


def _contention_status_code(error: BaseException) -> bool:
    """True when a wrapped error carries a contention/aborted status code."""
    for name in ("code", "status_code"):
        value = getattr(error, name, None)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value in _CONTENSION_HTTP_CODES:
            return True
    grpc_code = getattr(error, "grpc_status_code", None)
    if isinstance(grpc_code, int) and not isinstance(grpc_code, bool) and grpc_code in _CONTENSION_GRPC_CODES:
        return True
    return False


def _is_transaction_contention(error: BaseException) -> bool:
    """Walk an exception's full causal graph for a retryable contention signal.

    ``__cause__`` covers explicit ``raise X from Y``; ``__context__`` covers an
    implicit chain (raised inside ``except`` without ``from``); exception groups
    contribute every member. A visited-id set guards cycles, and wrapped errors
    are matched on a contention status code, not only on ``FirestoreAborted``.
    """
    stack: list[BaseException] = [error]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if id(current) in seen or current is None:
            continue
        seen.add(id(current))
        if isinstance(current, FirestoreAborted) or _contention_status_code(current):
            return True
        for child in (current.__cause__, current.__context__):
            if isinstance(child, BaseException):
                stack.append(child)
        # PEP 654 exception groups expose their members via .exceptions.
        group_members = getattr(current, "exceptions", None)
        if isinstance(group_members, (list, tuple)):
            stack.extend(e for e in group_members if isinstance(e, BaseException))
    return False


def _jitter(random_value: Callable[[], float]) -> float:
    """A [0,1] jitter fraction from the RNG; a corrupt RNG (NaN/Inf/out-of-range)
    degrades to a fixed 0.5 rather than propagating into sleep(delay)."""
    try:
        value = float(random_value())
    except (TypeError, ValueError):
        return 0.5
    if value != value or value in (float("inf"), float("-inf")):  # NaN / ±Inf
        return 0.5
    return min(max(value, 0.0), 1.0)


def run_with_transaction_contention_retry(
    transaction_factory: Callable[[], Any],
    operation: Callable[[Any], T],
    *,
    operation_name: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
    on_retry: Callable[[int, float, BaseException], None] | None = None,
) -> T:
    """Run a decorated Firestore transaction with bounded equal-jitter retry.

    A new transaction is created for every outer attempt.  Only contention is
    replayed: an ``Aborted`` anywhere in the raised error's causal graph
    (``__cause__``, ``__context__``, exception-group members) or a wrapped error
    carrying HTTP 409 / gRPC-10 status — the same signals the SDK maps to
    aborted transactions.  Firestore aborts are atomic, so callers must keep all
    writes and idempotency checks inside ``operation``.
    """

    if not callable(transaction_factory):
        raise TypeError("transaction_factory must be callable")
    if not callable(operation):
        raise TypeError("operation must be callable")
    if not callable(sleep):
        raise TypeError("sleep must be callable")
    if not callable(random_value):
        raise TypeError("random_value must be callable")
    if on_retry is not None and not callable(on_retry):
        raise TypeError("on_retry must be callable")
    # bool is a subclass of int — a bare isinstance(max_attempts, int) would let
    # True/False through as 1/0. Reject it explicitly, then bound the count.
    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError("max_attempts must be a positive integer")
    operation_name = operation_name if isinstance(operation_name, str) and operation_name else "operation"

    for attempt in range(1, max_attempts + 1):
        try:
            result = operation(transaction_factory())
            if attempt > 1:
                logger.info(
                    "firestore_transaction_contention operation=%s attempt=%d/%d outcome=recovered",
                    operation_name,
                    attempt,
                    max_attempts,
                )
            return result
        except Exception as error:
            if not _is_transaction_contention(error):
                raise
            if attempt >= max_attempts:
                logger.error(
                    "firestore_transaction_contention operation=%s attempt=%d/%d outcome=exhausted",
                    operation_name,
                    attempt,
                    max_attempts,
                )
                raise FirestoreContentionExhausted(
                    f"Firestore transaction contention exhausted for {operation_name}"
                ) from error

            # The exponent is capped so an extreme attempt count cannot overflow the
            # shift; the jitter source is clamped so NaN/Inf can't reach sleep().
            high_delay = min(_INITIAL_MAX_DELAY_SECONDS * (2 ** min(attempt - 1, 30)), _MAX_DELAY_SECONDS)
            low_delay = high_delay / 2
            delay = low_delay + ((high_delay - low_delay) * _jitter(random_value))
            logger.warning(
                "firestore_transaction_contention operation=%s attempt=%d/%d outcome=retry delay_ms=%d",
                operation_name,
                attempt,
                max_attempts,
                round(delay * 1000),
            )
            if on_retry is not None:
                try:
                    on_retry(attempt, delay, error)
                except Exception:
                    logger.warning("firestore_transaction_contention on_retry hook raised; continuing")
            sleep(delay)

    raise AssertionError("unreachable")
