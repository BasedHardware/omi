"""Queue consumer protocol and the push/pull drivers (contract (a)).

The batch GPU worker keeps ``WorkerQueue`` unchanged; this protocol is for CPU kinds (enrichment,
provider STT) hosted on the ``workers`` role. Push deliveries are Cloud Tasks wakes named
``{prefix}-{row_id}-{wake_token}``; the outbox row is the only state.

Response mapping (contract (d)), via ``http_response``:
    DONE / DEFERRED / DISCARDED / STALE / BUSY -> 200 {"status": outcome, "reason": reason}
    RETRY                                       -> 409 retry.retry_response(reason)
An unexpected exception propagates (the route answers 500) and counts ``omi_consumer_unexpected_total``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable, ClassVar, Protocol

from fastapi.responses import JSONResponse
from prometheus_client import Counter

from database.outbox import Claim, Outbox, OutboxKind, Outcome
from utils.observability.reasons import ConsumerReason, RetryReason
from utils.workers.retry import retry_response

__all__ = [
    'Claim',
    'Outbox',
    'OutboxKind',
    'Outcome',
    'QueueConsumer',
    'Result',
    'Role',
    'http_response',
    'run_pull',
    'run_push',
]

CONSUMER_UNEXPECTED_TOTAL = Counter(
    'omi_consumer_unexpected_total',
    'Unexpected exceptions raised by queue consumers (the row stays leased; the sweep re-wakes it).',
    ['kind'],
)
CONSUMER_RESULTS_TOTAL = Counter(
    'omi_consumer_results_total',
    'Queue consumer deliveries by outcome and reason.',
    ['kind', 'outcome', 'reason'],
)


class Role(StrEnum):
    """Deployable role that hosts the consumer (B8 vocabulary)."""

    WORKERS = 'workers'  # CPU: enrichment, provider_stt, maintenance
    GPU_BATCH = 'gpu_batch'  # batch-pipeline-worker; consumes WorkerQueue, not QueueConsumer


@dataclass(frozen=True)
class Result:
    outcome: Outcome
    reason: ConsumerReason | RetryReason  # RETRY requires a RetryReason; every other outcome a ConsumerReason
    available_at: float | None = None  # required for RETRY and for DEFERRED returned by process(); None when
    # claim_key answered DEFERRED (the outbox already re-armed the row and created its wake)

    def __post_init__(self) -> None:
        outcome = Outcome(self.outcome)
        if outcome is Outcome.RETRY:
            if not isinstance(self.reason, RetryReason):
                raise TypeError('RETRY requires a RetryReason')
        elif not isinstance(self.reason, ConsumerReason):
            raise TypeError(f'{outcome.value} requires a ConsumerReason')
        if outcome is Outcome.RETRY and self.available_at is None:
            raise ValueError('retry requires available_at')


class QueueConsumer(Protocol):
    kind: ClassVar[OutboxKind]
    role: ClassVar[Role]
    lease_seconds: ClassVar[float]  # push kinds: > dispatch deadline (1500s), or >= 4 * heartbeat_seconds
    heartbeat_seconds: ClassVar[float]  # <= lease_seconds / 4; 0 means no heartbeat

    def process(self, claim: Claim, heartbeat: Callable[[], bool]) -> Result:
        """``heartbeat()`` renews lease_until; False means the lease was lost: stop and return STALE."""
        ...


_LOST_LEASE = Result(Outcome.STALE, ConsumerReason.STALE_TOKEN)


def _settle(consumer: QueueConsumer, outbox: Outbox, claim: Claim, result: Result, now: float) -> Result:
    """Apply a consumer's result to the row. A fenced-out write means the lease was lost: STALE."""
    reason = result.reason.value
    if result.outcome in (Outcome.DONE, Outcome.DISCARDED):
        settled = outbox.ack(claim, reason, now=now)
    elif result.outcome is Outcome.DEFERRED:
        if result.available_at is None:
            raise ValueError('a consumer that defers must return available_at')
        # The outbox re-arms the row and creates the new wake itself (contract (b)).
        settled = outbox.defer(claim, result.available_at, reason, now=now) is not None
    elif result.outcome is Outcome.RETRY:
        settled = outbox.release(claim, reason, now=now)
    else:  # STALE / BUSY: the consumer found it no longer owns the work; nothing to write
        settled = True
    return result if settled else _LOST_LEASE


def _process(consumer: QueueConsumer, outbox: Outbox, claim: Claim, now: float) -> Result:
    # One clock for the lease: settle no earlier than the last heartbeat. A settle at the entry ``now`` after a
    # long, heartbeated run would place the outbox's settle/coalesce window in the past (M1 Grok L01-1).
    latest = [now]

    def heartbeat() -> bool:
        latest[0] = max(latest[0], time.time())
        return outbox.heartbeat(claim, consumer.lease_seconds, now=latest[0])

    try:
        result = consumer.process(claim, heartbeat)
    except Exception:
        CONSUMER_UNEXPECTED_TOTAL.labels(kind=consumer.kind.value).inc()
        raise
    return _settle(consumer, outbox, claim, result, latest[0])


def _count(consumer: QueueConsumer, result: Result) -> Result:
    CONSUMER_RESULTS_TOTAL.labels(
        kind=consumer.kind.value, outcome=result.outcome.value, reason=result.reason.value
    ).inc()
    return result


def run_push(consumer: QueueConsumer, outbox: Outbox, row_id: str, wake_token: str, *, now: float) -> Result:
    """Handle one Cloud Tasks wake: claim by key, process, settle the row."""
    claimed = outbox.claim_key(row_id, wake_token, consumer.lease_seconds, now=now)
    if not isinstance(claimed, Claim):
        outcome = Outcome(claimed)
        if outcome is Outcome.BUSY:
            return _count(consumer, Result(Outcome.BUSY, ConsumerReason.LEASE_HELD))
        if outcome is Outcome.STALE:
            return _count(consumer, Result(Outcome.STALE, ConsumerReason.STALE_TOKEN))
        if outcome is Outcome.DEFERRED:  # not due: the outbox re-armed the row and created its wake
            return _count(consumer, Result(Outcome.DEFERRED, ConsumerReason.NOT_DUE))
        if outcome is Outcome.DISCARDED:
            return _count(consumer, Result(Outcome.DISCARDED, ConsumerReason.SUPERSEDED))
        raise ValueError(f'claim_key returned unsupported outcome {outcome.value!r}')
    return _count(consumer, _process(consumer, outbox, claimed, now))


def run_pull(consumer: QueueConsumer, outbox: Outbox, *, limit: int, now: float) -> list[Result]:
    """Claim up to ``limit`` due rows and process each; one consumer exception stops the batch."""
    results: list[Result] = []
    for claim in outbox.claim(limit, consumer.lease_seconds, now=now):
        results.append(_count(consumer, _process(consumer, outbox, claim, now)))
    return results


def http_response(result: Result) -> JSONResponse:
    """The only push mapping (contract (d)): 200 for consumed deliveries, 409 retry for RETRY."""
    if result.outcome is Outcome.RETRY:
        return retry_response(result.reason)  # type: ignore[arg-type]
    return JSONResponse(status_code=200, content={'status': result.outcome.value, 'reason': result.reason.value})
