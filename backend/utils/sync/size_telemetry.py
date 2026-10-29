"""Content-free attribution scoped to one sync call and one size-backstop run."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import wraps
from inspect import signature
from logging import Logger
from typing import Callable, Iterator, ParamSpec, TypeVar

from config.sync_telemetry import bounded_correlation_ref
from utils.conversation_shape_fields import bucket_le, segment_count, speech_seconds
from utils.metrics import CONVERSATION_DURATION_BUCKETS, CONVERSATION_SEGMENT_BUCKETS


@dataclass
class _Attribution:
    job_ref: str = 'none'
    attempt_ref: str = 'none'
    # Keys stay in memory only; values contain buckets, never transcript text.
    shapes: dict[str, str] = field(default_factory=dict)
    backstop: bool = False
    rollover: str | None = None


_P = ParamSpec('_P')
_R = TypeVar('_R')

_current: ContextVar[_Attribution | None] = ContextVar('sync_size_attribution', default=None)


def shape_fields(payload: dict | None) -> str:
    if payload is None or not isinstance(payload.get('transcript_segments'), list):
        return 'segments_bucket=unknown speech_seconds_bucket=unknown'
    return (
        f'segments_bucket={bucket_le(segment_count(payload), CONVERSATION_SEGMENT_BUCKETS)} '
        f'speech_seconds_bucket={bucket_le(speech_seconds(payload), CONVERSATION_DURATION_BUCKETS)}'
    )


def remember_size_payload(cid: str | None, payload: dict) -> None:
    current = _current.get()
    if current is not None and cid is not None:
        current.shapes[cid] = shape_fields(payload)


def size_fields(payload: dict | None = None, *, cid: str | None = None, target_kind: str = 'none') -> str:
    current = _current.get() or _Attribution()
    shape = current.shapes.get(cid, shape_fields(payload)) if cid is not None else shape_fields(payload)
    target_kind = target_kind if target_kind in {'new_row', 'sibling_row', 'none'} else 'none'
    return f'job_ref={current.job_ref} attempt_ref={current.attempt_ref} {shape} ' f'rollover_target_kind={target_kind}'


def log_size_rollover(log: Logger, message: str, *args: object) -> None:
    if args:
        message = message % args
    current = _current.get()
    if current is not None and current.backstop:
        current.rollover = message
    else:
        log.warning('%s stage=plan', message)


def finish_size_attempt(log: Logger, *, committed: bool) -> None:
    current = _current.get()
    if current is not None and current.rollover is not None:
        if committed:
            log.warning('%s stage=commit', current.rollover)
        current.rollover = None


@contextmanager
def size_backstop_scope() -> Iterator[None]:
    parent = _current.get() or _Attribution()
    token = _current.set(_Attribution(parent.job_ref, parent.attempt_ref, backstop=True))
    try:
        yield
    finally:
        _current.reset(token)


def with_size_attribution(fn: Callable[_P, _R]) -> Callable[_P, _R]:
    """Keep refs across synchronous ingestion without persisting them in a row."""

    call_signature = signature(fn)

    @wraps(fn)
    def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        arguments = call_signature.bind_partial(*args, **kwargs).arguments
        token = _current.set(
            _Attribution(
                bounded_correlation_ref(arguments.get('job_id')), bounded_correlation_ref(arguments.get('attempt_ref'))
            )
        )
        try:
            return fn(*args, **kwargs)
        finally:
            _current.reset(token)

    return wrapped
