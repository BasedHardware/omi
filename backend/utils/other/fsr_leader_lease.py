"""Best-effort fleet maintenance admission, default off; Redis outages fail open.

The opaque owner token fences renew/release, and a monotonically increasing
generation identifies each ownership epoch. A separate tick key survives owner
shutdown for recovery loops. Queue sampling ties cooldown to a live owner so a
dead publisher cannot delay alert-visible takeover. Callbacks are admitted
only after revalidating ownership; cooperative scan boundaries can call
``check_leader_lease``. This is not a replacement for transactional job claims:
already-issued external operations cannot be revoked by a Redis lease.
"""

from __future__ import annotations

import logging
import math
import os
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
if ARGV[1] ~= '' and owner == ARGV[1] then
    redis.call('PEXPIRE', KEYS[1], ARGV[3])
    generation = tonumber(redis.call('GET', KEYS[2]))
elseif redis.call('SET', KEYS[1], ARGV[2], 'NX', 'PX', ARGV[3]) then
    generation = redis.call('INCR', KEYS[2])
else
    return {0, 0, 0, redis.call('PTTL', KEYS[1])}
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
        if not self._lock.acquire(blocking=False):
            _count(self.loop, 'skipped')
            return None
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
            self._lock.release()

    def release(self) -> None:
        self.closed = True
        self._stop_idle_heartbeat()
        self._release_token()

    def _release_token(self) -> None:
        if not self.token:
            return
        try:
            self.client.eval(_RELEASE, 1, self.keys[0], self.token)
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


def release_loop_leases() -> None:
    # Only the fixed main.py inventory is registered; never unbounded uid labels.
    for loop in _LOOPS:
        loop_lease(loop).release()


_LOOPS = (
    'reconcile_pending_deletion_wipes',
    'reconcile_listen_finalization_jobs',
    'reconcile_stale_processing_conversations',
    'reconcile_stale_in_progress_conversations',
    'reconcile_abandoned_byok_finalization_jobs',
    'publish_all_queue_oldest_ready_ages',
)
