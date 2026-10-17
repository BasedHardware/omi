"""Bounded outer retries for Firestore transaction contention.

The Firestore SDK retries ``Aborted`` errors raised by commit, but not errors
raised while the decorated transaction body performs reads.  A fresh outer
transaction is therefore required for read-time contention.  Keep this helper
narrow: ambiguous commit outcomes and unrelated provider failures must not be
replayed.
"""

from collections import deque
import logging
import math
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
_MAX_EXPONENT = 10


class FirestoreContentionExhausted(RuntimeError):
    """Raised after every bounded transaction-contention attempt is used."""


def is_transaction_contention(error: BaseException) -> bool:
    """Return True if error or any wrapped cause signals Firestore transaction contention."""
    if not isinstance(error, BaseException):
        return False

    queue: deque[BaseException] = deque([error])
    seen: set[int] = set()

    while queue:
        curr = queue.popleft()
        curr_id = id(curr)
        if curr_id in seen:
            continue
        seen.add(curr_id)

        # 1. Direct type match on FirestoreAborted (google.api_core.exceptions.Aborted)
        if isinstance(curr, FirestoreAborted):
            return True

        name = type(curr).__name__
        mod = getattr(type(curr), "__module__", "") or ""

        # Positive domain anchor: match Aborted/gRPC codes originating from Google, gRPC, or local/test scopes
        is_google_or_grpc = (
            mod.startswith(("google.", "grpc", "database.", "tests.", "__main__"))
            or not mod
        )

        if is_google_or_grpc:
            if name in ("Aborted", "FirestoreAborted"):
                return True

            # Status code or gRPC code match
            raw_code = getattr(curr, "code", None)
            if callable(raw_code):
                try:
                    grpc_code = raw_code()
                except Exception:
                    grpc_code = None
            else:
                grpc_code = raw_code

            if grpc_code is not None:
                code_name = getattr(grpc_code, "name", None)
                if code_name == "ABORTED" or str(grpc_code) in ("10", "ABORTED", "StatusCode.ABORTED"):
                    return True
                if grpc_code == 10:
                    return True

            grpc_status = getattr(curr, "grpc_status_code", None)
            if grpc_status in (10, "10", "ABORTED"):
                return True

        # 2. Traverse explicit cause (__cause__)
        cause = getattr(curr, "__cause__", None)
        if isinstance(cause, BaseException) and id(cause) not in seen:
            queue.append(cause)

        # 3. Traverse SDK wrapper cause (e.g. google.api_core.exceptions.RetryError.cause)
        sdk_cause = getattr(curr, "cause", None)
        if isinstance(sdk_cause, BaseException) and id(sdk_cause) not in seen:
            queue.append(sdk_cause)

        # 4. Traverse ExceptionGroup / BaseExceptionGroup exceptions (PEP 654)
        exceptions = getattr(curr, "exceptions", None)
        if isinstance(exceptions, (tuple, list)):
            for sub_exc in exceptions:
                if isinstance(sub_exc, BaseException) and id(sub_exc) not in seen:
                    queue.append(sub_exc)

    return False


# Alias for backward compatibility
_is_transaction_contention = is_transaction_contention


def run_with_transaction_contention_retry(
    transaction_factory: Callable[[], Any],
    operation: Callable[[Any], T],
    *,
    operation_name: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    """Run a decorated Firestore transaction with bounded equal-jitter retry.

    A new transaction is created for every outer attempt.  Only explicit
    ``Aborted`` contention, including the SDK's exhausted-attempt wrapper, is
    replayed.  Firestore aborts are atomic, so callers must keep all writes and
    idempotency checks inside ``operation``.
    """

    if isinstance(max_attempts, bool) or not isinstance(max_attempts, int) or max_attempts < 1:
        raise ValueError("max_attempts must be positive")

    if not isinstance(operation_name, str) or not operation_name.strip():
        raise ValueError("operation_name must be a non-empty string")
    op_name = operation_name.strip()

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

    for attempt in range(1, max_attempts + 1):
        try:
            result = operation(transaction_factory())
            if attempt > 1:
                logger.info(
                    "firestore_transaction_contention operation=%s attempt=%d/%d outcome=recovered",
                    op_name,
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
                    op_name,
                    attempt,
                    max_attempts,
                )
                raise FirestoreContentionExhausted(
                    f"Firestore transaction contention exhausted for {op_name}"
                ) from error

            attempt_exp = min(attempt - 1, _MAX_EXPONENT)
            high_delay = min(_INITIAL_MAX_DELAY_SECONDS * (2 ** attempt_exp), _MAX_DELAY_SECONDS)
            low_delay = high_delay / 2

            try:
                raw_rnd = float(random_value())
                if math.isnan(raw_rnd) or math.isinf(raw_rnd):
                    raw_rnd = 0.5
            except (TypeError, ValueError, OverflowError):
                raw_rnd = 0.5

            jitter = min(max(raw_rnd, 0.0), 1.0)
            delay = low_delay + ((high_delay - low_delay) * jitter)
            if math.isnan(delay) or math.isinf(delay) or delay < 0.0:
                delay = low_delay

            logger.warning(
                "firestore_transaction_contention operation=%s attempt=%d/%d outcome=retry delay_ms=%d",
                op_name,
                attempt,
                max_attempts,
                round(delay * 1000),
            )

            if on_retry is not None:
                try:
                    on_retry(attempt, error, delay)
                except Exception:
                    logger.exception("on_retry callback raised an exception for %s", op_name)

            sleep(delay)

    raise AssertionError("unreachable")
