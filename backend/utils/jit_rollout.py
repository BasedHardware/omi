"""Backend-authoritative rollout decisions for just-in-time processing.

This module owns a read-only control-plane decision.  It deliberately has no
client input other than the Firebase-authenticated UID supplied by the router.

Admission is one PostHog exposure flag plus a code-owned two-UID allowlist
that bypasses the flag.  A known-false or absent flag is off.  Provider
timeouts, missing configuration, and malformed values stay ``unknown`` and
cannot admit a non-allowlist user.  The allowlist still admits when PostHog
is down.
"""

# LIFECYCLE: permanent

from __future__ import annotations

import asyncio
import importlib
import logging
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from utils.executors import run_blocking

logger = logging.getLogger(__name__)

JIT_PROCESSING_FLAG_KEY = 'jit-processing-v1'
# Retired admission keys. Kept as names so tests can prove they no longer
# authorize work. Do not read them for permits_work.
JIT_LEDGER_MIGRATION_FLAG_KEY = 'jit-processing-ledger-migration-v1'
JIT_KILL_SWITCH_FLAG_KEY = 'jit-processing-kill-switch-v1'
JIT_DAILY_SWEEP_FLAG_KEY = 'daily-memory-sweep-v1'
JIT_ADMISSION_ALLOWLIST = frozenset(
    {
        'vi7SA9ckQCe4ccobWNxlbdcNdC23',
        '9OqYLlKJv4hmeYpIhwJcHBR975i2',
    }
)
MAX_JIT_ROLLOUT_CACHE_SECONDS = 30.0
DEFAULT_JIT_ROLLOUT_CACHE_SECONDS = 20.0
# Unknown/error snapshots are cached only this briefly: long enough that a
# fleet whose flags are absent (the normal dark state) does not pay one
# uncached provider call per conversation finalization, short enough that a
# provider recovery is observed within seconds. UNKNOWN can never authorize
# work, so this only ever extends fail-closed behavior.
UNKNOWN_JIT_ROLLOUT_CACHE_SECONDS = 5.0
DEFAULT_JIT_ROLLOUT_TIMEOUT_SECONDS = 2.0
SYNC_JIT_ROLLOUT_RESULT_TIMEOUT_SECONDS = 5.0
DEFAULT_JIT_ROLLOUT_CACHE_ENTRIES = 4096
POSTHOG_CONTROL_MAX_WORKERS = 4
POSTHOG_CONTROL_MAX_QUEUE = 16
POSTHOG_CONTROL_QUEUE_WAIT_SECONDS = 0.25

# Feature-flag reads are control-plane calls and must not consume the shared
# sync pipeline pool.  The semaphore bounds both active calls and submitted
# work; a slot is held until the underlying thread actually finishes, even if
# the async caller has already received a timeout/fail-off result.
_posthog_control_executor: ThreadPoolExecutor | None = None
_posthog_control_executor_lock = threading.Lock()


def _get_posthog_control_executor() -> ThreadPoolExecutor:
    global _posthog_control_executor
    with _posthog_control_executor_lock:
        if _posthog_control_executor is None:
            _posthog_control_executor = ThreadPoolExecutor(
                max_workers=POSTHOG_CONTROL_MAX_WORKERS,
                thread_name_prefix='posthog-control',
            )
        return _posthog_control_executor


def close_posthog_control_plane() -> None:
    """Stop accepting control-plane work without blocking application shutdown.

    Queued calls are cancelled; already-running SDK calls retain their own
    bounded timeout and are not waited on here. A later in-process app startup
    lazily creates a fresh isolated executor.
    """
    global _posthog_control_executor
    with _posthog_control_executor_lock:
        executor = _posthog_control_executor
        _posthog_control_executor = None
    if executor is not None:
        executor.shutdown(wait=False, cancel_futures=True)


class TriState(str, Enum):
    ENABLED = 'enabled'
    DISABLED = 'disabled'
    UNKNOWN = 'unknown'


class JITDecisionStage(str, Enum):
    READ_ONLY = 'read_only'
    INGRESS = 'ingress'
    PAID_BOUNDARY = 'paid_boundary'


class JITDecisionReason(str, Enum):
    EVALUATED = 'evaluated'
    ROLLOUT_ENABLED = 'rollout_enabled'
    ROLLOUT_DISABLED = 'rollout_disabled'
    KILL_SWITCH_ENABLED = 'kill_switch_enabled'
    PROVIDER_TIMEOUT = 'provider_timeout'
    CONFIGURATION_MISSING = 'configuration_missing'
    MALFORMED_RESPONSE = 'malformed_response'
    PROVIDER_ERROR = 'provider_error'
    FLAG_ABSENT = 'flag_absent'


class JITErrorClass(str, Enum):
    NONE = 'none'
    TIMEOUT = 'timeout'
    CONFIGURATION = 'configuration'
    MALFORMED = 'malformed'
    PROVIDER = 'provider'
    ABSENT = 'absent'


@dataclass(frozen=True)
class JITFlagEvaluation:
    rollout: TriState
    kill_switch: TriState
    reason: JITDecisionReason
    error_class: JITErrorClass = JITErrorClass.NONE


@dataclass(frozen=True)
class JITRolloutDecision:
    rollout: TriState
    kill_switch: TriState
    effective: TriState
    reason: JITDecisionReason
    error_class: JITErrorClass
    cache_hit: bool
    cache_ttl_seconds: int

    @property
    def permits_work(self) -> bool:
        return self.effective == TriState.ENABLED


FlagProvider = Callable[[str], Awaitable[JITFlagEvaluation]]


@runtime_checkable
class _ForceRefreshProvider(Protocol):
    """Optional provider seam for uncached authority reads."""

    def force_refresh(self, uid: str) -> Awaitable[JITFlagEvaluation]: ...


@dataclass(frozen=True)
class _CacheEntry:
    evaluation: JITFlagEvaluation
    expires_at: float


def is_jit_admission_allowlisted(uid: str) -> bool:
    """Return True when the authenticated Firebase UID bypasses the exposure flag."""

    return uid.strip() in JIT_ADMISSION_ALLOWLIST


def _allowlisted_decision(*, cache_hit: bool = False, cache_ttl_seconds: int = 0) -> JITRolloutDecision:
    return JITRolloutDecision(
        rollout=TriState.ENABLED,
        kill_switch=TriState.DISABLED,
        effective=TriState.ENABLED,
        reason=JITDecisionReason.ROLLOUT_ENABLED,
        error_class=JITErrorClass.NONE,
        cache_hit=cache_hit,
        cache_ttl_seconds=cache_ttl_seconds,
    )


def _effective_decision(
    evaluation: JITFlagEvaluation, *, cache_hit: bool, cache_ttl_seconds: int
) -> JITRolloutDecision:
    # Kill-switch / ledger-migration / daily-sweep flags are not admission
    # authority. A known-false or absent exposure flag is off. Unknown is
    # reserved for genuine provider, timeout, configuration, or malformed
    # failures so those states fail closed for non-allowlist users.
    if evaluation.rollout == TriState.ENABLED:
        effective = TriState.ENABLED
        reason = JITDecisionReason.ROLLOUT_ENABLED
    elif evaluation.rollout == TriState.DISABLED:
        effective = TriState.DISABLED
        reason = (
            evaluation.reason
            if evaluation.reason == JITDecisionReason.FLAG_ABSENT
            else JITDecisionReason.ROLLOUT_DISABLED
        )
    else:
        effective = TriState.UNKNOWN
        reason = evaluation.reason
    return JITRolloutDecision(
        rollout=evaluation.rollout,
        kill_switch=TriState.DISABLED,
        effective=effective,
        reason=reason,
        error_class=evaluation.error_class,
        cache_hit=cache_hit,
        cache_ttl_seconds=cache_ttl_seconds,
    )


class JITRolloutAuthority:
    """Resolve and briefly cache owner-isolated, fully-known flag snapshots."""

    def __init__(
        self,
        provider: FlagProvider,
        *,
        ttl_seconds: float = DEFAULT_JIT_ROLLOUT_CACHE_SECONDS,
        max_entries: int = DEFAULT_JIT_ROLLOUT_CACHE_ENTRIES,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0 or ttl_seconds > MAX_JIT_ROLLOUT_CACHE_SECONDS:
            raise ValueError(f'ttl_seconds must be in (0, {MAX_JIT_ROLLOUT_CACHE_SECONDS:g}]')
        if max_entries <= 0:
            raise ValueError('max_entries must be positive')
        self._provider = provider
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._monotonic = monotonic
        self._cache: OrderedDict[str, _CacheEntry] = OrderedDict()

    async def resolve(
        self,
        uid: str,
        *,
        stage: JITDecisionStage,
        force_refresh: bool = False,
    ) -> JITRolloutDecision:
        if not uid.strip():
            raise ValueError('authenticated uid is required')
        if is_jit_admission_allowlisted(uid):
            decision = _allowlisted_decision()
            self._record(decision, stage=stage, latency_ms=0)
            return decision
        started_at = self._monotonic()
        now = started_at
        if not force_refresh:
            entry = self._cache.get(uid)
            if entry is not None:
                if entry.expires_at > now:
                    self._cache.move_to_end(uid)
                    decision = _effective_decision(
                        entry.evaluation,
                        cache_hit=True,
                        cache_ttl_seconds=max(0, int(entry.expires_at - now)),
                    )
                    self._record(decision, stage=stage, latency_ms=0)
                    return decision
                del self._cache[uid]

        if force_refresh and isinstance(self._provider, _ForceRefreshProvider):
            evaluation = await self._provider.force_refresh(uid)
        else:
            evaluation = await self._provider(uid)
        finished_at = self._monotonic()
        # Complete provider answers cache for the full TTL. Unknown/error
        # snapshots cache only for a short negative TTL: UNKNOWN can never
        # authorize work, so this cannot extend an outage into an
        # authorization — it only stops a fleet with absent flags from paying
        # one uncached provider call per request.
        complete = evaluation.rollout != TriState.UNKNOWN
        entry_ttl = self._ttl_seconds if complete else min(UNKNOWN_JIT_ROLLOUT_CACHE_SECONDS, self._ttl_seconds)
        self._cache[uid] = _CacheEntry(evaluation=evaluation, expires_at=finished_at + entry_ttl)
        self._cache.move_to_end(uid)
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)
        decision = _effective_decision(
            evaluation,
            cache_hit=False,
            cache_ttl_seconds=int(entry_ttl),
        )
        self._record(decision, stage=stage, latency_ms=max(0, int((finished_at - started_at) * 1000)))
        return decision

    @staticmethod
    def _record(decision: JITRolloutDecision, *, stage: JITDecisionStage, latency_ms: int) -> None:
        # Fixed-field, bounded telemetry only. Never add UID, prompt, memory,
        # transcript, OCR, image, URL, or exception text to this event.
        logger.info(
            'jit_rollout_decision decision=%s reason=%s stage=%s latency_ms=%d cost_class=%s error_class=%s',
            decision.effective.value,
            decision.reason.value,
            stage.value,
            min(latency_ms, 30_000),
            'control_plane_only',
            decision.error_class.value,
        )


class PostHogJITFlagProvider:
    """Read the single server-owned PostHog exposure flag in one bounded decide request."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_JIT_ROLLOUT_TIMEOUT_SECONDS,
        client_factory: Callable[[], Any | None] | None = None,
        rollout_flag_key: str = JIT_PROCESSING_FLAG_KEY,
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > MAX_JIT_ROLLOUT_CACHE_SECONDS:
            raise ValueError('timeout_seconds must be positive and bounded')
        self._timeout_seconds = timeout_seconds
        self._client_factory = client_factory or self._build_client
        if not rollout_flag_key.strip():
            raise ValueError('rollout_flag_key is required')
        self._rollout_flag_key = rollout_flag_key
        self._client: Any | None = None
        self._client_lock = threading.Lock()
        self._control_slots = asyncio.BoundedSemaphore(POSTHOG_CONTROL_MAX_WORKERS + POSTHOG_CONTROL_MAX_QUEUE)
        self._inflight: dict[str, tuple[asyncio.Task[JITFlagEvaluation], asyncio.Event]] = {}

    def _build_client(self) -> Any | None:
        api_key = (os.getenv('POSTHOG_PROJECT_API_KEY') or os.getenv('POSTHOG_API_KEY') or '').strip()
        if not api_key:
            return None
        module = importlib.import_module('posthog')
        client_class = getattr(module, 'Posthog')
        return client_class(
            project_api_key=api_key,
            host=os.getenv('POSTHOG_HOST', 'https://app.posthog.com'),
            send=False,
            sync_mode=True,
            feature_flags_request_timeout_seconds=self._timeout_seconds,
        )

    def _fetch(self, uid: str) -> Mapping[str, Any]:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = self._client_factory()
        if self._client is None:
            raise LookupError('posthog_unconfigured')
        variants = self._client.get_feature_variants(uid)
        if not isinstance(variants, Mapping):
            raise TypeError('malformed_feature_flags')
        return variants

    async def __call__(self, uid: str) -> JITFlagEvaluation:
        # Requests for the same owner share one in-flight decision, preventing
        # a cold-cache fanout from multiplying identical PostHog calls.
        entry = self._inflight.get(uid)
        if entry is None:
            control_done = asyncio.Event()
            in_flight = asyncio.create_task(
                self._resolve_uncached(uid, control_done),
                name='posthog-jit-decide',
            )
            entry = (in_flight, control_done)
            self._inflight[uid] = entry

            def forget(completed: asyncio.Task[JITFlagEvaluation]) -> None:
                if not completed.cancelled():
                    completed.exception()

                async def remove_after_control_finishes() -> None:
                    await control_done.wait()
                    if self._inflight.get(uid) == entry:
                        self._inflight.pop(uid, None)

                if control_done.is_set():
                    if self._inflight.get(uid) == entry:
                        self._inflight.pop(uid, None)
                else:
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        # The event loop is already closing; process shutdown
                        # will discard this in-memory coalescing state.
                        self._inflight.pop(uid, None)
                    else:
                        loop.create_task(remove_after_control_finishes(), name='posthog-jit-coalesce-cleanup')

            in_flight.add_done_callback(forget)
        return await asyncio.shield(entry[0])

    async def force_refresh(self, uid: str) -> JITFlagEvaluation:
        """Read flags independently of any stale same-owner coalesced call."""

        # A final authority fence must not join a request that started before
        # the exposure flag changed. Keep the bulkhead and provider timeout,
        # but use a fresh in-flight task rather than the normal same-UID
        # coalescer.
        return await self._resolve_uncached(uid, asyncio.Event())

    async def _resolve_uncached(self, uid: str, control_done: asyncio.Event) -> JITFlagEvaluation:
        try:
            await asyncio.wait_for(
                self._control_slots.acquire(),
                timeout=POSTHOG_CONTROL_QUEUE_WAIT_SECONDS,
            )
        except asyncio.TimeoutError:
            control_done.set()
            return JITFlagEvaluation(
                TriState.UNKNOWN,
                TriState.UNKNOWN,
                JITDecisionReason.PROVIDER_TIMEOUT,
                JITErrorClass.TIMEOUT,
            )
        except asyncio.CancelledError:
            control_done.set()
            raise

        try:
            call = asyncio.create_task(
                run_blocking(_get_posthog_control_executor(), self._fetch, uid),
                name='posthog-jit-fetch',
            )
        except BaseException:
            self._control_slots.release()
            control_done.set()
            raise

        def release_slot(completed: asyncio.Task[Any]) -> None:
            self._control_slots.release()
            control_done.set()
            if not completed.cancelled():
                completed.exception()

        # Keep the bulkhead slot tied to the real executor work.  Cancelling
        # wait_for must not release a slot while its thread is still blocked,
        # otherwise repeated provider timeouts could grow the executor queue.
        call.add_done_callback(release_slot)
        try:
            variants = await asyncio.wait_for(
                asyncio.shield(call),
                timeout=self._timeout_seconds,
            )
        except asyncio.TimeoutError:
            return JITFlagEvaluation(
                TriState.UNKNOWN,
                TriState.UNKNOWN,
                JITDecisionReason.PROVIDER_TIMEOUT,
                JITErrorClass.TIMEOUT,
            )
        except LookupError:
            return JITFlagEvaluation(
                TriState.UNKNOWN,
                TriState.UNKNOWN,
                JITDecisionReason.CONFIGURATION_MISSING,
                JITErrorClass.CONFIGURATION,
            )
        except TypeError:
            return JITFlagEvaluation(
                TriState.UNKNOWN,
                TriState.UNKNOWN,
                JITDecisionReason.MALFORMED_RESPONSE,
                JITErrorClass.MALFORMED,
            )
        except Exception:
            return JITFlagEvaluation(
                TriState.UNKNOWN,
                TriState.UNKNOWN,
                JITDecisionReason.PROVIDER_ERROR,
                JITErrorClass.PROVIDER,
            )

        if self._rollout_flag_key not in variants:
            return JITFlagEvaluation(
                TriState.DISABLED,
                TriState.DISABLED,
                JITDecisionReason.FLAG_ABSENT,
                JITErrorClass.ABSENT,
            )
        rollout = _flag_state(variants, self._rollout_flag_key)
        if rollout == TriState.UNKNOWN:
            return JITFlagEvaluation(
                TriState.UNKNOWN,
                TriState.DISABLED,
                JITDecisionReason.MALFORMED_RESPONSE,
                JITErrorClass.MALFORMED,
            )
        return JITFlagEvaluation(rollout, TriState.DISABLED, JITDecisionReason.EVALUATED)


def _flag_state(flags: Mapping[str, Any], key: str) -> TriState:
    value = flags.get(key)
    if value is True:
        return TriState.ENABLED
    if value is False:
        return TriState.DISABLED
    return TriState.UNKNOWN


_authority = JITRolloutAuthority(PostHogJITFlagProvider())

# Synchronous callers (conversation finalization threads, the FastAPI sync
# threadpool, first-open workers) must never share asyncio primitives or
# in-flight tasks with the server's event loop: awaiting a Task attached to a
# different loop raises, per-call ``asyncio.run`` loops strand coalescer
# entries, and cross-thread cache mutation races. All sync resolution instead
# runs on one long-lived control loop thread with its own authority/provider
# instances, so every asyncio object involved is confined to a single loop.
_sync_authority = JITRolloutAuthority(PostHogJITFlagProvider())
_control_loop: asyncio.AbstractEventLoop | None = None
_control_loop_lock = threading.Lock()


def _get_control_loop() -> asyncio.AbstractEventLoop:
    global _control_loop
    with _control_loop_lock:
        if _control_loop is None or _control_loop.is_closed():
            loop = asyncio.new_event_loop()
            thread = threading.Thread(target=loop.run_forever, name='jit-rollout-control-loop', daemon=True)
            thread.start()
            _control_loop = loop
        return _control_loop


def _unavailable_decision(reason: JITDecisionReason, error_class: JITErrorClass) -> JITRolloutDecision:
    return JITRolloutDecision(
        rollout=TriState.UNKNOWN,
        kill_switch=TriState.UNKNOWN,
        effective=TriState.UNKNOWN,
        reason=reason,
        error_class=error_class,
        cache_hit=False,
        cache_ttl_seconds=0,
    )


def resolve_jit_rollout_sync(
    uid: str,
    *,
    stage: JITDecisionStage,
    force_refresh: bool = False,
    result_timeout_seconds: float = SYNC_JIT_ROLLOUT_RESULT_TIMEOUT_SECONDS,
) -> JITRolloutDecision:
    """Loop-confined resolution for non-async callers; unavailable states fail closed."""

    if is_jit_admission_allowlisted(uid):
        return _allowlisted_decision()
    try:
        future = asyncio.run_coroutine_threadsafe(
            _sync_authority.resolve(uid, stage=stage, force_refresh=force_refresh),
            _get_control_loop(),
        )
    except Exception:
        return _unavailable_decision(JITDecisionReason.PROVIDER_ERROR, JITErrorClass.PROVIDER)
    try:
        return future.result(timeout=result_timeout_seconds)
    except FuturesTimeoutError:
        future.cancel()
        return _unavailable_decision(JITDecisionReason.PROVIDER_TIMEOUT, JITErrorClass.TIMEOUT)
    except Exception:
        return _unavailable_decision(JITDecisionReason.PROVIDER_ERROR, JITErrorClass.PROVIDER)


async def resolve_jit_rollout(
    uid: str,
    *,
    stage: JITDecisionStage,
    force_refresh: bool = False,
) -> JITRolloutDecision:
    if is_jit_admission_allowlisted(uid):
        return _allowlisted_decision()
    return await _authority.resolve(uid, stage=stage, force_refresh=force_refresh)


async def resolve_jit_ledger_migration_rollout(
    uid: str,
    *,
    stage: JITDecisionStage,
    force_refresh: bool = False,
) -> JITRolloutDecision:
    """Same admission helper as processing; the retired migration flag is ignored."""

    return await resolve_jit_rollout(uid, stage=stage, force_refresh=force_refresh)


__all__ = [
    'JITDecisionStage',
    'JITDecisionReason',
    'JITErrorClass',
    'JITFlagEvaluation',
    'JIT_ADMISSION_ALLOWLIST',
    'JIT_DAILY_SWEEP_FLAG_KEY',
    'JIT_KILL_SWITCH_FLAG_KEY',
    'JIT_LEDGER_MIGRATION_FLAG_KEY',
    'JIT_PROCESSING_FLAG_KEY',
    'JITRolloutAuthority',
    'JITRolloutDecision',
    'PostHogJITFlagProvider',
    'TriState',
    'close_posthog_control_plane',
    'is_jit_admission_allowlisted',
    'resolve_jit_ledger_migration_rollout',
    'resolve_jit_rollout',
    'resolve_jit_rollout_sync',
]
