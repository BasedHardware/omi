"""One router outcome per eligible far-future upload request."""

from collections.abc import Awaitable, Callable, Iterable
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from typing import ParamSpec, TypeVar

from prometheus_client import Counter

from utils.observability.reasons import FutureCaptureRequestOutcome as Outcome
from utils.observability.reasons import ReasonFamily, reason_label
from utils.sync.capture_clock import is_implausible_future_capture_time
from utils.sync.files import get_timestamp_from_path

_OUTCOMES = Counter(
    'omi_sync_future_capture_request_outcome_total',
    'One outcome per eligible v2 far-future upload or durable receipt-clock repair',
    ('outcome',),
)
for _outcome in Outcome:
    _OUTCOMES.labels(outcome=reason_label(ReasonFamily.SYNC_FUTURE_CAPTURE_REQUEST, _outcome, Outcome)).inc(0)


@dataclass
class _Observation:
    eligible: bool = False
    outcome: Outcome = Outcome.PRE_OFFSET_ERROR


# run_blocking propagates the context into the decode executor. The decoder marks
# the same observation for both admission and repair. Only the route emits it.
_observation: ContextVar[_Observation | None] = ContextVar('future_capture_request', default=None)

P = ParamSpec('P')
R = TypeVar('R')


def observe_upload(handler: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(handler)
    async def run(*args: P.args, **kwargs: P.kwargs) -> R:
        observation = _Observation()
        token = _observation.set(observation)
        try:
            return await handler(*args, **kwargs)
        finally:
            _observation.reset(token)
            if observation.eligible:
                try:
                    _OUTCOMES.labels(
                        outcome=reason_label(ReasonFamily.SYNC_FUTURE_CAPTURE_REQUEST, observation.outcome, Outcome)
                    ).inc()
                except Exception:
                    pass  # Telemetry must preserve the response or exception.

    return run


def classify_upload(filenames: Iterable[str], received_at: float) -> None:
    observation = _observation.get()
    if observation is None:
        return
    for filename in filenames:
        try:
            if is_implausible_future_capture_time(get_timestamp_from_path(filename), now=received_at):
                observation.eligible = True
                return
        except Exception:
            # Staging retains the authoritative validation and refusal order.
            # A malformed sibling can still accompany an eligible file.
            continue


def include_receipt_clock_repair() -> None:
    observation = _observation.get()
    if observation is not None:
        observation.eligible = True


def mark(outcome: Outcome) -> None:
    observation = _observation.get()
    if observation is not None and observation.eligible and observation.outcome is not Outcome.REACHED_OFFSETS:
        observation.outcome = outcome
