"""Bounded outer retries for Firestore transaction contention.

The Firestore SDK retries ``Aborted`` errors raised by commit, but not errors
raised while the decorated transaction body performs reads.  A fresh outer
transaction is therefore required for read-time contention.  Keep this helper
narrow: ambiguous commit outcomes and unrelated provider failures must not be
replayed.
"""

from __future__ import annotations

from collections import deque
import logging
import math
import random
import time
from typing import Any, Callable, Optional, TypeVar

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
_MAX_EXPONENT = 10


class FirestoreContentionExhausted(RuntimeError):
    """Raised after every bounded transaction-contention attempt is used."""


def is_transaction_contention(error: BaseException) -> bool:
    """Check if an exception or any wrapped cause/context represents Firestore transaction contention.

    Traverses both explicit causal chains (``__cause__``) and implicit exception contexts
    (``__context__``), as well as multi-exception groups, using a double-ended queue for linear
    traversal while guarding against cyclical references.
    """
    queue: deque[BaseException] = deque([error])
    seen: set[int] = set()

    while queue:
        current = queue.popleft()
        curr_id = id(current)
        if curr_id in seen:
            continue
        seen.add(curr_id)

        if isinstance(current, FirestoreAborted):
            return True

        # Check for raw gRPC RpcError status via callable code() or attribute
        raw_code = getattr(current, "code", None)
        code_val = raw_code() if callable(raw_code) else raw_code
        grpc_status = getattr(current, "grpc_status_code", None)

        if code_val in (10, "10", "ABORTED") or getattr(code_val, "name", None) == "ABORTED":
            return True
        if grpc_status in (10, "10", "ABORTED") or getattr(grpc_status, "name", None) == "ABORTED":
            return True

        if getattr(current, "__cause__", None) is not None:
            queue.append(current.__cause__)  # type: ignore[arg-type]

        # Handle ExceptionGroup / BaseExceptionGroup unrolling if present
        nested_exceptions = getattr(current, "exceptions", None)
        if isinstance(nested_exceptions, (list, tuple)):
            for nested in nested_exceptions:
                if isinstance(nested, BaseException):
                    queue.append(nested)

    return False


_is_transaction_contention = is_transaction_contention


def run_with_transaction_contention_retry(
    transaction_factory: Callable[[], Any],
    operation: Callable[[Any], T],
    *,
    operation_name: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
    on_retry: Optional[Callable[[str, int, int, float, BaseException], None]] = None,
) -> T:
    """Run a decorated Firestore transaction with bounded equal-jitter retry.

    A new transaction is created for every outer attempt.  Only explicit
    ``Aborted`` contention, including the SDK's exhausted-attempt wrapper, is
    replayed.  Firestore aborts are atomic, so callers must keep all writes and
    idempotency checks inside ``operation``.
    """
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("max_attempts must be positive")

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

    clean_op_name = (
        operation_name.strip() if isinstance(operation_name, str) and operation_name.strip() else "unnamed_operation"
    )

    for attempt in range(1, max_attempts + 1):
        try:
            result = operation(transaction_factory())
            if attempt > 1:
                logger.info(
                    "firestore_transaction_contention operation=%s attempt=%d/%d outcome=recovered",
                    clean_op_name,
                    attempt,
                    max_attempts,
                )
            return result
        except Exception as error:
            if not is_transaction_contention(error):
                raise
            if attempt >= max_attempts:
                logger.error(
                    "firestore_transaction_contention operation=%s attempt=%d/%d outcome=exhausted",
                    clean_op_name,
                    attempt,
                    max_attempts,
                )
                raise FirestoreContentionExhausted(
                    f"Firestore transaction contention exhausted for {clean_op_name}"
                ) from error

            exponent = min(attempt - 1, _MAX_EXPONENT)
            high_delay = min(_INITIAL_MAX_DELAY_SECONDS * (2**exponent), _MAX_DELAY_SECONDS)
            low_delay = high_delay / 2.0

            try:
                raw_jitter = float(random_value())
            except (TypeError, ValueError, OverflowError):
                raw_jitter = 0.5
            if math.isnan(raw_jitter) or math.isinf(raw_jitter):
                raw_jitter = 0.5

            jitter = min(max(raw_jitter, 0.0), 1.0)
            delay = max(0.0, low_delay + ((high_delay - low_delay) * jitter))

            logger.warning(
                "firestore_transaction_contention operation=%s attempt=%d/%d outcome=retry delay_ms=%d",
                clean_op_name,
                attempt,
                max_attempts,
                round(delay * 1000),
            )

            if on_retry is not None:
                try:
                    on_retry(clean_op_name, attempt, max_attempts, delay, error)
                except Exception:
                    logger.warning(
                        "firestore_transaction_contention on_retry callback failed for %s",
                        clean_op_name,
                        exc_info=True,
                    )

            sleep(delay)

    raise AssertionError("unreachable")


__all__ = [
    "DEFAULT_MAX_ATTEMPTS",
    "FirestoreAborted",
    "FirestoreContentionExhausted",
    "is_transaction_contention",
    "run_with_transaction_contention_retry",
]
