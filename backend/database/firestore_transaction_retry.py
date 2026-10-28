"""Bounded outer retries for Firestore transaction contention.

The Firestore SDK retries ``Aborted`` errors raised by commit, but not errors
raised while the decorated transaction body performs reads.  A fresh outer
transaction is therefore required for read-time contention.  Keep this helper
narrow: ambiguous commit outcomes and unrelated provider failures must not be
replayed.

Attempts are bounded twice.  ``max_attempts`` bounds the chain count for every
caller.  A caller that owns a wall-clock budget — the sync handler's request
budget, a batch projection claim's lease — additionally scopes a deadline, and
a retry (attempt 2 onward) starts only while the remaining budget covers a
reserve derived from the last attempt's observed duration, so total retry wall
time stays at ``deadline + one in-flight attempt`` at worst.  The deadline
never refuses the first attempt: a caller that reached the transaction always
gets one try, so scoping a deadline can only remove retries, never the attempt
itself.  Expired-transaction retirements count as contention here (an expired
chain is atomic and wrote nothing, exactly like an aborted one), but only
under those bounds; with no deadline in scope they keep the three-fresh-chain
ceiling of the inner ``run_transactional`` default.
"""

import logging
import random
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator, TypeVar

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
# Firestore retires any transaction chain after 270 seconds (the documented
# transaction lifetime quota — the same retirement that surfaces as
# "transaction has expired"), so an attempt that already started cannot run
# materially past this.  The deadline gate cannot stop an in-flight attempt,
# which is why the accepted bound below is "deadline + one in-flight attempt"
# rather than the deadline alone.
FIRESTORE_TRANSACTION_CHAIN_SECONDS = 270.0
# A retry (attempt 2 onward) starts only while the remaining budget covers this
# fraction of the last attempt's observed duration, and never less than the
# floor.  Fast Aborted contention (near-zero observed durations) therefore
# spends the full attempt cap inside a short budget — the claim lease or the
# sync handler window — while a chain that already consumed real time raises
# the reserve enough that another full chain still fits before the deadline.
RETRY_RESERVE_FACTOR = 1.5
RETRY_RESERVE_FLOOR_SECONDS = 30.0
# With no deadline in scope, expired-transaction retries keep today's ceiling
# of three fresh chains (database._client.run_transactional's default);
# Aborted contention keeps the full DEFAULT_MAX_ATTEMPTS policy either way.
_EXPIRED_CHAIN_CEILING_WITHOUT_DEADLINE = 3

_EXPIRED_TRANSACTION_MARKER = "transaction has expired"


class FirestoreContentionExhausted(RuntimeError):
    """Raised after every bounded transaction-contention attempt is used.

    ``reason`` is the closed outcome token ``attempts_exhausted`` or
    ``deadline_exhausted``; callers log it, never the message.
    """

    def __init__(self, message: str, *, reason: str = "attempts_exhausted") -> None:
        super().__init__(message)
        self.reason = reason


def _is_expired_transaction(error: BaseException) -> bool:
    # A retired chain reports itself as ``InvalidArgument`` at commit or as
    # ``Aborted`` on a streaming read; either way nothing was written.
    return (
        isinstance(error, (FirestoreInvalidArgument, FirestoreAborted))
        and _EXPIRED_TRANSACTION_MARKER in str(error).lower()
    )


def _is_transaction_contention(error: BaseException) -> bool:
    current: BaseException | None = error
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        if isinstance(current, FirestoreAborted) or _is_expired_transaction(current):
            return True
        seen.add(id(current))
        current = current.__cause__
    return False


_retry_deadline: ContextVar[float | None] = ContextVar("firestore_transaction_retry_deadline", default=None)


@contextmanager
def transaction_retry_deadline_scope(deadline: float | None) -> Iterator[None]:
    """Bound nested Firestore transaction retries to ``deadline`` (monotonic seconds).

    ``run_blocking`` copies ContextVars into executor leaves, so a caller that
    owns a wall-clock budget scopes it once here and every nested
    ``run_with_transaction_contention_retry`` inherits it; ``None`` restores
    the default attempt-only bound.  Scopes nest by token, and a ``None``
    scope inside a bounded one opts a subregion back out.
    """
    token = _retry_deadline.set(deadline)
    try:
        yield
    finally:
        _retry_deadline.reset(token)


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
    deadline: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
    random_value: Callable[[], float] = random.random,
    monotonic: Callable[[], float] = time.monotonic,
) -> T:
    """Run a decorated Firestore transaction with bounded equal-jitter retry.

    A new transaction is created for every outer attempt.  Only explicit
    ``Aborted`` contention — including the SDK's exhausted-attempt wrapper —
    and expired-transaction retirements are replayed.  Firestore aborts and
    expiries are atomic, so callers must keep all writes and idempotency
    checks inside ``operation``.  When this helper nests ``run_transactional``,
    the outer layer owns every attempt: the inner call runs with
    ``attempts=1`` so a single budget bounds the whole chain count.

    ``deadline`` (monotonic seconds; the ambient ``transaction_retry_deadline_scope``
    applies when the parameter is ``None``) adds a wall-clock bound.  The first
    attempt is never gated — a caller that reached the transaction always gets
    one try, so a deadline scope can only remove retries, never make the call
    worse than running the transaction once.  Each retry (attempt 2 onward)
    starts only while the remaining budget covers
    ``max(last attempt's observed duration × RETRY_RESERVE_FACTOR,
    RETRY_RESERVE_FLOOR_SECONDS)``, and a post-failure jitter sleep never runs
    past the deadline.  When the reserve does not fit, the loop stops with
    ``FirestoreContentionExhausted(reason='deadline_exhausted')``.  The
    accepted bound is ``deadline + one in-flight attempt``: an attempt that
    already started cannot be stopped, and Firestore retires any chain at
    270 s; callers keep a post-transaction margin (the sync handler's 120 s)
    to absorb that tail.  Callers without a deadline keep the attempt-only
    bound — expiry at three fresh chains, Aborted at ``max_attempts``.
    """

    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")

    if deadline is None:
        deadline = _retry_deadline.get()
    last_error: Exception | None = None
    last_attempt_seconds = 0.0
    expired_chains = 0
    for attempt in range(1, max_attempts + 1):
        if attempt > 1 and deadline is not None:
            remaining = deadline - monotonic()
            reserve = max(last_attempt_seconds * RETRY_RESERVE_FACTOR, RETRY_RESERVE_FLOOR_SECONDS)
            if remaining < reserve:
                logger.error(
                    "firestore_transaction_contention operation=%s attempt=%d/%d outcome=deadline_exhausted "
                    "remaining_ms=%d reserve_ms=%d",
                    operation_name,
                    attempt,
                    max_attempts,
                    round(remaining * 1000),
                    round(reserve * 1000),
                )
                error = FirestoreContentionExhausted(
                    f"Firestore transaction retry deadline exhausted for {operation_name}",
                    reason="deadline_exhausted",
                )
                if last_error is not None:
                    raise error from last_error
                raise error
        attempt_started = monotonic()
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
            last_error = error
            last_attempt_seconds = monotonic() - attempt_started
            if not _is_transaction_contention(error):
                raise
            if _is_expired_transaction(error):
                expired_chains += 1
            if attempt >= max_attempts or (
                deadline is None and expired_chains >= _EXPIRED_CHAIN_CEILING_WITHOUT_DEADLINE
            ):
                # The attempt cap, or — with no wall-clock budget in scope —
                # the expired-chain ceiling at today's run_transactional default.
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
            if deadline is not None and deadline - monotonic() < delay:
                # Never sleep past the deadline: after the attempts themselves,
                # the jitter would be the only remaining overspend.
                logger.error(
                    "firestore_transaction_contention operation=%s attempt=%d/%d outcome=deadline_exhausted "
                    "remaining_ms=%d delay_ms=%d",
                    operation_name,
                    attempt,
                    max_attempts,
                    round((deadline - monotonic()) * 1000),
                    round(delay * 1000),
                )
                raise FirestoreContentionExhausted(
                    f"Firestore transaction retry deadline exhausted for {operation_name}",
                    reason="deadline_exhausted",
                ) from error
            logger.warning(
                "firestore_transaction_contention operation=%s attempt=%d/%d outcome=retry delay_ms=%d",
                operation_name,
                attempt,
                max_attempts,
                round(delay * 1000),
            )
            sleep(delay)

    raise AssertionError("unreachable")
