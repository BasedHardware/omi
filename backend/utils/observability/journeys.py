"""Closed, privacy-safe outcome metrics for real product traffic journeys."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterable, AsyncIterator, Callable, Mapping
from datetime import datetime, timezone
from time import monotonic
from typing import Literal, TypeVar, cast

from starlette.requests import ClientDisconnect

from utils.metrics import (
    OMI_CAPTURE_FINALIZATION_RECONCILIATIONS_TOTAL,
    OMI_CLIENT_JOURNEY_ACCEPTED_TOTAL,
    OMI_CLIENT_JOURNEY_DURATION_SECONDS,
    OMI_CLIENT_JOURNEY_ISSUES_TOTAL,
    OMI_CLIENT_JOURNEY_TERMINAL_TOTAL,
    OMI_JOURNEY_ACCEPTED_TOTAL,
    OMI_JOURNEY_LATENCY_SECONDS,
    OMI_JOURNEY_TERMINAL_TOTAL,
)
from utils.journey_metrics_contract import (
    ClientJourneyIssueClass,
    ClientJourneyName,
    ClientJourneyOutcome,
    ClientKind,
    bounded_client_journey,
    bounded_client_journey_issue_class,
    bounded_client_journey_outcome,
    bounded_client_kind,
    resolve_client_kind,
)

JourneyName = Literal['chat_response', 'pusher_session', 'capture_finalization']
JourneyOutcome = Literal['success', 'failure', 'cancelled', 'stale']
ReconciliationOutcome = Literal['requeued', 'enqueue_failed']

_JOURNEYS = frozenset({'chat_response', 'pusher_session', 'capture_finalization'})
_OUTCOMES = frozenset({'success', 'failure', 'cancelled', 'stale'})
_RECONCILIATION_OUTCOMES = frozenset({'requeued', 'enqueue_failed'})


def _journey(value: str) -> JourneyName:
    if value not in _JOURNEYS:
        raise ValueError(f'unknown journey: {value}')
    return cast(JourneyName, value)


def _outcome(value: str) -> JourneyOutcome:
    if value not in _OUTCOMES:
        raise ValueError(f'unknown journey outcome: {value}')
    return cast(JourneyOutcome, value)


def record_journey_accepted(journey: JourneyName) -> None:
    """Record an accepted journey after its authoritative durable/protocol boundary."""
    OMI_JOURNEY_ACCEPTED_TOTAL.labels(journey=_journey(journey)).inc()


def record_journey_terminal(journey: JourneyName, outcome: JourneyOutcome, elapsed_seconds: float) -> None:
    """Record exactly one terminal outcome and its elapsed time for one journey."""
    labels = {'journey': _journey(journey), 'outcome': _outcome(outcome)}
    OMI_JOURNEY_TERMINAL_TOTAL.labels(**labels).inc()
    OMI_JOURNEY_LATENCY_SECONDS.labels(**labels).observe(max(0.0, elapsed_seconds))


class JourneyAttempt:
    """In-process accepted journey with a one-shot terminal outcome."""

    def __init__(self, journey: JourneyName) -> None:
        self.journey: JourneyName = _journey(journey)
        self.started_at = monotonic()
        self._finished = False
        record_journey_accepted(self.journey)

    @property
    def finished(self) -> bool:
        return self._finished

    def finish(self, outcome: JourneyOutcome) -> None:
        if self._finished:
            return
        self._finished = True
        record_journey_terminal(self.journey, outcome, monotonic() - self.started_at)


_StreamItem = TypeVar('_StreamItem')


class _ObservedClientJourneyStream(AsyncIterator[_StreamItem]):
    """Lazily start an observed stream and close abandoned attempts."""

    def __init__(
        self,
        attempt: 'ClientJourneyAttempt',
        iterator_factory: Callable[[], AsyncIterator[_StreamItem]],
    ) -> None:
        self._attempt = attempt
        self._iterator_factory = iterator_factory
        self._iterator: AsyncIterator[_StreamItem] | None = None

    def __aiter__(self) -> '_ObservedClientJourneyStream[_StreamItem]':
        return self

    async def __anext__(self) -> _StreamItem:
        if self._iterator is None:
            self._iterator = self._iterator_factory()
        return await self._iterator.__anext__()

    async def aclose(self) -> None:
        if self._iterator is None:
            self._attempt.abandon_stream()
            return
        close = getattr(self._iterator, 'aclose', None)
        if close is not None:
            await close()
        if not self._attempt.finished:
            self._attempt.abandon_stream()

    def __del__(self) -> None:
        attempt = getattr(self, '_attempt', None)
        if attempt is not None and not attempt.finished:
            try:
                attempt.abandon_stream()
            except Exception:
                # Object finalizers may run during interpreter shutdown.
                pass


logger = logging.getLogger(__name__)

_RECORDER_WARNING_INTERVAL_SECONDS = 60.0
_recorder_warning_lock = threading.Lock()
_last_recorder_warning_at = 0.0


def _record_fail_open(what: str, record: Callable[[], None]) -> None:
    """Run a metric write that must never propagate into a product request.

    Observability is not allowed to break the thing it observes. It is equally
    not allowed to fail silently: a recorder that quietly stops writing is
    indistinguishable from a healthy path with nothing to report, which is the
    failure mode this whole metric family exists to make visible. Failures are
    swallowed for the caller and logged at a bounded rate for the operator.
    """

    global _last_recorder_warning_at
    try:
        record()
    except Exception:
        now = monotonic()
        with _recorder_warning_lock:
            due = now - _last_recorder_warning_at >= _RECORDER_WARNING_INTERVAL_SECONDS
            if due:
                _last_recorder_warning_at = now
        if due:
            logger.warning('client_journey_metric_record_failed what=%s', what, exc_info=True)


def record_client_journey_accepted(journey: object, client_kind: object) -> None:
    """Record a bounded acceptance event without creating labels from raw input."""

    _record_fail_open(
        'accepted',
        lambda: OMI_CLIENT_JOURNEY_ACCEPTED_TOTAL.labels(
            journey=bounded_client_journey(journey),
            client_kind=bounded_client_kind(client_kind),
        ).inc(),
    )


def record_client_journey_terminal(
    journey: object,
    client_kind: object,
    outcome: object,
    elapsed_seconds: float,
    *,
    issue_class: object | None = None,
) -> None:
    """Record one bounded terminal event plus duration and optional issue detail.

    This function is also the cross-process API: a durable worker can pass an
    elapsed duration derived from persisted acceptance time. These counters are
    not queue state and must never be subtracted to infer in-flight work.
    """

    def _record() -> None:
        journey_label = bounded_client_journey(journey)
        client_kind_label = bounded_client_kind(client_kind)
        outcome_label = bounded_client_journey_outcome(outcome)
        OMI_CLIENT_JOURNEY_TERMINAL_TOTAL.labels(
            journey=journey_label,
            client_kind=client_kind_label,
            outcome=outcome_label,
        ).inc()
        OMI_CLIENT_JOURNEY_DURATION_SECONDS.labels(
            journey=journey_label,
            outcome=outcome_label,
        ).observe(max(0.0, elapsed_seconds))
        if outcome_label in {'failure', 'degraded', 'unknown'}:
            OMI_CLIENT_JOURNEY_ISSUES_TOTAL.labels(
                journey=journey_label,
                client_kind=client_kind_label,
                issue_class=bounded_client_journey_issue_class(issue_class),
            ).inc()

    _record_fail_open('terminal', _record)


class ClientJourneyAttempt:
    """Fail-closed client journey attempt with streaming-aware completion.

    A normal context exit without an explicit terminal is a failure. Attaching
    a stream transfers terminal ownership to the returned iterator so a
    ``StreamingResponse`` can consume it after the context has exited.
    """

    def __init__(
        self,
        journey: ClientJourneyName,
        client_kind: ClientKind,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.journey = bounded_client_journey(journey)
        self.client_kind = bounded_client_kind(client_kind)
        self._clock = clock
        self.started_at = clock()
        self._outcome: ClientJourneyOutcome | None = None
        self._issue_class: ClientJourneyIssueClass | None = None
        self._stream_active = False
        self._stream_attached = False
        self._stream_success_requested = False
        record_client_journey_accepted(self.journey, self.client_kind)

    @property
    def finished(self) -> bool:
        return self._outcome is not None

    @property
    def outcome(self) -> ClientJourneyOutcome | None:
        return self._outcome

    @property
    def issue_class(self) -> ClientJourneyIssueClass | None:
        return self._issue_class

    def __enter__(self) -> 'ClientJourneyAttempt':
        return self

    def __exit__(self, exc_type: type[BaseException] | None, _exc: BaseException | None, _tb: object) -> bool:
        if not self.finished and exc_type is not None:
            self.fail('unknown')
        elif not self.finished and not self._stream_attached:
            self.fail('incomplete_attempt')
        return False

    def finish(self, outcome: object, *, issue_class: object | None = None) -> None:
        outcome_label = bounded_client_journey_outcome(outcome)
        if outcome_label == 'success' and self._stream_attached:
            self._stream_success_requested = True
            return
        if self.finished:
            return
        self._outcome = outcome_label
        self._issue_class = (
            bounded_client_journey_issue_class(issue_class)
            if outcome_label in {'failure', 'degraded', 'unknown'}
            else None
        )
        record_client_journey_terminal(
            self.journey,
            self.client_kind,
            outcome_label,
            self._clock() - self.started_at,
            issue_class=self._issue_class,
        )

    def succeed(self) -> None:
        self.finish('success')

    def fail(self, issue_class: object = 'unknown') -> None:
        self.finish('failure', issue_class=issue_class)

    def degrade(self, issue_class: object) -> None:
        self.finish('degraded', issue_class=issue_class)

    def cancel(self) -> None:
        self.finish('cancelled')

    def abandon_stream(self) -> None:
        """Terminalize an attached stream that was not exhausted."""

        self._stream_active = False
        self._stream_attached = False
        self.cancel()

    def observe_stream(
        self,
        source: AsyncIterable[_StreamItem],
        *,
        success_when: Callable[[_StreamItem], bool],
        failure_when: Callable[[_StreamItem], bool],
        failure_class: object = 'provider_error',
        missing_success_class: object = 'empty_answer',
    ) -> AsyncIterator[_StreamItem]:
        """Yield a stream and terminalize only after its semantic contract is known.

        ``failure_when`` terminalizes immediately, so an in-band error frame
        wins over a later success marker. Seeing a success item is necessary but
        not sufficient: clean exhaustion is also required, so a later source
        exception cannot leave a success.
        """

        if self._stream_attached:
            raise RuntimeError('a stream is already attached to this journey attempt')
        self._stream_attached = True

        async def observed() -> AsyncIterator[_StreamItem]:
            success_observed = False
            self._stream_active = True
            try:
                async for item in source:
                    if not self.finished:
                        if failure_when(item):
                            self.fail(failure_class)
                        elif success_when(item):
                            success_observed = True
                    yield item
            except (asyncio.CancelledError, GeneratorExit, ClientDisconnect, OSError):
                self.abandon_stream()
                raise
            except BaseException:
                self._stream_active = False
                self._stream_attached = False
                self.fail(failure_class)
                raise
            else:
                self._stream_active = False
                self._stream_attached = False
                if not self.finished:
                    if success_observed or self._stream_success_requested:
                        self.succeed()
                    else:
                        self.fail(missing_success_class)
            finally:
                self._stream_active = False
                self._stream_attached = False
                if not self.finished:
                    self.fail('incomplete_stream')

        return _ObservedClientJourneyStream(self, observed)


def record_conversation_finalization_client_terminal(
    outcome: object,
    job: Mapping[str, object],
    *,
    client_kind: object | None = None,
    issue_class: object | None = None,
) -> None:
    """Terminalize a client journey only when its originating client is known."""

    def _record() -> None:
        resolved_client_kind = client_kind
        if resolved_client_kind is None:
            if 'client_platform' not in job:
                return
            resolved_client_kind = resolve_client_kind(x_app_platform=job.get('client_platform'), user_agent=None)
        accepted_at = job.get('created_at')
        if not isinstance(accepted_at, datetime):
            logger.warning('Conversation finalization client metric missing accepted timestamp')
            return
        if accepted_at.tzinfo is None:
            accepted_at = accepted_at.replace(tzinfo=timezone.utc)
        record_client_journey_terminal(
            'conversation_finalization',
            bounded_client_kind(resolved_client_kind),
            outcome,
            (datetime.now(timezone.utc) - accepted_at).total_seconds(),
            issue_class=issue_class,
        )

    _record_fail_open('conversation finalization terminal', _record)


def record_capture_finalization_terminal(outcome: JourneyOutcome, accepted_at: datetime | None) -> None:
    """Terminalize a durable capture job using its persisted acceptance time."""
    if accepted_at is None:
        # Legacy jobs can predate created_at. Keep the outcome visible without
        # fabricating a latency value.
        labels = {'journey': _journey('capture_finalization'), 'outcome': _outcome(outcome)}
        OMI_JOURNEY_TERMINAL_TOTAL.labels(**labels).inc()
        return
    if accepted_at.tzinfo is None:
        accepted_at = accepted_at.replace(tzinfo=timezone.utc)
    elapsed_seconds = (datetime.now(timezone.utc) - accepted_at).total_seconds()
    record_journey_terminal('capture_finalization', outcome, elapsed_seconds)


def record_capture_finalization_reconciliation(outcome: ReconciliationOutcome) -> None:
    """Record a bounded reconciliation event for stale capture work."""
    if outcome not in _RECONCILIATION_OUTCOMES:
        raise ValueError(f'unknown finalization reconciliation outcome: {outcome}')
    OMI_CAPTURE_FINALIZATION_RECONCILIATIONS_TOTAL.labels(outcome=outcome).inc()
