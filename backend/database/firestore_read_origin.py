"""Bounded, best-effort read attribution. Labels never contain request paths or IDs.

Use ``with read_origin('job:daily_summary')`` or the same expression as a
sync/async function decorator. Names are registered on first recording, with a
process-wide cap. Pass source-code constants, never user-derived job names.
"""

import inspect
import re
import threading
from contextlib import ContextDecorator
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, Literal, TypeVar, cast

from prometheus_client import REGISTRY, Counter

MAX_ORIGINS = 400


def _origin_label_overflow_counter() -> Counter:
    # Import isolation evicts modules while the process-wide registry survives.
    try:
        return Counter(
            'omi_firestore_origin_label_overflow_total',
            'Firestore read origin observations folded into overflow because the origin cap is full.',
        )
    except ValueError:
        return cast(
            Counter,
            REGISTRY._names_to_collectors['omi_firestore_origin_label_overflow_total'],  # type: ignore[attr-defined]
        )


FIRESTORE_ORIGIN_LABEL_OVERFLOW = _origin_label_overflow_counter()
_known_origins: set[str] = set()
_origin_lock = threading.Lock()
_JOB_NAME = re.compile(r'^(job|task):[A-Za-z_][A-Za-z0-9_.:-]{0,119}$')
# Existing launcher names include uid/job/session suffixes. Keep those solely
# on asyncio.Task, never on telemetry. These are source-code task families.
_TASK_FAMILIES = (
    'transcript_import',
    'migrate_memories',
    'migrate_persona_accounts',
    'fair_use_classifier',
    'sync_fair_use_classifier',
    'sync_job_fair_use_classifier',
    'sync_pipeline',
    'pusher_finalization',
    'sync:uid-lease',
    'sync:inline-lease',
)
_F = TypeVar('_F', bound=Callable[..., Any])

_read_origin: ContextVar[Any] = ContextVar('firestore_read_origin', default=None)
_SCOPE_ORIGIN_CACHE = '_omi_firestore_read_origin'


def _bounded_origin(label: str) -> str:
    if label in ('unset', 'http:unmatched', 'ws:unmatched', 'overflow'):
        return label
    if label in _known_origins:
        return label
    with _origin_lock:
        if label in _known_origins:
            return label
        if len(_known_origins) < MAX_ORIGINS:
            _known_origins.add(label)
            return label
    FIRESTORE_ORIGIN_LABEL_OVERFLOW.inc()
    return 'overflow'


def current_read_origin() -> str:
    """Resolve Starlette's route only at recording time, after routing ran."""
    try:
        value = _read_origin.get()
        if isinstance(value, dict):
            protocol = 'ws' if value.get('type') == 'websocket' else 'http'
            path = getattr(value.get('route'), 'path', None)
            # Only router-owned templates are used, never scope['path'].
            path = path if isinstance(path, str) and path.startswith('/') else None
            cached: Any = value.get(_SCOPE_ORIGIN_CACHE)
            if cached is not None and cached[:2] == (protocol, path):
                label = cached[2]
            else:
                label = f'{protocol}:{path}' if path is not None else f'{protocol}:unmatched'
                value[_SCOPE_ORIGIN_CACHE] = (protocol, path, label)
        elif isinstance(value, str) and _JOB_NAME.fullmatch(value):
            label = value
        else:
            label = 'unset'
        return _bounded_origin(label)
    except Exception:
        return 'unset'


class read_origin(ContextDecorator):
    """Scoped constant job/task origin; safe for concurrent decorator invocations."""

    def __init__(self, name: str):
        self.name = name

    def _recreate_cm(self) -> 'read_origin':
        return type(self)(self.name)

    def __enter__(self) -> 'read_origin':
        self.token = _read_origin.set(self.name)
        return self

    def __exit__(self, *exc: object) -> Literal[False]:
        _read_origin.reset(self.token)
        return False

    def __call__(self, func: _F) -> _F:
        if inspect.iscoroutinefunction(func):

            @wraps(func)
            async def wrapped(*args: Any, **kwargs: Any) -> Any:
                with self._recreate_cm():
                    return await func(*args, **kwargs)

            return cast(_F, wrapped)
        return super().__call__(func)


def bind_read_scope(scope: Any):
    """Middleware-only binding; retains the live scope for lazy route resolution."""
    return _read_origin.set(scope)


def reset_read_scope(token: Any) -> None:
    _read_origin.reset(token)


def background_task_read_origin(name: str) -> read_origin:
    """Strip known runtime identifier suffixes without changing the task's name."""
    try:
        for family in _TASK_FAMILIES:  # Fixed-size registry, independent of reads/users.
            if name.startswith(family + ':'):
                return read_origin(f'task:{family}')
        if name.startswith('x_initial_sync_'):
            return read_origin('task:x_initial_sync')
        return read_origin(f'task:{name}')
    except Exception:
        return read_origin('unset')
