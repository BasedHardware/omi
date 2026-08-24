"""Backend-authoritative rollout decisions for just-in-time processing.

This module owns a read-only control-plane decision.  It deliberately has no
client input other than the Firebase-authenticated UID supplied by the router.
Missing configuration, absent or malformed flags, provider errors, and
timeouts all remain ``unknown`` and therefore cannot activate product work.
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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Any

from utils.executors import run_blocking

logger = logging.getLogger(__name__)

JIT_PROCESSING_FLAG_KEY = 'jit-processing-v1'
JIT_KILL_SWITCH_FLAG_KEY = 'jit-processing-kill-switch-v1'
MAX_JIT_ROLLOUT_CACHE_SECONDS = 30.0
DEFAULT_JIT_ROLLOUT_CACHE_SECONDS = 20.0
DEFAULT_JIT_ROLLOUT_TIMEOUT_SECONDS = 2.0
DEFAULT_JIT_ROLLOUT_CACHE_ENTRIES = 4096
POSTHOG_CONTROL_MAX_WORKERS = 4
POSTHOG_CONTROL_MAX_QUEUE = 16
POSTHOG_CONTROL_QUEUE_WAIT_SECONDS = 0.25

# Feature-flag reads are control-plane calls and must not consume the shared
# sync pipeline pool.  The semaphore bounds both active calls and submitted
# work; a slot is held until the underlying thread actually finishes, even if
# the async caller has already received a timeout/fail-off result.
_posthog_control_executor = ThreadPoolExecutor(
    max_workers=POSTHOG_CONTROL_MAX_WORKERS,
    thread_name_prefix='posthog-control',
)


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


@dataclass(frozen=True)
class _CacheEntry:
    evaluation: JITFlagEvaluation
    expires_at: float


def _effective_decision(
    evaluation: JITFlagEvaluation, *, cache_hit: bool, cache_ttl_seconds: int
) -> JITRolloutDecision:
    if evaluation.kill_switch == TriState.ENABLED:
        effective = TriState.DISABLED
        reason = JITDecisionReason.KILL_SWITCH_ENABLED
    elif evaluation.rollout == TriState.DISABLED:
        effective = TriState.DISABLED
        reason = JITDecisionReason.ROLLOUT_DISABLED
    elif evaluation.rollout == TriState.ENABLED and evaluation.kill_switch == TriState.DISABLED:
        effective = TriState.ENABLED
        reason = JITDecisionReason.ROLLOUT_ENABLED
    else:
        effective = TriState.UNKNOWN
        reason = evaluation.reason
    return JITRolloutDecision(
        rollout=evaluation.rollout,
        kill_switch=evaluation.kill_switch,
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

        evaluation = await self._provider(uid)
        finished_at = self._monotonic()
        # Cache only complete provider answers. Unknown/error snapshots retry on
        # the next request instead of extending an outage into an authorization.
        if evaluation.rollout != TriState.UNKNOWN and evaluation.kill_switch != TriState.UNKNOWN:
            self._cache[uid] = _CacheEntry(evaluation=evaluation, expires_at=finished_at + self._ttl_seconds)
            self._cache.move_to_end(uid)
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)
        decision = _effective_decision(
            evaluation,
            cache_hit=False,
            cache_ttl_seconds=(
                int(self._ttl_seconds)
                if evaluation.rollout != TriState.UNKNOWN and evaluation.kill_switch != TriState.UNKNOWN
                else 0
            ),
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
    """Read both server-owned PostHog flags in one bounded decide request."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_JIT_ROLLOUT_TIMEOUT_SECONDS,
        client_factory: Callable[[], Any | None] | None = None,
    ) -> None:
        if timeout_seconds <= 0 or timeout_seconds > MAX_JIT_ROLLOUT_CACHE_SECONDS:
            raise ValueError('timeout_seconds must be positive and bounded')
        self._timeout_seconds = timeout_seconds
        self._client_factory = client_factory or self._build_client
        self._client: Any | None = None
        self._client_lock = threading.Lock()
        self._control_slots = asyncio.BoundedSemaphore(POSTHOG_CONTROL_MAX_WORKERS + POSTHOG_CONTROL_MAX_QUEUE)
        self._inflight: dict[str, asyncio.Task[JITFlagEvaluation]] = {}

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
        in_flight = self._inflight.get(uid)
        if in_flight is None:
            in_flight = asyncio.create_task(self._resolve_uncached(uid), name='posthog-jit-decide')
            self._inflight[uid] = in_flight

            def forget(completed: asyncio.Task[JITFlagEvaluation]) -> None:
                if self._inflight.get(uid) is completed:
                    self._inflight.pop(uid, None)
                if not completed.cancelled():
                    completed.exception()

            in_flight.add_done_callback(forget)
        return await asyncio.shield(in_flight)

    async def _resolve_uncached(self, uid: str) -> JITFlagEvaluation:
        try:
            await asyncio.wait_for(
                self._control_slots.acquire(),
                timeout=POSTHOG_CONTROL_QUEUE_WAIT_SECONDS,
            )
        except asyncio.TimeoutError:
            return JITFlagEvaluation(
                TriState.UNKNOWN,
                TriState.UNKNOWN,
                JITDecisionReason.PROVIDER_TIMEOUT,
                JITErrorClass.TIMEOUT,
            )

        try:
            call = asyncio.create_task(
                run_blocking(_posthog_control_executor, self._fetch, uid),
                name='posthog-jit-fetch',
            )
        except BaseException:
            self._control_slots.release()
            raise

        def release_slot(completed: asyncio.Task[Any]) -> None:
            self._control_slots.release()
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

        rollout = _flag_state(variants, JIT_PROCESSING_FLAG_KEY)
        kill_switch = _flag_state(variants, JIT_KILL_SWITCH_FLAG_KEY)
        if rollout == TriState.UNKNOWN or kill_switch == TriState.UNKNOWN:
            reason = (
                JITDecisionReason.FLAG_ABSENT
                if (JIT_PROCESSING_FLAG_KEY not in variants or JIT_KILL_SWITCH_FLAG_KEY not in variants)
                else JITDecisionReason.MALFORMED_RESPONSE
            )
            error_class = JITErrorClass.ABSENT if reason == JITDecisionReason.FLAG_ABSENT else JITErrorClass.MALFORMED
            return JITFlagEvaluation(rollout, kill_switch, reason, error_class)
        return JITFlagEvaluation(rollout, kill_switch, JITDecisionReason.EVALUATED)


def _flag_state(flags: Mapping[str, Any], key: str) -> TriState:
    value = flags.get(key)
    if value is True:
        return TriState.ENABLED
    if value is False:
        return TriState.DISABLED
    return TriState.UNKNOWN


_authority = JITRolloutAuthority(PostHogJITFlagProvider())


async def resolve_jit_rollout(
    uid: str,
    *,
    stage: JITDecisionStage,
    force_refresh: bool = False,
) -> JITRolloutDecision:
    return await _authority.resolve(uid, stage=stage, force_refresh=force_refresh)


__all__ = [
    'JITDecisionStage',
    'JITDecisionReason',
    'JITErrorClass',
    'JITFlagEvaluation',
    'JITRolloutAuthority',
    'JITRolloutDecision',
    'PostHogJITFlagProvider',
    'TriState',
    'resolve_jit_rollout',
]
