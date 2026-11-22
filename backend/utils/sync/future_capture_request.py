"""One router outcome per eligible far-future upload request."""

from collections.abc import Awaitable, Callable, Iterable
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum
from functools import wraps
from typing import ParamSpec, TypeVar

from prometheus_client import Counter

from utils.sync.capture_clock import is_implausible_future_capture_time
from utils.sync.files import get_timestamp_from_path


class Outcome(StrEnum):
    PREFLIGHT_REFUSED = 'preflight_refused'
    IDENTITY_REQUIRED = 'identity_required'
    ROUTE_DECLINED = 'route_declined'
    PRIOR_CUSTODY = 'prior_custody'
    DECODE_MEMO_HIT = 'decode_memo_hit'
    DECODE_FAILED = 'decode_failed'
    PRE_OFFSET_ERROR = 'pre_offset_error'
    REACHED_OFFSETS = 'reached_offsets'


_OUTCOMES = Counter(
    'omi_sync_future_capture_request_outcome_total',
    'One outcome per clamp-enabled v2 upload request carrying a far-future file',
    ('outcome',),
)
for _outcome in Outcome:
    _OUTCOMES.labels(outcome=_outcome).inc(0)


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
                    _OUTCOMES.labels(outcome=observation.outcome).inc()
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


def mark(outcome: Outcome) -> None:
    observation = _observation.get()
    if observation is not None and observation.eligible and observation.outcome is not Outcome.REACHED_OFFSETS:
        observation.outcome = outcome
