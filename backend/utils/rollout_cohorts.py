# LIFECYCLE: permanent
"""Bounded cohort cache and application wiring, shared by all serving hosts."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from concurrent.futures import Future
import contextvars
from dataclasses import dataclass
import logging
from threading import RLock
import time
from typing import Any, Callable

from config import rollout_cohorts as policy, stt_cap_dispatch
from config.policy.cohorts import batch_members, recovery_members
from config.rollout_cohorts import (
    COLLECTION as COLLECTION,
    COHORT_ENVS,
    valid_uid,
    rollout_environment,
    in_rollout_cohort,
    rollout_cohort_members as rollout_cohort_members,
    load_rollout_cohorts as load_rollout_cohorts,
    warm_rollout_cohorts as warm_rollout_cohorts,
)
from database.rollout_cohorts import read_memberships, read_cohort_members
from utils import executors
from utils.observability.fallback import record_fallback
from utils.rollout.runtime_percent import configure_runtime_percent
from utils.stt_cap_cohort import runtime_cohort

TTL_SECONDS = 60
MAX_USERS = 4096
logger = logging.getLogger(__name__)


def _submit_read(fn, *args):
    return executors.get_rollout_executor().submit(contextvars.copy_context().run, fn, *args)


_background_submitter: Callable[..., Any] | None = _submit_read


@dataclass
class _Entry:
    future: Future
    expires: float = float('inf')


class _TTLReads:
    """Bounded positive/negative/error cache with one in-flight read per key."""

    def __init__(self, reader: Callable[[str], Any], capacity: int = MAX_USERS, *, discovery: bool = False):
        self.reader = reader
        self.capacity = capacity
        self.discovery = discovery
        self.entries: OrderedDict[str, _Entry] = OrderedDict()
        self.lock = RLock()

    def _refresh(self, key: str, entry: _Entry) -> None:
        try:
            value = self.reader(key)
        except Exception:
            # SDK exceptions carry document paths and therefore UIDs. Never log them.
            logger.warning('event=rollout_cohort_read outcome=denied')
            value = None
        if self.discovery and key.endswith(':dream-agent') and not value:
            _dream_cohort_degraded('unavailable' if value is None else 'empty')
        with self.lock:
            entry.expires = min(time.monotonic() + TTL_SECONDS, getattr(value, 'deadline', float('inf')))
            entry.future.set_result(value)

    def request(self, key: str, *, background: bool) -> Future:
        with self.lock:
            entry = self.entries.get(key)
            if entry is not None and (not entry.future.done() or entry.expires > time.monotonic()):
                self.entries.move_to_end(key)
                return entry.future
            if entry is not None:
                del self.entries[key]
            if len(self.entries) >= self.capacity:
                victim = next((k for k, value in self.entries.items() if value.future.done()), None)
                if victim is None:
                    denied: Future = Future()
                    denied.set_result(None)
                    return denied
                del self.entries[victim]
            entry = _Entry(Future())
            self.entries[key] = entry
        if background:
            try:
                if _background_submitter is None:
                    raise RuntimeError('cohort scheduler not configured')
                _background_submitter(self._refresh, key, entry)
            except Exception:
                with self.lock:
                    entry.expires = time.monotonic() + TTL_SECONDS
                    entry.future.set_result(None)
        else:
            self._refresh(key, entry)
        return entry.future

    def get(self, key: str) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            future = self.request(key, background=False)
            try:
                return future.result(timeout=1.25)
            except TimeoutError:
                return None
        future = self.request(key, background=True)
        return future.result() if future.done() else None


_cache = _TTLReads(read_memberships)


def _dream_cohort_degraded(outcome: str) -> None:
    logger.error('event=dream_cohort_health outcome=%s', outcome)
    record_fallback(
        component='agent_tools',
        from_mode='dream_cohort',
        to_mode='declared_eligibility',
        reason='unavailable' if outcome == 'unavailable' else 'policy',
        outcome='degraded',
        log=logger,
    )


def _in_rollout_cohort(
    uid: str, name: str, *, legacy_members: tuple[str, ...] | None = None, legacy_all: bool = False
) -> bool:
    """Warm checks cost zero reads; missing fields retain explicit legacy env members."""
    if not valid_uid(uid) or name not in COHORT_ENVS:
        return False
    members = _cache.get(uid)
    if members is None:
        if name == 'dream-agent':
            _dream_cohort_degraded('unavailable')
            raise policy.RolloutCohortUnavailable('dream cohort membership unavailable')
        return False
    try:
        members = members.get(rollout_environment(), {})
    except ValueError:
        return False
    if name in members:
        return members[name] is True
    return policy.legacy_membership(uid, name, legacy_members=legacy_members, legacy_all=legacy_all)


def _load_rollout_cohorts(uid: str) -> None:
    """Preload in a synchronous request dependency (already on a worker thread)."""
    if valid_uid(uid):
        runtime_cohort.tokens()
        _cache.get(uid)


async def _warm_rollout_cohorts(uid: str) -> None:
    """Await the first listen read without blocking the loop or extending SDK retries."""
    if not valid_uid(uid):
        return
    runtime_cohort.tokens()
    future = _cache.request(uid, background=True)
    if future.done():
        return
    try:
        await asyncio.wait_for(asyncio.shield(asyncio.wrap_future(future)), timeout=1.25)
    except asyncio.TimeoutError:
        pass  # The pending cache entry denies admission until its read completes.


_member_cache = _TTLReads(read_cohort_members, capacity=4 * len(COHORT_ENVS), discovery=True)


def _rollout_cohort_members(name: str) -> tuple[str, ...]:
    """Bounded background-job discovery; never query the collection per request."""
    if name not in COHORT_ENVS:
        return ()
    try:
        members = _member_cache.get(rollout_environment() + ':' + name)
    except ValueError:
        return ()
    if members is None:
        if name == 'dream-agent':
            raise policy.RolloutCohortUnavailable('dream cohort discovery unavailable')
        return ()
    legacy = {item.strip() for item in COHORT_ENVS[name]().split(',') if valid_uid(item.strip())}
    return tuple(sorted(set(members) | {uid for uid in legacy if in_rollout_cohort(uid, name)}))


def configure_rollout_runtime() -> None:
    stt_cap_dispatch.configure_cohort_resolver(runtime_cohort.tokens)
    policy.configure_resolvers(
        _in_rollout_cohort,
        _rollout_cohort_members,
        _load_rollout_cohorts,
        _warm_rollout_cohorts,
        env_readers={'batch-pipeline': batch_members, 'batch-pipeline-recovery': recovery_members},
    )
    # Runtime percents and legacy_sync (`rollout_cohorts/_ramp`, contract (f)) bind with the cohorts.
    configure_runtime_percent()
