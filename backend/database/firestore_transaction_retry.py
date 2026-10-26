"""Bounded outer retries for Firestore transaction contention.

The Firestore SDK retries ``Aborted`` errors raised by commit, but not errors
raised while the decorated transaction body performs reads.  A fresh outer
transaction is therefore required for read-time contention.  Keep this helper
narrow: ambiguous commit outcomes and unrelated provider failures must not be
replayed.

A server-side transaction-chain expiry (``InvalidArgument`` "transaction has
expired") is classified as contention here too: nothing was written and only a
fresh transaction can succeed, which is exactly what this bounded budget does.
"""

import logging
import random
import time
from typing import Any, Callable, TypeVar

try:
    # The fallback classes below rebind these names in lightweight stub environments.
    from google.api_core.exceptions import Aborted as FirestoreAborted  # type: ignore[reportAssignmentType]
    from google.api_core.exceptions import InvalidArgument as FirestoreInvalidArgument  # type: ignore[reportAssignmentType]
except Exception:  # pragma: no cover - lightweight tests may stub only google.cloud

    class FirestoreAborted(Exception):
        """Stub-safe fallback for test environments without google-api-core."""

    class FirestoreInvalidArgument(Exception):
        """Stub-safe fallback for test environments without google-api-core."""


logger = logging.getLogger(__name__)

T = TypeVar("T")

DEFAULT_MAX_ATTEMPTS = 5
_INITIAL_MAX_DELAY_SECONDS = 0.2
_MAX_DELAY_SECONDS = 1.0

# Same server-side retirement message ``database._client`` matches; this module
# cannot import that one (``_client`` imports the retry helpers defined here).
_EXPIRED_TRANSACTION_MARKER = "transaction has expired"


class FirestoreContentionExhausted(RuntimeError):
    """Raised after every bounded transaction-contention attempt is used."""


def is_expired_transaction_error(error: BaseException) -> bool:
    """True when Firestore has retired the transaction id mid-flight.

    A commit reports the retirement as ``InvalidArgument`` 400. A streaming read
    (``BatchGetDocuments`` / ``RunQuery``) reports the same retirement as
    ``Aborted`` 409, raised from ``google.api_core.grpc_helpers``. The SDK
    retries ``Aborted`` only when ``_commit`` raises it, and that retry reuses
    the dead id, so both surfaces need a fresh transaction.
    """
    return (
        isinstance(error, (FirestoreAborted, FirestoreInvalidArgument))
        and _EXPIRED_TRANSACTION_MARKER in str(error).lower()
    )


def _is_transaction_contention(error: BaseException) -> bool:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, FirestoreAborted):
            return True
        if is_expired_transaction_error(current):
            return True
        seen.add(id(current))
        current = current.__cause__
    return False


def equal_jitter_delay(attempt: int, random_value: Callable[[], float] = random.random) -> float:
    """Equal-jitter delay for one failed attempt. ``attempt`` is 1-based.

    Two delays at the default schedule stay under half a second, so a
    three-attempt caller finishes well inside a few seconds.
    """
    if attempt < 1:
        raise ValueError("attempt must be positive")
    high_delay = min(_INITIAL_MAX_DELAY_SECONDS * (2 ** (attempt - 1)), _MAX_DELAY_SECONDS)
    low_delay = high_delay / 2
    jitter = min(max(random_value(), 0.0), 1.0)
    return low_delay + ((high_delay - low_delay) * jitter)


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
    ``Aborted`` contention (including the SDK's exhausted-attempt wrapper) and
    an expired transaction id are replayed.  Firestore aborts are atomic, so
    callers must keep all writes and idempotency checks inside ``operation``.
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

            delay = equal_jitter_delay(attempt, random_value)
            logger.warning(
                "firestore_transaction_contention operation=%s attempt=%d/%d outcome=retry delay_ms=%d",
                operation_name,
                attempt,
                max_attempts,
                round(delay * 1000),
            )
            sleep(delay)

    raise AssertionError("unreachable")
