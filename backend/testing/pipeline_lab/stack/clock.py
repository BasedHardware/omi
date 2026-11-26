"""Harness-owned virtual wall clock (DESIGN L3), with no new dependency.

Patched: ``time.time``, ``time.time_ns``, ``datetime.datetime.now/utcnow/today`` and
``datetime.date.today``, in the ``time``/``datetime`` modules and in every loaded
module that bound those names (``from datetime import datetime``).

Scope: ``time.time``/``time_ns`` are patched process-wide (plain functions, no type
identity involved). The ``datetime``/``date`` *classes* are swapped only inside product
packages (:data:`PRODUCT_PACKAGES`): bound names (``from datetime import datetime``) and
module references (``import datetime`` -> a proxy module whose ``datetime``/``date`` are
the lab types). Libraries such as pydantic, protobuf and the Firestore client keep the
real classes, so building a schema or encoding a timestamp mid-run is unaffected.

Two modes (:data:`CLOCK_MODES`):

- ``sim`` (``tick=False``): the wall clock reads exactly the last :meth:`LabClock.set` instant.
  It moves only when the driver moves it (to the next event, task or sweep), never because
  real seconds passed, so the same inputs give the same stamps. A day replay in this mode
  also passes ``product_monotonic=True`` to :func:`installed_clock` (below).
- ``tick`` (``tick=True``, the historical default): after :meth:`LabClock.set` the clock
  reads the target instant plus the real time elapsed since. Each pass is then stamped at
  arrival plus its real latency, which is what made day replays bistable.

``product_monotonic=True`` also gives *product* code (callers in
:data:`MONOTONIC_PRODUCT_PACKAGES`) a monotonic clock that follows the replay:
``time.monotonic``/``monotonic_ns`` and ``asyncio`` loop ``time()``. It reads the virtual
instant of the last ``set``, so a deadline, lease or circuit-breaker cooldown armed at 09:00 has
expired by an 11:00 event, as in production, whatever the replay's real speed, and a lease
checked exactly at its expiry decides the same way every run. Product polls and I/O budgets
(``while ... monotonic() < deadline: sleep``, ``finalizer.py``, ``speaker_identity_retry.py``)
would spin forever on a frozen clock, so once an event has run for
:data:`MONOTONIC_GRACE_SECONDS` of real time the product's monotonic clock starts advancing in
real time from there; :attr:`LabClock.late_monotonic_reads` counts reads past that point (each is
a place where real time reached a product decision). Every other caller (``asyncio`` internals,
``threading``, gRPC, the lab's barrier and drivers) keeps the real monotonic clock.
``time.perf_counter`` is never patched (product code uses it for metrics only).

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
_REAL_MONOTONIC = _time.monotonic
_REAL_MONOTONIC_NS = _time.monotonic_ns

CLOCK_MODES = ('sim', 'tick')
# Real seconds an event may run before the product's monotonic clock starts to move (liveness).
MONOTONIC_GRACE_SECONDS = 30.0

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

# Callers that get the replay's monotonic clock under ``product_monotonic``: product code only.
# ``testing`` is left out on purpose: the lab's barrier, drivers and timings measure real time.
MONOTONIC_PRODUCT_PACKAGES = tuple(p for p in PRODUCT_PACKAGES if p != 'testing')
_MONOTONIC_ROOTS = frozenset(MONOTONIC_PRODUCT_PACKAGES)


class LabClock:
    def __init__(
        self,
        start: _dt.datetime | None = None,
        *,
        tick: bool = True,
        monotonic_grace: float = MONOTONIC_GRACE_SECONDS,
    ):
        self.tick = tick
        self.monotonic_grace = 0.0 if tick else monotonic_grace
        self.late_monotonic_reads = 0
        self._lock = threading.Lock()
        self._target = 0.0
        self._anchor = 0.0
        self._mono_anchor = 0.0
        self._origin: float | None = None
        self._mono_origin = _REAL_MONOTONIC()
        self._mono_last = 0.0
        self.set(start or _REAL_DATETIME.now(_dt.timezone.utc))

    @classmethod
    def for_mode(cls, start: _dt.datetime | None, mode: str, **kwargs: float) -> 'LabClock':
        if mode not in CLOCK_MODES:
            raise ValueError(f'unknown clock mode {mode!r}; expected one of {CLOCK_MODES}')
        return cls(start, tick=mode == 'tick', **kwargs)

    @property
    def mode(self) -> str:
        return 'tick' if self.tick else 'sim'

    def set(self, instant: _dt.datetime) -> None:
        if instant.tzinfo is None:
            raise ValueError('lab clock instants must be timezone-aware')
        with self._lock:
            self._target = instant.timestamp()
            self._anchor = _REAL_TIME()
            self._mono_anchor = _REAL_MONOTONIC()
            if self._origin is None:
                self._origin = self._target

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

    def monotonic(self) -> float:
        """The product's monotonic clock: the virtual instant of the last ``set``, plus the real time
        the current event has run beyond ``monotonic_grace`` (zero for a ticking clock).

        Never decreases, even if the driver sets an earlier instant.
        """
        with self._lock:
            late = (_REAL_MONOTONIC() - self._mono_anchor) - self.monotonic_grace
            if late > 0 and not self.tick:
                self.late_monotonic_reads += 1
            value = self._mono_origin + (self._target - (self._origin or 0.0)) + max(0.0, late)
            if value < self._mono_last:
                value = self._mono_last
            self._mono_last = value
            return value


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


def _product_caller(depth: int = 2) -> bool:
    try:
        name = sys._getframe(depth).f_globals.get('__name__') or ''
    except ValueError:
        return False
    return name.split('.', 1)[0] in _MONOTONIC_ROOTS


def _monotonic_now() -> float:
    clock = _clock()
    if clock is None or not _product_caller():
        return _REAL_MONOTONIC()
    return clock.monotonic()


def _monotonic_now_ns() -> int:
    clock = _clock()
    if clock is None or not _product_caller():
        return _REAL_MONOTONIC_NS()
    return int(clock.monotonic() * 1_000_000_000)


def _loop_time(self) -> float:  # replaces asyncio.BaseEventLoop.time
    clock = _clock()
    if clock is None or not _product_caller():
        return _REAL_MONOTONIC()
    return clock.monotonic()


def _install_product_monotonic(stack: ExitStack) -> None:
    import asyncio.base_events as base_events

    _time.monotonic = _monotonic_now
    _time.monotonic_ns = _monotonic_now_ns
    original_loop_time = base_events.BaseEventLoop.time
    base_events.BaseEventLoop.time = _loop_time  # type: ignore[method-assign]

    def restore() -> None:
        _time.monotonic = _REAL_MONOTONIC
        _time.monotonic_ns = _REAL_MONOTONIC_NS
        base_events.BaseEventLoop.time = original_loop_time  # type: ignore[method-assign]

    stack.callback(restore)
    # ``from time import monotonic`` inside product modules. Everyone else's bound names
    # (``threading``'s ``_time``, ``asyncio``) keep the real function.
    replace_everywhere(stack, _REAL_MONOTONIC, _monotonic_now, only_prefixes=MONOTONIC_PRODUCT_PACKAGES)
    replace_everywhere(stack, _REAL_MONOTONIC_NS, _monotonic_now_ns, only_prefixes=MONOTONIC_PRODUCT_PACKAGES)


@contextmanager
def installed_clock(
    clock: LabClock, *, scope: tuple[str, ...] | None = PRODUCT_PACKAGES, product_monotonic: bool = False
) -> Iterator[LabClock]:
    """Install ``clock`` for the block. ``scope=None`` swaps datetime in every module.

    ``product_monotonic`` also gives product callers the replay's monotonic and loop clock.
    """
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
        if product_monotonic:
            _install_product_monotonic(stack)
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


__all__ = [
    'CLOCK_MODES',
    'MONOTONIC_GRACE_SECONDS',
    'LabClock',
    'LabDatetime',
    'LabDate',
    'installed_clock',
    'real_now',
    '_real',
]
