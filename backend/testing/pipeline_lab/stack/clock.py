"""Harness-owned virtual wall clock (DESIGN L3), with no new dependency.

Patched: ``time.time``, ``time.time_ns``, ``datetime.datetime.now/utcnow/today`` and
``datetime.date.today``, in the ``time``/``datetime`` modules and in every loaded
module that bound those names (``from datetime import datetime``). Not patched:
``time.monotonic``/``perf_counter`` and the asyncio loop clock, so timeouts,
leases measured on monotonic time and executor waits stay real.

Scope: ``time.time``/``time_ns`` are patched process-wide (plain functions, no type
identity involved). The ``datetime``/``date`` *classes* are swapped only inside product
packages (:data:`PRODUCT_PACKAGES`): bound names (``from datetime import datetime``) and
module references (``import datetime`` -> a proxy module whose ``datetime``/``date`` are
the lab types). Libraries such as pydantic, protobuf and the Firestore client keep the
real classes, so building a schema or encoding a timestamp mid-run is unaffected.

By default the clock *ticks*: after :meth:`LabClock.set` it reads the target
instant plus the real time elapsed since. A strictly frozen clock would hang any
product loop that waits for ``time.time()`` to pass a deadline. Pass
``tick=False`` for a fully frozen clock in tests.

The clock is process-global. Chain stages that need different instants therefore
run one at a time (the driver is serial on the ordered path).
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
import datetime as _dt
import threading
import time as _time
import sys
import types
from typing import Iterator

from testing.pipeline_lab.stack.patching import replace_everywhere

_REAL_DATETIME = _dt.datetime
_REAL_DATE = _dt.date
_REAL_TIME = _time.time
_REAL_TIME_NS = _time.time_ns

_ACTIVE: 'LabClock | None' = None

# Backend packages whose code reads the wall clock. ``testing.pipeline_lab.stack`` is
# always skipped by the patcher, so the clock itself keeps the real types.
PRODUCT_PACKAGES = (
    'utils',
    'database',
    'routers',
    'models',
    'config',
    'services',
    'modal',
    'jobs',
    'pusher',
    'llm_gateway',
    'testing',
)


class LabClock:
    def __init__(self, start: _dt.datetime | None = None, *, tick: bool = True):
        self.tick = tick
        self._lock = threading.Lock()
        self._target = 0.0
        self._anchor = 0.0
        self.set(start or _REAL_DATETIME.now(_dt.timezone.utc))

    def set(self, instant: _dt.datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError('lab clock instants must be timezone-aware')
        with self._lock:
            self._target = instant.timestamp()
            self._anchor = _REAL_TIME()

    def advance(self, seconds: float) -> None:
        with self._lock:
            self._target += seconds

    def timestamp(self) -> float:
        with self._lock:
            if self.tick:
                return self._target + (_REAL_TIME() - self._anchor)
            return self._target

    def now(self) -> _dt.datetime:
        return _REAL_DATETIME.fromtimestamp(self.timestamp(), tz=_dt.timezone.utc)


def _clock() -> LabClock | None:
    return _ACTIVE


class _DatetimeMeta(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _REAL_DATETIME)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, _REAL_DATETIME)


class _DateMeta(type):
    def __instancecheck__(cls, obj):
        return isinstance(obj, _REAL_DATE)

    def __subclasscheck__(cls, sub):
        return issubclass(sub, _REAL_DATE)


def _real(value):
    """Return plain datetime/date instances so no lab subclass leaks into stored data."""
    if type(value) is LabDatetime:
        return _REAL_DATETIME(
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            value.second,
            value.microsecond,
            value.tzinfo,
            fold=value.fold,
        )
    if type(value) is LabDate:
        return _REAL_DATE(value.year, value.month, value.day)
    return value


class LabDatetime(_REAL_DATETIME, metaclass=type('LabDatetimeMeta', (_DatetimeMeta, type(_REAL_DATETIME)), {})):
    @classmethod
    def now(cls, tz=None):
        clock = _clock()
        if clock is None:
            return _REAL_DATETIME.now(tz)
        current = clock.now()
        if tz is None:
            return current.astimezone().replace(tzinfo=None)
        return current.astimezone(tz)

    @classmethod
    def utcnow(cls):
        clock = _clock()
        if clock is None:
            return _REAL_DATETIME.utcnow()
        return clock.now().replace(tzinfo=None)

    @classmethod
    def today(cls):
        return cls.now()

    # Constructors inherited from datetime build ``cls``; return plain instances.
    @classmethod
    def fromtimestamp(cls, *args, **kwargs):
        return _REAL_DATETIME.fromtimestamp(*args, **kwargs)

    @classmethod
    def utcfromtimestamp(cls, *args, **kwargs):
        return _REAL_DATETIME.utcfromtimestamp(*args, **kwargs)

    @classmethod
    def fromisoformat(cls, *args, **kwargs):
        return _REAL_DATETIME.fromisoformat(*args, **kwargs)

    @classmethod
    def strptime(cls, *args, **kwargs):
        return _REAL_DATETIME.strptime(*args, **kwargs)

    @classmethod
    def combine(cls, *args, **kwargs):
        return _REAL_DATETIME.combine(*args, **kwargs)

    @classmethod
    def fromordinal(cls, *args, **kwargs):
        return _REAL_DATETIME.fromordinal(*args, **kwargs)

    @classmethod
    def fromisocalendar(cls, *args, **kwargs):
        return _REAL_DATETIME.fromisocalendar(*args, **kwargs)

    def __new__(cls, *args, **kwargs):
        return _REAL_DATETIME(*args, **kwargs)


class LabDate(_REAL_DATE, metaclass=type('LabDateMeta', (_DateMeta, type(_REAL_DATE)), {})):
    @classmethod
    def today(cls):
        clock = _clock()
        if clock is None:
            return _REAL_DATE.today()
        return clock.now().astimezone().date()

    @classmethod
    def fromtimestamp(cls, *args, **kwargs):
        return _REAL_DATE.fromtimestamp(*args, **kwargs)

    @classmethod
    def fromisoformat(cls, *args, **kwargs):
        return _REAL_DATE.fromisoformat(*args, **kwargs)

    @classmethod
    def fromordinal(cls, *args, **kwargs):
        return _REAL_DATE.fromordinal(*args, **kwargs)

    @classmethod
    def fromisocalendar(cls, *args, **kwargs):
        return _REAL_DATE.fromisocalendar(*args, **kwargs)

    def __new__(cls, *args, **kwargs):
        return _REAL_DATE(*args, **kwargs)


# Transport and runtime libraries compute deadlines and expiries from ``time.time()``: gRPC's
# ``_channel._deadline`` is ``time.time() + timeout`` and the C core compares it with the real
# clock, so a virtual "earlier" instant makes every Firestore RPC already expired (504). Calls
# whose direct caller lives in one of these packages get real time; everything else, product
# code included, keeps the process-wide virtual ``time.time`` (DESIGN L3).
REAL_TIME_CALLERS = (
    'grpc',
    'google.api_core',
    'google.auth',
    'google.cloud',
    'google.protobuf',
    'firebase_admin',
    'urllib3',
    'requests',
    'httpx',
    'httpcore',
    'h11',
    'h2',
    'anyio',
    'aiohttp',
    'ssl',
    'socket',
    'selectors',
    'asyncio',
    'concurrent',
    'threading',
    'queue',
    'redis',
    'logging',
)
_REAL_TIME_ROOTS = frozenset(REAL_TIME_CALLERS)


def _real_caller(depth: int = 2) -> bool:
    try:
        name = sys._getframe(depth).f_globals.get('__name__') or ''
    except ValueError:
        return False
    parts = name.split('.')
    return parts[0] in _REAL_TIME_ROOTS or '.'.join(parts[:2]) in _REAL_TIME_ROOTS


def _time_now() -> float:
    clock = _clock()
    if clock is None or _real_caller():
        return _REAL_TIME()
    return clock.timestamp()


def _time_now_ns() -> int:
    clock = _clock()
    if clock is None or _real_caller():
        return _REAL_TIME_NS()
    return int(clock.timestamp() * 1_000_000_000)


@contextmanager
def installed_clock(clock: LabClock, *, scope: tuple[str, ...] | None = PRODUCT_PACKAGES) -> Iterator[LabClock]:
    """Install ``clock`` for the block. ``scope=None`` swaps datetime in every module."""
    global _ACTIVE
    if _ACTIVE is not None and _ACTIVE is not clock:
        raise RuntimeError('another lab clock is already installed')
    with ExitStack() as stack:
        _ACTIVE = clock

        def clear() -> None:
            global _ACTIVE
            _ACTIVE = None

        stack.callback(clear)
        _time.time = _time_now
        _time.time_ns = _time_now_ns

        def restore_time() -> None:
            _time.time = _REAL_TIME
            _time.time_ns = _REAL_TIME_NS

        stack.callback(restore_time)
        replace_everywhere(stack, _REAL_TIME, _time_now)
        replace_everywhere(stack, _REAL_TIME_NS, _time_now_ns)
        if scope is None:
            _dt.datetime = LabDatetime  # type: ignore[misc]
            _dt.date = LabDate  # type: ignore[misc]

            def restore_module() -> None:
                _dt.datetime = _REAL_DATETIME  # type: ignore[misc]
                _dt.date = _REAL_DATE  # type: ignore[misc]

            stack.callback(restore_module)
        else:
            replace_everywhere(stack, _dt, _datetime_module_proxy(), only_prefixes=scope)
        replace_everywhere(stack, _REAL_DATETIME, LabDatetime, only_prefixes=scope)
        replace_everywhere(stack, _REAL_DATE, LabDate, only_prefixes=scope)
        yield clock


def _datetime_module_proxy() -> types.ModuleType:
    """A stand-in for ``import datetime`` inside product modules: lab classes, real everything else."""
    proxy = types.ModuleType('datetime')
    proxy.__dict__.update({k: v for k, v in vars(_dt).items() if not k.startswith('__')})
    proxy.datetime = LabDatetime
    proxy.date = LabDate
    return proxy


def real_now() -> _dt.datetime:
    """Real wall time, for timings in run.json; unaffected by the lab clock."""
    return _REAL_DATETIME.fromtimestamp(_REAL_TIME(), tz=_dt.timezone.utc)


__all__ = ['LabClock', 'LabDatetime', 'LabDate', 'installed_clock', 'real_now', '_real']
