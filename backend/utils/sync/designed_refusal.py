"""Owns the one log record that marks a sync-local-files 503 as a designed refusal.

The Cloud Run rollout guard (``cloud-run-guard.json`` ``designed_refusals``)
excludes a ``POST /v2/sync-local-files`` 503 from its error rate only when one
``sync_upload_refused uid=... status=503 reason=... trace=...`` stdout line names
that request's trace id. Every other 503 counts as a failure.

The handler only *marks* a designed refusal, immediately before returning or
raising its 503. The record is written by the outermost wrapper once the final
outcome is known, and only when that outcome is the very response or exception
the handler produced and it is a 503. A wrapper that replaces it (for example
the custody finalizer's own 503) leaves the request unrecorded, so it counts.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, Optional, ParamSpec, TypeVar

logger = logging.getLogger(__name__)

_CLOUD_TRACE_ID = re.compile(r'([0-9a-fA-F]{32})(?:/|$)')
P = ParamSpec('P')
R = TypeVar('R')


@dataclass
class _Request:
    mark: Optional[tuple[str, str, str]] = None
    outcome: Any = None


_request: ContextVar[_Request | None] = ContextVar('sync_designed_refusal', default=None)


def mark_designed_refusal(uid: str, reason: str, cloud_trace_context: Optional[str]) -> None:
    """Mark this request's upcoming 503 as designed. Outside ``records_designed_refusals`` it is a no-op."""
    request = _request.get()
    if request is None:
        return
    match = _CLOUD_TRACE_ID.match(cloud_trace_context) if isinstance(cloud_trace_context, str) else None
    request.mark = (uid, reason, match.group(1).lower() if match else '-')


def records_designed_refusals(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Outermost runtime wrapper: write the record only for the handler's own final 503."""

    @wraps(fn)
    async def run(*args: P.args, **kwargs: P.kwargs) -> R:
        request = _Request()
        token = _request.set(request)
        try:
            result = await fn(*args, **kwargs)
        except BaseException as error:
            _record(request, error)
            raise
        else:
            _record(request, result)
            return result
        finally:
            _request.reset(token)

    return run


def designed_refusal_outcome(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Innermost wrapper: remember exactly what the handler itself returned or raised."""

    @wraps(fn)
    async def run(*args: P.args, **kwargs: P.kwargs) -> R:
        request = _request.get()
        try:
            result = await fn(*args, **kwargs)
        except BaseException as error:
            if request is not None:
                request.outcome = error
            raise
        if request is not None:
            request.outcome = result
        return result

    return run


def _record(request: _Request, final: Any) -> None:
    if request.mark is None or final is not request.outcome or getattr(final, 'status_code', None) != 503:
        return
    uid, reason, trace = request.mark
    logger.info('sync_upload_refused uid=%s status=503 reason=%s trace=%s', uid, reason, trace)
