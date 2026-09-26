"""Claim-local proof at the daily summary agent's provider boundary.

Only the instrumented agent can certify a preparation failure. Mutable QA
evidence and exception type alone are never proof; the exact issued exception
must belong to the current claim and its irreversible dispatch latch be clear.
"""

from contextvars import ContextVar, Token
from functools import wraps
from typing import Callable, ParamSpec, TypeVar

from models.memory_contracts import MemoryExtractionError

_P = ParamSpec('_P')
_R = TypeVar('_R')
_active: ContextVar['SweepDispatchScope | None'] = ContextVar('sweep_dispatch_scope', default=None)


class SweepPreDispatchError(MemoryExtractionError):
    """A typed signal, accepted only with its issuing claim's live proof."""


class SweepDispatchScope:
    def __init__(self, *, before_provider_dispatch: Callable[[], None] | None = None) -> None:
        self._before_provider_dispatch = before_provider_dispatch
        self._dispatched = False
        self._issued: SweepPreDispatchError | None = None
        self._reason: str | None = None
        self._token: Token['SweepDispatchScope | None'] | None = None

    def __enter__(self) -> 'SweepDispatchScope':
        self._token = _active.set(self)
        return self

    def __exit__(self, *_args: object) -> None:
        assert self._token is not None
        _active.reset(self._token)

    def proves_pre_dispatch(self, error: Exception) -> bool:
        return error is self._issued and not self._dispatched

    def pre_dispatch_reason(self, error: Exception) -> str | None:
        return self._reason if self.proves_pre_dispatch(error) else None

    @staticmethod
    def mark_provider_dispatch() -> None:
        """Latch before recording request evidence or entering any provider call."""
        scope = _active.get()
        if scope is not None:
            if scope._before_provider_dispatch is not None:
                scope._before_provider_dispatch()
            scope._dispatched = True

    @staticmethod
    def certify_pre_dispatch(function: Callable[_P, _R]) -> Callable[_P, _R]:
        """Wrap only the instrumented summary agent, never an arbitrary builder."""

        @wraps(function)
        def wrapped(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            try:
                return function(*args, **kwargs)
            except Exception as error:
                scope = _active.get()
                if scope is None or scope._dispatched:
                    raise
                reason = error.extractor if isinstance(error, MemoryExtractionError) else 'daily_sweep_summary_agent'
                if reason not in {
                    'daily_sweep_summary_input_budget',
                    'daily_sweep_summary_agent',
                    'source_locked_before_dispatch',
                    'source_lock_check_unavailable',
                }:
                    reason = 'daily_sweep_summary_agent'
                certified = SweepPreDispatchError(reason)
                scope._issued = certified
                scope._reason = reason
                raise certified from error

        return wrapped
