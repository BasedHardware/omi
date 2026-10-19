"""Best-effort fleet maintenance admission, default off; Redis outages fail open.

The opaque owner token fences renew/release, and a monotonically increasing
generation identifies each ownership epoch. A separate tick key limits recovery
scans to one admission per interval. Once it expires, even a heartbeating owner
cannot block takeover. Queue sampling ties cooldown to a live owner so a dead
publisher cannot delay alert-visible takeover. Callbacks are admitted
only after revalidating ownership; cooperative scan boundaries can call
``check_leader_lease``. This is not a replacement for transactional job claims:
already-issued external operations cannot be revoked by a Redis lease.
"""

from __future__ import annotations

import logging
import math
import os
import signal
import socket
import threading
import time
import uuid
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, Callable, TypeVar

from prometheus_client import Counter

from config.firestore_read_levers import lever_enabled

logger = logging.getLogger(__name__)
T = TypeVar('T')
_LEASE_TOTAL = Counter('omi_fsr_leader_lease_total', 'Fleet maintenance lease admissions.', ['loop', 'outcome'])
QUEUE_AGE_LOOP = 'publish_all_queue_oldest_ready_ages'

# All keys share a Redis Cluster hash tag. Redis time is represented by key TTLs,
# so replica wall-clock skew cannot cause an extra tick.
_ADMIT = """
-- fsr_admit
local owner = redis.call('GET', KEYS[1])
local generation = 0
local tick_ttl = redis.call('PTTL', KEYS[3])
-- A recovery heartbeat proves ownership, not progress. An expired admission
-- must allow another pod to work, even if the previous callback is wedged.
-- Queue publishing has its separate live-owner/120s handoff protocol.
local stale = ARGV[5] == '0' and tick_ttl < 0
if stale then
    redis.call('DEL', KEYS[3])
end
if ARGV[1] ~= '' and owner == ARGV[1] then
    redis.call('PEXPIRE', KEYS[1], ARGV[3])
    generation = tonumber(redis.call('GET', KEYS[2]))
elseif stale then
    redis.call('SET', KEYS[1], ARGV[2], 'PX', ARGV[3])
    generation = redis.call('INCR', KEYS[2])
elseif redis.call('SET', KEYS[1], ARGV[2], 'NX', 'PX', ARGV[3]) then
    generation = redis.call('INCR', KEYS[2])
else
    local retry = redis.call('PTTL', KEYS[1])
    if ARGV[5] == '0' and tick_ttl >= 0 then
        retry = math.min(retry, tick_ttl)
    end
    return {0, 0, 0, retry}
end
-- Queue cooldown belongs to a live owner, never to an expired ownership epoch.
if ARGV[5] == '1' and owner ~= ARGV[1] then
    redis.call('DEL', KEYS[3])
end
local admitted = redis.call('SET', KEYS[3], generation, 'NX', 'PX', ARGV[4])
return {generation, admitted and 1 or 0, owner == ARGV[1] and 1 or 0, redis.call('PTTL', KEYS[3])}
"""
_RENEW = """
-- fsr_renew
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE = """
-- fsr_release
if redis.call('GET', KEYS[1]) == ARGV[1] then
    if ARGV[2] == '1' then
        redis.call('DEL', KEYS[2])
    end
    return redis.call('DEL', KEYS[1])
end
return 0
"""


def singleton_loops_enabled() -> bool:
    identity = os.getenv('HOSTNAME') or f'{os.getenv("K_REVISION", "local")}:{socket.gethostname()}'
    return lever_enabled('singleton_loops', identity)


def queue_age_publisher_eligible() -> bool:
    return not singleton_loops_enabled() or os.getenv('FSR_QUEUE_AGE_PUBLISHER') == '1'


def queue_age_lease_seconds() -> int:
    try:
        configured = int(os.getenv('FSR_QUEUE_AGE_LEASE_SECONDS', '120'))
    except ValueError:
        configured = 120
    # Reserve at least 120s of the 240s handoff budget for scheduling/sampling.
    return min(120, max(1, configured))


@lru_cache(maxsize=1)
def _redis_client() -> Any:
    from database.redis_db import create_bounded_redis_client

    return create_bounded_redis_client(0.25)


def _count(loop: str, outcome: str) -> None:
    _LEASE_TOTAL.labels(loop=loop, outcome=outcome).inc()


def _ttl_ms(interval_seconds: float) -> int:
    try:
        configured = int(os.getenv('FSR_LEADER_LEASE_TTL_SECONDS', '0'))
    except ValueError:
        configured = 0
    # Always strictly longer than the cadence, even under a bad override.
    return max(int(interval_seconds * 1000) + 1000, (configured or int(2 * interval_seconds)) * 1000)


def _max_hold_seconds(interval_seconds: float) -> float:
    try:
        configured = int(os.getenv('FSR_LEASE_MAX_HOLD_SECONDS', '900'))
    except ValueError:
        configured = 900
    return max(2 * interval_seconds, configured)


class LeaseLost(RuntimeError):
    """The admission's ownership epoch is no longer current."""


class _Permit:
    def __init__(self, lease: LeaderLease, token: str, generation: int, ttl_ms: int, started: float):
        self.lease = lease
        self.token = token
        self.generation = generation
        self.ttl_ms = ttl_ms
        self.deadline = started + ttl_ms / 1000
        self.fail_open = False
        self.lost = False
        self.started = started
        self.max_hold_deadline: float | None = None
        self._lock = threading.Lock()

    def _hold_expired(self, now: float) -> bool:
        if self.max_hold_deadline is not None and now >= self.max_hold_deadline:
            if not self.lost:
                _count(self.lease.loop, 'max_hold_exceeded')
                logger.warning(
                    'fsr_leader_lease loop=%s outcome=max_hold_exceeded elapsed_seconds=%.3f',
                    self.lease.loop,
                    now - self.started,
                )
            self.lost = True
            return True
        return False

    def begin_admission(self, started: float, max_hold: float) -> None:
        with self._lock:
            self.started = started
            self.max_hold_deadline = started + max_hold

    def heartbeat_delay(self) -> float:
        with self._lock:
            delay = self.ttl_ms / 3000
            if self.max_hold_deadline is not None:
                delay = min(delay, max(0.001, self.max_hold_deadline - self.lease.clock()))
            return delay

    def end_admission(self) -> None:
        with self._lock:
            self._hold_expired(self.lease.clock())
            # A healthy queue owner may heartbeat while idle between samples.
            # Only time spent in an admitted callback counts toward this cap.
            if self.lease.loop == QUEUE_AGE_LOOP:
                self.max_hold_deadline = None
                try:
                    self._check(require_ownership=False)
                except LeaseLost:
                    pass

    def check(self, *, require_ownership: bool = False) -> None:
        with self._lock:
            self._check(require_ownership=require_ownership)

    def _check(self, *, require_ownership: bool) -> None:
        started = self.lease.clock()
        if self._hold_expired(started):
            raise LeaseLost(self.lease.loop)
        if self.lease.closed or self.lost:
            raise LeaseLost(self.lease.loop)
        if self.lease.loop == QUEUE_AGE_LOOP and not queue_age_publisher_eligible():
            self.lost = True
            raise LeaseLost(self.lease.loop)
        if self.fail_open and not require_ownership:
            return
        if started >= self.deadline:
            self.lost = True
            raise LeaseLost(self.lease.loop)
        try:
            ttl_ms = self.ttl_ms
            if self.max_hold_deadline is not None:
                ttl_ms = min(ttl_ms, max(1, math.ceil((self.max_hold_deadline - started) * 1000)))
            renewed = self.lease.client.eval(_RENEW, 1, self.lease.keys[0], self.token, ttl_ms)
        except Exception:
            self.fail_open = True
            _count(self.lease.loop, 'redis_error')
            logger.warning('fsr_leader_lease loop=%s outcome=redis_error; running locally', self.lease.loop)
            if require_ownership:
                raise LeaseLost(self.lease.loop)
            return
        if not renewed or self.lease.clock() >= started + ttl_ms / 1000:
            self.lost = True
            raise LeaseLost(self.lease.loop)
        self.fail_open = False
        self.deadline = started + ttl_ms / 1000


_current_permit: ContextVar[_Permit | None] = ContextVar('fsr_leader_permit', default=None)


def check_leader_lease(*, require_ownership: bool = False) -> None:
    """Fence a boundary; publication requires confirmation after an admitted scan.

    No permit means the lever is off or acquisition failed open, preserving
    local work when Redis was already down before admission.
    """
    permit = _current_permit.get()
    if permit is not None:
        permit.check(require_ownership=require_ownership)


class LeaderLease:
    """One process's ownership state for one fleet loop (also a hermetic test seam)."""

    def __init__(self, loop: str, *, redis_client: Any = None, clock: Callable[[], float] = time.monotonic):
        self.loop = loop
        self._client = redis_client
        self.clock = clock
        self.keys = tuple(f'omi:fsr:leader:v1:{{{loop}}}:{suffix}' for suffix in ('lease', 'generation', 'tick'))
        self.token = ''
        self.closed = False
        self.next_check_at: float | None = None
        self._lock = threading.Lock()
        self._lock_started: float | None = None
        self._blocked_since: float | None = None
        self._idle_permit: _Permit | None = None
        self._idle_stopped = threading.Event()
        self._idle_renewal: threading.Thread | None = None

    def _stop_idle_heartbeat(self) -> None:
        self._idle_stopped.set()
        if self._idle_renewal is not None:
            self._idle_renewal.join(timeout=1)
        self._idle_permit = None

    def _keep_queue_owner_alive(self, permit: _Permit, on_skip: Callable[[], None] | None) -> None:
        if self._idle_permit is permit and self._idle_renewal is not None and self._idle_renewal.is_alive():
            return
        self._stop_idle_heartbeat()
        self._idle_permit = permit
        stopped = self._idle_stopped = threading.Event()

        def heartbeat() -> None:
            while not stopped.wait(permit.heartbeat_delay()):
                if not singleton_loops_enabled():
                    return
                try:
                    permit.check()
                except LeaseLost:
                    if on_skip is not None:
                        on_skip()
                    return
                if permit.fail_open:
                    return

        self._idle_renewal = threading.Thread(target=heartbeat, name='fsr-queue-owner', daemon=True)
        self._idle_renewal.start()

    @property
    def client(self) -> Any:
        return self._client if self._client is not None else _redis_client()

    def run(
        self, callback: Callable[[], T], interval_seconds: float, *, on_skip: Callable[[], None] | None = None
    ) -> T | None:
        if not singleton_loops_enabled():
            return callback()
        if self.closed:
            return None
        if not self._lock.acquire(blocking=False):
            now = self.clock()
            if self.loop != QUEUE_AGE_LOOP:
                self.next_check_at = now + interval_seconds
            if self._blocked_since is None:
                self._blocked_since = now
            started = self._lock_started if self._lock_started is not None else self._blocked_since
            if self.loop != QUEUE_AGE_LOOP and now - started >= _max_hold_seconds(interval_seconds):
                # Do not steal/unlock a running callback's mutex or inherit its
                # fenced context. Later calls must retain lever-off capacity.
                _count(self.loop, 'fail_open_local')
                from utils.observability.fallback import record_fallback

                record_fallback(
                    component='firestore_read',
                    from_mode='singleton_loop',
                    to_mode='local',
                    reason='timeout',
                    outcome='degraded',
                    log=logger,
                )
                context_token = _current_permit.set(None)
                try:
                    return callback()
                finally:
                    _current_permit.reset(context_token)
            _count(self.loop, 'skipped_local_busy')
            _count(self.loop, 'skipped')
            return None
        self._lock_started = self.clock()
        self._blocked_since = None
        try:
            if self.closed:
                return None
            queue_age = self.loop == QUEUE_AGE_LOOP
            if queue_age and not queue_age_publisher_eligible():
                self._stop_idle_heartbeat()
                self._release_token()
                self.token = ''
                self.next_check_at = None
                if on_skip is not None:
                    on_skip()
                _count(self.loop, 'skipped')
                return None
            candidate = uuid.uuid4().hex
            ttl_ms = queue_age_lease_seconds() * 1000 if queue_age else _ttl_ms(interval_seconds)
            max_hold = 2 * ttl_ms / 1000 if queue_age else _max_hold_seconds(interval_seconds)
            ttl_ms = min(ttl_ms, max(1, int(max_hold * 1000)))
            started = self.clock()
            try:
                generation, admitted, retained, remaining_ms = self.client.eval(
                    _ADMIT,
                    3,
                    *self.keys,
                    self.token,
                    candidate,
                    ttl_ms,
                    max(1, int(interval_seconds * 1000)),
                    int(queue_age),
                )
            except Exception:
                _count(self.loop, 'redis_error')
                logger.warning('fsr_leader_lease loop=%s outcome=redis_error; running locally', self.loop)
                self.next_check_at = None
                return callback()
            self.next_check_at = started + max(1, remaining_ms) / 1000
            if generation:
                self.token = self.token if retained else candidate
            else:
                self.token = ''
            permit = self._idle_permit if queue_age and retained else None
            if queue_age and generation:
                if permit is None or permit.lost or permit.fail_open:
                    permit = _Permit(self, self.token, int(generation), ttl_ms, started)
                permit.deadline = started + ttl_ms / 1000
                if admitted:
                    permit.begin_admission(started, max_hold)
                try:
                    permit.check()
                except LeaseLost:
                    _count(self.loop, 'skipped')
                    if on_skip is not None:
                        on_skip()
                    return None
                self._keep_queue_owner_alive(permit, on_skip)
            elif queue_age:
                self._stop_idle_heartbeat()
            if not admitted:
                _count(self.loop, 'skipped_cooldown' if generation else 'skipped_owner')
                _count(self.loop, 'skipped')
                # A retained leader's cooldown is not ownership loss.
                if not generation and on_skip is not None:
                    on_skip()
                return None
            permit = permit or _Permit(self, self.token, int(generation), ttl_ms, started)
            if not queue_age:
                permit.begin_admission(started, max_hold)
            stopped = threading.Event()

            def heartbeat() -> None:
                while not stopped.wait(permit.heartbeat_delay()):
                    try:
                        permit.check()
                    except LeaseLost:
                        return
                    if permit.fail_open:
                        return

            renewal = threading.Thread(target=heartbeat, name=f'fsr-lease-{self.loop}', daemon=True)
            context_token = _current_permit.set(permit)
            try:
                permit.check()  # Do not start work using a paused/expired admission.
                _count(self.loop, 'acquired')
                if not queue_age:
                    renewal.start()
                return callback()
            except LeaseLost:
                _count(self.loop, 'skipped')
                if on_skip is not None:
                    on_skip()
                return None
            finally:
                permit.end_admission()
                stopped.set()
                if renewal.ident is not None:
                    renewal.join(timeout=1)
                _current_permit.reset(context_token)
        finally:
            self._lock_started = None
            self._lock.release()

    def release(self, *, clear_tick: bool = False) -> None:
        self.closed = True
        self._stop_idle_heartbeat()
        self._release_token(clear_tick=clear_tick)

    def _release_token(self, *, clear_tick: bool = False) -> None:
        if not self.token:
            return
        try:
            self.client.eval(_RELEASE, 2, self.keys[0], self.keys[2], self.token, int(clear_tick))
        except Exception:
            _count(self.loop, 'redis_error')
            logger.warning('fsr_leader_lease loop=%s outcome=redis_error on release', self.loop)


@lru_cache(maxsize=16)
def loop_lease(loop: str) -> LeaderLease:
    return LeaderLease(loop)


def poll_delay(interval_seconds: float, *, deletion: bool = False, queue_age: bool = False) -> float:
    """Wake at an observed lease expiry rather than overshooting by a full tick.

    The tick key enforces scan spacing for a live queue owner and for all
    recovery loops. Queue ownership expires independently of the scan interval;
    its own scheduler also polls before any expiry has been observed.
    """
    if not singleton_loops_enabled():
        return interval_seconds
    delay = min(interval_seconds, queue_age_lease_seconds()) if queue_age else interval_seconds
    loops = (QUEUE_AGE_LOOP,) if queue_age else (_LOOPS[:1] if deletion else _LOOPS[1:-1])
    for loop in loops:
        lease = loop_lease(loop)
        if lease.next_check_at is not None:
            delay = min(delay, max(0.01, lease.next_check_at - lease.clock()))
    return delay


def release_loop_leases(*, clear_tick: bool = False) -> None:
    # Only the fixed main.py inventory is registered; never unbounded uid labels.
    for loop in _LOOPS:
        loop_lease(loop).release(clear_tick=clear_tick)


_LOOPS = (
    'reconcile_pending_deletion_wipes',
    'reconcile_listen_finalization_jobs',
    'reconcile_stale_processing_conversations',
    'reconcile_stale_in_progress_conversations',
    'reconcile_abandoned_byok_finalization_jobs',
    'publish_all_queue_oldest_ready_ages',
)


_sigterm_installed = False
_sigterm_release_started = False


def release_loop_leases_on_sigterm(signum: int, frame: Any) -> None:
    """Start bounded-client cleanup outside asyncio and the busy DB executor.

    Never perform Redis work in a Python signal handler: it can interrupt a
    thread while that same thread owns a Redis/permit lock.
    """
    global _sigterm_release_started
    if _sigterm_release_started or not singleton_loops_enabled():
        return
    _sigterm_release_started = True
    worker = threading.Thread(
        target=lambda: release_loop_leases(clear_tick=True), name='fsr-sigterm-release', daemon=True
    )
    worker.start()


def install_loop_lease_sigterm_handler() -> None:
    """Chain the server's SIGTERM handler; preserve normal graceful shutdown."""
    global _sigterm_installed
    if _sigterm_installed or not singleton_loops_enabled() or threading.current_thread() is not threading.main_thread():
        return
    previous = signal.getsignal(signal.SIGTERM)

    def handle(signum: int, frame: Any) -> None:
        release_loop_leases_on_sigterm(signum, frame)
        if callable(previous):
            previous(signum, frame)
        elif previous == signal.SIG_DFL:
            # An embedding without a server handler still gets a short cleanup
            # opportunity, then the original default termination semantics.
            for thread in threading.enumerate():
                if thread.name == 'fsr-sigterm-release':
                    thread.join(timeout=2)
            signal.signal(signum, signal.SIG_DFL)
            signal.raise_signal(signum)

    signal.signal(signal.SIGTERM, handle)
    _sigterm_installed = True
