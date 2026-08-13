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


def _is_transaction_contention(error: BaseException) -> bool:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, FirestoreAborted):
            return True
        seen.add(id(current))
        current = current.__cause__
    return False


def run_with_transaction_contention_retry(
    transaction_factory: Callable[[], Any],
    operation: Callable[[Any], T],
    *,
    operation_name: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
) -> T:
    """Run a decorated Firestore transaction with bounded equal-jitter retry.

    A new transaction is created for every outer attempt.  Only explicit
    ``Aborted`` contention, including the SDK's exhausted-attempt wrapper, is
    replayed.  Firestore aborts are atomic, so callers must keep all writes and
    idempotency checks inside ``operation``.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")

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

            high_delay = min(_INITIAL_MAX_DELAY_SECONDS * (2 ** (attempt - 1)), _MAX_DELAY_SECONDS)
            low_delay = high_delay / 2
            jitter = min(max(random_value(), 0.0), 1.0)
            delay = low_delay + ((high_delay - low_delay) * jitter)
            logger.warning(
                "firestore_transaction_contention operation=%s attempt=%d/%d outcome=retry delay_ms=%d",
                operation_name,
                attempt,
                max_attempts,
                round(delay * 1000),
            )
            sleep(delay)

    raise AssertionError("unreachable")
