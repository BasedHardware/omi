"""What a database lock costs the live v3 builder's commit.

The builder ends a pass with one transaction over every recording row and conversation it loaded. A writer
that lands on one of those rows at the same moment (an uploaded unit being attached, a summary being stored)
makes Firestore abort the commit. The commit's retries are ``run_preloaded_transaction_with_contention_retry``
(up to three fresh transactions with a jittered wait, SCA-2918); this module changes none of that. It only
meters each commit: how it ended, how long it took with every attempt and wait included, how many extra
attempts were made and how many documents those attempts read again (the database cost of retrying).

``outcome="exhausted"`` is the commit that gave up on a lock. That pass is answered 409 and the task queue
runs it again on the queue's own schedule (30 s at the earliest), so its share of all commits is how often a
user waits that long for a pass, and the number to read before adding any faster follow-up.

Which document and which writer held the lock, and every pass thrown away by its own guards, is recorded by
``conversations_v3_collisions`` (``event=v3_pass_collision``); this module does not repeat it.

Production readback (backend-sync exports the commit counter and the two cost counters):
``sum by (outcome) (increase(omi_conversations_v3_builder_commit_total[1h]))`` for the share of commits that
recovered or gave up, ``increase(omi_conversations_v3_builder_commit_extra_reads_total[1h])`` against
``omi_firestore_billed_reads_total`` for the share of reads spent on retries. The duration histogram is read
from the service's own /metrics.
"""

import logging
import time
from typing import Callable, TypeVar

from prometheus_client import Counter, Histogram

from database.firestore_transaction_retry import (
    FirestoreContentionExhausted,
    _is_transaction_contention,  # pyright: ignore[reportPrivateUsage] -- the one shared definition of contention
)
from utils.conversations.v3 import Conflict

logger = logging.getLogger(__name__)

T = TypeVar('T')

# first_try: committed without contention. recovered: committed after at least one aborted attempt.
# exhausted: the commit gave up on a lock (every attempt was aborted, its transaction expired, or its time ran out).
# A pass thrown away by its own guards (source_changed, lease_lost and so on) has no outcome here: the
# collision record counts it as ``raced``.
OUTCOMES = ('first_try', 'recovered', 'exhausted', 'error')

COMMITS = Counter(
    'omi_conversations_v3_builder_commit_total',
    'Live v3 builder commit batches by outcome',
    ['outcome'],
)
EXTRA_ATTEMPTS = Counter(
    'omi_conversations_v3_builder_commit_extra_attempts_total',
    'Commit attempts beyond the first, made after a lock abort',
)
EXTRA_READS = Counter(
    'omi_conversations_v3_builder_commit_extra_reads_total',
    'Estimated documents read again by those extra attempts (the database cost of retrying)',
)
SECONDS = Histogram(
    'omi_conversations_v3_builder_commit_seconds',
    'Wall time of one live v3 builder commit batch, every attempt and lock wait included',
    ['outcome'],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32),
)
for _outcome in OUTCOMES:
    COMMITS.labels(_outcome)


def _now() -> float:
    return time.monotonic()


def _cost(attempts: int, reads_per_attempt: int) -> int:
    """Count the attempts beyond the first and the documents they read again. Returns those reads."""
    extra = max(0, attempts - 1)
    if extra:
        try:
            EXTRA_ATTEMPTS.inc(extra)
            EXTRA_READS.inc(extra * reads_per_attempt)
        except Exception:
            pass  # Meters never fail a commit.
    return extra * reads_per_attempt


def _record(outcome: str, started: float, attempts: int, reads_per_attempt: int) -> None:
    seconds = _now() - started
    extra_reads = _cost(attempts, reads_per_attempt)
    try:
        COMMITS.labels(outcome).inc()
        SECONDS.labels(outcome).observe(seconds)
    except Exception:
        pass
    if outcome == 'recovered':
        # What the lock cost a commit that got through: one line per commit, with the totals the
        # per-attempt ``v3_pass_collision outcome=lock_retried`` lines do not carry. A handled case, so info,
        # like those lines. A commit that gave up is logged by the collision record (``lock_failed``).
        logger.info(
            'event=v3_commit_contention outcome=%s attempts=%d seconds=%.2f extra_reads=%d',
            outcome,
            attempts,
            seconds,
            extra_reads,
        )


def run(
    execute: Callable[[], T],
    *,
    reads_per_attempt: int = 0,
    attempts: Callable[[], int] | None = None,
) -> T:
    """Run one commit batch of the live builder. ``execute`` runs the commit with its own retries.

    ``attempts`` reports how many times the transaction body has run so far (the retry runs it again
    after a lock abort); ``reads_per_attempt`` is the caller's estimate of the documents one run reads.
    Both only feed the meters. The result or the error of ``execute`` leaves unchanged.
    """
    started = _now()

    def tried() -> int:
        try:
            return max(1, int(attempts())) if attempts is not None else 1
        except Exception:
            return 1

    try:
        result = execute()
    except Conflict:
        # Thrown away by the pass's own guards, which the collision record reports. Only the attempts a
        # lock aborted before that are counted here.
        _cost(tried(), reads_per_attempt)
        raise
    except Exception as error:
        gave_up = isinstance(error, FirestoreContentionExhausted) or _is_transaction_contention(error)
        _record('exhausted' if gave_up else 'error', started, tried(), reads_per_attempt)
        raise
    _record('recovered' if tried() > 1 else 'first_try', started, tried(), reads_per_attempt)
    return result
